"""
Real-time lock-in with three-stage tri-ΔE lock (uses qsd_control_core).

Stages
  0 acquire  — inner residual/phase only, F_ref = Mg
  1 hold     — ΔE₁ quiet + |v|; freeze φ, keep F_ref = Mg
  2 armed    — ΔE₂ quieter hold; slew-limited outer PID begins
  3 track    — physical gate |y−y_ref|<ε & |v|; φ_ref from F_ref/A(y)

Open-loop baseline can replay the closed-loop stage clock (fair comparison).
Gain schedule written to results/qsd_gain_schedule.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qsd_control_core import (  # noqa: E402
    Scorecard,
    SensorModel,
    TriDeltaLock,
    delta_e,
    diverged_from_series,
    dt_step,
    rms,
    sat,
    save_gain_schedule,
    wiener_noise,
)

# -------------------- Parameters --------------------
M = 1e-4
G = 9.81
MG = M * G

C0_MAX = 6.0 * MG
H0 = 0.0008
TAU = 0.005
B_DAMP = 5e-3

DT = 5e-5
N_STEPS = 30000

K_ACQ = 70.0
K_LOCKED = 35.0
LAM = 0.4
ALPHA = 0.12

KP = 4.0
KD = 0.12
KI = 0.15
Y_REF = 0.0015
INTEG_LIM = 0.0015
F_SLEW = 2.0 * MG

DE1 = 0.020
DE2 = 0.015
GAP_ERR_MAX = 1.5e-4  # physical |y − y_ref|
GAP_V_MAX = 0.005
V_MAX = 0.005
QUIET_LEN = 400
HOLD_LEN = 300
ARM_LEN = 300
LOSS_DE = 0.14
LOSS_LEN = 600
LOCK_GRACE_S = 0.15

PHI_MIN = 0.08
PHI_MAX = np.pi / 2

NOISE_AMP = 0.0015
Y_FLOOR = 0.0002
Y_CEIL = 0.008
Y0 = 0.0022
F0_FRAC = 0.7


def force_gain(y: float) -> float:
    return C0_MAX / (1.0 + (y / H0) ** 2)


def phi_from_force(f_ref: float, y: float) -> float:
    a = max(force_gain(y), 1e-15)
    s = float(np.clip(f_ref / a, np.sin(PHI_MIN), 0.95))
    return float(np.arcsin(s))


def slew(prev: float, target: float, rate: float, dt: float) -> float:
    step = rate * dt
    return float(np.clip(target, prev - step, prev + step))


def run_loop(
    seed: int = 42,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    enable_disturbances: bool = True,
    rich_sensing: bool = True,
    stage_trace: Sequence[int] | None = None,
    disturbance: str = "nominal",
) -> list[dict[str, float]]:
    """
    stage_trace: if set, force stage[k] from a prior closed run (stage clock).
    disturbance: nominal | step_force | chirp | bias_walk | dropout_burst
    """
    rng = np.random.default_rng(seed)

    y = float(Y0)
    v = 0.0
    a0 = force_gain(y)
    phi = float(np.arcsin(np.clip(MG / a0, 0.0, 1.0)))
    phi0 = phi
    f_ac = F0_FRAC * MG
    f_ref = MG
    phi_ref = phi
    integ = 0.0

    locker = TriDeltaLock(
        de1=DE1,
        de2=DE2,
        gap_err_max=GAP_ERR_MAX,
        gap_v_max=GAP_V_MAX,
        v_max=V_MAX,
        quiet_len=QUIET_LEN,
        hold_len=HOLD_LEN,
        arm_len=ARM_LEN,
        loss_de=LOSS_DE,
        loss_len=LOSS_LEN,
        grace_s=LOCK_GRACE_S,
        dt=DT,
        require_gap_for_track=True,
    )

    bias0 = 0.002 * MG if rich_sensing else 0.0
    drop0 = 0.005 if rich_sensing else 0.0
    if disturbance == "bias_walk":
        bias0 = 0.002 * MG
    if disturbance == "dropout_burst":
        drop0 = 0.005

    sensor = SensorModel(
        tau_s=0.001 if rich_sensing else 0.0,
        bias=bias0,
        dropout_prob=drop0,
        noise_std=0.0005 * MG if rich_sensing else 0.0,
    )
    sensor.reset(f_ac)

    log: list[dict[str, float]] = []

    for k in range(n_steps):
        t = k * DT
        if stage_trace is not None:
            stage = int(stage_trace[min(k, len(stage_trace) - 1)])
        elif closed_loop:
            stage = locker.stage
        else:
            stage = 0

        # Disturbance battery extras
        d_extra = 0.0
        if disturbance == "step_force" and t >= 0.8:
            d_extra = 0.08 * MG
        elif disturbance == "chirp":
            d_extra = 0.02 * MG * np.sin(2 * np.pi * (5.0 + 40.0 * t) * t)
        if disturbance == "bias_walk":
            sensor.bias = bias0 + 0.01 * MG * (t / max(n_steps * DT, 1e-9))
        if disturbance == "dropout_burst":
            sensor.dropout_prob = 0.25 if 0.6 <= t < 0.75 else drop0

        c_available = force_gain(y)
        c = c_available * np.sin(np.clip(phi, PHI_MIN, PHI_MAX))
        d_f = wiener_noise(rng, NOISE_AMP * MG, DT) if enable_disturbances else 0.0
        f_ac = f_ac + (DT / TAU) * (c - f_ac) + d_f + d_extra * DT / TAU

        f_meas = sensor.measure(f_ac, DT, rng)
        if np.isnan(f_meas):
            f_meas = f_ac

        f_min = c_available * np.sin(PHI_MIN)
        f_max = 0.95 * c_available
        apply_outer = closed_loop and stage >= 2
        if not apply_outer:
            f_ref_tgt = MG
            integ = 0.0
        else:
            integ += (y - Y_REF) * DT
            integ = float(np.clip(integ, -INTEG_LIM, INTEG_LIM))
            f_ref_tgt = MG - KP * (y - Y_REF) - KD * v - KI * integ
            f_ref_tgt = float(np.clip(f_ref_tgt, f_min, f_max))

        slew_rate = F_SLEW if stage >= 2 else 8.0 * MG
        f_ref = slew(f_ref, f_ref_tgt, slew_rate, DT)
        f_ref = float(np.clip(f_ref, f_min, f_max))

        r = f_meas - f_ref
        de = delta_e(r, scale=MG)
        gap_err = abs(y - Y_REF)

        acc = (f_ac - MG - B_DAMP * v) / M
        v = v + acc * DT
        y = y + v * DT
        if y < Y_FLOOR:
            y = Y_FLOOR
            v = max(0.0, v)
        if y > Y_CEIL:
            y = Y_CEIL
            v = min(0.0, v)

        prev_stage = locker.stage
        if closed_loop and stage_trace is None:
            locker.update(t, de, abs(v), gap_err_abs=gap_err)
            if locker.stage == 1 and prev_stage == 0:
                phi_ref = phi
            if locker.stage == 0 and prev_stage > 0:
                integ = 0.0
            stage = locker.stage

        phi = float(np.clip(phi, PHI_MIN, PHI_MAX))
        e = sat(r / MG, ALPHA)

        if closed_loop:
            if stage == 0:
                phi = dt_step(phi, -K_ACQ * e, DT, PHI_MIN, PHI_MAX)
            elif stage == 1:
                phi = dt_step(
                    phi, -K_LOCKED * e - LAM * (phi - phi_ref), DT, PHI_MIN, PHI_MAX
                )
            else:
                phi_ref = phi_from_force(f_ref, y)
                phi = dt_step(
                    phi, -K_LOCKED * e - LAM * (phi - phi_ref), DT, PHI_MIN, PHI_MAX
                )
        else:
            # Open loop: hold initial phase branch (stage clock may still advance)
            phi = phi0

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
                "gap_err": gap_err,
                "gap_err_mm": gap_err * 1000.0,
                "y": y,
                "y_mm": y * 1000.0,
                "v": v,
                "ell": float(stage),
                "stage": float(stage),
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
    stage = np.array([h["stage"] for h in history])
    locked = stage >= 1.0
    tracking = stage >= 3.0

    t_lock = float(t[np.argmax(locked)]) if locked.any() else float("nan")
    t_track = float(t[np.argmax(tracking)]) if tracking.any() else float("nan")
    n_tail = max(1, int(round(0.3 / DT)))

    if tracking.any() and not np.isnan(t_track):
        post = y[t >= (t_track + 0.15)]
        post_mean = float(np.mean(post) * 1000.0) if post.size else float("nan")
        post_rms = float(np.std(post) * 1000.0) if post.size else float("nan")
        track_err = (post - Y_REF) * 1000.0
        track_rms = rms(track_err) if track_err.size else float("nan")
        hold_mean = float(np.mean(y[tracking]) * 1000.0)
        hold_rms = float(np.std(y[tracking]) * 1000.0)
    elif locked.any():
        hold_mean = float(np.mean(y[locked]) * 1000.0)
        hold_rms = float(np.std(y[locked]) * 1000.0)
        post_mean = post_rms = track_rms = float("nan")
    else:
        hold_mean = hold_rms = post_mean = post_rms = track_rms = float("nan")

    drops = int(np.sum((stage[1:] < 0.5) & (stage[:-1] >= 0.5)))

    return {
        "lock_in": bool(locked.any()),
        "reached_track": bool(tracking.any()),
        "time_to_lock_s": t_lock,
        "time_to_track_s": t_track,
        "fraction_locked": float(locked.mean()),
        "fraction_tracking": float(tracking.mean()),
        "lock_drop_count": drops,
        "final_r_over_mg": float(abs(r[-1]) / MG),
        "final_delta_e": float(de[-1]),
        "final_gap_mm": float(y[-1] * 1000.0),
        "final_abs_v": float(abs(v[-1])),
        "final_stage": float(stage[-1]),
        "hold_mean_mm": hold_mean,
        "hold_rms_mm": hold_rms,
        "post_lock_mean_mm": post_mean,
        "post_lock_rms_mm": post_rms,
        "track_rms_mm": track_rms,
        "gap_rms_tail_mm": float(np.std(y[-n_tail:]) * 1000.0),
        "y_ref_mm": float(Y_REF * 1000.0),
        "diverged": diverged_from_series(y * 1000.0, bound=Y_CEIL * 1000.0 * 0.95),
        "corridor_fraction": float((np.abs(y - Y_REF) < GAP_ERR_MAX).mean()),
        "gap_err_rms_mm": rms((y - Y_REF) * 1000.0),
        "de1": DE1,
        "de2": DE2,
        "gap_err_max_mm": GAP_ERR_MAX * 1000.0,
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
        notes="tri-ΔE + physical gap gate; stage-clock open baseline; slew F_ref",
        extras=c,
    )


def paired_closed_open(seed: int = 42, **kwargs) -> tuple[list, list]:
    """Closed run + open run on the same stage clock."""
    closed = run_loop(seed=seed, closed_loop=True, **kwargs)
    stages = [int(h["stage"]) for h in closed]
    open_ = run_loop(
        seed=seed, closed_loop=False, stage_trace=stages, **kwargs
    )
    return closed, open_


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

    sched_path = save_gain_schedule(out_dir / "qsd_gain_schedule.csv")

    params = {
        "DT": DT,
        "N": len(history),
        "DE1": DE1,
        "DE2": DE2,
        "gap_err_max": GAP_ERR_MAX,
        "F_slew": F_SLEW,
        "quiet_len": QUIET_LEN,
        "hold_len": HOLD_LEN,
        "arm_len": ARM_LEN,
        "tri_delta_lock": True,
        "physical_gap_gate": True,
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
        gap_mm = np.array([h["gap_err_mm"] for h in history])
        phi = np.array([h["phi"] for h in history])
        y_mm = np.array([h["y_mm"] for h in history])
        stage = np.array([h["stage"] for h in history])

        fig, axs = plt.subplots(5, 1, figsize=(10, 12), sharex=True)
        axs[0].plot(t, de, lw=1.1, label=r"residual $\Delta E$")
        axs[0].axhline(DE1, color="C1", ls="--", alpha=0.7, label=r"$\Delta E_1$")
        axs[0].axhline(DE2, color="C2", ls="--", alpha=0.7, label=r"$\Delta E_2$")
        for s, name, col in ((1, "hold", "purple"), (2, "armed", "brown"), (3, "track", "green")):
            hit = stage >= s
            if hit.any():
                axs[0].axvline(t[np.argmax(hit)], color=col, ls=":", alpha=0.8, label=name)
        axs[0].set_ylabel(r"$\Delta E$")
        axs[0].set_title("Tri-ΔE lock-in + physical gap gate")
        axs[0].legend(frameon=False, ncol=4, fontsize=8)
        axs[0].grid(alpha=0.3)

        axs[1].plot(t, stage, color="k", lw=1.2)
        axs[1].set_ylabel("stage")
        axs[1].set_yticks([0, 1, 2, 3])
        axs[1].grid(alpha=0.3)

        axs[2].plot(t, phi, color="orange", lw=1.1)
        axs[2].set_ylabel(r"$\phi$")
        axs[2].grid(alpha=0.3)

        axs[3].plot(t, gap_mm, color="green", lw=1.1)
        axs[3].axhline(GAP_ERR_MAX * 1000.0, color="r", ls="--", label="ε")
        axs[3].set_ylabel("|gap err| mm")
        axs[3].legend(frameon=False)
        axs[3].grid(alpha=0.3)

        axs[4].plot(t, y_mm, color="tab:blue", lw=1.1)
        axs[4].axhline(Y_REF * 1000.0, color="k", ls="--", alpha=0.6)
        axs[4].set_ylabel("Gap (mm)")
        axs[4].set_xlabel("Time (s)")
        axs[4].grid(alpha=0.3)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_sector_closed_loop_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {
        "csv": csv_path,
        "summary": summary_path,
        "figure": fig_path,
        "schedule": sched_path,
    }


def self_test(seed: int = 42) -> dict[str, Any]:
    closed, open_ = paired_closed_open(seed=seed)
    csum = compute_metrics(closed)
    osum = compute_metrics(open_)

    sat_vals = np.array([h["sat_e"] for h in closed])
    assert np.all(np.abs(sat_vals) <= ALPHA + 1e-12)
    assert csum["lock_in"], "failed stage-1 hold"
    assert csum["reached_track"], "failed to reach stage-3 track"
    assert csum["time_to_lock_s"] < 1.0
    assert csum["time_to_track_s"] < 1.5
    assert csum["lock_drop_count"] <= 2
    assert abs(csum["post_lock_mean_mm"] - Y_REF * 1000.0) < 0.15
    assert csum["post_lock_rms_mm"] < 0.12
    # Stage clocks match
    assert [h["stage"] for h in closed] == [h["stage"] for h in open_]
    assert abs(csum["final_gap_mm"] - Y_REF * 1000.0) < abs(
        osum["final_gap_mm"] - Y_REF * 1000.0
    )
    card = make_scorecard(closed, open_)
    assert card.rms_ratio < 0.5

    return {"ok": True, "closed": csum, "open": osum, "scorecard": card}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    lt = summary["time_to_lock_s"]
    tt = summary.get("time_to_track_s", float("nan"))
    print(
        f"[{label}] Lock-in: {summary['lock_in']}"
        + (f" at {lt:.3f} s" if summary["lock_in"] and not np.isnan(lt) else "")
        + (
            f" | track at {tt:.3f} s"
            if summary.get("reached_track") and not np.isnan(tt)
            else ""
        )
    )
    print(f"[{label}] Final stage  : {int(summary.get('final_stage', 0))}")
    print(f"[{label}] Final gap    : {summary['final_gap_mm']:.3f} mm")
    if not np.isnan(summary["post_lock_mean_mm"]):
        print(
            f"[{label}] Post-track mean/RMS: {summary['post_lock_mean_mm']:.3f} / "
            f"{summary['post_lock_rms_mm']:.3f} mm"
        )
    print(
        f"[{label}] Lock/track frac / drops: "
        f"{summary['fraction_locked']:.3f} / "
        f"{summary.get('fraction_tracking', 0):.3f} / "
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

    closed, open_ = paired_closed_open(
        seed=args.seed,
        enable_disturbances=not args.no_disturbances,
    )
    card = make_scorecard(closed, open_)
    print_summary(compute_metrics(closed), "closed")
    print(card.row())
    paths = save_outputs(closed, card.to_dict(), args.out_dir)

    try:
        import shutil

        for dest_dir in (Path("artifacts"), Path("/opt/cursor/artifacts")):
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(paths["figure"], dest_dir / "realtime_lockin.png")
            shutil.copy(paths["figure"], dest_dir / "tri_delta_lockin.png")
            shutil.copy(paths["schedule"], dest_dir / "qsd_gain_schedule.csv")
    except Exception:
        pass

    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")
    print(f"Wrote {paths['schedule']}")


if __name__ == "__main__":
    main()
