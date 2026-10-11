"""
Shared QSD sector-bounded control primitives.

Hard rules encoded here:
- sector saturation sat_α
- ΔE = log(1 + |r|/scale)
- DT-scaled phase/control rates: u ← u + DT · ú
- DT-scaled process noise (√DT Wiener) — not measurement noise
- quiet-window lock detector (lock first, then track)
- richer sensing: lag + bias + dropouts
- unified scorecard for every demo
"""

from __future__ import annotations

import csv
import json
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Deque, Iterable, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def sat(x: float, alpha: float = 0.15) -> float:
    """Sector saturation."""
    return float(np.clip(x, -alpha, alpha))


def delta_e(residual: float, scale: float = 1.0) -> float:
    """ΔE = log(1 + |r|/scale). NaN/inf residual → NaN."""
    if not np.isfinite(residual):
        return float("nan")
    return float(np.log1p(np.abs(residual) / max(scale, 1e-15)))


def wrap_pi(phi: float) -> float:
    """Wrap angle to (−π, π]."""
    w = float((phi + np.pi) % (2.0 * np.pi) - np.pi)
    # (x+π)%(2π)−π yields [−π, π); map −π → +π for (−π, π]
    return float(np.pi) if w == -np.pi else w


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
    """DT-scaled white process noise: σ √dt · N(0,1)."""
    return float(sigma * np.sqrt(max(dt, 0.0)) * rng.standard_normal())


def wiener_noise_array(
    rng: np.random.Generator, sigma: float, dt: float, size: int
) -> np.ndarray:
    return sigma * np.sqrt(max(dt, 0.0)) * rng.standard_normal(size)


def _window_array(buf: Deque[float], n: int) -> np.ndarray:
    """Last n samples of a deque as a float array (no copy of unused head)."""
    if n <= 0 or len(buf) < n:
        return np.empty(0, dtype=float)
    # deque has no slicing; fromiter over reversed then flip is awkward — list once
    return np.fromiter(list(buf)[-n:], dtype=float, count=n)


def _nanmean(a: np.ndarray) -> float:
    if a.size == 0 or not np.any(np.isfinite(a)):
        return float("nan")
    return float(np.nanmean(a))


def _nanmax(a: np.ndarray) -> float:
    if a.size == 0 or not np.any(np.isfinite(a)):
        return float("nan")
    return float(np.nanmax(a))


# ---------------------------------------------------------------------------
# Sensing
# ---------------------------------------------------------------------------

@dataclass
class SensorModel:
    """
    First-order lag + constant bias + random dropouts.

    Measurement noise is per-sample σ·N(0,1) (NOT √dt Wiener — that is for process noise).
    Lag uses the exact discrete update: a = −expm1(−dt/τ).
    """

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

        # Exact discrete first-order lag (stable for any dt > 0)
        if self.tau_s > 1e-12:
            a = float(-np.expm1(-dt / self.tau_s))
            self._state = self._state + a * (truth - self._state)
        else:
            self._state = float(truth)

        y = self._state + self.bias
        if self.noise_std > 0.0:
            y += self.noise_std * float(rng.standard_normal())

        if self.dropout_prob > 0.0 and rng.random() < self.dropout_prob:
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
    NaN samples are ignored in window stats.
    """

    de_th: float = 0.02
    v_max: float = np.inf
    quiet_len: int = 500
    loss_mult: float = 5.0
    grace_s: float = 0.2

    locked: bool = field(default=False, init=False)
    t_lock: float = field(default=float("nan"), init=False)
    drop_count: int = field(default=0, init=False)
    _de_buf: Deque[float] = field(default_factory=deque, init=False, repr=False)
    _v_buf: Deque[float] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        self._de_buf = deque(maxlen=self.quiet_len)
        self._v_buf = deque(maxlen=self.quiet_len)

    def reset(self) -> None:
        self.locked = False
        self.t_lock = float("nan")
        self.drop_count = 0
        self._de_buf.clear()
        self._v_buf.clear()

    def update(self, t: float, de: float, v_abs: float = 0.0) -> bool:
        self._de_buf.append(float(de))
        self._v_buf.append(float(v_abs))

        de_a = _window_array(self._de_buf, len(self._de_buf))
        v_a = _window_array(self._v_buf, len(self._v_buf))

        if not self.locked:
            if len(self._de_buf) == self.quiet_len:
                mean_de, max_de, max_v = _nanmean(de_a), _nanmax(de_a), _nanmax(v_a)
                if (
                    np.isfinite(mean_de)
                    and mean_de < self.de_th
                    and max_de < self.de_th * 1.3
                    and max_v < self.v_max
                ):
                    self.locked = True
                    self.t_lock = t
        else:
            if (
                (t - self.t_lock) > self.grace_s
                and len(self._de_buf) == self.quiet_len
            ):
                mean_de = _nanmean(de_a)
                if np.isfinite(mean_de) and mean_de > self.de_th * self.loss_mult:
                    self.locked = False
                    self.drop_count += 1
                    self.t_lock = float("nan")

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

    Buffers are continuous (not cleared on stage advance) so loss-of-lock can
    fire after grace_s. Stage 3 also drops on sustained physical gap error.
    NaN samples are ignored in window stats.
    """

    de1: float = 0.020
    de2: float = 0.015
    gap_err_max: float = 1.5e-4
    gap_v_max: float = 0.005
    v_max: float = 0.005
    quiet_len: int = 400
    hold_len: int = 300
    arm_len: int = 300
    loss_de: float = 0.12
    loss_len: int = 500
    loss_gap_mult: float = 3.0  # mean |gap| > mult·ε ⇒ track loss
    grace_s: float = 0.15
    require_gap_for_track: bool = True

    stage: int = field(default=0, init=False)
    t_stage: float = field(default=0.0, init=False)
    t_lock: float = field(default=float("nan"), init=False)
    t_track: float = field(default=float("nan"), init=False)
    drop_count: int = field(default=0, init=False)
    _de_buf: Deque[float] = field(default_factory=deque, init=False, repr=False)
    _v_buf: Deque[float] = field(default_factory=deque, init=False, repr=False)
    _gap_buf: Deque[float] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        maxlen = max(self.quiet_len, self.hold_len, self.arm_len, self.loss_len)
        self._de_buf = deque(maxlen=maxlen)
        self._v_buf = deque(maxlen=maxlen)
        self._gap_buf = deque(maxlen=maxlen)

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

    def _residual_ok(self, th: float, n: int) -> bool:
        if len(self._de_buf) < n:
            return False
        de_w = _window_array(self._de_buf, n)
        v_w = _window_array(self._v_buf, n)
        mean_de, max_de, max_v = _nanmean(de_w), _nanmax(de_w), _nanmax(v_w)
        if not (np.isfinite(mean_de) and np.isfinite(max_de) and np.isfinite(max_v)):
            return False
        return mean_de < th and max_de < th * 1.3 and max_v < self.v_max

    def _gap_ok(self, n: int) -> bool:
        if len(self._gap_buf) < n:
            return False
        g = _window_array(self._gap_buf, n)
        v = _window_array(self._v_buf, n)
        mean_g, max_g, max_v = _nanmean(g), _nanmax(g), _nanmax(v)
        if not (np.isfinite(mean_g) and np.isfinite(max_g) and np.isfinite(max_v)):
            return False
        return (
            mean_g < self.gap_err_max
            and max_g < self.gap_err_max * 1.5
            and max_v < self.gap_v_max
        )

    def _residual_loss(self, t: float) -> bool:
        if (t - self.t_stage) <= self.grace_s or len(self._de_buf) < self.loss_len:
            return False
        mean_de = _nanmean(_window_array(self._de_buf, self.loss_len))
        return bool(np.isfinite(mean_de) and mean_de > self.loss_de)

    def _gap_loss(self, t: float) -> bool:
        """Sustained physical gap error while tracking."""
        if (t - self.t_stage) <= self.grace_s or len(self._gap_buf) < self.loss_len:
            return False
        mean_g = _nanmean(_window_array(self._gap_buf, self.loss_len))
        return bool(
            np.isfinite(mean_g) and mean_g > self.gap_err_max * self.loss_gap_mult
        )

    def update(
        self,
        t: float,
        de: float,
        v_abs: float = 0.0,
        gap_err_abs: float | None = None,
    ) -> int:
        """
        Advance/drop lock stage.

        gap_err_abs: physical |y − y_ref| (or None if not measured this step).
        When None, gap checks are skipped for that sample (stored as NaN).
        """
        gap = float("nan") if gap_err_abs is None else float(gap_err_abs)
        self._push(de, v_abs, gap)

        if self.stage == 0:
            if self._residual_ok(self.de1, self.quiet_len):
                self.stage = 1
                self.t_stage = t
                self.t_lock = t
        elif self.stage == 1:
            if self._residual_ok(self.de2, self.hold_len):
                self.stage = 2
                self.t_stage = t
            elif self._residual_loss(t):
                self._drop(t)
        elif self.stage == 2:
            residual_ok = self._residual_ok(self.de2, self.arm_len)
            gap_ok = self._gap_ok(self.arm_len) if self.require_gap_for_track else True
            if residual_ok and gap_ok:
                self.stage = 3
                self.t_stage = t
                self.t_track = t
            elif self._residual_loss(t):
                self._drop(t)
        else:  # stage 3 track — residual OR physical gap can drop lock
            if self._residual_loss(t) or self._gap_loss(t):
                self._drop(t)

        return self.stage

    def _drop(self, t: float) -> None:
        self.stage = 0
        self.drop_count += 1
        self.t_stage = t
        self.t_lock = float("nan")
        self.t_track = float("nan")
        # Clear so a fresh acquisition window is required
        self._de_buf.clear()
        self._v_buf.clear()
        self._gap_buf.clear()


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
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in keys})
    return path


# ---------------------------------------------------------------------------
# Unified scorecard
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    """JSON serializer for numpy scalars/arrays and NaN → None."""
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return None if not math.isfinite(x) else x
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [_json_default(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): _json_default(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_default(v) for v in obj]
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _sanitize_for_json(obj.tolist())
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return None if not math.isfinite(x) else x
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    return obj


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
        if self.open_loop_rms <= 0 or not np.isfinite(self.open_loop_rms):
            return float("nan")
        if not np.isfinite(self.hold_or_track_rms):
            return float("nan")
        return float(self.hold_or_track_rms / self.open_loop_rms)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rms_ratio"] = self.rms_ratio
        return _sanitize_for_json(d)

    def row(self) -> str:
        if self.lock_in:
            if np.isfinite(self.time_to_lock_s):
                lock = f"{self.time_to_lock_s:.3f}s"
            else:
                lock = "yes"  # locked but time unknown — not "no"
        else:
            lock = "no"
        ratio = f"{self.rms_ratio:.3f}" if np.isfinite(self.rms_ratio) else "nan"
        de = f"{self.final_delta_e:.4f}" if np.isfinite(self.final_delta_e) else "nan"
        return (
            f"{self.demo:18}  lock={lock:8}  corr={self.corridor_fraction:5.1%}  "
            f"ratio={ratio:6}  rms={self.hold_or_track_rms:.4g}  open={self.open_loop_rms:.4g}  "
            f"ΔE∞={de}  diverged={self.diverged}"
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
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return path


def rms(x: Iterable[float]) -> float:
    arr = np.asarray(list(x), dtype=float)
    if arr.size == 0:
        return float("nan")
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(finite * finite)))


def diverged_from_series(
    values: Sequence[float],
    bound: float,
    frac: float = 0.05,
) -> bool:
    """True if more than `frac` of samples are non-finite or exceed `bound`."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return True
    bad = ~np.isfinite(arr) | (np.abs(arr) > bound)
    return float(np.mean(bad)) > frac
