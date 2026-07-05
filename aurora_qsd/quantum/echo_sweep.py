"""Willow echo parameter sweeps — θ, τ, and QSD pulse variants (simulator)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.quantum.echo_protocol import (
    PULSE_VARIANTS,
    THETA_STAR_WILLOW,
    THETA_STAR_WILLOW_DEG,
    _willow_idle_noise_model,
    pooled_echo_fidelity,
)


@dataclass
class SweepPoint:
    label: str
    value: float
    f_qsd: float
    f_x: float
    f_none: float
    delta_qsd_x: float
    delta_qsd_none: float


@dataclass
class WillowEchoSweepResult:
    shots: int
    t2_ns: float
    baseline_tau_ns: float = 1000.0
    theta_sweep: list[SweepPoint] = field(default_factory=list)
    tau_sweep: list[SweepPoint] = field(default_factory=list)
    pulse_sweep: list[dict] = field(default_factory=list)
    best_theta_deg: float = THETA_STAR_WILLOW_DEG
    best_tau_ns: float = 1000.0
    best_pulse: str = "phase"
    best_f_qsd: float = 0.0
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "shots": self.shots,
            "t2_ns": self.t2_ns,
            "baseline_tau_ns": self.baseline_tau_ns,
            "theta_sweep": [p.__dict__ for p in self.theta_sweep],
            "tau_sweep": [p.__dict__ for p in self.tau_sweep],
            "pulse_sweep": self.pulse_sweep,
            "best_theta_deg": self.best_theta_deg,
            "best_tau_ns": self.best_tau_ns,
            "best_pulse": self.best_pulse,
            "best_f_qsd": self.best_f_qsd,
            "recommendation": self.recommendation,
        }


def _make_sim(tau_ns: float, t2_ns: float):
    from qiskit_aer import AerSimulator

    return AerSimulator(noise_model=_willow_idle_noise_model(tau_ns=tau_ns, t2_ns=t2_ns))


def _sweep_point(
    sim,
    label: str,
    value: float,
    shots: int,
    tau_ns: float,
    theta: float,
    pulse_variant: str = "phase",
) -> SweepPoint:
    f_qsd = pooled_echo_fidelity(sim, "qsd", shots, tau_ns, theta, pulse_variant=pulse_variant)
    f_x = pooled_echo_fidelity(sim, "x", shots, tau_ns, theta)
    f_none = pooled_echo_fidelity(sim, "none", shots, tau_ns, theta)
    return SweepPoint(
        label=label,
        value=value,
        f_qsd=f_qsd,
        f_x=f_x,
        f_none=f_none,
        delta_qsd_x=f_qsd - f_x,
        delta_qsd_none=f_qsd - f_none,
    )


def sweep_theta(
    shots: int = 1000,
    tau_ns: float = 1000.0,
    t2_ns: float = 2000.0,
    span_deg: float = 20.0,
    n_points: int = 9,
    pulse_variant: str = "tridelta",
) -> list[SweepPoint]:
    """Sweep echo angle θ around θ* = 22.5°."""
    sim = _make_sim(tau_ns, t2_ns)
    thetas_deg = np.linspace(THETA_STAR_WILLOW_DEG - span_deg, THETA_STAR_WILLOW_DEG + span_deg, n_points)
    return [
        _sweep_point(
            sim,
            label=f"{deg:.1f}°",
            value=float(deg),
            shots=shots,
            tau_ns=tau_ns,
            theta=float(np.radians(deg)),
            pulse_variant=pulse_variant,
        )
        for deg in thetas_deg
    ]


def sweep_tau(
    shots: int = 1000,
    theta: float = THETA_STAR_WILLOW,
    t2_ns: float = 2000.0,
    taus_ns: tuple[float, ...] = (250, 500, 1000, 1500, 2000, 3000),
    pulse_variant: str = "tridelta",
) -> list[SweepPoint]:
    """Sweep idle time τ."""
    points: list[SweepPoint] = []
    for tau in taus_ns:
        sim = _make_sim(tau, t2_ns)
        points.append(
            _sweep_point(
                sim,
                label=f"{int(tau)} ns",
                value=float(tau),
                shots=shots,
                tau_ns=tau,
                theta=theta,
                pulse_variant=pulse_variant,
            )
        )
    return points


def sweep_pulse_variants(
    shots: int = 1000,
    tau_ns: float = 1000.0,
    theta: float = THETA_STAR_WILLOW,
    t2_ns: float = 2000.0,
) -> list[dict]:
    """Compare QSD pulse variants against X and no-echo baselines."""
    sim = _make_sim(tau_ns, t2_ns)
    f_x = pooled_echo_fidelity(sim, "x", shots, tau_ns, theta)
    f_none = pooled_echo_fidelity(sim, "none", shots, tau_ns, theta)
    rows = []
    for variant in PULSE_VARIANTS:
        f_qsd = pooled_echo_fidelity(sim, "qsd", shots, tau_ns, theta, pulse_variant=variant)
        rows.append(
            {
                "pulse": variant,
                "f_qsd": f_qsd,
                "f_x": f_x,
                "f_none": f_none,
                "delta_qsd_x": f_qsd - f_x,
                "delta_qsd_none": f_qsd - f_none,
            }
        )
    return rows


def run_willow_echo_sweep(
    shots: int = 1000,
    tau_ns: float = 1000.0,
    t2_ns: float = 2000.0,
    span_deg: float = 20.0,
    n_theta: int = 9,
    taus_ns: tuple[float, ...] = (250, 500, 1000, 1500, 2000, 3000),
) -> WillowEchoSweepResult:
    """Full θ + τ + pulse sweep with best-settings recommendation."""
    out = WillowEchoSweepResult(shots=shots, t2_ns=t2_ns, baseline_tau_ns=tau_ns)

    out.theta_sweep = sweep_theta(shots, tau_ns, t2_ns, span_deg, n_theta)
    best_theta = max(out.theta_sweep, key=lambda p: p.f_qsd)
    out.best_theta_deg = best_theta.value

    theta_rad = float(np.radians(out.best_theta_deg))
    out.tau_sweep = sweep_tau(shots, theta_rad, t2_ns, taus_ns)
    best_tau = max(out.tau_sweep, key=lambda p: p.f_qsd)
    out.best_tau_ns = best_tau.value

    out.pulse_sweep = sweep_pulse_variants(shots, out.best_tau_ns, theta_rad, t2_ns)
    best_pulse = max(out.pulse_sweep, key=lambda r: r["f_qsd"])
    out.best_pulse = best_pulse["pulse"]
    out.best_f_qsd = best_pulse["f_qsd"]

    ref_x = best_pulse["f_x"]
    ref_none = best_pulse["f_none"]
    if out.best_f_qsd > ref_x and out.best_f_qsd > ref_none:
        out.recommendation = (
            f"Try Willow with pulse={out.best_pulse}, θ={out.best_theta_deg:.1f}°, "
            f"τ={int(out.best_tau_ns)} ns (sim F={out.best_f_qsd:.3f} beats X and no-echo)."
        )
    else:
        out.recommendation = (
            f"Best sim config: pulse={out.best_pulse}, θ={out.best_theta_deg:.1f}°, "
            f"τ={int(out.best_tau_ns)} ns (F={out.best_f_qsd:.3f}). "
            f"Still below X ({ref_x:.3f}) or no-echo ({ref_none:.3f}) — try hardware calibration."
        )

    return out
