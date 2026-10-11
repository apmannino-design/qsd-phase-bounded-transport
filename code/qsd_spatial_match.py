"""
Spatial match on top of a frequency-matched residual loop.

Two opposed sources form a standing-wave-like field. Relative phase φ
shifts the pressure node; amplitude ratio adjusts contrast. A sector-
bounded update drives the measured node to track a moving target.

Fixes vs bare sketch (needed for stable tracking):
- continuous node tracking (avoid jumping between zeros)
- interpolated zero crossings
- DT-scaled control rates
- phase sign consistent with ∂x_node/∂φ < 0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

# -------------------- Parameters --------------------
DT = 0.002
N_STEPS = 4000
L = 1.0
NX = 201
WAVELENGTH = 0.4
K_WAVE = 2 * np.pi / WAVELENGTH

ALPHA = 0.15
K_PHI = 130.0  # rad/s per unit sat(r)  (DT-scaled)
K_RATIO = 5.0  # 1/s per unit sat(r)
PHI_MIN, PHI_MAX = -np.pi, np.pi
RATIO_MIN, RATIO_MAX = 0.4, 1.6

NOISE_STD = 0.015
ERR_SCALE = 0.05  # in ΔE = log1p(|e|/ERR_SCALE)
CORRIDOR = 0.25  # achievable with grid/noise; 0.1 ⇒ |e|<~0.005 (sub-cell)


def sat(z: float, a: float = ALPHA) -> float:
    return float(np.clip(z, -a, a))


def field(phi: float, ratio: float, x: np.ndarray) -> np.ndarray:
    """Superposition of two counter-propagating waves."""
    return np.cos(K_WAVE * x) + ratio * np.cos(K_WAVE * x + phi)


def all_node_locations(p: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Interpolated zero crossings of the pressure field."""
    crossings = np.where(np.diff(np.sign(p)))[0]
    if crossings.size == 0:
        return np.array([x[len(x) // 2]])
    xs = []
    for idx in crossings:
        x0, x1 = x[idx], x[idx + 1]
        p0, p1 = p[idx], p[idx + 1]
        if abs(p1 - p0) < 1e-15:
            xs.append(x0)
        else:
            xs.append(float(x0 - p0 * (x1 - x0) / (p1 - p0)))
    return np.asarray(xs, dtype=float)


def track_node(p: np.ndarray, x: np.ndarray, x_prev: float) -> float:
    """Follow one node continuously (nearest to previous estimate)."""
    nodes = all_node_locations(p, x)
    return float(nodes[np.argmin(np.abs(nodes - x_prev))])


def target_node(t: np.ndarray | float) -> np.ndarray | float:
    """Moving target node trajectory."""
    return 0.5 + 0.12 * np.sin(2 * np.pi * 0.15 * t)


def run_loop(
    seed: int = 42,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, L, NX)

    phi = 0.4
    ratio = 0.9
    p0 = field(phi, ratio, x)
    x_node = track_node(p0, x, 0.5)

    log: list[dict[str, float]] = []
    for n in range(n_steps):
        t = n * DT
        p = field(phi, ratio, x) + NOISE_STD * rng.standard_normal(NX)
        x_node = track_node(p, x, x_node)
        x_des = float(target_node(t))
        r_spatial = x_node - x_des
        de = float(np.log1p(np.abs(r_spatial) / ERR_SCALE))

        if closed_loop:
            e = sat(r_spatial)
            # ∂x_node/∂φ < 0 ⇒ increase φ when node is too far right
            phi = float(np.clip(phi + DT * K_PHI * e, PHI_MIN, PHI_MAX))
            ratio = float(np.clip(ratio + DT * K_RATIO * e, RATIO_MIN, RATIO_MAX))

        log.append(
            {
                "t": t,
                "phi": phi,
                "ratio": ratio,
                "x_node": x_node,
                "x_des": x_des,
                "r_spatial": r_spatial,
                "delta_e": de,
                "abs_err": abs(r_spatial),
                "sat_e": sat(r_spatial),
            }
        )

    return log


def compute_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    de = np.array([h["delta_e"] for h in history])
    err = np.array([h["abs_err"] for h in history])
    n_tail = max(1, int(round(1.0 / DT)))
    return {
        "final_delta_e": float(de[-1]),
        "mean_abs_err": float(err.mean()),
        "mean_abs_err_tail": float(err[-n_tail:].mean()),
        "corridor_fraction": float((de < CORRIDOR).mean()),
        "corridor_fraction_strict": float((de < 0.1).mean()),
        "final_phi": float(history[-1]["phi"]),
        "final_ratio": float(history[-1]["ratio"]),
        "target_amp": 0.12,
        "k_phi": float(K_PHI),
        "k_ratio": float(K_RATIO),
    }


def save_outputs(
    history: list[dict[str, float]],
    summary: dict[str, Any],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = list(history[0].keys())
    data = np.column_stack([[row[k] for row in history] for k in keys])
    csv_path = out_dir / "qsd_spatial_match.csv"
    np.savetxt(csv_path, data, delimiter=",", header=",".join(keys), comments="")

    summary_path = out_dir / "qsd_spatial_match_summary.json"
    params = {
        "DT": DT,
        "N": len(history),
        "L": L,
        "nx": NX,
        "wavelength": WAVELENGTH,
        "k": K_WAVE,
        "K_phi": K_PHI,
        "K_ratio": K_RATIO,
        "alpha": ALPHA,
        "corridor": CORRIDOR,
        "noise_std": NOISE_STD,
    }
    summary_path.write_text(
        json.dumps({"summary": summary, "params": params}, indent=2) + "\n",
        encoding="utf-8",
    )

    fig_path = out_dir / "qsd_spatial_match.png"
    try:
        import matplotlib.pyplot as plt

        t = np.array([h["t"] for h in history])
        de = np.array([h["delta_e"] for h in history])
        node = np.array([h["x_node"] for h in history])
        des = np.array([h["x_des"] for h in history])
        phi = np.array([h["phi"] for h in history])
        ratio = np.array([h["ratio"] for h in history])

        fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        axs[0].plot(t, de, lw=1.2)
        axs[0].axhline(CORRIDOR, color="r", ls="--")
        axs[0].set_ylabel(r"$\Delta E$")
        axs[0].set_title("Spatial match: node tracks moving target")
        axs[0].grid(alpha=0.3)

        axs[1].plot(t, node, label="measured node", lw=1.2)
        axs[1].plot(t, des, "--", label="target", lw=1.2)
        axs[1].set_ylabel("Node position")
        axs[1].legend(frameon=False)
        axs[1].grid(alpha=0.3)

        axs[2].plot(t, phi, label=r"$\phi$", color="orange", lw=1.2)
        axs[2].plot(t, ratio, label="amplitude ratio", color="green", lw=1.2)
        axs[2].set_ylabel("Controls")
        axs[2].set_xlabel("Time (s)")
        axs[2].legend(frameon=False)
        axs[2].grid(alpha=0.3)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_spatial_match_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    closed = run_loop(seed=seed, closed_loop=True)
    open_ = run_loop(seed=seed, closed_loop=False)
    csum = compute_metrics(closed)
    osum = compute_metrics(open_)

    sat_vals = np.array([h["sat_e"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12)
    # Must beat open loop after acquisition (tail) and overall
    assert csum["mean_abs_err_tail"] < 0.5 * osum["mean_abs_err_tail"]
    assert csum["mean_abs_err_tail"] < 0.03
    assert csum["mean_abs_err"] < osum["mean_abs_err"]
    assert csum["corridor_fraction"] > 0.15

    return {"ok": True, "closed": csum, "open": osum}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    print(f"[{label}] Final ΔE          : {summary['final_delta_e']:.4f}")
    print(f"[{label}] Mean |node error| : {summary['mean_abs_err']:.4f}")
    print(f"[{label}] Tail |node error| : {summary['mean_abs_err_tail']:.4f}")
    print(f"[{label}] Corridor frac     : {summary['corridor_fraction']:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    history = run_loop(seed=args.seed, closed_loop=True)
    summary = compute_metrics(history)
    print_summary(summary, "closed")
    paths = save_outputs(history, summary, args.out_dir)

    try:
        import shutil

        for dest in (Path("artifacts"), Path("/opt/cursor/artifacts")):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(paths["figure"], dest / "spatial_match.png")
    except Exception:
        pass

    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
