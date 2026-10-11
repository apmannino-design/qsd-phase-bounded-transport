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
# Unified scorecard
# ---------------------------------------------------------------------------

@dataclass
class Scorecard:
    """One honest scorecard for every demo."""

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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def row(self) -> str:
        lock = f"{self.time_to_lock_s:.3f}s" if self.lock_in and not np.isnan(self.time_to_lock_s) else "no"
        return (
            f"{self.demo:18}  lock={lock:8}  corr={self.corridor_fraction:5.1%}  "
            f"rms={self.hold_or_track_rms:.4g}  open_rms={self.open_loop_rms:.4g}  "
            f"ΔE∞={self.final_delta_e:.4f}  diverged={self.diverged}"
        )


def print_scorecard_table(cards: Sequence[Scorecard]) -> None:
    print("=" * 88)
    print("QSD SCORECARD")
    print("=" * 88)
    for c in cards:
        print(c.row())
        if c.notes:
            print(f"  note: {c.notes}")
    print("=" * 88)


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
