"""Aurora Principle: phase-match faster than you dissipate."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.constants import THETA_STAR
from aurora_qsd.core.iss import contraction_rate, return_time


@dataclass(frozen=True)
class AuroraCondition:
    """Result of Aurora condition check: Γ_lock > Γ_loss."""

    gamma_lock: float
    gamma_loss: float
    satisfied: bool
    loss_fraction_bound: float
    return_time: float
    recommendation: str


def check_aurora_condition(
    rho: float,
    t2_us: float,
    gate_time_ns: float = 100.0,
    e0: float = 0.1,
    epsilon: float = 0.01,
) -> AuroraCondition:
    """
    Check whether QSD contraction outruns decoherence (Aurora condition).

    Γ_loss ~ 1/T2 (decoherence rate)
    Γ_lock = -½ ln(ρ) (basin contraction rate from gate sequence)

    When Γ_lock > Γ_loss, periodic re-preparation sustains coherence.
    """
    gamma_lock = contraction_rate(rho) / (gate_time_ns * 1e-9)
    gamma_loss = 1.0 / (t2_us * 1e-6) if t2_us > 0 else float("inf")

    satisfied = gamma_lock > gamma_loss
    ratio = gamma_loss / gamma_lock if gamma_lock > 0 else float("inf")
    loss_fraction = ratio * (e0**2) / (THETA_STAR**2) if gamma_lock > 0 else 1.0
    tau_ret = return_time(rho, epsilon, e0)

    if satisfied:
        rec = (
            f"Aurora condition SATISFIED (Γ_lock={gamma_lock:.2e} > Γ_loss={gamma_loss:.2e}). "
            f"Re-preparation every ~{max(3, int(tau_ret))} layers recommended."
        )
    else:
        needed_rho = np.exp(-2.0 * gamma_loss)
        rec = (
            f"Aurora condition NOT satisfied (Γ_lock={gamma_lock:.2e} ≤ Γ_loss={gamma_loss:.2e}). "
            f"Increase lock strength (target ρ < {needed_rho:.4f}) or shorten circuit depth."
        )

    return AuroraCondition(
        gamma_lock=gamma_lock,
        gamma_loss=gamma_loss,
        satisfied=satisfied,
        loss_fraction_bound=float(loss_fraction),
        return_time=float(tau_ret),
        recommendation=rec,
    )


def optimal_relock_interval(
    rho: float,
    t2_us: float,
    layers_per_gate_block: int = 7,
    safety_factor: float = 0.7,
) -> int:
    """
    Recommend re-lock interval in circuit layers (from ibm_fez campaign).

    Hardware-validated: re-lock every 7 layers sustains ZZZ at depth 1241.
    """
    aurora = check_aurora_condition(rho=rho, t2_us=t2_us)
    if not aurora.satisfied:
        return max(3, layers_per_gate_block // 2)

    # Time budget: fraction of T2 before decoherence wins
    t2_layers = int(t2_us * 1e-3 / 0.1)  # rough: 100ns per layer
    interval = max(3, int(safety_factor * t2_layers * aurora.gamma_lock / aurora.gamma_loss))
    return min(interval, layers_per_gate_block * 3)
