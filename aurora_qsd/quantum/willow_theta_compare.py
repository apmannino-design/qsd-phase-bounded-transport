"""
Willow θ head-to-head — platform θ* vs merger partition θ on full chip.

Compares QSD depth sunscreen at:
  - platform optimum (22.49°)
  - SO(2) merger partition angle (27.61°)
on interior line + all 32 disjoint cells (96 qubits).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import (
    MERGER_PARTITION_THETA_DEG,
    THETA_STAR_WILLOW_HW_DEG,
)
from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_SUNSCREEN_LAYERS
from aurora_qsd.quantum.willow_lines import WillowLine, extract_disjoint_3q_lines, get_line
from aurora_qsd.quantum.willow_run import (
    _depth_head_to_head,
    _require_cirq,
)


@dataclass
class ThetaArmSummary:
    theta_deg: float
    label: str
    interior_abs_gap: float = 0.0
    cells_winning: int = 0
    n_cells: int = 0
    abs_gap_median: float = 0.0
    abs_gap_mean: float = 0.0
    abs_gap_min: float = 0.0
    cells: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "theta_deg": self.theta_deg,
            "label": self.label,
            "interior_abs_gap": self.interior_abs_gap,
            "cells_winning": self.cells_winning,
            "n_cells": self.n_cells,
            "abs_gap_median": self.abs_gap_median,
            "abs_gap_mean": self.abs_gap_mean,
            "abs_gap_min": self.abs_gap_min,
            "cells": self.cells,
        }


@dataclass
class ThetaCompareResult:
    processor: str = "willow_pink"
    depth_layers: int = OPTIMAL_SUNSCREEN_LAYERS
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL
    shots_interior: int = 0
    shots_cells: int = 0
    negative_offset_deg: float = 70.0
    arms: list[ThetaArmSummary] = field(default_factory=list)
    winner_theta_deg: float = 0.0
    winner_label: str = ""
    margin_median_gap: float = 0.0
    elapsed_s: float = 0.0
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "depth_layers": self.depth_layers,
            "relock_interval": self.relock_interval,
            "shots_interior": self.shots_interior,
            "shots_cells": self.shots_cells,
            "negative_offset_deg": self.negative_offset_deg,
            "arms": [a.to_dict() for a in self.arms],
            "winner_theta_deg": self.winner_theta_deg,
            "winner_label": self.winner_label,
            "margin_median_gap": self.margin_median_gap,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _run_arm_campaign(
    sampler,
    theta_deg: float,
    label: str,
    shots_interior: int,
    shots_cells: int,
    depth_layers: int,
    relock_interval: int,
    negative_offset_deg: float,
    cells: list[WillowLine],
) -> ThetaArmSummary:
    theta = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta, offset_deg=negative_offset_deg)

    interior = get_line("interior")
    print(f"[theta_compare] {label} θ={theta_deg:.2f}° interior ...", flush=True)
    interior_row = _depth_head_to_head(
        sampler, interior, shots_interior, theta, theta_neg, depth_layers, relock_interval
    )

    gaps: list[float] = []
    rows: list[dict] = []
    for i, line in enumerate(cells):
        print(f"[theta_compare] {label} cell {i + 1}/{len(cells)} {line.labels()}", flush=True)
        row = _depth_head_to_head(
            sampler, line, shots_cells, theta, theta_neg, depth_layers, relock_interval
        )
        row["cell_id"] = i
        row["line"] = line.labels()
        rows.append(row)
        gaps.append(row["abs_gap"])

    return ThetaArmSummary(
        theta_deg=theta_deg,
        label=label,
        interior_abs_gap=float(interior_row["abs_gap"]),
        cells_winning=int(sum(1 for g in gaps if g >= 0.05)),
        n_cells=len(cells),
        abs_gap_median=float(np.median(gaps)) if gaps else 0.0,
        abs_gap_mean=float(np.mean(gaps)) if gaps else 0.0,
        abs_gap_min=float(np.min(gaps)) if gaps else 0.0,
        cells=rows,
    )


def run_theta_head_to_head(
    shots_interior: int = 2000,
    shots_cells: int = 500,
    depth_layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    negative_offset_deg: float = 70.0,
    thetas: list[tuple[float, str]] | None = None,
) -> ThetaCompareResult:
    """
    Full-chip Willow sim comparison: platform θ* vs merger partition θ.
    """
    _require_cirq()
    from cirq_google import engine

    thetas = thetas or [
        (THETA_STAR_WILLOW_HW_DEG, "platform_theta_star"),
        (MERGER_PARTITION_THETA_DEG, "merger_partition_theta"),
    ]

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    sampler = proc.get_sampler()
    cells = extract_disjoint_3q_lines(proc.get_device())

    t0 = time.time()
    out = ThetaCompareResult(
        depth_layers=depth_layers,
        relock_interval=relock_interval,
        shots_interior=shots_interior,
        shots_cells=shots_cells,
        negative_offset_deg=negative_offset_deg,
    )

    for theta_deg, label in thetas:
        arm = _run_arm_campaign(
            sampler,
            theta_deg,
            label,
            shots_interior,
            shots_cells,
            depth_layers,
            relock_interval,
            negative_offset_deg,
            cells,
        )
        out.arms.append(arm)

    # Winner by median chip gap (primary), interior gap (tiebreak)
    ranked = sorted(
        out.arms,
        key=lambda a: (a.abs_gap_median, a.interior_abs_gap, a.cells_winning),
        reverse=True,
    )
    winner = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else winner
    margin = winner.abs_gap_median - runner.abs_gap_median

    out.winner_theta_deg = winner.theta_deg
    out.winner_label = winner.label
    out.margin_median_gap = float(margin)
    out.elapsed_s = time.time() - t0

    if margin >= 0.05:
        out.verdict = "THETA_WIN"
        out.notes = (
            f"{winner.label} wins: median |Δ|={winner.abs_gap_median:.3f} vs "
            f"{runner.label} {runner.abs_gap_median:.3f} (margin {margin:.3f}); "
            f"interior {winner.interior_abs_gap:.3f} vs {runner.interior_abs_gap:.3f}."
        )
    elif margin >= 0.02:
        out.verdict = "MARGINAL"
        out.notes = f"Marginal θ preference ({margin:.3f} median gap); not decisive on sim."
    else:
        out.verdict = "TIE"
        out.notes = (
            f"No meaningful θ difference on sim (margin {margin:.3f}); "
            f"platform {THETA_STAR_WILLOW_HW_DEG}° retained."
        )

    return out
