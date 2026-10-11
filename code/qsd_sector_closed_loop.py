"""
QSD sector-bounded update for acoustic (near-field plate) force balance.

Implements the classical sketch:

    C(φ) = C₀ sin φ
    τ Ḟ_ac = C(φ) - F_ac + d(t)
    F_net = F_ac - Mg,   r = F_net
    ΔE = log(1 + |r|)
    φ⁺ = clip(φ - K sat_α(r))

with the ISS residual envelope |r_t| ≤ ρ^{t/2}|r_0| + D/(1-√ρ).

Toy illustration of sector-bounded feedback — not a hardware claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

# ---------- parameters ----------
THETA_STAR = np.pi / 8  # design angle (rad); π/8 = 22.5° exactly
ALPHA = 0.15  # sector half-width (rad)
K = 0.8  # feedback gain
RHO = 0.85  # target contraction factor (ISS sketch)
DT = 0.001  # sample period Δt (s)
N_STEPS = 4000  # simulation length
TAU = 0.02  # acoustic force lag (s)
C0 = 1.0  # coupling amplitude
CORRIDOR_GATE = 0.1  # ΔE corridor threshold
PHI_MIN, PHI_MAX = 0.0, np.pi / 2  # clip φ to the coupling branch
MG_BASE = C0 * np.sin(THETA_STAR)  # balanced load at θ*
MG_STEP = 0.15  # load step amplitude (Mg units)
D_NOISE = 0.02  # process-noise std on the force ODE


def load_mg(t: float) -> float:
    """Payload / balance load Mg_k (step during 1–2.5 s)."""
    if 1.0 < t < 2.5:
        return MG_BASE + MG_STEP
    return MG_BASE


def disturbance(t: float, rng: np.random.Generator) -> float:
    """Process disturbance d(t) entering the force ODE."""
    del t
    return D_NOISE * float(rng.standard_normal())


def sat(x: float, alpha: float) -> float:
    """Sector saturation sat_α(·)."""
    return float(np.clip(x, -alpha, alpha))


def coupling(phi: float, c0: float = C0) -> float:
    """C(φ) = C₀ sin φ."""
    return c0 * float(np.sin(phi))


def compute_delta_e(r: float) -> float:
    """ΔE = log(1 + |r|)."""
    return float(np.log1p(np.abs(r)))


def plant_step(f_ac: float, phi: float, d: float) -> float:
    """
    Discrete force update consistent with τ Ḟ_ac = C(φ) - F_ac + d(t):

        F_{k+1} = F_k + (Δt/τ) (C₀ sin φ_{k+1} - F_k + d_k)
    """
    return f_ac + (DT / TAU) * (coupling(phi) - f_ac + d)


def iss_envelope(r0: float, t: np.ndarray, rho: float, d_bound: float) -> np.ndarray:
    """|r_t| ≤ ρ^{t/2}|r_0| + D/(1-√ρ), with t in sample units via t/Δt."""
    sqrt_rho = np.sqrt(rho)
    steps = t / DT
    transient = (rho ** (steps / 2.0)) * abs(r0)
    steady = d_bound / (1.0 - sqrt_rho) if sqrt_rho < 1.0 else np.inf
    return transient + steady


def run_qsd_loop(
    seed: int = 42,
    closed_loop: bool = True,
    n_steps: int = N_STEPS,
    phi0: float | None = None,
) -> list[dict[str, float]]:
    """
    Discrete closed-loop sketch:

        r_k = F_ac,k - Mg_k
        φ_{k+1} = clip(φ_k - K sat_α(r_k))   (held open-loop if disabled)
        F_ac,k+1 = F_ac,k + (Δt/τ)(C₀ sin φ_{k+1} - F_ac,k + d_k)
    """
    rng = np.random.default_rng(seed)
    t = 0.0
    phi = float(THETA_STAR if phi0 is None else phi0)
    f_ac = coupling(phi)  # start near the φ₀ equilibrium force
    log: list[dict[str, float]] = []

    for _ in range(n_steps):
        mg = load_mg(t)
        d = disturbance(t, rng)
        r = f_ac - mg
        delta_e = compute_delta_e(r)
        sat_r = sat(r, ALPHA)

        if closed_loop:
            phi = float(np.clip(phi - K * sat_r, PHI_MIN, PHI_MAX))

        f_ac = plant_step(f_ac, phi, d)

        log.append(
            {
                "t": t,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "f_ac": f_ac,
                "mg": mg,
                "r": r,
                "delta_e": delta_e,
                "d": d,
                "sat_r": sat_r,
                "c_phi": coupling(phi),
            }
        )
        t += DT

    return log


def summarize(history: list[dict[str, float]], tail_s: float = 1.0) -> dict[str, float]:
    """Corridor / ISS-style summary statistics on residual r."""
    r = np.array([h["r"] for h in history])
    delta_e = np.array([h["delta_e"] for h in history])
    phi = np.array([h["phi"] for h in history])
    d = np.array([h["d"] for h in history])

    n_tail = max(1, int(round(tail_s / DT)))
    corridor = delta_e < CORRIDOR_GATE
    r_tail = r[-n_tail:]
    d_bound = float(np.max(np.abs(d)))

    return {
        "theta_star_rad": float(THETA_STAR),
        "theta_star_deg": float(np.degrees(THETA_STAR)),
        "alpha": float(ALPHA),
        "k": float(K),
        "rho": float(RHO),
        "c0": float(C0),
        "mg_base": float(MG_BASE),
        "final_delta_e": float(delta_e[-1]),
        "mean_delta_e_tail": float(delta_e[-n_tail:].mean()),
        "fraction_in_corridor": float(corridor.mean()),
        "fraction_in_corridor_tail": float(corridor[-n_tail:].mean()),
        "final_phi_deg": float(np.degrees(phi[-1])),
        "final_r": float(r[-1]),
        "abs_r_mean_tail": float(np.abs(r_tail).mean()),
        "error_std_tail": float((r_tail - r_tail.mean()).std()),
        "disturbance_bound_obs": d_bound,
        "iss_steady_bound": float(d_bound / (1.0 - np.sqrt(RHO))),
    }


def history_to_arrays(history: list[dict[str, float]]) -> dict[str, np.ndarray]:
    keys = history[0].keys()
    return {k: np.array([h[k] for h in history]) for k in keys}


def save_outputs(
    history: list[dict[str, float]],
    summary: dict[str, float],
    out_dir: Path,
) -> dict[str, Path]:
    """Write CSV, JSON summary, and a time-series figure."""
    out_dir.mkdir(parents=True, exist_ok=True)
    arrays = history_to_arrays(history)

    csv_path = out_dir / "qsd_sector_closed_loop.csv"
    header = ",".join(arrays.keys())
    data = np.column_stack([arrays[k] for k in arrays])
    np.savetxt(csv_path, data, delimiter=",", header=header, comments="")

    summary_path = out_dir / "qsd_sector_closed_loop_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    fig_path = out_dir / "qsd_sector_closed_loop.png"
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(4, 1, figsize=(9, 9), sharex=True)
        axes[0].plot(arrays["t"], arrays["f_ac"], label="F_ac", color="#1f4e5f")
        axes[0].plot(arrays["t"], arrays["mg"], label="Mg", color="#c45c26", ls="--")
        axes[0].set_ylabel("force")
        axes[0].legend(loc="upper right", fontsize=8)
        axes[0].set_title("QSD sector-bounded acoustic force balance (toy)")

        axes[1].plot(arrays["t"], arrays["r"], color="#1f4e5f", label="r = F_ac − Mg")
        axes[1].axhline(0.0, color="#888888", lw=0.8)
        axes[1].set_ylabel("r")
        axes[1].legend(loc="upper right", fontsize=8)

        axes[2].plot(arrays["t"], arrays["delta_e"], color="#1f4e5f", label="ΔE")
        axes[2].axhline(CORRIDOR_GATE, color="#c45c26", ls="--", lw=1, label="corridor")
        axes[2].set_ylabel("ΔE")
        axes[2].legend(loc="upper right", fontsize=8)

        axes[3].plot(arrays["t"], arrays["phi_deg"], color="#1f4e5f", label="φ (deg)")
        axes[3].axhline(
            np.degrees(THETA_STAR), color="#c45c26", ls="--", lw=1, label="θ* = 22.5°"
        )
        axes[3].plot(arrays["t"], arrays["d"], color="#888888", alpha=0.6, label="d")
        axes[3].set_ylabel("φ / d")
        axes[3].set_xlabel("t (s)")
        axes[3].legend(loc="upper right", fontsize=8)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=120)
        plt.close(fig)
    except Exception as exc:  # plotting is optional
        fig_path = out_dir / "qsd_sector_closed_loop_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    """
    Assertions for the φ / F_ac sketch:
    - sector saturation stays inside α
    - closed loop keeps the ΔE corridor on the post-step tail
    - closed-loop tail |r| beats open loop (φ held)
    - θ* = π/8 and Mg_base = C₀ sin θ*
    """
    closed = run_qsd_loop(seed=seed, closed_loop=True, phi0=0.35)
    open_ = run_qsd_loop(seed=seed, closed_loop=False, phi0=0.35)
    closed_sum = summarize(closed)
    open_sum = summarize(open_)

    sat_vals = np.array([h["sat_r"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12), "sector saturation exceeded ALPHA"
    assert closed_sum["fraction_in_corridor_tail"] > 0.5, (
        "closed loop failed to stay in ΔE corridor after load step"
    )
    assert closed_sum["abs_r_mean_tail"] < open_sum["abs_r_mean_tail"], (
        "closed loop did not improve tail |r| vs open loop"
    )
    assert abs(THETA_STAR - np.pi / 8) < 1e-15, "θ* must be π/8 exactly"
    assert abs(MG_BASE - C0 * np.sin(THETA_STAR)) < 1e-12, "Mg_base must equal C₀ sin θ*"

    return {"ok": True, "closed": closed_sum, "open": open_sum}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    print(f"[{label}] θ*               : {summary['theta_star_deg']:.1f}° (π/8)")
    print(f"[{label}] Final ΔE          : {summary['final_delta_e']:.4f}")
    print(f"[{label}] Mean ΔE (last 1 s): {summary['mean_delta_e_tail']:.4f}")
    print(f"[{label}] Fraction in corridor (ΔE<{CORRIDOR_GATE}): {summary['fraction_in_corridor']:.3f}")
    print(f"[{label}] Corridor (tail)   : {summary['fraction_in_corridor_tail']:.3f}")
    print(f"[{label}] Final φ           : {summary['final_phi_deg']:.2f}°")
    print(f"[{label}] Final r           : {summary['final_r']:.4f}")
    print(f"[{label}] |r| mean (tail)   : {summary['abs_r_mean_tail']:.4f}")
    print(f"[{label}] Error std (tail)  : {summary['error_std_tail']:.4f}")
    print(f"[{label}] ISS steady bound  : {summary['iss_steady_bound']:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results"),
        help="Directory for CSV/JSON/PNG outputs",
    )
    parser.add_argument("--self-test", action="store_true", help="Run assertions and exit")
    parser.add_argument(
        "--phi0",
        type=float,
        default=None,
        help="Initial φ (rad); default θ* = π/8",
    )
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    history = run_qsd_loop(seed=args.seed, closed_loop=True, phi0=args.phi0)
    summary = summarize(history)
    print_summary(summary, "closed")
    paths = save_outputs(history, summary, args.out_dir)
    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
