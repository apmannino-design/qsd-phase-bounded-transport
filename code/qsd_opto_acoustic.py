"""
Opto-acoustic frequency-matched residual loop (uses qsd_control_core).

Photoacoustic plant: pressure tracks η I sin(φ) through a first-order lag.
Sector-bounded QSD update on relative optical–acoustic phase φ (DT-scaled).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qsd_control_core import (  # noqa: E402
    SensorModel,
    Scorecard,
    delta_e,
    diverged_from_series,
    dt_step,
    rms,
    sat,
    wiener_noise,
)

DT = 0.002
N_STEPS = 3000
TAU = 0.015
I_OPT = 1.0
ETA = 0.9
P_REF = 0.6
# Preserve prior per-step gain 3.2 as a rate: 3.2 / DT
K_PHI_RATE = 3.2 / DT
ALPHA = 0.25
PHI_MIN = 0.15
PHI_MAX = np.pi / 2
CORRIDOR = 0.07
NOISE_STD = 0.008 / np.sqrt(DT)  # match prior raw-step intensity under √DT rule


def plant_step(
    phi: float,
    intensity: float,
    p: float,
    rng: np.random.Generator,
) -> float:
    target = ETA * intensity * np.sin(phi)
    d = wiener_noise(rng, NOISE_STD, DT)
    return float(p + (DT / TAU) * (target - p) + d)


def run_loop(
    seed: int = 1,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    rich_sensing: bool = True,
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    phi = 0.8
    p = 0.3
    # Mild sensing imperfections (noise_std is per-sample σ, not √dt Wiener).
    # Keep τ ≲ DT so the stiff K_PHI_RATE loop stays well damped.
    sensor = SensorModel(
        tau_s=0.001 if rich_sensing else 0.0,
        bias=0.002 if rich_sensing else 0.0,
        dropout_prob=0.005 if rich_sensing else 0.0,
        noise_std=1e-4 if rich_sensing else 0.0,
    )
    sensor.reset(p)
    log: list[dict[str, float]] = []

    for k in range(n_steps):
        t = k * DT
        p = plant_step(phi, I_OPT, p, rng)
        p_meas = sensor.measure(p, DT, rng)
        if np.isnan(p_meas):
            p_meas = p  # should not happen with hold_on_dropout

        residual = p_meas - P_REF
        de = delta_e(residual, scale=1.0)
        e = sat(residual, ALPHA)

        if closed_loop:
            # DT-scaled sector update (negative feedback on pressure error)
            phi = dt_step(phi, -K_PHI_RATE * e, DT, PHI_MIN, PHI_MAX)

        log.append(
            {
                "t": t,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "p": p,
                "p_meas": p_meas,
                "residual": residual,
                "delta_e": de,
                "sat_e": e,
                "target_drive": ETA * I_OPT * np.sin(phi),
            }
        )
    return log


def compute_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    de = np.array([h["delta_e"] for h in history])
    r = np.array([h["residual"] for h in history])
    p = np.array([h["p"] for h in history])
    n_tail = max(1, int(round(1.0 / DT)))
    return {
        "final_delta_e": float(de[-1]),
        "mean_delta_e_tail": float(de[-n_tail:].mean()),
        "corridor_fraction": float((de < CORRIDOR).mean()),
        "abs_r_mean_tail": float(np.abs(r[-n_tail:]).mean()),
        "track_rms": rms(r[-n_tail:]),
        "final_p": float(p[-1]),
        "final_phi": float(history[-1]["phi"]),
        "diverged": diverged_from_series(r, bound=0.5),
    }


def make_scorecard(
    closed: list[dict[str, float]], open_: list[dict[str, float]]
) -> Scorecard:
    c = compute_metrics(closed)
    o = compute_metrics(open_)
    return Scorecard(
        demo="opto_acoustic",
        lock_in=True,  # single-loop match; "locked" when in corridor
        time_to_lock_s=float(
            next(
                (h["t"] for h in closed if h["delta_e"] < CORRIDOR),
                float("nan"),
            )
        ),
        corridor_fraction=c["corridor_fraction"],
        hold_or_track_rms=c["track_rms"],
        open_loop_rms=o["track_rms"],
        final_delta_e=c["final_delta_e"],
        diverged=c["diverged"],
        notes="DT-scaled φ rate + sensor lag/bias/dropout",
        extras=c,
    )


def save_outputs(
    history: list[dict[str, float]],
    summary: dict[str, Any],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = list(history[0].keys())
    data = np.column_stack([[row[k] for row in history] for k in keys])
    csv_path = out_dir / "qsd_opto_acoustic.csv"
    np.savetxt(csv_path, data, delimiter=",", header=",".join(keys), comments="")
    summary_path = out_dir / "qsd_opto_acoustic_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    fig_path = out_dir / "qsd_opto_acoustic.png"
    try:
        import matplotlib.pyplot as plt

        t = np.array([h["t"] for h in history])
        de = np.array([h["delta_e"] for h in history])
        phi = np.array([h["phi"] for h in history])
        p = np.array([h["p"] for h in history])
        fig, ax = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        ax[0].plot(t, de, lw=1.3)
        ax[0].axhline(CORRIDOR, color="r", ls="--")
        ax[0].set_ylabel(r"$\Delta E$")
        ax[0].set_title("Opto-acoustic matched loop (core)")
        ax[0].grid(alpha=0.3)
        ax[1].plot(t, phi, color="orange", lw=1.3)
        ax[1].set_ylabel(r"$\phi$")
        ax[1].grid(alpha=0.3)
        ax[2].plot(t, p, color="green", lw=1.3, label="p")
        ax[2].axhline(P_REF, color="k", ls="--", label="target")
        ax[2].set_ylabel("Pressure")
        ax[2].set_xlabel("Time (s)")
        ax[2].legend()
        ax[2].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_opto_acoustic_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")
    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 1) -> dict[str, Any]:
    closed = run_loop(seed=seed, closed_loop=True)
    open_ = run_loop(seed=seed, closed_loop=False)
    c = compute_metrics(closed)
    o = compute_metrics(open_)
    assert c["corridor_fraction"] > 0.9
    assert c["track_rms"] < o["track_rms"]
    assert not c["diverged"]
    phi_star = float(np.arcsin(P_REF / (ETA * I_OPT)))
    phi_tail = float(np.mean([h["phi"] for h in closed[-500:]]))
    assert abs(phi_tail - phi_star) < 0.1
    return {"ok": True, "closed": c, "open": o, "scorecard": make_scorecard(closed, open_)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print(result["scorecard"].row())
        return

    closed = run_loop(seed=args.seed, closed_loop=True)
    open_ = run_loop(seed=args.seed, closed_loop=False)
    card = make_scorecard(closed, open_)
    summary = {"summary": card.to_dict(), "metrics": compute_metrics(closed)}
    print(card.row())
    paths = save_outputs(closed, summary, args.out_dir)
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
