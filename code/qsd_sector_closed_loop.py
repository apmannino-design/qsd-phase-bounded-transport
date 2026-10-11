"""
QSD sector-bounded control on a near-field acoustic levitation (NFAL) plate.

Physics (Lee–Wang / Chu–Apfel near-field squeeze film):
    p̄ = γ(γ+1)/8 · (a_eff² p₀) / h²
    a_eff = a_max sin φ          # match / coupling angle
    F_ac = p̄ · A
    m ḧ = F_ac − m g − b ḣ     # vertical plate dynamics

Because a free plate passively seeks F≈mg by changing h, the controlled
"output" residual is the gap error (levitation height), while φ is the
match/coupling actuator:

    e_h = (h − h*) / h*
    ΔE  = log(1 + |e_h|)
    φ⁺  = clip(φ − K sat_α(e_h))

Scientific reduced-order control study — not a hardware endorsement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nfal_physics import (  # noqa: E402
    G,
    NFALParams,
    acoustic_force_n,
    balanced_params,
    equilibrium_gap,
    squeeze_number,
)


def sat(x: float, alpha: float) -> float:
    return float(np.clip(x, -alpha, alpha))


def compute_delta_e(e_h: float) -> float:
    return float(np.log1p(np.abs(e_h)))


def mass_schedule(t: float, params: NFALParams) -> float:
    if 1.0 < t < 2.5:
        return params.mass_kg + params.mass_step_kg
    return params.mass_kg


def run_nfal_loop(
    params: NFALParams | None = None,
    seed: int = 42,
    closed_loop: bool = True,
    t_final: float = 4.0,
    phi0: float | None = None,
) -> list[dict[str, float]]:
    """Integrate NFAL plate dynamics + sector-bounded φ (height regulation)."""
    p = params or balanced_params()
    rng = np.random.default_rng(seed)

    dt = p.dt_s
    n_steps = int(round(t_final / dt))
    phi = float(p.theta_star if phi0 is None else phi0)

    # Start near the φ₀ open-loop equilibrium, then close the loop on h*.
    h = float(np.clip(equilibrium_gap(p, phi, p.mass_kg), 2.0 * p.a_max, 5e-3))
    v = 0.0
    f_hat = acoustic_force_n(p, h, phi)
    t = 0.0
    log: list[dict[str, float]] = []

    for _ in range(n_steps):
        mass = mass_schedule(t, p)
        weight = mass * G

        f_true = acoustic_force_n(p, h, phi) + p.force_noise_std_n * float(
            rng.standard_normal()
        )
        f_hat = f_hat + (dt / p.tau_force_s) * (f_true - f_hat)

        e_h = (h - p.h_star) / p.h_star
        delta_e = compute_delta_e(e_h)
        sat_e = sat(e_h, p.alpha)
        r_force = f_hat - weight

        if closed_loop:
            # h > h* ⇒ reduce coupling angle; h < h* ⇒ increase φ
            phi = float(np.clip(phi - p.k_gain * sat_e, p.phi_min, p.phi_max))

        acc = (f_true - weight - p.damping_ns_m * v) / mass
        v = v + dt * acc
        h = h + dt * v
        h = float(np.clip(h, 1.5 * p.a_max, 5e-3))
        if h <= 1.5 * p.a_max and v < 0.0:
            v = 0.0

        log.append(
            {
                "t": t,
                "h_um": h * 1e6,
                "h_m": h,
                "v": v,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "f_true": f_true,
                "f_hat": f_hat,
                "mg": weight,
                "mass_g": mass * 1e3,
                "e_h": e_h,
                "r_force": r_force,
                "delta_e": delta_e,
                "sat_e": sat_e,
                "a_eff_um": p.a_max * float(np.sin(phi)) * 1e6,
                "squeeze_number": squeeze_number(p, h),
                "p_bar_kpa": (f_true / p.area) / 1000.0,
            }
        )
        t += dt

    return log


def summarize(history: list[dict[str, float]], params: NFALParams) -> dict[str, float]:
    dt = params.dt_s
    n_tail = max(1, int(round(1.0 / dt)))
    # mass-step window
    t = np.array([row["t"] for row in history])
    step = (t > 1.0) & (t < 2.5)

    delta_e = np.array([row["delta_e"] for row in history])
    e_h = np.array([row["e_h"] for row in history])
    h_um = np.array([row["h_um"] for row in history])
    phi_deg = np.array([row["phi_deg"] for row in history])
    sigma = np.array([row["squeeze_number"] for row in history])
    corridor = delta_e < params.corridor_gate

    return {
        "theta_star_deg": float(np.degrees(params.theta_star)),
        "a_max_um": float(params.a_max * 1e6),
        "h_star_um": float(params.h_star * 1e6),
        "mass_g": float(params.mass_kg * 1e3),
        "freq_khz": float(params.freq_hz / 1e3),
        "final_delta_e": float(delta_e[-1]),
        "mean_delta_e_tail": float(delta_e[-n_tail:].mean()),
        "mean_delta_e_step": float(delta_e[step].mean()) if step.any() else float("nan"),
        "fraction_in_corridor": float(corridor.mean()),
        "fraction_in_corridor_tail": float(corridor[-n_tail:].mean()),
        "fraction_in_corridor_step": float(corridor[step].mean()) if step.any() else float("nan"),
        "final_phi_deg": float(phi_deg[-1]),
        "final_h_um": float(h_um[-1]),
        "mean_h_um_tail": float(h_um[-n_tail:].mean()),
        "mean_h_um_step": float(h_um[step].mean()) if step.any() else float("nan"),
        "abs_eh_mean_tail": float(np.abs(e_h[-n_tail:]).mean()),
        "abs_eh_mean_step": float(np.abs(e_h[step]).mean()) if step.any() else float("nan"),
        "mean_squeeze_number": float(sigma.mean()),
        "min_squeeze_number": float(sigma.min()),
    }


def history_to_arrays(history: list[dict[str, float]]) -> dict[str, np.ndarray]:
    keys = history[0].keys()
    return {k: np.array([row[k] for row in history]) for k in keys}


def save_outputs(
    history: list[dict[str, float]],
    summary: dict[str, Any],
    params: NFALParams,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    arrays = history_to_arrays(history)

    csv_path = out_dir / "qsd_sector_closed_loop.csv"
    header = ",".join(arrays.keys())
    data = np.column_stack([arrays[k] for k in arrays])
    np.savetxt(csv_path, data, delimiter=",", header=header, comments="")

    payload = {"summary": summary, "params": params.to_dict()}
    summary_path = out_dir / "qsd_sector_closed_loop_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    fig_path = out_dir / "qsd_sector_closed_loop.png"
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(4, 1, figsize=(9, 9), sharex=True)
        axes[0].plot(arrays["t"], arrays["h_um"], color="#1f4e5f", label="h")
        axes[0].axhline(params.h_star * 1e6, color="#c45c26", ls="--", lw=1, label="h*")
        axes[0].set_ylabel("gap (μm)")
        axes[0].legend(loc="upper right", fontsize=8)
        axes[0].set_title(
            "NFAL physics + QSD sector height regulation "
            f"(f={params.freq_hz/1e3:.0f} kHz, m={params.mass_kg*1e3:.0f} g)"
        )

        axes[1].plot(arrays["t"], arrays["f_hat"] * 1e3, color="#1f4e5f", label="F̂")
        axes[1].plot(arrays["t"], arrays["mg"] * 1e3, color="#c45c26", ls="--", label="mg")
        axes[1].set_ylabel("force (mN)")
        axes[1].legend(loc="upper right", fontsize=8)

        axes[2].plot(arrays["t"], arrays["delta_e"], color="#1f4e5f", label="ΔE")
        axes[2].axhline(
            params.corridor_gate, color="#c45c26", ls="--", lw=1, label="corridor"
        )
        axes[2].set_ylabel("ΔE")
        axes[2].legend(loc="upper right", fontsize=8)

        axes[3].plot(arrays["t"], arrays["phi_deg"], color="#1f4e5f", label="φ (deg)")
        axes[3].axhline(
            np.degrees(params.theta_star),
            color="#c45c26",
            ls="--",
            lw=1,
            label="θ* = 22.5°",
        )
        axes[3].set_ylabel("φ (deg)")
        axes[3].set_xlabel("t (s)")
        axes[3].legend(loc="upper right", fontsize=8)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=120)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_sector_closed_loop_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    p = balanced_params()

    # Design identity: Lee–Wang force at (h*, θ*) equals payload weight.
    f_star = acoustic_force_n(p, p.h_star, p.theta_star)
    assert abs(f_star - p.mass_kg * G) / (p.mass_kg * G) < 1e-9

    # NFAL regime check at the design gap.
    assert squeeze_number(p, p.h_star) > 10.0

    closed = run_nfal_loop(p, seed=seed, closed_loop=True, phi0=0.30)
    open_ = run_nfal_loop(p, seed=seed, closed_loop=False, phi0=0.30)
    csum = summarize(closed, p)
    osum = summarize(open_, p)

    sat_vals = np.array([row["sat_e"] for row in closed])
    assert np.all(np.abs(sat_vals) <= p.alpha + 1e-12)
    assert csum["fraction_in_corridor_tail"] > 0.7
    # Closed loop should hold h* through the mass step better than open loop.
    assert csum["abs_eh_mean_step"] < 0.5 * osum["abs_eh_mean_step"]
    assert abs(p.theta_star - np.pi / 8) < 1e-15

    return {"ok": True, "closed": csum, "open": osum, "params": p.to_dict()}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    print(
        f"[{label}] f / a_max / h*  : {summary['freq_khz']:.0f} kHz, "
        f"{summary['a_max_um']:.2f} μm, {summary['h_star_um']:.1f} μm"
    )
    print(f"[{label}] mass            : {summary['mass_g']:.1f} g")
    print(f"[{label}] Final ΔE        : {summary['final_delta_e']:.4f}")
    print(f"[{label}] Mean ΔE (tail)  : {summary['mean_delta_e_tail']:.4f}")
    print(f"[{label}] Mean ΔE (step)  : {summary['mean_delta_e_step']:.4f}")
    print(f"[{label}] Corridor (tail) : {summary['fraction_in_corridor_tail']:.3f}")
    print(f"[{label}] Corridor (step) : {summary['fraction_in_corridor_step']:.3f}")
    print(
        f"[{label}] Final φ / h     : {summary['final_phi_deg']:.2f}°, "
        f"{summary['final_h_um']:.1f} μm"
    )
    print(f"[{label}] |e_h| mean step : {summary['abs_eh_mean_step']:.4f}")
    print(f"[{label}] ⟨σ⟩ squeeze     : {summary['mean_squeeze_number']:.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--phi0", type=float, default=0.30, help="initial φ (rad)")
    parser.add_argument("--t-final", type=float, default=4.0)
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    params = balanced_params()
    history = run_nfal_loop(
        params, seed=args.seed, closed_loop=True, t_final=args.t_final, phi0=args.phi0
    )
    summary = summarize(history, params)
    print_summary(summary, "closed")
    paths = save_outputs(history, summary, params, args.out_dir)
    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
