"""PAT plant, disturbance, and controllers (open-loop, PD/PID, QSD-ISS).

Pointing error is a 2-axis residual in radians. Boresight is 0, 0 — θ* is
*not* a physical beam offset. The QSD controller maps radial pointing error
into the third-harmonic potential so the well sits at boresight, then applies
Theorem 6 ISS contraction plus periodic re-lock ("sunscreen") pulses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from aurora_qsd.core.constants import DEFAULT_K_GAIN, DEFAULT_RHO, THETA_STAR
from aurora_qsd.core.iss import contraction_rate, iss_bound
from aurora_qsd.core.phase_potential import basin_boundary, phase_force
from aurora_qsd.optical.constants import (
    DEFAULT_ACQ_FOV_URAD,
    DEFAULT_FSM_WN_HZ,
    DEFAULT_FSM_ZETA,
    DEFAULT_PAT_DT,
)


class ControllerName(str, Enum):
    OPEN = "open"
    PID = "pid"
    QSD = "qsd"
    QSD_WRONG = "qsd_wrong"  # negative control: lock to a potential hill


@dataclass
class PATPlant:
    """Second-order fast-steering-mirror plant, two axes, identical."""

    dt: float = DEFAULT_PAT_DT
    wn_hz: float = DEFAULT_FSM_WN_HZ
    zeta: float = DEFAULT_FSM_ZETA

    def __post_init__(self) -> None:
        self.wn = 2.0 * np.pi * self.wn_hz
        # state: [az, az_dot, el, el_dot]
        self.x = np.zeros(4)

    def reset(self, x0: np.ndarray | None = None) -> None:
        self.x = np.zeros(4) if x0 is None else np.asarray(x0, dtype=float).copy()

    def _deriv(self, x: np.ndarray, u_az: float, u_el: float) -> np.ndarray:
        az, azd, el, eld = x
        azdd = self.wn**2 * (u_az - az) - 2.0 * self.zeta * self.wn * azd
        eldd = self.wn**2 * (u_el - el) - 2.0 * self.zeta * self.wn * eld
        return np.array([azd, azdd, eld, eldd], dtype=float)

    def step(self, u_az: float, u_el: float) -> np.ndarray:
        """Advance one sample with RK4 substeps. u is commanded angle (rad)."""
        # Keep h·ωn ≲ 0.2 so the 200 Hz plant is stable at 500 Hz outer rate
        n_sub = max(4, int(np.ceil(self.wn * self.dt / 0.2)))
        h = self.dt / n_sub
        x = self.x
        for _ in range(n_sub):
            k1 = self._deriv(x, u_az, u_el)
            k2 = self._deriv(x + 0.5 * h * k1, u_az, u_el)
            k3 = self._deriv(x + 0.5 * h * k2, u_az, u_el)
            k4 = self._deriv(x + h * k3, u_az, u_el)
            x = x + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        x = np.clip(x, [-2e-3, -0.5, -2e-3, -0.5], [2e-3, 0.5, 2e-3, 0.5])
        self.x = x
        return self.x[[0, 2]]


def colored_jitter(
    n: int,
    dt: float,
    rms_rad: float,
    corr_s: float,
    rng: np.random.Generator,
    n_axes: int = 2,
) -> np.ndarray:
    """Unit-variance AR(1) jitter scaled to ``rms_rad``, shape (n, n_axes)."""
    alpha = np.exp(-dt / max(corr_s, dt))
    innov = np.sqrt(max(1.0 - alpha**2, 1e-12))
    out = np.empty((n, n_axes))
    out[0] = rng.normal(0.0, 1.0, size=n_axes)
    for i in range(1, n):
        out[i] = alpha * out[i - 1] + innov * rng.normal(0.0, 1.0, size=n_axes)
    # rescale to requested RMS
    rms = np.sqrt(np.mean(out**2, axis=0, keepdims=True))
    rms = np.where(rms > 0, rms, 1.0)
    return out / rms * rms_rad


@dataclass
class PIDController:
    """Classical fine-stage PI. Output is an FSM angle command (disturbance estimate).

    Velocity-form PI so a constant disturbance is held by the integrator and
    the comparison with QSD-ISS is on the same type-1 architecture.
    """

    dt: float
    kp: float = 0.25
    ki: float = 60.0
    u_max: float = 5e-4  # 500 μrad command clamp

    cmd: np.ndarray = field(default_factory=lambda: np.zeros(2))
    prev_e: np.ndarray = field(default_factory=lambda: np.zeros(2))

    def reset(self) -> None:
        self.cmd = np.zeros(2)
        self.prev_e = np.zeros(2)

    def update(self, e_meas: np.ndarray) -> np.ndarray:
        """Positive error (beam +az of boresight) increases +az command."""
        delta = self.kp * (e_meas - self.prev_e) + self.ki * e_meas * self.dt
        self.prev_e = np.asarray(e_meas, dtype=float).copy()
        self.cmd = np.clip(self.cmd + delta, -self.u_max, self.u_max)
        return self.cmd.copy()


@dataclass
class QSDISSController:
    """
    ISS sector-bounded pointing controller with QSD basin geometry.

    Coordinate map: radial error r is sent into the potential as
        Θ(r) = θ* + (r / r_basin) · 3θ*
    so r = 0 sits at the well and r = r_basin is the escape edge.

    Architecture matches the PI controller (type-1 command integrator) with
    the ISS step size k = 1 − √ρ, a small F(Θ) gain trim, and periodic
    re-lock pulses. Coarse acquisition outside the 200 μrad basin.
    """

    dt: float
    rho: float = DEFAULT_RHO
    k_gain: float = DEFAULT_K_GAIN
    k_nl: float = 0.04
    relock_interval: int = 7
    relock_extra: float = 0.04
    acq_fov_rad: float = DEFAULT_ACQ_FOV_URAD * 1e-6
    k_acq: float = 0.20
    u_max: float = 5e-4
    wrong_well: bool = False  # negative control: regulate to an off-boresight well
    wrong_offset_rad: float = 40e-6
    sensor_noise_rad: float = 0.4e-6

    step_index: int = 0
    last_in_basin: bool = True
    cmd: np.ndarray = field(default_factory=lambda: np.zeros(2))

    def reset(self) -> None:
        self.step_index = 0
        self.last_in_basin = True
        self.cmd = np.zeros(2)

    @property
    def gamma(self) -> float:
        """Continuous-time contraction rate (1/s) matching ρ per sample."""
        return contraction_rate(self.rho) / self.dt

    @property
    def r_basin(self) -> float:
        return self.acq_fov_rad

    def _theta_of_radius(self, r: float) -> float:
        lock = THETA_STAR + (np.pi / 2 if self.wrong_well else 0.0)
        return lock + (r / max(self.r_basin, 1e-12)) * basin_boundary()

    def update(self, e_meas: np.ndarray) -> np.ndarray:
        self.step_index += 1
        target = np.array([self.wrong_offset_rad, 0.0]) if self.wrong_well else 0.0
        e_reg = e_meas - target
        r_reg = float(np.linalg.norm(e_reg))
        in_basin = r_reg <= self.r_basin
        self.last_in_basin = in_basin

        if not in_basin:
            k = self.k_acq
        else:
            k = (1.0 - np.sqrt(self.rho)) * (self.k_gain / 0.45)
            if r_reg > 0:
                theta = self._theta_of_radius(r_reg)
                # F(θ*+δ) < 0 for δ>0; a positive extra gain is −F (small)
                force = float(phase_force(theta))
                k = k + self.k_nl * max(0.0, -force)
            if self.relock_interval > 0 and (self.step_index % self.relock_interval == 0):
                k = k + self.relock_extra

        self.cmd = np.clip(self.cmd + k * e_reg, -self.u_max, self.u_max)
        return self.cmd.copy()

    def iss_envelope(self, e0: float, t_steps: int, d_bound: float) -> np.ndarray:
        return np.array([iss_bound(e0, t, self.rho, d_bound) for t in range(t_steps)])


def pat_aurora_condition(
    rho: float,
    dt: float,
    jitter_corr_s: float,
) -> dict:
    """
    Optical PAT restatement of the Aurora condition: Γ_lock > Γ_jitter.

    Γ_lock = (−½ ln ρ) / dt   (ISS contraction per second)
    Γ_jitter = 1 / τ_corr     (disturbance bandwidth)
    """
    gamma_lock = contraction_rate(rho) / dt
    gamma_jitter = 1.0 / max(jitter_corr_s, dt)
    satisfied = gamma_lock > gamma_jitter
    return {
        "gamma_lock": float(gamma_lock),
        "gamma_jitter": float(gamma_jitter),
        "satisfied": bool(satisfied),
        "recommendation": (
            "PAT Aurora SATISFIED: contraction outruns jitter."
            if satisfied
            else "PAT Aurora NOT satisfied: raise FSM rate, lower ρ, or calm the platform."
        ),
    }
