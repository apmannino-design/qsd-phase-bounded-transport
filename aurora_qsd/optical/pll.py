"""Optical carrier PLL at Costas-loop rate (not the 500 Hz PAT loop).

Residual phase φ degrades coherent BPSK as SNR_eff = SNR · cos²(φ).
QSD-ISS and PI run on wrapped phase error with the same type-1 command
integrator used for pointing. Doppler feedforward subtracts the known
range-rate beat; the residual is a small frequency offset.

This is a loop-referred model (dt = 50 μs, 20 kHz), not a 1550 nm field
propagator and not a claim that θ* is an optical phase setpoint.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.constants import DEFAULT_K_GAIN, DEFAULT_RHO, THETA_STAR
from aurora_qsd.core.iss import one_step_iss_coverage
from aurora_qsd.core.phase_potential import basin_boundary, phase_force
from aurora_qsd.optical.constants import (
    DEFAULT_DOPPLER_FF_RESIDUAL_HZ,
    DEFAULT_DOPPLER_RESIDUAL_HZ,
    DEFAULT_LINEWIDTH_HZ,
    DEFAULT_PLL_DT,
)
from aurora_qsd.optical.modem import coherent_ber
from aurora_qsd.optical.pat import ControllerName


def wrap_pi(x: np.ndarray | float) -> np.ndarray | float:
    return (np.asarray(x) + np.pi) % (2.0 * np.pi) - np.pi


@dataclass
class PIPhaseLock:
    dt: float
    kp: float = 0.35
    ki: float = 80.0
    u_max: float = 3.0  # rad of NCO phase per sample stack

    cmd: float = 0.0
    prev_e: float = 0.0

    def reset(self) -> None:
        self.cmd = 0.0
        self.prev_e = 0.0

    def update(self, e: float) -> float:
        e = float(wrap_pi(e))
        delta = self.kp * (e - self.prev_e) + self.ki * e * self.dt
        self.prev_e = e
        self.cmd = float(np.clip(self.cmd + delta, -self.u_max, self.u_max))
        return self.cmd


@dataclass
class QSDPhaseLock:
    dt: float
    rho: float = DEFAULT_RHO
    k_gain: float = DEFAULT_K_GAIN
    k_nl: float = 0.04
    relock_interval: int = 7
    relock_extra: float = 0.04
    u_max: float = 3.0
    lock_offset: float = 0.0  # π/2 for the negative-control quadrature well
    basin_rad: float = float(np.pi / 2)

    cmd: float = 0.0
    step_index: int = 0

    def reset(self) -> None:
        self.cmd = 0.0
        self.step_index = 0

    def update(self, e: float) -> float:
        self.step_index += 1
        e_reg = float(wrap_pi(e - self.lock_offset))
        r = abs(e_reg)
        if r > self.basin_rad:
            k = 0.25
        else:
            k = (1.0 - np.sqrt(self.rho)) * (self.k_gain / 0.45)
            frac = r / max(self.basin_rad, 1e-12)
            theta = THETA_STAR + frac * basin_boundary()
            force = float(phase_force(theta))
            k = k + self.k_nl * max(0.0, -force)
            if self.relock_interval > 0 and (self.step_index % self.relock_interval == 0):
                k = k + self.relock_extra
        self.cmd = float(np.clip(self.cmd + k * e_reg, -self.u_max, self.u_max))
        return self.cmd


@dataclass
class PLLRun:
    name: str
    t: np.ndarray
    phase_err_rad: np.ndarray
    rms_rad: float
    cycle_slips: int
    mean_bpsk_ber: float
    one_step_iss: float
    feedforward: bool


@dataclass
class PLLResult:
    runs: dict[str, PLLRun]
    verdicts: dict[str, dict]
    feedforward: bool
    notes: str


def _carrier_phase(
    n: int,
    dt: float,
    linewidth_hz: float,
    residual_doppler_hz: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Wiener laser phase + constant residual Doppler (rad)."""
    sigma = np.sqrt(2.0 * np.pi * linewidth_hz * dt)
    w = rng.normal(0.0, sigma, size=n)
    doppler = 2.0 * np.pi * residual_doppler_hz * dt * np.ones(n)
    return np.cumsum(w + doppler)


def _run_lock(
    name: ControllerName,
    phi_true: np.ndarray,
    dt: float,
    rho: float,
    d_step: float,
    snr_elec: float,
) -> PLLRun:
    n = phi_true.size
    t = np.arange(n) * dt
    if name is ControllerName.OPEN:
        ctrl = None
    elif name is ControllerName.PID:
        ctrl = PIPhaseLock(dt=dt)
        ctrl.reset()
    elif name is ControllerName.QSD_WRONG:
        ctrl = QSDPhaseLock(dt=dt, lock_offset=0.5 * np.pi)
        ctrl.reset()
    else:
        ctrl = QSDPhaseLock(dt=dt, lock_offset=0.0)
        ctrl.reset()

    nco = 0.0
    err = np.zeros(n)
    slips = 0
    prev = 0.0
    for i in range(n):
        e = float(wrap_pi(phi_true[i] - nco))
        if abs(e - prev) > np.pi:
            slips += 1
        prev = e
        if ctrl is None:
            u = 0.0
        else:
            u = ctrl.update(e)
        nco = u
        err[i] = float(wrap_pi(phi_true[i] - nco))

    bers = np.array([coherent_ber(snr_elec, float(ph)) for ph in err])
    return PLLRun(
        name=name.value,
        t=t,
        phase_err_rad=err,
        rms_rad=float(np.sqrt(np.mean(err**2))),
        cycle_slips=int(slips),
        mean_bpsk_ber=float(np.mean(bers)),
        one_step_iss=one_step_iss_coverage(np.abs(err), rho, d_step),
        feedforward=False,
    )


def run_pll_campaign(
    duration_s: float = 0.15,
    dt: float = DEFAULT_PLL_DT,
    seed: int = 0,
    linewidth_hz: float = DEFAULT_LINEWIDTH_HZ,
    feedforward: bool = True,
    snr_elec: float = 25.0,
) -> PLLResult:
    """Compare open / PI / QSD / inverted-well PLL. Deterministic for ``seed``."""
    rng = np.random.default_rng(seed)
    n = int(max(16, round(duration_s / dt)))
    residual_hz = (
        DEFAULT_DOPPLER_FF_RESIDUAL_HZ if feedforward else DEFAULT_DOPPLER_RESIDUAL_HZ
    )
    phi = _carrier_phase(n, dt, linewidth_hz, residual_hz, rng)
    dphi = np.abs(np.diff(np.unwrap(phi)))
    d_step = float(np.percentile(dphi, 95)) if dphi.size else 0.0
    rho = DEFAULT_RHO

    runs = {}
    for name in (
        ControllerName.OPEN,
        ControllerName.PID,
        ControllerName.QSD,
        ControllerName.QSD_WRONG,
    ):
        run = _run_lock(name, phi, dt, rho, d_step, snr_elec)
        run.feedforward = feedforward
        runs[name.value] = run

    q, p, o, w = runs["qsd"], runs["pid"], runs["open"], runs["qsd_wrong"]

    def pack(tag, passed, detail):
        return {
            "test": tag,
            "passed": bool(passed),
            "verdict": "PASS" if passed else "NULL",
            "detail": detail,
        }

    verdicts = {
        "P1_qsd_beats_open_phase": pack(
            "P1",
            q.rms_rad < o.rms_rad,
            f"QSD RMS {q.rms_rad:.3f} rad vs open {o.rms_rad:.3f} rad",
        ),
        "P2_qsd_slips_noninferior_pid": pack(
            "P2",
            q.cycle_slips <= p.cycle_slips + max(1, int(0.1 * (p.cycle_slips + 1))),
            f"QSD slips {q.cycle_slips} vs PID {p.cycle_slips}",
        ),
        "P3_one_step_iss": pack(
            "P3",
            q.one_step_iss >= 0.95,
            f"one-step ISS coverage {q.one_step_iss:.3f}",
        ),
        "P4_inverted_well_worse": pack(
            "P4",
            q.mean_bpsk_ber < w.mean_bpsk_ber,
            f"QSD BPSK BER {q.mean_bpsk_ber:.2e} vs quadrature-well {w.mean_bpsk_ber:.2e}",
        ),
    }
    n_pass = sum(1 for v in verdicts.values() if v["passed"])
    ff = "with Doppler feedforward" if feedforward else "no Doppler feedforward"
    notes = (
        f"PLL ({ff}, Δν={linewidth_hz:.0f} Hz, {n} samples @ {1/dt:.0f} Hz): "
        f"{n_pass}/4 PASS. Loop-referred simulation, not a field propagator."
    )
    return PLLResult(runs=runs, verdicts=verdicts, feedforward=feedforward, notes=notes)


def compare_feedforward(seed: int = 0) -> dict:
    """P5: feedforward should reduce QSD phase RMS vs no-FF."""
    on = run_pll_campaign(seed=seed, feedforward=True)
    off = run_pll_campaign(seed=seed, feedforward=False)
    q_on = on.runs["qsd"].rms_rad
    q_off = off.runs["qsd"].rms_rad
    passed = q_on < q_off
    return {
        "test": "P5",
        "passed": passed,
        "verdict": "PASS" if passed else "NULL",
        "detail": f"QSD RMS with FF {q_on:.3f} rad vs no-FF {q_off:.3f} rad",
        "with_ff": on,
        "without_ff": off,
    }
