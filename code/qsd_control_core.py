"""
Shared QSD sector-bounded control primitives.

Hard rules encoded here:
- sector saturation sat_α
- ΔE = log(1 + |r|/scale)
- DT-scaled phase/control rates: u ← u + DT · ú
- DT-scaled process noise (√DT Wiener)
- quiet-window lock detector (lock first, then track)
- richer sensing: lag + bias + dropouts
- unified scorecard for every demo
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def sat(x: float, alpha: float = 0.15) -> float:
    """Sector saturation."""
    return float(np.clip(x, -alpha, alpha))


def delta_e(residual: float, scale: float = 1.0) -> float:
    """ΔE = log(1 + |r|/scale)."""
    return float(np.log1p(np.abs(residual) / max(scale, 1e-15)))


def wrap_pi(phi: float) -> float:
    """Wrap angle to (−π, π]."""
    return float((phi + np.pi) % (2.0 * np.pi) - np.pi)


def wrap_delta(a: float, b: float) -> float:
    """Shortest signed angle a−b on the circle."""
    return wrap_pi(a - b)


def dt_step(u: float, u_dot: float, dt: float, lo: float | None = None, hi: float | None = None) -> float:
    """DT-scaled Euler step with optional clip."""
    out = u + dt * u_dot
    if lo is not None or hi is not None:
        out = float(np.clip(out, -np.inf if lo is None else lo, np.inf if hi is None else hi))
    return float(out)


def wiener_noise(rng: np.random.Generator, sigma: float, dt: float) -> float:
    """DT-scaled white noise: σ √dt · N(0,1)."""
    return float(sigma * np.sqrt(max(dt, 0.0)) * rng.standard_normal())


def wiener_noise_array(
    rng: np.random.Generator, sigma: float, dt: float, size: int
) -> np.ndarray:
    return sigma * np.sqrt(max(dt, 0.0)) * rng.standard_normal(size)


# ---------------------------------------------------------------------------
# Sensing
# ---------------------------------------------------------------------------

@dataclass
class SensorModel:
    """First-order lag + constant bias + random dropouts."""

    tau_s: float = 0.0
    bias: float = 0.0
    dropout_prob: float = 0.0
    noise_std: float = 0.0
    hold_on_dropout: bool = True

    _state: float = field(default=0.0, init=False, repr=False)
    _last_out: float = field(default=0.0, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    def reset(self, x0: float = 0.0) -> None:
        self._state = float(x0)
        self._last_out = float(x0) + self.bias
        self._initialized = True

    def measure(self, truth: float, dt: float, rng: np.random.Generator) -> float:
        if not self._initialized:
            self.reset(truth)

        # lag toward truth
        if self.tau_s > 1e-12:
            self._state = self._state + (dt / self.tau_s) * (truth - self._state)
        else:
            self._state = float(truth)

        y = self._state + self.bias
        if self.noise_std > 0.0:
            y += wiener_noise(rng, self.noise_std, dt)

        if self.dropout_prob > 0.0 and rng.random() < self.dropout_prob:
            # dropout: hold last good output or NaN
            return float(self._last_out) if self.hold_on_dropout else float("nan")

        self._last_out = float(y)
        return self._last_out


# ---------------------------------------------------------------------------
# Quiet-window lock (lock first, then track)
# ---------------------------------------------------------------------------

@dataclass
class QuietWindowLock:
    """
    Acquisition latch: require a quiet residual (and optional |v|) window
    before enabling outer tracking. Optional loss-of-lock on sustained ΔE.
    """

    de_th: float = 0.02
    v_max: float = np.inf
    quiet_len: int = 500
    loss_mult: float = 5.0
    grace_s: float = 0.2
    dt: float = 0.001

    locked: bool = field(default=False, init=False)
    t_lock: float = field(default=float("nan"), init=False)
    _de_buf: list[float] = field(default_factory=list, init=False)
    _v_buf: list[float] = field(default_factory=list, init=False)
    drop_count: int = field(default=0, init=False)

    def reset(self) -> None:
        self.locked = False
        self.t_lock = float("nan")
        self._de_buf.clear()
        self._v_buf.clear()
        self.drop_count = 0

    def update(self, t: float, de: float, v_abs: float = 0.0) -> bool:
        self._de_buf.append(float(de))
        self._v_buf.append(float(v_abs))
        if len(self._de_buf) > self.quiet_len:
            self._de_buf.pop(0)
            self._v_buf.pop(0)

        if not self.locked:
            if len(self._de_buf) == self.quiet_len:
                if (
                    float(np.mean(self._de_buf)) < self.de_th
                    and float(np.max(self._de_buf)) < self.de_th * 1.3
                    and float(np.max(self._v_buf)) < self.v_max
                ):
                    self.locked = True
                    self.t_lock = t
                    self._de_buf.clear()
                    self._v_buf.clear()
        else:
            if (
                (t - self.t_lock) > self.grace_s
                and len(self._de_buf) == self.quiet_len
                and float(np.mean(self._de_buf)) > self.de_th * self.loss_mult
            ):
                self.locked = False
                self.drop_count += 1
                self.t_lock = float("nan")
                self._de_buf.clear()
                self._v_buf.clear()

        return self.locked


# ---------------------------------------------------------------------------
# Three-stage tri-ΔE lock (acquire → hold → track)
# ---------------------------------------------------------------------------

@dataclass
class TriDeltaLock:
    """
    Three-stage lock:

      stage 0  acquire  — residual loop only
      stage 1  hold     — residual quiet (ΔE₁ + |v|); freeze φ, hold F_ref
      stage 2  armed    — quieter residual (ΔE₂); outer may slew in
      stage 3  track    — physical gap gate |y−y_ref|<ε and |v|<v* (plus residual)

    Stage 2→3 uses physical gap/velocity, not a third log-ΔE scale.
    Loss-of-lock uses a looser residual ΔE gate with hysteresis.
    """

    de1: float = 0.020  # stage 0 → 1 (residual)
    de2: float = 0.015  # stage 1 → 2 (confirm hold)
    gap_err_max: float = 1.5e-4  # |y − y_ref| for stage 2 → 3
    gap_v_max: float = 0.005  # |v| while checking gap gate
    v_max: float = 0.005  # |v| for residual quiet windows
    quiet_len: int = 400
    hold_len: int = 300
    arm_len: int = 300
    loss_de: float = 0.12
    loss_len: int = 500
    grace_s: float = 0.15
    dt: float = 0.001
    require_gap_for_track: bool = True

    stage: int = field(default=0, init=False)
    t_stage: float = field(default=0.0, init=False)
    t_lock: float = field(default=float("nan"), init=False)
    t_track: float = field(default=float("nan"), init=False)
    drop_count: int = field(default=0, init=False)
    _de_buf: list[float] = field(default_factory=list, init=False)
    _v_buf: list[float] = field(default_factory=list, init=False)
    _gap_buf: list[float] = field(default_factory=list, init=False)

    @property
    def locked(self) -> bool:
        return self.stage >= 1

    @property
    def holding(self) -> bool:
        return self.stage == 1

    @property
    def armed(self) -> bool:
        return self.stage == 2

    @property
    def tracking(self) -> bool:
        return self.stage >= 3

    def reset(self) -> None:
        self.stage = 0
        self.t_stage = 0.0
        self.t_lock = float("nan")
        self.t_track = float("nan")
        self.drop_count = 0
        self._de_buf.clear()
        self._v_buf.clear()
        self._gap_buf.clear()

    def _push(self, de: float, v_abs: float, gap_err_abs: float) -> None:
        self._de_buf.append(float(de))
        self._v_buf.append(float(v_abs))
        self._gap_buf.append(float(gap_err_abs))
        maxlen = max(self.quiet_len, self.hold_len, self.arm_len, self.loss_len)
        if len(self._de_buf) > maxlen:
            self._de_buf.pop(0)
            self._v_buf.pop(0)
            self._gap_buf.pop(0)

    def _clear_bufs(self) -> None:
        self._de_buf.clear()
        self._v_buf.clear()
        self._gap_buf.clear()

    def _residual_ok(self, th: float, n: int) -> bool:
        if len(self._de_buf) < n:
            return False
        de_w = self._de_buf[-n:]
        if float(np.mean(de_w)) >= th or float(np.max(de_w)) >= th * 1.3:
            return False
        if float(np.max(self._v_buf[-n:])) >= self.v_max:
            return False
        return True

    def _gap_ok(self, n: int) -> bool:
        if len(self._gap_buf) < n:
            return False
        g = self._gap_buf[-n:]
        v = self._v_buf[-n:]
        return (
            float(np.mean(g)) < self.gap_err_max
            and float(np.max(g)) < self.gap_err_max * 1.5
            and float(np.max(v)) < self.gap_v_max
        )

    def _loss(self, t: float) -> bool:
        return (
            (t - self.t_stage) > self.grace_s
            and len(self._de_buf) >= self.loss_len
            and float(np.mean(self._de_buf[-self.loss_len:])) > self.loss_de
        )

    def update(
        self,
        t: float,
        de: float,
        v_abs: float = 0.0,
        gap_err_abs: float = 0.0,
        gap_de: float | None = None,  # deprecated alias; ignored if gap_err_abs set
    ) -> int:
        # Backward-compatible: old callers passed gap_de as 4th positional via gap_de=
        if gap_de is not None and gap_err_abs == 0.0:
            # Treat legacy gap_de as a soft proxy only when physical err not supplied
            gap_err_abs = float(gap_de) * 0.001
        self._push(de, v_abs, gap_err_abs)

        if self.stage == 0:
            if self._residual_ok(self.de1, self.quiet_len):
                self.stage = 1
                self.t_stage = t
                self.t_lock = t
                self._clear_bufs()
        elif self.stage == 1:
            if self._residual_ok(self.de2, self.hold_len):
                self.stage = 2
                self.t_stage = t
                self._clear_bufs()
            elif self._loss(t):
                self._drop(t)
        elif self.stage == 2:
            residual_ok = self._residual_ok(self.de2, self.arm_len)
            gap_ok = self._gap_ok(self.arm_len) if self.require_gap_for_track else True
            if residual_ok and gap_ok:
                self.stage = 3
                self.t_stage = t
                self.t_track = t
                self._clear_bufs()
            elif self._loss(t):
                self._drop(t)
        else:
            if self._loss(t):
                self._drop(t)

        return self.stage

    def _drop(self, t: float) -> None:
        self.stage = 0
        self.drop_count += 1
        self.t_stage = t
        self.t_lock = float("nan")
        self.t_track = float("nan")
        self._clear_bufs()


# ---------------------------------------------------------------------------
# Stage gain schedule
# ---------------------------------------------------------------------------

STAGE_NAMES = ("acquire", "hold", "armed", "track")


def default_gain_schedule() -> list[dict[str, Any]]:
    """Explicit stage-dependent gains (design table, not magic numbers)."""
    return [
        {
            "stage": 0,
            "name": "acquire",
            "K_phi": 70.0,
            "lam": 0.0,
            "Kp": 0.0,
            "Kd": 0.0,
            "Ki": 0.0,
            "F_slew_over_Mg": 8.0,
            "F_ref": "Mg",
            "gate": "—",
        },
        {
            "stage": 1,
            "name": "hold",
            "K_phi": 35.0,
            "lam": 0.4,
            "Kp": 0.0,
            "Kd": 0.0,
            "Ki": 0.0,
            "F_slew_over_Mg": 8.0,
            "F_ref": "Mg",
            "gate": "ΔE1 + |v|",
        },
        {
            "stage": 2,
            "name": "armed",
            "K_phi": 35.0,
            "lam": 0.4,
            "Kp": 4.0,
            "Kd": 0.12,
            "Ki": 0.15,
            "F_slew_over_Mg": 2.0,
            "F_ref": "slew PID",
            "gate": "ΔE2",
        },
        {
            "stage": 3,
            "name": "track",
            "K_phi": 35.0,
            "lam": 0.4,
            "Kp": 4.0,
            "Kd": 0.12,
            "Ki": 0.15,
            "F_slew_over_Mg": 2.0,
            "F_ref": "slew PID",
            "gate": "|y−yref|<ε & |v|",
        },
    ]


def save_gain_schedule(path: Path, rows: Sequence[dict[str, Any]] | None = None) -> Path:
    rows = list(rows) if rows is not None else default_gain_schedule()
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0].keys())
    lines = [",".join(keys)]
    for r in rows:
        lines.append(",".join(str(r[k]) for k in keys))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Unified scorecard
# ---------------------------------------------------------------------------

@dataclass
class Scorecard:
    """One honest scorecard for every demo. Headline metric: rms_ratio."""

    demo: str
    lock_in: bool
    time_to_lock_s: float
    corridor_fraction: float
    hold_or_track_rms: float
    open_loop_rms: float
    final_delta_e: float
    diverged: bool
    notes: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def rms_ratio(self) -> float:
        """closed / open track RMS (lower is better; <1 means closed wins)."""
        if self.open_loop_rms <= 0 or np.isnan(self.open_loop_rms):
            return float("nan")
        return float(self.hold_or_track_rms / self.open_loop_rms)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rms_ratio"] = self.rms_ratio
        return d

    def row(self) -> str:
        lock = f"{self.time_to_lock_s:.3f}s" if self.lock_in and not np.isnan(self.time_to_lock_s) else "no"
        ratio = f"{self.rms_ratio:.3f}" if not np.isnan(self.rms_ratio) else "nan"
        return (
            f"{self.demo:18}  lock={lock:8}  corr={self.corridor_fraction:5.1%}  "
            f"ratio={ratio:6}  rms={self.hold_or_track_rms:.4g}  open={self.open_loop_rms:.4g}  "
            f"ΔE∞={self.final_delta_e:.4f}  diverged={self.diverged}"
        )


def print_scorecard_table(cards: Sequence[Scorecard]) -> None:
    print("=" * 96)
    print("QSD SCORECARD  (headline: ratio = closed_rms / open_rms)")
    print("=" * 96)
    for c in cards:
        print(c.row())
        if c.notes:
            print(f"  note: {c.notes}")
    print("=" * 96)


def save_scorecards(cards: Sequence[Scorecard], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"scorecards": [c.to_dict() for c in cards]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def rms(x: Iterable[float]) -> float:
    arr = np.asarray(list(x), dtype=float)
    if arr.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(arr * arr)))


def diverged_from_series(
    values: Sequence[float],
    bound: float,
    frac: float = 0.05,
) -> bool:
    """True if more than `frac` of samples exceed `bound` in magnitude."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return True
    return float(np.mean(np.abs(arr) > bound)) > frac
