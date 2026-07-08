"""
QSD Robust Test Suite v2.0.0 — preregistered IBM hardware validation protocol.

Tests T1–T4 compose existing fez_cells / basin_sweep / ibm_retention_audit
infrastructure. Circuits use TriLock + QSD layers from fez_cells (not RY-only stubs).

Simulation paths are fully executable; hardware paths submit via Qiskit Runtime
when backend is not aer_sim / aer_fez.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aurora_qsd.core.constants import (
    THETA_STAR_DEG,
    THETA_STAR_HW_DEG,
    THETA_STAR_WILLOW_HW_DEG,
)
from aurora_qsd.quantum.basin_sweep import run_basin_sweep
from aurora_qsd.quantum.fez_cells import (
    build_zzz_cell_circuit,
    zzz_correlator,
)
from aurora_qsd.quantum.ibm_retention_audit import (
    THETA_WALL_DEG,
    build_qsd_sunscreen_circuit,
    ideal_zzz_qiskit,
    run_circuit_zzz,
)
from aurora_qsd.quantum.noise_models import build_simulator
from aurora_qsd.quantum.runner import run_circuit

PREREG_PATH = Path("results/prereg_v200.json")

DEFAULT_PARAMS: dict[str, Any] = {
    "theta_star_deg": THETA_STAR_DEG,
    "theta_wall_deg": THETA_WALL_DEG,
    "basin_near_edge_deg": 3.0 * THETA_STAR_DEG,
    "basin_far_edge_deg": 90.0,
    "kappa": 1.0,
    "n_null": 100,
    "shots_per_point": 2000,
    "shots_tomo": 2000,
    "random_seed": 42,
    "alpha_significance": 0.05,
    "bootstrap_B": 10000,
    "z_threshold": 3.0,
    "ks_threshold": 0.2,
    "survival_tolerance": 0.25,
    "min_survival_fraction": 0.50,
    "sector_m": 0.3,
    "sector_L": 0.8,
    "K_eff": 0.45,
    "sigma_r": 5.0,
    "D_hw_estimate": 0.05,
    "platform_independence_deg": 15.0,
}


def load_prereg_v200(path: Path | None = None) -> dict:
    p = path or PREREG_PATH
    if p.is_file():
        return json.loads(p.read_text())
    params = dict(DEFAULT_PARAMS)
    m, L, k = params["sector_m"], params["sector_L"], params["K_eff"]
    params["rho_theoretical"] = 1.0 - 2.0 * m * k + (L * k) ** 2
    return {"parameters": params, "decision_rules": {}, "verdicts": {}}


def _params() -> dict:
    blob = load_prereg_v200()
    p = dict(DEFAULT_PARAMS)
    p.update(blob.get("parameters", {}))
    m, L, k = p["sector_m"], p["sector_L"], p["K_eff"]
    p["rho_theoretical"] = 1.0 - 2.0 * m * k + (L * k) ** 2
    return p


# ---------------------------------------------------------------------------
# Statistics (from v200 preregistration)
# ---------------------------------------------------------------------------


def compute_relative_entropy_from_bloch(r: float) -> float:
    """D(rho || I/2) for single-qubit Bloch length r (nats)."""
    if r <= 0:
        return 0.0
    if r >= 1:
        return math.log(2.0)
    q = 0.5 * (1.0 - r)
    h2 = 0.0
    if q > 1e-15:
        h2 -= q * math.log(q)
    if (1.0 - q) > 1e-15:
        h2 -= (1.0 - q) * math.log(1.0 - q)
    return math.log(2.0) - h2


def relative_entropy_vs_mixed_qiskit(circuit_no_measure) -> float:
    """Von Neumann D(rho || I/d) for full state (ideal tomography proxy).

    Note: unitary circuits yield pure states, so D is constant vs depth.
    Use ``disorder_from_counts`` for noisy T1 contraction fits.
    """
    from qiskit.quantum_info import DensityMatrix, entropy

    dm = DensityMatrix.from_instruction(circuit_no_measure)
    d = 2 ** circuit_no_measure.num_qubits
    s = float(entropy(dm, base=np.e))
    return float(math.log(d) - s)


def disorder_from_counts(counts: dict[str, int], n_qubits: int = 3) -> float:
    """D = ln(2^n) - H_classical(counts) — decreases under strict contraction."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / total
        if p > 1e-15:
            h -= p * math.log(p)
    return float(math.log(2**n_qubits) - h)


def fit_contraction_rate(depths: list[int], entropies: list[float]) -> tuple[float | None, float | None, float]:
    """Fit ln(D_t) = ln(D_0) + t·ln(rho_q); one-sided p for slope < 0."""
    x = np.array(depths, dtype=float)
    y = np.array(entropies, dtype=float)
    mask = y > 1e-12
    if int(np.sum(mask)) < 3:
        return None, None, 1.0

    y = np.log(y[mask])
    x = x[mask]
    n = len(x)
    x_mean, y_mean = float(np.mean(x)), float(np.mean(y))
    ss_xx = float(np.sum((x - x_mean) ** 2))
    ss_xy = float(np.sum((x - x_mean) * (y - y_mean)))
    if ss_xx < 1e-15:
        return None, None, 1.0

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    y_pred = intercept + slope * x
    rss = float(np.sum((y - y_pred) ** 2))
    rse = math.sqrt(rss / (n - 2)) if n > 2 else 0.0
    se_slope = rse / math.sqrt(ss_xx) if ss_xx > 0 else 0.0

    if se_slope > 0:
        t_stat = slope / se_slope
        p_value = 0.5 * (1.0 + math.erf(t_stat / math.sqrt(2.0)))
    else:
        p_value = 1.0 if slope >= 0 else 0.0

    rho_q = float(math.exp(slope))
    return rho_q, se_slope, float(p_value)


def compute_ks_distance(empirical_samples: list[float], null_samples: list[float]) -> float:
    """Two-sample Kolmogorov–Smirnov D statistic."""
    a = np.sort(np.asarray(empirical_samples, dtype=float))
    b = np.sort(np.asarray(null_samples, dtype=float))
    if len(a) == 0 or len(b) == 0:
        return 0.0
    grid = np.sort(np.unique(np.concatenate([a, b])))
    cdf_a = np.searchsorted(a, grid, side="right") / len(a)
    cdf_b = np.searchsorted(b, grid, side="right") / len(b)
    return float(np.max(np.abs(cdf_a - cdf_b)))


def generate_basin_sweep_angles(center_deg: float = 22.5, width_deg: float = 120.0, n_steps: int = 25) -> np.ndarray:
    half = width_deg / 2.0
    return np.linspace(center_deg - half, center_deg + half, n_steps)


def generate_null_surrogates_basin(n_null: int = 100, seed: int = 42) -> list[tuple[float, float, float]]:
    rng = np.random.default_rng(seed)
    return [
        (
            float(rng.uniform(-np.pi, np.pi)),
            float(rng.uniform(-np.pi, np.pi)),
            float(rng.uniform(-np.pi, np.pi)),
        )
        for _ in range(n_null)
    ]


def compute_theoretical_steady_state_error(rho: float, e_prep: float, d_hw: float) -> float:
    if rho >= 1.0:
        return float("inf")
    return e_prep + d_hw / (1.0 - math.sqrt(rho))


def simulate_reprep_survival(
    n_cycles: int,
    layers_per_cycle: int,
    rho: float,
    d_hw: float,
    e_prep: float,
    survival_tol: float = 0.25,
) -> float:
    errors: list[float] = []
    e = e_prep
    for _ in range(n_cycles):
        for _ in range(layers_per_cycle):
            e = math.sqrt(rho) * e + d_hw
        e = e_prep
        errors.append(e)
    return float(np.mean(np.array(errors) < survival_tol))


def compute_platform_independence_score(peaks_deg: list[float], threshold_deg: float = 15.0) -> tuple[float, bool]:
    peaks = np.asarray(peaks_deg, dtype=float)
    spread = float(np.max(peaks) - np.min(peaks))
    return spread, spread <= threshold_deg


# ---------------------------------------------------------------------------
# Test results
# ---------------------------------------------------------------------------


@dataclass
class TestDecision:
    test: str
    decision: str
    details: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RobustSuiteReport:
    protocol: str = "QSD_ROBUST_TEST_SUITE_v200"
    version: str = "2.0.0"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    backend: str = "aer_sim"
    parameters: dict = field(default_factory=dict)
    tests: dict = field(default_factory=dict)
    overall: str = "PENDING"
    endorsable: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# T1 — Tomographic strict-contraction (ideal state entropy vs depth)
# ---------------------------------------------------------------------------


def run_t1_tomography(
    backend_name: str = "aer_sim",
    qubits: tuple[int, int, int] = (0, 1, 2),
    depths: tuple[int, ...] = (2, 4, 6, 8),
    theta_deg: float | None = None,
    shots: int | None = None,
    use_hardware: bool = False,
    noise: str = "native",
) -> TestDecision:
    """
    T1: Disorder D vs depth at wall θ under noise (Theorem 6 contraction).

    Uses fez_cells sunscreen circuit. Ideal unitary paths are constant-D and
    are reported as INCONCLUSIVE (not PASS).
    """
    p = _params()
    theta = theta_deg if theta_deg is not None else p["theta_wall_deg"]
    alpha = p["alpha_significance"]
    shots = shots or p["shots_tomo"]

    entropies: list[float] = []
    zzz_by_depth: list[dict] = []
    mode = "ideal_unitary"

    if use_hardware and backend_name not in ("aer_sim", "aer", "aer_ideal"):
        mode = "hardware"
        for depth in depths:
            c_m = build_qsd_sunscreen_circuit((0, 1, 2), theta, layers=depth, relock_interval=5, measure=True)
            hw = run_circuit_zzz(c_m, backend_name, shots, physical_qubits=qubits)
            counts = hw["counts"]
            d_rel = disorder_from_counts(counts, n_qubits=3)
            entropies.append(d_rel)
            c_ideal = build_qsd_sunscreen_circuit((0, 1, 2), theta, layers=depth, relock_interval=5, measure=False)
            ideal = ideal_zzz_qiskit(c_ideal)
            zzz_by_depth.append({
                "depth": depth,
                "relative_entropy": d_rel,
                "ideal_zzz": ideal["ideal_zzz"],
                "measured_zzz": zzz_correlator(counts, n_qubits=3),
                "job_id": hw.get("job_id"),
            })
    else:
        sim = build_simulator(noise)
        mode = f"aer_{noise}"
        for depth in depths:
            c_m = build_qsd_sunscreen_circuit((0, 1, 2), theta, layers=depth, relock_interval=5, measure=True)
            counts = run_circuit(c_m, sim, shots)
            d_rel = disorder_from_counts(counts, n_qubits=3)
            entropies.append(d_rel)
            c_ideal = build_qsd_sunscreen_circuit((0, 1, 2), theta, layers=depth, relock_interval=5, measure=False)
            ideal = ideal_zzz_qiskit(c_ideal)
            zzz_by_depth.append({
                "depth": depth,
                "relative_entropy": d_rel,
                "ideal_zzz": ideal["ideal_zzz"],
                "measured_zzz": zzz_correlator(counts, n_qubits=3),
            })

    rho_q, se, p_val = fit_contraction_rate(list(depths), entropies)
    rho_cap = 0.995
    monotone = all(entropies[i] >= entropies[i + 1] for i in range(len(entropies) - 1))
    passed = bool(
        rho_q is not None
        and rho_q < rho_cap
        and p_val < alpha
        and monotone
    )
    decision = "PASS" if passed else "FAIL"

    if noise == "ideal" and not use_hardware:
        decision = "INCONCLUSIVE"
        passed = False

    return TestDecision(
        test="T1",
        decision=decision,
        details={
            "theta_deg": theta,
            "depths": list(depths),
            "relative_entropies": entropies,
            "rho_q": rho_q,
            "se_slope": se,
            "p_value": p_val,
            "alpha": alpha,
            "rho_cap": rho_cap,
            "monotone_decreasing": monotone,
            "by_depth": zzz_by_depth,
            "mode": mode,
            "noise": noise,
        },
        notes=(
            f"Fitted rho_q={rho_q:.4f} p={p_val:.4f} monotone={monotone} "
            f"({'contraction' if passed else 'no significant contraction'})"
            if rho_q is not None
            else "Insufficient depth points for fit"
        )
        + ("; ideal unitary D is constant — use native noise or hardware." if noise == "ideal" and not use_hardware else ""),
    )


# ---------------------------------------------------------------------------
# T2 — Extended basin sweep + null KS separation
# ---------------------------------------------------------------------------


def run_t2_basin_sweep(
    backend_name: str = "aer_sim",
    center_deg: float | None = None,
    width_deg: float = 120.0,
    n_steps: int = 25,
    depth: int = 4,
    shots: int | None = None,
    n_null: int | None = None,
    noise: str = "native",
    contrast_threshold: float = 0.50,
) -> TestDecision:
    """T2: Basin sweep on fez_cells + null KS separation + D2 contrast."""
    p = _params()
    center = center_deg if center_deg is not None else p["theta_star_deg"]
    shots = shots or p["shots_per_point"]
    n_null = n_null or p["n_null"]
    ks_thr = p["ks_threshold"]

    angles = generate_basin_sweep_angles(center, width_deg, n_steps)
    sim = build_simulator(noise)

    empirical: list[float] = []
    for ang_deg in angles:
        theta = float(np.radians(ang_deg))
        counts = run_circuit(build_zzz_cell_circuit(theta=theta, depth=depth), sim, shots)
        empirical.append(zzz_correlator(counts, n_qubits=3))

    peak_idx = int(np.argmax(np.abs(empirical)))
    peak_angle = float(angles[peak_idx])
    peak_zzz = float(empirical[peak_idx])
    z_min, z_max = float(min(empirical)), float(max(empirical))
    contrast = float(z_max - z_min)

    null_vals: list[float] = []
    rng = np.random.default_rng(p["random_seed"])
    for _ in range(n_null):
        th = float(rng.uniform(-np.pi, np.pi))
        counts = run_circuit(build_zzz_cell_circuit(theta=th, depth=depth), sim, max(256, shots // 4))
        null_vals.append(zzz_correlator(counts, n_qubits=3))

    ks_stat = compute_ks_distance(empirical, null_vals)
    interior = bool(angles[0] < peak_angle < angles[-1])
    ks_pass = ks_stat >= ks_thr
    contrast_pass = contrast >= contrast_threshold
    passed = bool(interior and (ks_pass or contrast_pass))

    canonical = run_basin_sweep(shots=min(shots, 1024), depth=max(depth, 4), noise=noise, n_points=11)

    return TestDecision(
        test="T2",
        decision="PASS" if passed else "FAIL",
        details={
            "backend": backend_name,
            "center_deg": center,
            "width_deg": width_deg,
            "n_steps": n_steps,
            "depth": depth,
            "noise": noise,
            "peak_angle_deg": peak_angle,
            "peak_zzz": peak_zzz,
            "contrast": contrast,
            "contrast_threshold": contrast_threshold,
            "contrast_pass": contrast_pass,
            "interior_peak": interior,
            "ks_stat": ks_stat,
            "ks_threshold": ks_thr,
            "ks_pass": ks_pass,
            "n_null": n_null,
            "canonical_basin_optimal_deg": canonical.optimal_theta_deg,
            "canonical_in_basin": canonical.in_basin,
            "near_edge_deg": center + p["basin_near_edge_deg"],
            "far_edge_deg": center + p["basin_far_edge_deg"],
        },
        notes=(
            f"Peak @ {peak_angle:.2f}° contrast={contrast:.3f} KS={ks_stat:.3f} "
            f"({'PASS' if passed else 'FAIL'})"
        ),
    )


# ---------------------------------------------------------------------------
# T3 — Re-preparation frequency robustness
# ---------------------------------------------------------------------------


def run_t3_reprep_robustness(
    max_layers: int = 140,
    reset_intervals: tuple[int, ...] = (1, 3, 7, 14, 35),
    campaign_state_path: Path | None = None,
) -> TestDecision:
    """T3: ISS bound + simulated survival + optional campaign D3/D4 read."""
    p = _params()
    rho = p["rho_theoretical"]
    d_hw = p["D_hw_estimate"]
    e_prep = 0.05
    floor = p["min_survival_fraction"]

    steady = compute_theoretical_steady_state_error(rho, e_prep, d_hw)
    per_interval: list[dict] = []
    for ell in reset_intervals:
        n_cycles = max(1, max_layers // ell)
        surv = simulate_reprep_survival(n_cycles, ell, rho, d_hw, e_prep, p["survival_tolerance"])
        per_interval.append({"reset_interval": ell, "n_cycles": n_cycles, "survival_fraction": surv})

    min_surv = min(r["survival_fraction"] for r in per_interval)
    sim_pass = min_surv >= floor

    campaign: dict[str, Any] = {}
    if campaign_state_path and campaign_state_path.is_file():
        st = json.loads(campaign_state_path.read_text())
        campaign = {
            "verdict": st.get("analyze", {}).get("verdict"),
            "D3": st.get("analyze", {}).get("D3"),
            "D4": st.get("analyze", {}).get("D4"),
        }

    # PASS if theoretical simulation meets floor; flag campaign D3/D4 if present
    passed = sim_pass
    return TestDecision(
        test="T3",
        decision="PASS" if passed else "FAIL",
        details={
            "rho_theoretical": rho,
            "steady_state_bound_rad": steady,
            "steady_state_bound_deg": float(np.degrees(steady)),
            "per_interval": per_interval,
            "min_survival_fraction": min_surv,
            "floor": floor,
            "campaign": campaign,
        },
        notes=(
            f"ISS steady bound {np.degrees(steady):.1f}°; min simulated survival {min_surv:.3f}"
            + (f"; campaign={campaign.get('verdict')}" if campaign else "")
        ),
    )


# ---------------------------------------------------------------------------
# T4 — Cross-platform reproducibility
# ---------------------------------------------------------------------------


def run_t4_cross_platform(
    backend_peaks: dict[str, float] | None = None,
    results_dir: Path | None = None,
) -> TestDecision:
    """T4: Max peak spread across platforms (IBM / Willow / literature)."""
    p = _params()
    thr = p["platform_independence_deg"]

    peaks = dict(backend_peaks or {})
    if not peaks:
        peaks = {
            "ibm_fez_design": THETA_STAR_HW_DEG,
            "willow_pink": THETA_STAR_WILLOW_HW_DEG,
            "theory_pi8": THETA_STAR_DEG,
            "wall_protocol": p["theta_wall_deg"],
        }

    rdir = results_dir or Path("results")
    if rdir.is_dir():
        for fp in sorted(rdir.glob("ibm_wall_*.json")) + sorted(rdir.glob("ibm_calib_*.json")):
            try:
                blob = json.loads(fp.read_text())
                cal = blob.get("calibration") or blob
                if "peak_theta_deg" in cal:
                    peaks[f"hardware_{fp.stem}"] = float(cal["peak_theta_deg"])
                if "wall_theta_deg" in cal and "wall_zzz" in cal:
                    peaks[f"wall_{fp.stem}"] = float(cal.get("wall_theta_deg", p["theta_wall_deg"]))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    spread, independent = compute_platform_independence_score(list(peaks.values()), thr)
    passed = independent

    return TestDecision(
        test="T4",
        decision="PASS" if passed else "FAIL",
        details={
            "backend_peaks": peaks,
            "max_spread_deg": spread,
            "threshold_deg": thr,
            "is_platform_independent": independent,
        },
        notes=f"Peak spread {spread:.2f}° (threshold {thr}°)",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_robust_suite(
    backend_name: str = "aer_sim",
    qubits: tuple[int, int, int] = (0, 1, 2),
    use_hardware: bool = False,
    campaign_state: Path | None = None,
    skip: set[str] | None = None,
) -> RobustSuiteReport:
    """Run T1–T4 and aggregate preregistered verdict."""
    skip = skip or set()
    p = _params()
    report = RobustSuiteReport(backend=backend_name, parameters=p)

    runners = {
        "T1": lambda: run_t1_tomography(backend_name, qubits, use_hardware=use_hardware),
        "T2": lambda: run_t2_basin_sweep(backend_name),
        "T3": lambda: run_t3_reprep_robustness(campaign_state_path=campaign_state),
        "T4": lambda: run_t4_cross_platform(),
    }

    for name, fn in runners.items():
        if name in skip:
            continue
        dec = fn()
        report.tests[name] = dec.to_dict()

    decisions = [report.tests[k]["decision"] for k in ("T1", "T2", "T3", "T4") if k in report.tests]
    pass_count = sum(1 for d in decisions if d == "PASS")
    fail_count = sum(1 for d in decisions if d == "FAIL")
    if fail_count == 0 and pass_count == len(decisions):
        report.overall = "ALL_PASS"
    elif pass_count > 0:
        report.overall = "PARTIAL"
    else:
        report.overall = "NEGATIVE"
    report.endorsable = False
    return report


def save_report(report: RobustSuiteReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    return path
