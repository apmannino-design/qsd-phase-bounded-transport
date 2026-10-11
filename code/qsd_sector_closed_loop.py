"""
Real-time lock-in simulation (uses qsd_control_core).

- Acquisition: inner residual/phase loop only (F_ref = Mg)
- Quiet-window detector (ΔE + |v|) via QuietWindowLock
- Freeze phi_ref and enable outer PID only after confirmed lock
- Richer sensing: lag/bias/dropout on force measurement
- DT-scaled force noise + light damping
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
    QuietWindowLock,
    Scorecard,
    SensorModel,
    delta_e,
    diverged_from_series,
    dt_step,
    rms,
    sat,
    wiener_noise,
)

# -------------------- Parameters --------------------
M = 1e-4
G = 9.81
MG = M * G

C0_MAX = 6.0 * MG
H0 = 0.0008
TAU = 0.005
B_DAMP = 5e-3  # stabilizes force-lag plant for quiet-window acquisition

DT = 5e-5
N_STEPS = 30000

# Inner (phase-rate) gains
K_ACQ = 70.0
K_LOCKED = 35.0
LAM = 1.0  # soft freeze; stiff λ fights F_ref moves after outer loop engages
ALPHA = 0.12

# Outer loop (enabled only after lock)
KP = 5.0
KD = 0.10
KI = 0.25
Y_REF = 0.0015
INTEG_LIM = 0.0015

# Quiet-window detector
DE_TH = 0.020
V_MAX = 0.005
QUIET_LEN = 500  # samples (~25 ms)
LOSS_MULT = 5.0
LOCK_GRACE_S = 0.20

PHI_MIN = 0.08
PHI_MAX = np.pi / 2

NOISE_AMP = 0.0015  # σ for √DT Wiener on force (× Mg)
Y_FLOOR = 0.0002
Y_CEIL = 0.008
Y0 = 0.0022  # slight offset for acquisition demo
F0_FRAC = 0.7  # initial F_ac = 0.7 Mg


def force_gain(y: float) -> float:
    return C0_MAX / (1.0 + (y / H0) ** 2)


def run_loop(
    seed: int = 42,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    enable_disturbances: bool = True,
    rich_sensing: bool = True,
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)

    y = float(Y0)
    v = 0.0
    a0 = force_gain(y)
    phi = float(np.arcsin(np.clip(MG / a0, 0.0, 1.0)))
    f_ac = F0_FRAC * MG
    phi_ref = 0.0
    integ = 0.0

    locker = QuietWindowLock(
        de_th=DE_TH,
        v_max=V_MAX,
        quiet_len=QUIET_LEN,
        loss_mult=LOSS_MULT,
        grace_s=LOCK_GRACE_S,
        dt=DT,
    )
    sensor = SensorModel(
        tau_s=0.001 if rich_sensing else 0.0,
        bias=0.002 * MG if rich_sensing else 0.0,
        dropout_prob=0.005 if rich_sensing else 0.0,
        noise_std=0.0005 * MG if rich_sensing else 0.0,
    )
    sensor.reset(f_ac)

    log: list[dict[str, float]] = []

    for k in range(n_steps):
        t = k * DT

        c_available = force_gain(y)
        c = c_available * np.sin(np.clip(phi, PHI_MIN, PHI_MAX))
        d_f = wiener_noise(rng, NOISE_AMP * MG, DT) if enable_disturbances else 0.0
        f_ac = f_ac + (DT / TAU) * (c - f_ac) + d_f

        f_meas = sensor.measure(f_ac, DT, rng)
        if np.isnan(f_meas):
            f_meas = f_ac

        # Force reference: pure Mg during acquisition; outer PID after lock
        if (not closed_loop) or (not locker.locked):
            f_ref_raw = MG
            integ = 0.0
        else:
            integ += (y - Y_REF) * DT
            integ = float(np.clip(integ, -INTEG_LIM, INTEG_LIM))
            f_ref_raw = MG - KP * (y - Y_REF) - KD * v - KI * integ

        f_min = c_available * np.sin(PHI_MIN)
        f_max = 0.95 * c_available
        f_ref = float(np.clip(f_ref_raw, f_min, f_max))

        r = f_meas - f_ref
        de = delta_e(r, scale=MG)

        # Dynamics (truth plant uses true f_ac)
        acc = (f_ac - MG - B_DAMP * v) / M
        v = v + acc * DT
        y = y + v * DT
        if y < Y_FLOOR:
            y = Y_FLOOR
            v = max(0.0, v)
        if y > Y_CEIL:
            y = Y_CEIL
            v = min(0.0, v)

        was_locked = locker.locked
        if closed_loop:
            locker.update(t, de, abs(v))
            if locker.locked and not was_locked:
                phi_ref = phi
            if was_locked and not locker.locked:
                integ = 0.0

        phi = float(np.clip(phi, PHI_MIN, PHI_MAX))
        e = sat(r / MG, ALPHA)

        if closed_loop:
            if not locker.locked:
                phi = dt_step(phi, -K_ACQ * e, DT, PHI_MIN, PHI_MAX)
            else:
                phi_ref = float(np.clip(phi_ref, PHI_MIN, PHI_MAX))
                phi = dt_step(
                    phi, -K_LOCKED * e - LAM * (phi - phi_ref), DT, PHI_MIN, PHI_MAX
                )

        log.append(
            {
                "t": t,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "phi_ref": phi_ref,
                "f_ac": f_ac,
                "f_meas": f_meas,
                "f_ref": f_ref,
                "r": r,
                "r_over_mg": r / MG,
                "delta_e": de,
                "y": y,
                "y_mm": y * 1000.0,
                "v": v,
                "ell": float(locker.locked),
                "integ": integ,
                "sat_e": e,
                "c_available": c_available,
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

    t_lock = float(t[np.argmax(locked)]) if locked.any() else float("nan")
    n_tail = max(1, int(round(0.3 / DT)))

    if locked.any():
        hold_mean = float(np.mean(y[locked]) * 1000.0)
        hold_rms = float(np.std(y[locked]) * 1000.0)
        if not np.isnan(t_lock):
            post = y[t >= (t_lock + 0.2)]
            post_mean = float(np.mean(post) * 1000.0) if post.size else float("nan")
            post_rms = float(np.std(post) * 1000.0) if post.size else float("nan")
            track_err = (y[t >= (t_lock + 0.2)] - Y_REF) * 1000.0
            track_rms = rms(track_err) if track_err.size else float("nan")
        else:
            post_mean = post_rms = track_rms = float("nan")
    else:
        hold_mean = hold_rms = post_mean = post_rms = track_rms = float("nan")

    drops = int(np.sum(np.diff(ell.astype(float)) < -0.5))

    return {
        "lock_in": bool(locked.any()),
        "time_to_lock_s": t_lock,
        "fraction_locked": float(locked.mean()),
        "lock_drop_count": drops,
        "final_r_over_mg": float(abs(r[-1]) / MG),
        "final_delta_e": float(de[-1]),
        "final_gap_mm": float(y[-1] * 1000.0),
        "final_abs_v": float(abs(v[-1])),
        "hold_mean_mm": hold_mean,
        "hold_rms_mm": hold_rms,
        "post_lock_mean_mm": post_mean,
        "post_lock_rms_mm": post_rms,
        "track_rms_mm": track_rms,
        "gap_rms_tail_mm": float(np.std(y[-n_tail:]) * 1000.0),
        "y_ref_mm": float(Y_REF * 1000.0),
        "c0_over_mg": float(C0_MAX / MG),
        "kp": float(KP),
        "kd": float(KD),
        "ki": float(KI),
        "diverged": diverged_from_series(y * 1000.0, bound=Y_CEIL * 1000.0 * 0.95),
        # Honest gap corridor vs y_ref (mm); residual corridor alone is acquisition-dominated.
        "corridor_fraction": float((np.abs(y - Y_REF) < 0.00015).mean()),
        "gap_err_rms_mm": rms((y - Y_REF) * 1000.0),
    }


def make_scorecard(
    closed: list[dict[str, float]], open_: list[dict[str, float]]
) -> Scorecard:
    c = compute_metrics(closed)
    o = compute_metrics(open_)
    return Scorecard(
        demo="lock_in",
        lock_in=c["lock_in"],
        time_to_lock_s=c["time_to_lock_s"],
        corridor_fraction=c["corridor_fraction"],
        hold_or_track_rms=(
            c["track_rms_mm"] if not np.isnan(c["track_rms_mm"]) else c["gap_err_rms_mm"]
        ),
        open_loop_rms=o["gap_err_rms_mm"],
        final_delta_e=c["final_delta_e"],
        diverged=c["diverged"],
        notes="quiet-window lock then outer PID; sensor lag/bias/dropout on F",
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
    csv_path = out_dir / "qsd_sector_closed_loop.csv"
    np.savetxt(csv_path, data, delimiter=",", header=",".join(keys), comments="")

    params = {
        "m": M,
        "g": G,
        "C0_max_over_Mg": C0_MAX / MG,
        "h0": H0,
        "tau": TAU,
        "b_damp": B_DAMP,
        "DT": DT,
        "N": len(history),
        "K_acq": K_ACQ,
        "K_locked": K_LOCKED,
        "lam": LAM,
        "alpha": ALPHA,
        "Kp": KP,
        "Kd": KD,
        "Ki": KI,
        "y_ref": Y_REF,
        "DE_th": DE_TH,
        "quiet_len": QUIET_LEN,
        "noise_amp": NOISE_AMP,
        "y0": Y0,
        "uses_core": True,
    }
    summary_path = out_dir / "qsd_sector_closed_loop_summary.json"
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
            axs[0].axvline(lt, color="purple", ls=":", label="lock-in")
            axs[0].legend(frameon=False)
        axs[0].set_ylabel(r"$\Delta E$")
        axs[0].set_title("Real-time lock-in (core): acquisition then outer loop")
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
    closed = run_loop(seed=seed, closed_loop=True)
    open_ = run_loop(seed=seed, closed_loop=False)
    csum = compute_metrics(closed)
    osum = compute_metrics(open_)

    sat_vals = np.array([h["sat_e"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12)
    assert csum["lock_in"], "failed to lock"
    assert csum["time_to_lock_s"] < 1.0
    assert abs(csum["post_lock_mean_mm"] - Y_REF * 1000.0) < 0.15
    assert csum["post_lock_rms_mm"] < 0.10
    assert abs(csum["final_gap_mm"] - Y_REF * 1000.0) < abs(
        osum["final_gap_mm"] - Y_REF * 1000.0
    )

    return {
        "ok": True,
        "closed": csum,
        "open": osum,
        "scorecard": make_scorecard(closed, open_),
    }


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
    if not np.isnan(summary["post_lock_mean_mm"]):
        print(
            f"[{label}] Post-lock mean/RMS: {summary['post_lock_mean_mm']:.3f} / "
            f"{summary['post_lock_rms_mm']:.3f} mm"
        )
    print(
        f"[{label}] Lock fraction / drops: {summary['fraction_locked']:.3f} / "
        f"{int(summary['lock_drop_count'])}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--no-disturbances", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print(result["scorecard"].row())
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    history = run_loop(
        seed=args.seed,
        closed_loop=True,
        enable_disturbances=not args.no_disturbances,
    )
    open_ = run_loop(
        seed=args.seed,
        closed_loop=False,
        enable_disturbances=not args.no_disturbances,
    )
    card = make_scorecard(history, open_)
    summary = card.to_dict()
    print_summary(compute_metrics(history), "closed")
    print(card.row())
    paths = save_outputs(history, summary, args.out_dir)

    try:
        import shutil

        for dest_dir in (Path("artifacts"), Path("/opt/cursor/artifacts")):
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(paths["figure"], dest_dir / "realtime_lockin.png")
    except Exception:
        pass

    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
