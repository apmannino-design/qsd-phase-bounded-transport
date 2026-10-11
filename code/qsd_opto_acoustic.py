"""
Opto-acoustic frequency-matched residual loop.

Photoacoustic plant: pressure tracks I · sin(φ) through a first-order lag.
Sector-bounded QSD update on the relative optical–acoustic phase φ.

    ṗτ = 0.9 I sin(φ) − p + d(t)
    r = p − p_ref
    ΔE = log(1+|r|)
    φ ← clip(φ − K sat_α(r))
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

DT = 0.002
N_STEPS = 3000
TAU = 0.015
I_OPT = 1.0
ETA = 0.9  # photoacoustic conversion factor
P_REF = 0.6
K_GAIN = 3.2
ALPHA = 0.25
PHI_MIN = 0.15
PHI_MAX = np.pi / 2
CORRIDOR = 0.07
NOISE_STD = 0.008  # as written in the sketch (per-step); also offer √DT mode


def sat(x: float, a: float = ALPHA) -> float:
    return float(np.clip(x, -a, a))


def plant_step(
    phi: float,
    intensity: float,
    p: float,
    rng: np.random.Generator,
    noise_mode: str = "raw",
) -> float:
    """Photoacoustic conversion: pressure tracks I * sin(phi)."""
    target = ETA * intensity * np.sin(phi)
    if noise_mode == "sqrt_dt":
        d = NOISE_STD * np.sqrt(DT) * float(rng.standard_normal())
    else:
        d = NOISE_STD * float(rng.standard_normal())
    return float(p + (DT / TAU) * (target - p) + d)


def run_loop(
    seed: int = 1,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    noise_mode: str = "raw",
    phi0: float = 0.8,
    p0: float = 0.3,
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    phi = float(phi0)
    p = float(p0)
    intensity = I_OPT
    log: list[dict[str, float]] = []

    for k in range(n_steps):
        t = k * DT
        p = plant_step(phi, intensity, p, rng, noise_mode=noise_mode)
        residual = p - P_REF
        de = float(np.log1p(np.abs(residual)))
        sat_r = sat(residual)

        if closed_loop:
            # Sector-bounded match on relative phase
            phi = float(np.clip(phi - K_GAIN * sat_r, PHI_MIN, PHI_MAX))

        log.append(
            {
                "t": t,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "p": p,
                "residual": residual,
                "delta_e": de,
                "sat_r": sat_r,
                "target_drive": ETA * intensity * np.sin(phi),
                "I": intensity,
            }
        )

    return log


def compute_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    de = np.array([h["delta_e"] for h in history])
    p = np.array([h["p"] for h in history])
    r = np.array([h["residual"] for h in history])
    phi = np.array([h["phi"] for h in history])
    n_tail = max(1, int(round(1.0 / DT)))  # last 1 s

    return {
        "final_delta_e": float(de[-1]),
        "mean_delta_e_tail": float(de[-n_tail:].mean()),
        "corridor_fraction": float((de < CORRIDOR).mean()),
        "corridor_fraction_tail": float((de[-n_tail:] < CORRIDOR).mean()),
        "final_p": float(p[-1]),
        "final_phi": float(phi[-1]),
        "final_phi_deg": float(np.degrees(phi[-1])),
        "abs_r_mean_tail": float(np.abs(r[-n_tail:]).mean()),
        "p_ref": float(P_REF),
        "k_gain": float(K_GAIN),
        "alpha": float(ALPHA),
        "eta": float(ETA),
    }


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
    params = {
        "DT": DT,
        "N": len(history),
        "tau": TAU,
        "I": I_OPT,
        "eta": ETA,
        "p_ref": P_REF,
        "K": K_GAIN,
        "alpha": ALPHA,
        "corridor": CORRIDOR,
        "noise_std": NOISE_STD,
    }
    summary_path.write_text(
        json.dumps({"summary": summary, "params": params}, indent=2) + "\n",
        encoding="utf-8",
    )

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
        ax[0].set_title("Opto-acoustic matched loop")
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
    csum = compute_metrics(closed)
    osum = compute_metrics(open_)

    sat_vals = np.array([h["sat_r"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12)
    assert csum["corridor_fraction"] > 0.95
    assert csum["abs_r_mean_tail"] < 0.05
    assert abs(csum["final_p"] - P_REF) < 0.05
    assert csum["abs_r_mean_tail"] < osum["abs_r_mean_tail"]

    # Equilibrium identity: η I sin(φ*) = p_ref ⇒ φ* = arcsin(p_ref/(η I))
    phi_star = float(np.arcsin(P_REF / (ETA * I_OPT)))
    phi_tail = float(np.mean([h["phi"] for h in closed[-500:]]))
    assert abs(phi_tail - phi_star) < 0.05

    return {"ok": True, "closed": csum, "open": osum, "phi_star": phi_star}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    print(f"[{label}] Final ΔE: {summary['final_delta_e']:.4f}")
    print(
        f"[{label}] Corridor fraction (ΔE < {CORRIDOR}): "
        f"{summary['corridor_fraction']:.1%}"
    )
    print(
        f"[{label}] Final p / φ: {summary['final_p']:.4f} / "
        f"{summary['final_phi_deg']:.2f}°"
    )
    print(f"[{label}] |r| mean (tail): {summary['abs_r_mean_tail']:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--noise-mode",
        choices=("raw", "sqrt_dt"),
        default="raw",
        help="raw = sketch default; sqrt_dt = Wiener scaling",
    )
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        print(f"φ* (balance): {np.degrees(result['phi_star']):.2f}°")
        return

    history = run_loop(
        seed=args.seed, closed_loop=True, noise_mode=args.noise_mode
    )
    summary = compute_metrics(history)
    print_summary(summary, "closed")
    paths = save_outputs(history, summary, args.out_dir)

    try:
        import shutil

        for dest in (Path("artifacts"), Path("/opt/cursor/artifacts")):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(paths["figure"], dest / "opto_acoustic.png")
    except Exception:
        pass

    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
