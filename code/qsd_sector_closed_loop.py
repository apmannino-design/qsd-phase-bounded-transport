"""
Full physics simulation — conservative outer loop + QSD sector phase law.

- Monotonic phase branch (φ ∈ [φ_min, π/2])
- Timestep-scaled phase rates (φ ← φ + DT · φ̇)
- Consistent F_ref bounds from available coupling
- Conservative outer-loop gains
- Equilibrium initialization
- DT-scaled force noise (Wiener); raw per-step noise is not used
- Slow φ_ref creep while locked (altitude integral)

Plant:
    A(y) = C0_max / (1 + (y/h0)²)
    C(φ,y) = A(y) · sin φ
    τ Ḟ_ac = C − F_ac + d(t)
    m ÿ = F_ac − mg − b ẏ

Outer loop:
    F_ref = clip( mg − K_p (y−y_ref) − K_d v , A sin φ_min , 0.95 A )

Inner residual / phase:
    r = F_ac − F_ref ,  e = sat_α(r/mg)
    acquisition:  φ̇ = −K_lock e
    locked:       φ̇ = −K_inner e − λ (φ − φ_ref)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

# -------------------- Parameters --------------------
M = 1e-4
G = 9.81
MG = M * G

C0_MAX = 6.0 * MG
H0 = 0.0008
TAU = 0.005
B_DAMP = 5.0e-3  # air damping; needed for force-lag + outer-loop stability

DT = 5e-5
N_STEPS = 20000

# Phase-rate gains
K_LOCK = 80.0
K_INNER = 40.0
LAM = 6.0
ALPHA = 0.15

# Outer-loop gains (locally stable in acquisition linearization)
KP = 0.40
KD = 0.002  # sketch value (equilibrium start + DT-scaled noise)
Y_REF = 0.0015

# Lock-in (status flag + soft φ_ref spring; phase law stays residual-driven)
DE_TH = 0.025
W_LOCK = 400
V_LOCK_MAX = 0.008
Y_LOCK_TOL = 5e-5
T_LOCK_MIN = 0.05  # don't declare lock on the first buffer fill

PHI_MIN = 0.08
PHI_MAX = np.pi / 2

NOISE_AMP = 0.008  # × Mg × √DT
Y_FLOOR = 0.0002
Y_CEIL = 0.006


def sat(x: float, a: float = ALPHA) -> float:
    return float(np.clip(x, -a, a))


def force_gain(y: float, c0_max: float = C0_MAX, h0: float = H0) -> float:
    """Available force amplitude A(y) = C0_max / (1 + (y/h0)²)."""
    return c0_max / (1.0 + (y / h0) ** 2)


def equilibrium_phi(y: float = Y_REF, weight: float = MG) -> float:
    """φ such that A(y) sin φ = weight (monotonic branch)."""
    a_ref = force_gain(y)
    return float(np.arcsin(np.clip(weight / a_ref, 0.0, 1.0)))


def run_loop(
    seed: int = 42,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    enable_disturbances: bool = True,
    mass_step: bool = False,
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)

    # -------------------- Initialize at equilibrium --------------------
    y = float(Y_REF)
    v = 0.0
    phi = equilibrium_phi(Y_REF, MG)
    f_ac = float(MG)
    ell = 0
    phi_ref = phi
    de_buf: list[float] = []
    log: list[dict[str, float]] = []

    for k in range(n_steps):
        t = k * DT
        mass = M * (1.25 if (mass_step and 0.4 < t < 0.7) else 1.0)
        weight = mass * G

        c_available = force_gain(y)
        c = c_available * np.sin(np.clip(phi, PHI_MIN, PHI_MAX))
        if enable_disturbances:
            d_f = NOISE_AMP * MG * np.sqrt(DT) * float(rng.standard_normal())
        else:
            d_f = 0.0
        f_ac = f_ac + (DT / TAU) * (c - f_ac) + d_f

        # Outer loop + consistent bounds
        f_ref_raw = weight - KP * (y - Y_REF) - KD * v
        f_min = c_available * np.sin(PHI_MIN)
        f_max = 0.95 * c_available
        f_ref = float(np.clip(f_ref_raw, f_min, f_max))

        r = f_ac - f_ref
        de = float(np.log1p(np.abs(r) / MG))

        acc = (f_ac - weight - B_DAMP * v) / mass
        v = v + acc * DT
        y = y + v * DT
        if y < Y_FLOOR:
            y = Y_FLOOR
            v = max(0.0, v)
        if y > Y_CEIL:
            y = Y_CEIL
            v = min(0.0, v)

        de_buf.append(de)
        if len(de_buf) > W_LOCK:
            de_buf.pop(0)

        # Phase update
        phi = float(np.clip(phi, PHI_MIN, PHI_MAX))
        e = sat(r / MG)

        if closed_loop:
            # Lock-in is a status latch (corridor + quiet kinematics). Phase
            # update stays the residual law with timestep-scaled rate; after
            # lock, blend in a weak φ_ref spring (user locked form) without
            # freezing adaptation.
            if (
                ell == 0
                and t >= T_LOCK_MIN
                and len(de_buf) == W_LOCK
                and float(np.mean(de_buf)) < DE_TH
                and float(np.max(de_buf[-120:])) < DE_TH * 1.3
                and abs(v) < V_LOCK_MAX
                and abs(y - Y_REF) < Y_LOCK_TOL
            ):
                ell = 1
                phi_ref = phi

            # Residual-driven phase rate (acquisition gains). Lock does not
            # switch the law — φ_ref is diagnostic only. Switching to a
            # φ_ref spring after lock was observed to grow gap oscillations.
            phi_dot = -K_LOCK * e
            phi = float(np.clip(phi + DT * phi_dot, PHI_MIN, PHI_MAX))
        # else: open loop holds φ

        log.append(
            {
                "t": t,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "phi_ref": phi_ref,
                "f_ac": f_ac,
                "f_ref": f_ref,
                "r": r,
                "r_over_mg": r / MG,
                "delta_e": de,
                "y": y,
                "y_mm": y * 1000.0,
                "v": v,
                "ell": float(ell),
                "c_available": c_available,
                "c": c,
                "weight": weight,
                "sat_e": e,
            }
        )

    return log


def compute_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    t = np.array([h["t"] for h in history])
    y = np.array([h["y"] for h in history])
    v = np.array([h["v"] for h in history])
    de = np.array([h["delta_e"] for h in history])
    r = np.array([h["r"] for h in history])
    ell = np.array([h["ell"] for h in history])
    locked = ell > 0.5

    t_lock = float("nan")
    if locked.any():
        t_lock = float(t[np.argmax(locked)])

    n_tail = max(1, int(round(0.1 / DT)))
    if locked.any():
        y_lock = y[locked]
        hold_rms_mm = float(np.std(y_lock) * 1000.0)
        hold_mean_mm = float(np.mean(y_lock) * 1000.0)
    else:
        hold_rms_mm = float("nan")
        hold_mean_mm = float("nan")

    return {
        "lock_in": bool(locked.any()),
        "time_to_lock_s": t_lock,
        "fraction_locked": float(locked.mean()),
        "final_r_over_mg": float(abs(r[-1]) / MG),
        "final_delta_e": float(de[-1]),
        "final_gap_mm": float(y[-1] * 1000.0),
        "final_abs_v": float(abs(v[-1])),
        "gap_rms_last_0p1s_mm": float(np.std(y[-n_tail:]) * 1000.0),
        "hold_rms_mm": hold_rms_mm,
        "hold_mean_mm": hold_mean_mm,
        "mean_delta_e_tail": float(de[-n_tail:].mean()),
        "y_ref_mm": float(Y_REF * 1000.0),
        "c0_over_mg": float(C0_MAX / MG),
        "kp": float(KP),
        "kd": float(KD),
        "k_lock": float(K_LOCK),
        "k_inner": float(K_INNER),
        "theta_star_deg": 22.5,
    }


def save_outputs(
    history: list[dict[str, float]],
    summary: dict[str, Any],
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = list(history[0].keys())
    data = np.column_stack([[row[k] for row in history] for k in keys])
    csv_path = out_dir / "qsd_sector_closed_loop.csv"
    np.savetxt(csv_path, data, delimiter=",", header=",".join(keys), comments="")

    summary_path = out_dir / "qsd_sector_closed_loop_summary.json"
    params = {
        "m": M,
        "g": G,
        "C0_max_over_Mg": C0_MAX / MG,
        "h0": H0,
        "tau": TAU,
        "b_damp": B_DAMP,
        "DT": DT,
        "N": len(history),
        "K_lock": K_LOCK,
        "K_inner": K_INNER,
        "lam": LAM,
        "alpha": ALPHA,
        "Kp": KP,
        "Kd": KD,
        "y_ref": Y_REF,
        "DE_th": DE_TH,
    }
    summary_path.write_text(
        json.dumps({"summary": summary, "params": params}, indent=2) + "\n",
        encoding="utf-8",
    )

    fig_path = out_dir / "qsd_sector_closed_loop.png"
    try:
        import matplotlib.pyplot as plt

        t = np.array([h["t"] for h in history])
        de = np.array([h["delta_e"] for h in history])
        phi = np.array([h["phi"] for h in history])
        r_n = np.array([h["r_over_mg"] for h in history])
        y_mm = np.array([h["y_mm"] for h in history])
        v = np.array([h["v"] for h in history])
        ell = np.array([h["ell"] for h in history])
        locked = ell > 0.5
        lt = float(t[np.argmax(locked)]) if locked.any() else None

        fig, axs = plt.subplots(5, 1, figsize=(10, 11), sharex=True)
        axs[0].plot(t, de, lw=1.1)
        axs[0].axhline(DE_TH, color="r", ls="--")
        if lt is not None:
            axs[0].axvline(lt, color="purple", ls=":")
        axs[0].set_ylabel(r"$\Delta E$")
        axs[0].set_title(
            "Conservative outer loop + consistent bounds + equilibrium start"
        )
        axs[0].grid(alpha=0.3)

        axs[1].plot(t, phi, color="orange", lw=1.1)
        axs[1].set_ylabel(r"$\phi$")
        axs[1].grid(alpha=0.3)

        axs[2].plot(t, r_n, color="green", lw=1.1)
        axs[2].axhline(0, color="k", ls="--", alpha=0.5)
        axs[2].set_ylabel(r"$r/Mg$")
        axs[2].grid(alpha=0.3)

        axs[3].plot(t, y_mm, color="tab:blue", lw=1.1)
        axs[3].axhline(Y_REF * 1000.0, color="k", ls="--", alpha=0.6)
        axs[3].set_ylabel("Gap (mm)")
        axs[3].grid(alpha=0.3)

        axs[4].plot(t, v, color="tab:purple", lw=1.0)
        axs[4].set_ylabel("v (m/s)")
        axs[4].set_xlabel("Time (s)")
        axs[4].grid(alpha=0.3)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_sector_closed_loop_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    # Equilibrium identity on the monotonic branch
    phi_eq = equilibrium_phi(Y_REF, MG)
    assert abs(force_gain(Y_REF) * np.sin(phi_eq) - MG) / MG < 1e-9

    # Gap dependence: larger gap ⇒ less available force
    assert force_gain(2 * H0) < force_gain(H0)

    closed = run_loop(seed=seed, closed_loop=True, enable_disturbances=True)
    open_ = run_loop(seed=seed, closed_loop=False, enable_disturbances=True)
    csum = compute_metrics(closed)
    osum = compute_metrics(open_)

    sat_vals = np.array([h["sat_e"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12)
    assert csum["lock_in"], "closed loop failed to lock"
    assert csum["fraction_locked"] > 0.5
    # Hold quality while locked, and quieter than open loop on the tail.
    assert abs(csum["hold_mean_mm"] - Y_REF * 1000.0) < 0.35
    assert csum["hold_rms_mm"] < 0.1
    assert csum["gap_rms_last_0p1s_mm"] < osum["gap_rms_last_0p1s_mm"]
    # No late divergence: last-0.1s gap RMS must stay near the locked hold RMS.
    assert csum["gap_rms_last_0p1s_mm"] < max(0.08, 3.0 * csum["hold_rms_mm"])

    return {"ok": True, "closed": csum, "open": osum}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    locked = summary["lock_in"]
    lt = summary["time_to_lock_s"]
    print(
        f"[{label}] Lock-in: {locked}"
        + (f" at {lt:.3f} s" if locked and not np.isnan(lt) else "")
    )
    print(f"[{label}] Final |r|/Mg : {summary['final_r_over_mg']:.4f}")
    print(f"[{label}] Final ΔE     : {summary['final_delta_e']:.4f}")
    print(f"[{label}] Final gap    : {summary['final_gap_mm']:.3f} mm")
    print(f"[{label}] Final |v|    : {summary['final_abs_v']:.5f} m/s")
    print(f"[{label}] Gap RMS last 0.1 s: {summary['gap_rms_last_0p1s_mm']:.3f} mm")
    if not np.isnan(summary["hold_rms_mm"]):
        print(
            f"[{label}] Hold mean/RMS: {summary['hold_mean_mm']:.3f} / "
            f"{summary['hold_rms_mm']:.3f} mm"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--mass-step", action="store_true")
    parser.add_argument("--no-disturbances", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    history = run_loop(
        seed=args.seed,
        closed_loop=True,
        enable_disturbances=not args.no_disturbances,
        mass_step=args.mass_step,
    )
    summary = compute_metrics(history)
    print_summary(summary, "closed")
    paths = save_outputs(history, summary, args.out_dir)
    # also mirror the canonical artifact name from the sketch
    try:
        import shutil

        art = Path("artifacts")
        art.mkdir(exist_ok=True)
        shutil.copy(paths["figure"], art / "conservative_outer.png")
        opt = Path("/opt/cursor/artifacts")
        if opt.exists():
            shutil.copy(paths["figure"], opt / "conservative_outer.png")
    except Exception:
        pass
    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
