"""
QSD sector-bounded update sketch for simultaneous output-and-match
acoustic (near-field plate) control.

Minimal classical simulation of closed-loop mismatch dynamics under a
sector saturation. This is a toy plant illustration of the paper's
sector-bounded / ISS feedback idea — not a hardware claim.
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
RHO = 0.85  # target contraction factor (reference / ISS sketch)
DT = 0.001  # sample period (s)
N_STEPS = 4000  # simulation length
P_CMD = 1.0  # nominal balance pressure
CORRIDOR_GATE = 0.1  # ΔE corridor threshold
TAU = 0.02  # plant lag (s)
U_MIN, U_MAX = 0.0, 2.0


def disturbance(t: float, rng: np.random.Generator) -> float:
    """Load / disturbance schedule: step + noise."""
    base = 0.0
    if 1.0 < t < 2.5:
        base = 0.25  # load step
    return base + 0.02 * float(rng.standard_normal())


def sat(x: float, alpha: float) -> float:
    """Sector saturation."""
    return float(np.clip(x, -alpha, alpha))


def compute_delta_e(p_meas: float, p_cmd: float, p_ref: float = 1.0) -> float:
    """Nonnegative mismatch proxy used for corridor statistics."""
    r = (p_meas - p_cmd) / p_ref
    return float(np.log1p(np.abs(r)))


def signed_error(p_meas: float, p_cmd: float, p_ref: float = 1.0) -> float:
    """Signed relative pressure residual for negative feedback."""
    return (p_meas - p_cmd) / p_ref


def plant_step(u: float, d: float, state: dict[str, float]) -> float:
    """
    First-order lag with load bias (toy near-field plate).

    Disturbance enters as an equilibrium offset on the drive,
    so a step of size D shifts the free response toward u + D
    rather than integrating an unscaled per-sample kick.
    """
    p = state["p"]
    p_new = p + (DT / TAU) * ((u + d) - p)
    state["p"] = p_new
    return p_new


def iss_envelope(e0: float, t: np.ndarray, rho: float, d_bound: float) -> np.ndarray:
    """
    Crude ISS-style residual envelope (Theorem 6 sketch):
        |e_t| ≤ ρ^{t/2} |e_0| + D / (1 - √ρ)
    Time is mapped in sample units via t / DT for the discrete exponent.
    """
    sqrt_rho = np.sqrt(rho)
    steps = t / DT
    transient = (rho ** (steps / 2.0)) * abs(e0)
    steady = d_bound / (1.0 - sqrt_rho) if sqrt_rho < 1.0 else np.inf
    return transient + steady


def run_qsd_loop(
    seed: int = 42,
    closed_loop: bool = True,
    n_steps: int = N_STEPS,
) -> list[dict[str, float]]:
    """Simulate toy plant with optional sector-bounded feedback."""
    rng = np.random.default_rng(seed)
    t = 0.0
    state = {"p": 0.0}
    u = 0.0
    log: list[dict[str, float]] = []

    for _ in range(n_steps):
        d = disturbance(t, rng)
        p_meas = plant_step(u, d, state)
        delta_e = compute_delta_e(p_meas, P_CMD)
        e = signed_error(p_meas, P_CMD)

        if closed_loop:
            # Sector-bounded update (negative feedback through sat)
            u = u - K * sat(e, ALPHA)
            u = float(np.clip(u, U_MIN, U_MAX))

        log.append(
            {
                "t": t,
                "u": u,
                "p_meas": p_meas,
                "delta_e": delta_e,
                "e": e,
                "d": d,
                "sat_e": sat(e, ALPHA),
            }
        )
        t += DT

    return log


def summarize(history: list[dict[str, float]], tail_s: float = 1.0) -> dict[str, float]:
    """Corridor / ISS-style summary statistics."""
    t = np.array([h["t"] for h in history])
    delta_e = np.array([h["delta_e"] for h in history])
    e = np.array([h["e"] for h in history])
    u = np.array([h["u"] for h in history])
    d = np.array([h["d"] for h in history])

    n_tail = max(1, int(round(tail_s / DT)))
    corridor = delta_e < CORRIDOR_GATE
    e_tail = e[-n_tail:]
    e_tail_centered = e_tail - e_tail.mean()
    d_bound = float(np.max(np.abs(d)))

    return {
        "theta_star_rad": float(THETA_STAR),
        "theta_star_deg": float(np.degrees(THETA_STAR)),
        "alpha": float(ALPHA),
        "k": float(K),
        "rho": float(RHO),
        "final_delta_e": float(delta_e[-1]),
        "mean_delta_e_tail": float(delta_e[-n_tail:].mean()),
        "fraction_in_corridor": float(corridor.mean()),
        "fraction_in_corridor_tail": float(corridor[-n_tail:].mean()),
        "final_u": float(u[-1]),
        "error_std_tail": float(e_tail_centered.std()),
        "abs_error_mean_tail": float(np.abs(e_tail).mean()),
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
    """Write CSV, JSON summary, and a simple time-series figure."""
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

        fig, axes = plt.subplots(3, 1, figsize=(9, 7), sharex=True)
        axes[0].plot(arrays["t"], arrays["p_meas"], label="p_meas", color="#1f4e5f")
        axes[0].axhline(P_CMD, color="#c45c26", ls="--", lw=1, label="p_cmd")
        axes[0].set_ylabel("pressure")
        axes[0].legend(loc="upper right", fontsize=8)
        axes[0].set_title("QSD sector-bounded closed loop (toy acoustic plant)")

        axes[1].plot(arrays["t"], arrays["delta_e"], color="#1f4e5f", label="ΔE")
        axes[1].axhline(CORRIDOR_GATE, color="#c45c26", ls="--", lw=1, label="corridor")
        axes[1].set_ylabel("ΔE")
        axes[1].legend(loc="upper right", fontsize=8)

        axes[2].plot(arrays["t"], arrays["u"], color="#1f4e5f", label="u")
        axes[2].plot(arrays["t"], arrays["d"], color="#888888", alpha=0.7, label="d")
        axes[2].set_ylabel("u / d")
        axes[2].set_xlabel("t (s)")
        axes[2].legend(loc="upper right", fontsize=8)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=120)
        plt.close(fig)
    except Exception as exc:  # plotting is optional
        fig_path = out_dir / "qsd_sector_closed_loop_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    """
    Lightweight assertions for the toy loop:
    - closed loop recovers into corridor after the load step ends
    - closed-loop tail mismatch beats open loop
    - sector saturation never exceeds ALPHA
    """
    closed = run_qsd_loop(seed=seed, closed_loop=True)
    open_ = run_qsd_loop(seed=seed, closed_loop=False)
    closed_sum = summarize(closed)
    open_sum = summarize(open_)

    sat_vals = np.array([h["sat_e"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12), "sector saturation exceeded ALPHA"
    assert closed_sum["fraction_in_corridor_tail"] > 0.5, (
        "closed loop failed to stay in ΔE corridor after disturbance"
    )
    assert closed_sum["mean_delta_e_tail"] < open_sum["mean_delta_e_tail"], (
        "closed loop did not improve tail ΔE vs open loop"
    )
    assert abs(THETA_STAR - np.pi / 8) < 1e-15, "θ* must be π/8 exactly"

    return {
        "ok": True,
        "closed": closed_sum,
        "open": open_sum,
    }


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    print(f"[{label}] θ*               : {summary['theta_star_deg']:.1f}° (π/8)")
    print(f"[{label}] Final ΔE          : {summary['final_delta_e']:.4f}")
    print(f"[{label}] Mean ΔE (last 1 s): {summary['mean_delta_e_tail']:.4f}")
    print(f"[{label}] Fraction in corridor (ΔE<{CORRIDOR_GATE}): {summary['fraction_in_corridor']:.3f}")
    print(f"[{label}] Corridor (tail)   : {summary['fraction_in_corridor_tail']:.3f}")
    print(f"[{label}] Final drive u     : {summary['final_u']:.3f}")
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
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    np_history = run_qsd_loop(seed=args.seed, closed_loop=True)
    summary = summarize(np_history)
    print_summary(summary, "closed")
    paths = save_outputs(np_history, summary, args.out_dir)
    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
