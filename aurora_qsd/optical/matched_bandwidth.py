"""Matched-bandwidth PI vs QSD follow-up.

Hypothesis (gain scaling): the PAT “PI wins” / PLL “QSD wins” split is
because ISS steps k = 1−√ρ *per sample* while PI steps ki·e·dt. Matching
ki·dt = 1−√ρ (and kp = 0) should collapse the gap. QSD decorations
(phase-potential trim, re-lock) are tested by a stripped ISS-only arm.

The v0.1/v0.2 default PI gains are left untouched. This is a new suite.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from aurora_qsd.core.constants import DEFAULT_K_GAIN, DEFAULT_RHO
from aurora_qsd.core.iss import discrete_iss_gain, matched_integrator_ki
from aurora_qsd.optical.channel import TerminalSpec
from aurora_qsd.optical.constants import (
    DEFAULT_JITTER_CORR_S,
    DEFAULT_JITTER_RMS_URAD,
    DEFAULT_LINEWIDTH_HZ,
    DEFAULT_PAT_DT,
    DEFAULT_PLL_DT,
)
from aurora_qsd.optical.pat import PIDController, QSDISSController, colored_jitter
from aurora_qsd.optical.pll import (
    PIPhaseLock,
    QSDPhaseLock,
    _carrier_phase,
    _run_lock,
)
from aurora_qsd.optical.simulate import (
    ScenarioName,
    _geometry_series,
    _run_controller,
)

TIE_FRAC = 0.15  # “tie” if |a-b|/max(b,eps) ≤ 15%


def _pack(tag: str, passed: bool, detail: str) -> dict:
    return {
        "test": tag,
        "passed": bool(passed),
        "verdict": "PASS" if passed else "NULL",
        "detail": detail,
    }


def _rel_gap(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-15)


def _pat_scene(duration_s: float, dt: float, seed: int):
    rng = np.random.default_rng(seed)
    n = int(max(8, round(duration_s / dt)))
    t = np.arange(n) * dt
    spec = TerminalSpec(name="leo-isl-matched")
    geo_list = _geometry_series(ScenarioName.ISL, t, spec, arg_lat0_deg=0.0)
    disturbance = colored_jitter(
        n, dt, DEFAULT_JITTER_RMS_URAD * 1e-6, DEFAULT_JITTER_CORR_S, rng, n_axes=2
    )
    disturbance = disturbance + np.array([50e-6, 0.0]) * np.exp(-t / 0.15)[:, None]
    d_bound = float(np.percentile(np.linalg.norm(np.diff(disturbance, axis=0), axis=1), 95))
    return {
        "t": t,
        "spec": spec,
        "geo_list": geo_list,
        "disturbance": disturbance,
        "fades": np.ones(n),
        "d_bound": d_bound,
        "rng": np.random.default_rng(seed + 17),
    }


def run_matched_pat(
    duration_s: float = 4.0,
    dt: float = DEFAULT_PAT_DT,
    seed: int = 0,
) -> dict:
    rho = DEFAULT_RHO
    k = discrete_iss_gain(rho) * (DEFAULT_K_GAIN / 0.45)
    ki = k / dt
    scene = _pat_scene(duration_s, dt, seed)
    arms = {
        "open": None,
        "pid_orig": PIDController(dt=dt, kp=0.25, ki=60.0),
        "pid_matched": PIDController(dt=dt, kp=0.0, ki=ki),
        "qsd_full": QSDISSController(dt=dt, k_nl=0.04, relock_interval=7),
        "qsd_stripped": QSDISSController(dt=dt, k_nl=0.0, relock_interval=0, relock_extra=0.0),
    }
    runs = {}
    for label, ctrl in arms.items():
        runs[label] = _run_controller(
            label,
            scene["t"],
            scene["geo_list"],
            scene["spec"],
            scene["disturbance"],
            scene["fades"],
            False,
            50.0,
            scene["d_bound"],
            rho,
            np.random.default_rng(seed + 17),
            injected=ctrl,
        )
    q = runs["qsd_full"]
    qs = runs["qsd_stripped"]
    po = runs["pid_orig"]
    pm = runs["pid_matched"]
    gap_orig = _rel_gap(q.mean_err_urad, po.mean_err_urad)
    gap_m = _rel_gap(q.mean_err_urad, pm.mean_err_urad)
    verdicts = {
        "G1_pat_matching_shrinks_gap": _pack(
            "G1",
            gap_m < gap_orig,
            f"PAT |QSD−PI|/PI orig {gap_orig:.3f} → matched {gap_m:.3f} "
            f"(QSD {q.mean_err_urad:.3f}, PI_orig {po.mean_err_urad:.3f}, "
            f"PI_matched {pm.mean_err_urad:.3f} μrad)",
        ),
        "G3_pat_decorations_idle": _pack(
            "G3",
            _rel_gap(q.mean_err_urad, qs.mean_err_urad) <= TIE_FRAC,
            f"PAT QSD full {q.mean_err_urad:.3f} vs stripped {qs.mean_err_urad:.3f} μrad "
            f"(rel gap {_rel_gap(q.mean_err_urad, qs.mean_err_urad):.3f}, tie ≤ {TIE_FRAC})",
        ),
        "G5a_pat_qsd_not_better_than_matched_pi": _pack(
            "G5a",
            q.mean_err_urad >= pm.mean_err_urad * (1.0 - TIE_FRAC),
            f"PAT QSD {q.mean_err_urad:.3f} vs matched-PI {pm.mean_err_urad:.3f} μrad "
            "(PASS if QSD is not >15% better)",
        ),
        "G6a_pat_stripped_ties_matched_pi": _pack(
            "G6a",
            _rel_gap(qs.mean_err_urad, pm.mean_err_urad) <= TIE_FRAC,
            f"PAT stripped ISS {qs.mean_err_urad:.3f} vs matched-PI {pm.mean_err_urad:.3f} μrad "
            f"(rel gap {_rel_gap(qs.mean_err_urad, pm.mean_err_urad):.3f})",
        ),
    }
    return {
        "loop": "pat",
        "dt": dt,
        "k_iss": k,
        "ki_matched": ki,
        "runs": runs,
        "verdicts": verdicts,
    }


def run_matched_pll(
    duration_s: float = 0.15,
    dt: float = DEFAULT_PLL_DT,
    seed: int = 0,
) -> dict:
    rho = DEFAULT_RHO
    k = discrete_iss_gain(rho) * (DEFAULT_K_GAIN / 0.45)
    ki = k / dt
    rng = np.random.default_rng(seed)
    n = int(max(16, round(duration_s / dt)))
    from aurora_qsd.optical.constants import DEFAULT_DOPPLER_FF_RESIDUAL_HZ

    phi = _carrier_phase(n, dt, DEFAULT_LINEWIDTH_HZ, DEFAULT_DOPPLER_FF_RESIDUAL_HZ, rng)
    dphi = np.abs(np.diff(np.unwrap(phi)))
    d_step = float(np.percentile(dphi, 95)) if dphi.size else 0.0
    arms = {
        "open": None,
        "pid_orig": PIPhaseLock(dt=dt, kp=0.35, ki=80.0),
        "pid_matched": PIPhaseLock(dt=dt, kp=0.0, ki=ki),
        "qsd_full": QSDPhaseLock(dt=dt, k_nl=0.04, relock_interval=7),
        "qsd_stripped": QSDPhaseLock(dt=dt, k_nl=0.0, relock_interval=0, relock_extra=0.0),
    }
    runs = {}
    for label, ctrl in arms.items():
        run = _run_lock(label, phi, dt, rho, d_step, 25.0, injected=ctrl)
        run.feedforward = True
        runs[label] = run
    q = runs["qsd_full"]
    qs = runs["qsd_stripped"]
    po = runs["pid_orig"]
    pm = runs["pid_matched"]
    gap_orig = _rel_gap(q.rms_rad, po.rms_rad)
    gap_m = _rel_gap(q.rms_rad, pm.rms_rad)
    # G5: after matching, QSD is not meaningfully better than PI (ratio ≥ 1/1.15)
    not_better = q.rms_rad >= pm.rms_rad * (1.0 - TIE_FRAC)
    verdicts = {
        "G2_pll_matching_shrinks_gap": _pack(
            "G2",
            gap_m < gap_orig,
            f"PLL |QSD−PI|/PI orig {gap_orig:.3f} → matched {gap_m:.3f} "
            f"(QSD {q.rms_rad:.3f}, PI_orig {po.rms_rad:.3f}, "
            f"PI_matched {pm.rms_rad:.3f} rad)",
        ),
        "G4_pll_decorations_idle": _pack(
            "G4",
            _rel_gap(q.rms_rad, qs.rms_rad) <= TIE_FRAC,
            f"PLL QSD full {q.rms_rad:.3f} vs stripped {qs.rms_rad:.3f} rad "
            f"(rel gap {_rel_gap(q.rms_rad, qs.rms_rad):.3f}, tie ≤ {TIE_FRAC})",
        ),
        "G5b_pll_qsd_not_better_than_matched_pi": _pack(
            "G5b",
            not_better,
            f"PLL QSD {q.rms_rad:.3f} vs matched-PI {pm.rms_rad:.3f} rad "
            "(PASS if QSD is not >15% better — the Costas-rate ‘win’ dies)",
        ),
        "G6b_pll_stripped_ties_matched_pi": _pack(
            "G6b",
            _rel_gap(qs.rms_rad, pm.rms_rad) <= TIE_FRAC,
            f"PLL stripped ISS {qs.rms_rad:.3f} vs matched-PI {pm.rms_rad:.3f} rad "
            f"(rel gap {_rel_gap(qs.rms_rad, pm.rms_rad):.3f})",
        ),
    }
    return {
        "loop": "pll",
        "dt": dt,
        "k_iss": k,
        "ki_matched": ki,
        "runs": runs,
        "verdicts": verdicts,
    }


def run_matched_bandwidth_campaign(
    seed: int = 0,
    pat_seconds: float = 4.0,
    pll_seconds: float = 0.15,
) -> dict:
    """Pre-registered G1–G5. PASS = gain-scaling / decorations-idle hypothesis held."""
    pat = run_matched_pat(duration_s=pat_seconds, seed=seed)
    pll = run_matched_pll(duration_s=pll_seconds, seed=seed)
    verdicts = {**pat["verdicts"], **pll["verdicts"]}
    n_pass = sum(1 for v in verdicts.values() if v["passed"])
    notes = (
        f"Matched-bandwidth suite: {n_pass}/8 PASS. "
        f"PAT ki={pat['ki_matched']:.2f} 1/s, PLL ki={pll['ki_matched']:.1f} 1/s "
        f"so ki·dt = 1−√ρ = {pat['k_iss']:.4f}. kp=0 on matched PI. "
        "Hypothesis: the PAT/PLL reversal was gain scaling, not basin geometry."
    )
    return {"pat": pat, "pll": pll, "verdicts": verdicts, "notes": notes}


def write_matched_artifacts(result: dict, out_dir: Path) -> None:
    import csv

    out_dir = Path(out_dir)
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for run in result["pat"]["runs"].values():
        rows.append(
            {
                "loop": "pat",
                "controller": run.name,
                "mean_err_urad": run.mean_err_urad,
                "rms_err_urad": run.rms_err_urad,
                "availability": run.availability,
                "ki_matched": result["pat"]["ki_matched"],
            }
        )
    for run in result["pll"]["runs"].values():
        rows.append(
            {
                "loop": "pll",
                "controller": run.name,
                "rms_rad": run.rms_rad,
                "cycle_slips": run.cycle_slips,
                "mean_bpsk_ber": run.mean_bpsk_ber,
                "ki_matched": result["pll"]["ki_matched"],
            }
        )
    # two schemas — write separate CSVs
    pat_rows = [r for r in rows if r["loop"] == "pat"]
    pll_rows = [r for r in rows if r["loop"] == "pll"]
    with (out_dir / "matched_bandwidth_pat.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pat_rows[0].keys()))
        w.writeheader()
        w.writerows(pat_rows)
    with (out_dir / "matched_bandwidth_pll.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pll_rows[0].keys()))
        w.writeheader()
        w.writerows(pll_rows)
    with (out_dir / "matched_bandwidth_verdicts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["test", "passed", "verdict", "detail"])
        w.writeheader()
        w.writerows(result["verdicts"].values())

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
        order = ["open", "pid_orig", "pid_matched", "qsd_stripped", "qsd_full"]
        colors = {
            "open": "#888888",
            "pid_orig": "#1f77b4",
            "pid_matched": "#5fa8d3",
            "qsd_stripped": "#e07a5f",
            "qsd_full": "#d62728",
        }
        pat_y = [result["pat"]["runs"][k].mean_err_urad for k in order]
        pll_y = [result["pll"]["runs"][k].rms_rad for k in order]
        x = np.arange(len(order))
        axes[0].bar(x, pat_y, color=[colors[k] for k in order])
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(order, rotation=25, ha="right", fontsize=8)
        axes[0].set_ylabel("mean pointing residual (μrad)")
        axes[0].set_title("PAT 500 Hz")
        axes[0].grid(True, axis="y", alpha=0.3)
        axes[1].bar(x, pll_y, color=[colors[k] for k in order])
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(order, rotation=25, ha="right", fontsize=8)
        axes[1].set_ylabel("RMS phase (rad)")
        axes[1].set_title("PLL 20 kHz")
        axes[1].grid(True, axis="y", alpha=0.3)
        fig.suptitle("Matched bandwidth: ki·dt = 1−√ρ, kp = 0", fontsize=11)
        fig.tight_layout()
        fig.savefig(fig_dir / "matched_bandwidth.png", dpi=140)
        plt.close(fig)
    except ImportError:
        print("matplotlib not installed; skipping matched-bandwidth figure")
