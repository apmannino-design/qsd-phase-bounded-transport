"""Willow gain maximization sweep — θ, depth, re-lock on interior line."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_WILLOW_HW_DEG
from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_lines import WillowLine, extract_disjoint_3q_lines, get_line
from aurora_qsd.quantum.willow_run import _depth_head_to_head, _require_cirq


@dataclass
class SweepPoint:
    theta_deg: float
    depth_layers: int
    relock_interval: int
    zzz_theta_star: float = 0.0
    zzz_negative: float = 0.0
    abs_gap: float = 0.0
    shots: int = 0

    def to_dict(self) -> dict:
        return {
            "theta_deg": self.theta_deg,
            "depth_layers": self.depth_layers,
            "relock_interval": self.relock_interval,
            "zzz_theta_star": self.zzz_theta_star,
            "zzz_negative": self.zzz_negative,
            "abs_gap": self.abs_gap,
            "shots": self.shots,
        }


@dataclass
class GainSweepResult:
    phase: str = ""
    shots: int = 0
    line: list[str] = field(default_factory=list)
    points: list[SweepPoint] = field(default_factory=list)
    best: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    cells: dict = field(default_factory=dict)
    elapsed_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "shots": self.shots,
            "line": self.line,
            "points": [p.to_dict() for p in self.points],
            "best": self.best,
            "validation": self.validation,
            "cells": self.cells,
            "elapsed_s": self.elapsed_s,
        }


def _get_sampler():
    _require_cirq()
    from cirq_google import engine

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    return proc.get_sampler(), proc.get_device()


def _eval_point(
    sampler,
    line: WillowLine,
    theta_deg: float,
    depth_layers: int,
    relock_interval: int,
    shots: int,
    negative_offset_deg: float = 70.0,
) -> SweepPoint:
    theta_star = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta_star, offset_deg=negative_offset_deg)
    row = _depth_head_to_head(
        sampler, line, shots, theta_star, theta_neg, depth_layers, relock_interval
    )
    return SweepPoint(
        theta_deg=theta_deg,
        depth_layers=depth_layers,
        relock_interval=relock_interval,
        zzz_theta_star=row["qsd_theta_star"]["zzz"],
        zzz_negative=row["negative_theta"]["zzz"],
        abs_gap=row["abs_gap"],
        shots=shots,
    )


def run_gain_sweep(
    shots: int = 300,
    theta_values: list[float] | None = None,
    depth_values: list[int] | None = None,
    relock_values: list[int] | None = None,
    line_name: str = "interior",
    progress: bool = True,
) -> GainSweepResult:
    """Grid search θ × depth × re-lock; maximize |ΔZZZ| on interior line."""
    sampler, _ = _get_sampler()
    line = get_line(line_name)
    thetas = theta_values or [22.46, 22.47, 22.48, 22.49, 22.50]
    depths = depth_values or [12, 14, 16, 18, 20]
    relocks = relock_values or [2, 3, 4]

    t0 = time.time()
    out = GainSweepResult(phase="coarse_sweep", shots=shots, line=line.labels())
    grid = list(product(thetas, depths, relocks))
    for i, (th, depth, rl) in enumerate(grid):
        if progress:
            print(
                f"[gain_sweep] {i + 1}/{len(grid)} θ={th:.2f}° depth={depth} relock={rl}",
                flush=True,
            )
        pt = _eval_point(sampler, line, th, depth, rl, shots)
        out.points.append(pt)

    best_pt = max(out.points, key=lambda p: p.abs_gap)
    out.best = best_pt.to_dict()
    out.elapsed_s = time.time() - t0
    return out


def run_fine_sweep(
    center_theta: float,
    center_depth: int,
    center_relock: int,
    shots: int = 400,
    line_name: str = "interior",
) -> GainSweepResult:
    """Fine grid around coarse winner."""
    thetas = [round(center_theta + d, 3) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    depths = sorted({max(4, center_depth + d) for d in (-2, 0, 2)})
    relocks = sorted({max(2, center_relock + d) for d in (-1, 0, 1)})

    sampler, _ = _get_sampler()
    line = get_line(line_name)
    t0 = time.time()
    out = GainSweepResult(phase="fine_sweep", shots=shots, line=line.labels())
    grid = list(product(thetas, depths, relocks))
    for i, (th, depth, rl) in enumerate(grid):
        print(f"[fine] {i + 1}/{len(grid)} θ={th:.3f}° depth={depth} relock={rl}", flush=True)
        out.points.append(_eval_point(sampler, line, th, depth, rl, shots))

    best_pt = max(out.points, key=lambda p: p.abs_gap)
    out.best = best_pt.to_dict()
    out.elapsed_s = time.time() - t0
    return out


def validate_best(
    theta_deg: float,
    depth_layers: int,
    relock_interval: int,
    shots: int = 2000,
    line_name: str = "interior",
) -> dict:
    """High-shot validation of winning configuration."""
    sampler, _ = _get_sampler()
    line = get_line(line_name)
    print(
        f"[validate] θ={theta_deg:.3f}° depth={depth_layers} relock={relock_interval} shots={shots}",
        flush=True,
    )
    pt = _eval_point(sampler, line, theta_deg, depth_layers, relock_interval, shots)
    return pt.to_dict()


def run_winning_cells(
    theta_deg: float,
    depth_layers: int,
    relock_interval: int,
    shots: int = 400,
    min_prior_gap: float = 0.05,
    prior_results_path: str | Path | None = None,
) -> dict:
    """Run best config on cells that won in prior 96-qubit campaign."""
    sampler, device = _get_sampler()
    cells = extract_disjoint_3q_lines(device)

    winning_ids: set[int] | None = None
    path = Path(prior_results_path) if prior_results_path else Path("results/willow_max_qubits_96_depth_64.json")
    if path.exists():
        prior = json.loads(path.read_text())
        winning_ids = {
            c["cell_id"]
            for c in prior.get("cells", [])
            if c.get("abs_gap", 0.0) >= min_prior_gap
        }
        print(f"[cells] using {len(winning_ids)} prior winners from {path}", flush=True)

    gaps = []
    rows = []
    for i, line in enumerate(cells):
        if winning_ids is not None and i not in winning_ids:
            continue
        print(f"[cells] {line.labels()} ({i})", flush=True)
        pt = _eval_point(sampler, line, theta_deg, depth_layers, relock_interval, shots)
        rows.append({"cell_id": i, "line": line.labels(), **pt.to_dict()})
        gaps.append(pt.abs_gap)

    return {
        "n_cells": len(rows),
        "n_qubits": len(rows) * 3,
        "abs_gap_median": float(np.median(gaps)) if gaps else 0.0,
        "abs_gap_mean": float(np.mean(gaps)) if gaps else 0.0,
        "cells_winning": int(sum(1 for g in gaps if g >= 0.05)),
        "cells": rows,
    }


def run_full_gain_campaign(
    coarse_shots: int = 300,
    fine_shots: int = 400,
    validate_shots: int = 2000,
    cell_shots: int = 500,
    results_dir: str | Path = "results",
) -> dict:
    """Coarse → fine → validate → winning cells. Saves JSON at each stage."""
    out_dir = Path(results_dir)
    out_dir.mkdir(exist_ok=True)

    print("=" * 60 + "\nPHASE 1: COARSE SWEEP\n" + "=" * 60, flush=True)
    coarse = run_gain_sweep(shots=coarse_shots)
    (out_dir / "willow_gain_coarse.json").write_text(json.dumps(coarse.to_dict(), indent=2))
    print(f"Coarse best: |Δ|={coarse.best['abs_gap']:.3f} @ {coarse.best}", flush=True)

    b = coarse.best
    print("\n" + "=" * 60 + "\nPHASE 2: FINE SWEEP\n" + "=" * 60, flush=True)
    fine = run_fine_sweep(
        b["theta_deg"], b["depth_layers"], b["relock_interval"], shots=fine_shots
    )
    (out_dir / "willow_gain_fine.json").write_text(json.dumps(fine.to_dict(), indent=2))
    print(f"Fine best: |Δ|={fine.best['abs_gap']:.3f} @ {fine.best}", flush=True)

    b = fine.best
    print("\n" + "=" * 60 + "\nPHASE 3: HIGH-SHOT VALIDATION\n" + "=" * 60, flush=True)
    validation = validate_best(
        b["theta_deg"], b["depth_layers"], b["relock_interval"], shots=validate_shots
    )
    print(f"Validated: |Δ|={validation['abs_gap']:.3f}", flush=True)

    print("\n" + "=" * 60 + "\nPHASE 4: WINNING CELLS\n" + "=" * 60, flush=True)
    cells = run_winning_cells(
        b["theta_deg"], b["depth_layers"], b["relock_interval"], shots=cell_shots
    )
    print(
        f"Cells: median |Δ|={cells['abs_gap_median']:.3f} "
        f"{cells['cells_winning']}/{cells['n_cells']} win",
        flush=True,
    )

    summary = {
        "best_config": b,
        "coarse_best_abs_gap": coarse.best["abs_gap"],
        "fine_best_abs_gap": fine.best["abs_gap"],
        "validated_abs_gap": validation["abs_gap"],
        "validated": validation,
        "cells": cells,
    }
    (out_dir / "willow_gain_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
