"""Re-preparation interval advisor based on Aurora thermodynamics."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.aurora import check_aurora_condition, optimal_relock_interval
from aurora_qsd.core.constants import THETA_STAR_DEG, DEFAULT_RHO
from aurora_qsd.core.iss import iss_trajectory


@dataclass(frozen=True)
class RelockPlan:
    """Recommended re-preparation strategy for a quantum circuit."""

    relock_interval_layers: int
    total_depth: int
    n_relock_cycles: int
    rho: float
    gamma_lock: float
    gamma_loss: float
    aurora_satisfied: bool
    expected_zzz_floor: float
    iss_trajectory_deg: list[float]

    def summary(self) -> str:
        return (
            f"Relock Plan: every {self.relock_interval_layers} layers "
            f"({self.n_relock_cycles} cycles over depth {self.total_depth})\n"
            f"  Γ_lock={self.gamma_lock:.2e}, Γ_loss={self.gamma_loss:.2e} "
            f"→ Aurora {'OK' if self.aurora_satisfied else 'FAIL'}\n"
            f"  Expected ZZZ floor: {self.expected_zzz_floor:.3f}"
        )


class RelockAdvisor:
    """
    Advise on periodic re-preparation (Aurora sunscreen protocol).

    Based on ibm_fez hardware campaign:
      - No re-lock: ZZZ decays to +0.261
      - Re-lock every 7 layers: ZZZ sustains +0.672 at depth 1241
    """

    # Empirical ZZZ floors from hardware validation
    ZZZ_NO_RELOCK = 0.261
    ZZZ_RELOCK_7 = 0.672
    ZZZ_RELOCK_3 = 0.812

    def __init__(self, rho: float = DEFAULT_RHO):
        self.rho = rho

    def plan(
        self,
        total_depth: int,
        t2_us: float = 100.0,
        gate_time_ns: float = 100.0,
    ) -> RelockPlan:
        aurora = check_aurora_condition(rho=self.rho, t2_us=t2_us, gate_time_ns=gate_time_ns)
        interval = optimal_relock_interval(rho=self.rho, t2_us=t2_us)
        n_cycles = max(1, total_depth // interval)

        # Interpolate expected ZZZ from hardware data
        if interval <= 3:
            zzz = self.ZZZ_RELOCK_3
        elif interval <= 7:
            zzz = self.ZZZ_RELOCK_7
        else:
            zzz = self.ZZZ_NO_RELOCK + (self.ZZZ_RELOCK_7 - self.ZZZ_NO_RELOCK) * (7.0 / interval)

        traj = iss_trajectory(
            e0=np.radians(10.0),
            steps=n_cycles,
            rho=self.rho,
        )

        return RelockPlan(
            relock_interval_layers=interval,
            total_depth=total_depth,
            n_relock_cycles=n_cycles,
            rho=self.rho,
            gamma_lock=aurora.gamma_lock,
            gamma_loss=aurora.gamma_loss,
            aurora_satisfied=aurora.satisfied,
            expected_zzz_floor=zzz,
            iss_trajectory_deg=[float(np.degrees(e)) for e in traj],
        )
