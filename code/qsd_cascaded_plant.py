"""
Cascaded QSD plant: levitator gap + phase + spatial node (one scorecard).

Shared disturbance story and TriDeltaLock staging:
  stages 0–1  acquire/hold residual on force
  stage 2     arm outer gap PID (slew-limited)
  stage 3     track gap + track moving spatial node (FF+FB on unwrapped φ_s)
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
    wiener_noise,
    wiener_noise_array,
    wrap_pi,
)

# Levitator
M = 1e-4
G = 9.81
MG = M * G
C0_MAX = 6.0 * MG
H0 = 0.0008
TAU = 0.005
B_DAMP = 5e-3
DT = 5e-5
N_STEPS = 30000
Y_REF = 0.0015
Y0 = 0.0022
Y_FLOOR, Y_CEIL = 0.0002, 0.008
PHI_MIN, PHI_MAX = 0.08, np.pi / 2
K_ACQ, K_LOCKED, LAM, ALPHA = 70.0, 35.0, 0.4, 0.12
KP, KD, KI = 4.0, 0.12, 0.15
INTEG_LIM = 0.0015
F_SLEW = 2.0 * MG
NOISE_AMP = 0.0015
F0_FRAC = 0.7

# Spatial overlay (slower DT subsample via same DT, coarse field)
L, NX, WAVELENGTH = 1.0, 101, 0.4
K_WAVE = 2 * np.pi / WAVELENGTH
K_PHI_S = 40.0
FF_BLEND = 0.35
NODE_NOISE = 0.01 / np.sqrt(DT)
ERR_SCALE = 0.05

DE1, DE2 = 0.020, 0.015
GAP_ERR_MAX, V_MAX = 1.5e-4, 0.005


def force_gain(y: float) -> float:
    return C0_MAX / (1.0 + (y / H0) ** 2)


def phi_from_force(f_ref: float, y: float) -> float:
    a = max(force_gain(y), 1e-15)
    return float(np.arcsin(float(np.clip(f_ref / a, np.sin(PHI_MIN), 0.95))))


def slew(prev: float, target: float, rate: float, dt: float) -> float:
    step = rate * dt
    return float(np.clip(target, prev - step, prev + step))


def field(phi: float, x: np.ndarray) -> np.ndarray:
    return np.cos(K_WAVE * x) + np.cos(K_WAVE * x + phi)


def phi_from_target(x_des: float) -> float:
    return float(np.pi - 2.0 * K_WAVE * x_des)


def track_node(p: np.ndarray, x: np.ndarray, x_prev: float) -> float:
    crossings = np.where(np.diff(np.sign(p)))[0]
    if crossings.size == 0:
        return x_prev
    xs = []
    for idx in crossings:
        x0, x1 = x[idx], x[idx + 1]
        p0, p1 = p[idx], p[idx + 1]
        xs.append(x0 if abs(p1 - p0) < 1e-15 else float(x0 - p0 * (x1 - x0) / (p1 - p0)))
    xs = np.asarray(xs)
    return float(xs[np.argmin(np.abs(xs - x_prev))])


def target_node(t: float) -> float:
    return 0.5 + 0.08 * np.sin(2 * np.pi * 0.12 * t)


def run_loop(
    seed: int = 42,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    stage_trace: Sequence[int] | None = None,
    disturbance: str = "nominal",
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    xgrid = np.linspace(0.0, L, NX)

    y, v = float(Y0), 0.0
    phi = float(np.arcsin(np.clip(MG / force_gain(y), 0.0, 1.0)))
    phi0 = phi
    f_ac = F0_FRAC * MG
    f_ref = MG
    phi_ref = phi
    integ = 0.0

    phi_s = phi_from_target(0.5)
    x_node = 0.5

    locker = TriDeltaLock(
        de1=DE1,
        de2=DE2,
        gap_err_max=GAP_ERR_MAX,
        gap_v_max=V_MAX,
        v_max=V_MAX,
        quiet_len=400,
        hold_len=300,
        arm_len=300,
        loss_de=0.14,
        loss_len=600,
        grace_s=0.15,
    )
    sensor = SensorModel(tau_s=0.001, bias=0.002 * MG, dropout_prob=0.005, noise_std=0.0005 * MG)
    sensor.reset(f_ac)
    node_sensor = SensorModel(tau_s=0.008, bias=0.002, dropout_prob=0.01, noise_std=0.001)
    node_sensor.reset(x_node)

    log: list[dict[str, float]] = []
    for k in range(n_steps):
        t = k * DT
        if stage_trace is not None:
            stage = int(stage_trace[min(k, len(stage_trace) - 1)])
        elif closed_loop:
            stage = locker.stage
        else:
            stage = 0

        d_extra = 0.0
        if disturbance == "step_force" and t >= 0.8:
            d_extra = 0.08 * MG
        elif disturbance == "chirp":
            d_extra = 0.02 * MG * np.sin(2 * np.pi * (5.0 + 40.0 * t) * t)

        c_available = force_gain(y)
        c = c_available * np.sin(np.clip(phi, PHI_MIN, PHI_MAX))
        f_ac = f_ac + (DT / TAU) * (c - f_ac) + wiener_noise(rng, NOISE_AMP * MG, DT) + d_extra * DT / TAU
        f_meas = sensor.measure(f_ac, DT, rng)

        f_min, f_max = c_available * np.sin(PHI_MIN), 0.95 * c_available
        if closed_loop and stage >= 2:
            integ += (y - Y_REF) * DT
            integ = float(np.clip(integ, -INTEG_LIM, INTEG_LIM))
            f_ref_tgt = float(np.clip(MG - KP * (y - Y_REF) - KD * v - KI * integ, f_min, f_max))
        else:
            f_ref_tgt, integ = MG, 0.0
        f_ref = float(np.clip(slew(f_ref, f_ref_tgt, F_SLEW if stage >= 2 else 8 * MG, DT), f_min, f_max))

        r = f_meas - f_ref
        de = delta_e(r, scale=MG)
        gap_err = abs(y - Y_REF)

        acc = (f_ac - MG - B_DAMP * v) / M
        v = v + acc * DT
        y = float(np.clip(y + v * DT, Y_FLOOR, Y_CEIL))

        # Spatial channel (always measured; controlled only in stage 3)
        x_des = 0.5 if stage < 3 else float(target_node(t))
        p = field(wrap_pi(phi_s), xgrid) + wiener_noise_array(rng, NODE_NOISE, DT, NX)
        x_node = track_node(p, xgrid, x_node)
        x_meas = node_sensor.measure(x_node, DT, rng)
        r_s = x_meas - x_des
        de_s = delta_e(r_s, scale=ERR_SCALE)

        prev = locker.stage
        if closed_loop and stage_trace is None:
            locker.update(t, de, abs(v), gap_err_abs=gap_err)
            if locker.stage == 1 and prev == 0:
                phi_ref = phi
            if locker.stage == 0 and prev > 0:
                integ = 0.0
            stage = locker.stage

        e = sat(r / MG, ALPHA)
        if closed_loop:
            if stage == 0:
                phi = dt_step(phi, -K_ACQ * e, DT, PHI_MIN, PHI_MAX)
            elif stage == 1:
                phi = dt_step(phi, -K_LOCKED * e - LAM * (phi - phi_ref), DT, PHI_MIN, PHI_MAX)
            else:
                phi_ref = phi_from_force(f_ref, y)
                phi = dt_step(phi, -K_LOCKED * e - LAM * (phi - phi_ref), DT, PHI_MIN, PHI_MAX)
            if stage >= 3:
                dff = wrap_pi(phi_from_target(x_des) - wrap_pi(phi_s))
                phi_s = phi_s + FF_BLEND * dff + DT * K_PHI_S * sat(r_s, ALPHA)
        else:
            phi = phi0

        log.append(
            {
                "t": t,
                "stage": float(stage),
                "y": y,
                "y_mm": y * 1000.0,
                "v": v,
                "phi": phi,
                "f_ref": f_ref,
                "delta_e": de,
                "gap_err": gap_err,
                "x_node": x_node,
                "x_des": x_des,
                "r_spatial": r_s,
                "delta_e_spatial": de_s,
                "phi_spatial": wrap_pi(phi_s),
                "sat_e": e,
            }
        )
    return log


def compute_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    t = np.array([h["t"] for h in history])
    y = np.array([h["y"] for h in history])
    stage = np.array([h["stage"] for h in history])
    rs = np.array([h["r_spatial"] for h in history])
    de = np.array([h["delta_e"] for h in history])
    tracking = stage >= 3.0
    locked = stage >= 1.0
    t_lock = float(t[np.argmax(locked)]) if locked.any() else float("nan")
    t_track = float(t[np.argmax(tracking)]) if tracking.any() else float("nan")
    if tracking.any():
        gap_rms = rms((y[tracking] - Y_REF) * 1000.0)
        node_rms = rms(rs[tracking])
        comb = rms(np.concatenate([(y[tracking] - Y_REF) / GAP_ERR_MAX, rs[tracking] / 0.05]))
    else:
        gap_rms = rms((y - Y_REF) * 1000.0)
        node_rms = rms(rs)
        comb = float("nan")
    return {
        "lock_in": bool(locked.any()),
        "reached_track": bool(tracking.any()),
        "time_to_lock_s": t_lock,
        "time_to_track_s": t_track,
        "fraction_tracking": float(tracking.mean()),
        "lock_drop_count": int(np.sum((stage[1:] < 0.5) & (stage[:-1] >= 0.5))),
        "gap_track_rms_mm": gap_rms,
        "node_track_rms": node_rms,
        "combined_norm_rms": comb,
        "final_delta_e": float(de[-1]),
        "final_gap_mm": float(y[-1] * 1000.0),
        "corridor_fraction": float((np.abs(y - Y_REF) < GAP_ERR_MAX).mean()),
        "diverged": diverged_from_series(y * 1000.0, bound=Y_CEIL * 1000.0 * 0.95),
    }


def make_scorecard(closed: list, open_: list) -> Scorecard:
    c, o = compute_metrics(closed), compute_metrics(open_)
    return Scorecard(
        demo="cascaded",
        lock_in=c["lock_in"],
        time_to_lock_s=c["time_to_lock_s"],
        corridor_fraction=c["corridor_fraction"],
        hold_or_track_rms=c["combined_norm_rms"] if not np.isnan(c["combined_norm_rms"]) else c["gap_track_rms_mm"],
        open_loop_rms=o["combined_norm_rms"] if not np.isnan(o["combined_norm_rms"]) else o["gap_track_rms_mm"],
        final_delta_e=c["final_delta_e"],
        diverged=c["diverged"],
        notes="gap+φ+spatial cascade; shared TriDeltaLock + disturbances",
        extras=c,
    )


def paired_closed_open(seed: int = 42, **kwargs):
    closed = run_loop(seed=seed, closed_loop=True, **kwargs)
    stages = [int(h["stage"]) for h in closed]
    open_ = run_loop(seed=seed, closed_loop=False, stage_trace=stages, **kwargs)
    return closed, open_


def save_outputs(history, summary, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = list(history[0].keys())
    data = np.column_stack([[row[k] for row in history] for k in keys])
    csv_path = out_dir / "qsd_cascaded_plant.csv"
    np.savetxt(csv_path, data, delimiter=",", header=",".join(keys), comments="")
    summary_path = out_dir / "qsd_cascaded_plant_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    fig_path = out_dir / "qsd_cascaded_plant.png"
    try:
        import matplotlib.pyplot as plt

        t = np.array([h["t"] for h in history])
        fig, axs = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
        axs[0].plot(t, [h["stage"] for h in history], color="k")
        axs[0].set_ylabel("stage")
        axs[0].set_title("Cascaded plant: gap + phase + spatial node")
        axs[0].grid(alpha=0.3)
        axs[1].plot(t, [h["y_mm"] for h in history], label="gap")
        axs[1].axhline(Y_REF * 1000, color="k", ls="--")
        axs[1].set_ylabel("Gap mm")
        axs[1].grid(alpha=0.3)
        axs[2].plot(t, [h["x_node"] for h in history], label="node")
        axs[2].plot(t, [h["x_des"] for h in history], "--", label="des")
        axs[2].set_ylabel("Node")
        axs[2].legend(frameon=False)
        axs[2].grid(alpha=0.3)
        axs[3].plot(t, [h["delta_e"] for h in history], label="force ΔE")
        axs[3].plot(t, [h["delta_e_spatial"] for h in history], label="spatial ΔE")
        axs[3].set_ylabel(r"$\Delta E$")
        axs[3].set_xlabel("Time (s)")
        axs[3].legend(frameon=False)
        axs[3].grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_path, dpi=150)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_cascaded_plant_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")
    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    closed, open_ = paired_closed_open(seed=seed)
    c = compute_metrics(closed)
    assert c["lock_in"] and c["reached_track"]
    assert c["time_to_track_s"] < 1.5
    assert c["gap_track_rms_mm"] < 0.15
    assert c["node_track_rms"] < 0.05
    card = make_scorecard(closed, open_)
    assert card.rms_ratio < 1.0
    return {"ok": True, "closed": c, "scorecard": card}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        r = self_test(args.seed)
        print("SELF_TEST: PASS")
        print(r["scorecard"].row())
        return
    closed, open_ = paired_closed_open(seed=args.seed)
    card = make_scorecard(closed, open_)
    print(card.row())
    paths = save_outputs(closed, card.to_dict(), args.out_dir)
    try:
        import shutil

        for d in (Path("artifacts"), Path("/opt/cursor/artifacts")):
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy(paths["figure"], d / "cascaded_plant.png")
    except Exception:
        pass
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
