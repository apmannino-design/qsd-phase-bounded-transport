"""
Cascaded NFAL levitator control: outer position/velocity + inner QSD sector.

Plant (gap-dependent coupling):
    C(φ,h) = [γ(γ+1)/8 · (a_max sin φ)² p₀ / h²] · A
    m ḧ = C(φ,h) − m g − b ḣ + d_ext(t)

Outer loop augments the force residual (stops free integration / drift):
    r = (F̂ − mg) + K_p mg (h−h*)/h* + K_d mg (v / v_scale)

Inner QSD sector law (unchanged structure):
    ΔE = log(1 + |r_n|),  r_n = r / mg
    φ⁺ = clip_rate( φ − K sat_α(r_n) )   with back-calculation anti-windup

Lock-in freezes φ when ΔE and |v| are both small; unlocks on corridor exit.
Safety: gap floor/ceiling interlocks + phase-rate limits.
Disturbances: thermal phase walk, sensor noise, mass step, impulses.
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
    coupling_force_n,
    equilibrium_gap,
    squeeze_number,
)


def sat(x: float, alpha: float) -> float:
    return float(np.clip(x, -alpha, alpha))


def compute_delta_e(r_n: float) -> float:
    return float(np.log1p(np.abs(r_n)))


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
    h0: float | None = None,
    enable_disturbances: bool = True,
) -> list[dict[str, float]]:
    """Integrate cascaded outer position + inner sector φ control."""
    p = params or balanced_params()
    rng = np.random.default_rng(seed)
    dt = p.dt_s
    n_steps = int(round(t_final / dt))

    phi = float(p.theta_star if phi0 is None else phi0)
    phi_thermal = 0.0  # resonance / match phase walk
    if h0 is None:
        h = float(np.clip(equilibrium_gap(p, phi, p.mass_kg), 2.0 * p.a_max, p.h_ceil))
    else:
        h = float(h0)
    v = 0.0
    f_hat = coupling_force_n(p, phi + phi_thermal, h)
    r_n_filt = 0.0
    locked = False
    interlock = 0  # 0 ok, -1 floor, +1 ceiling
    impulses_done: set[float] = set()
    t = 0.0
    log: list[dict[str, float]] = []

    for _ in range(n_steps):
        mass = mass_schedule(t, p)
        weight = mass * G

        # --- disturbances ---
        if enable_disturbances:
            phi_thermal += p.thermal_phase_walk_std * np.sqrt(dt) * float(
                rng.standard_normal()
            )
            h_meas = h + p.gap_sensor_noise_std_m * float(rng.standard_normal())
            f_noise = p.force_noise_std_n * float(rng.standard_normal())
        else:
            h_meas = h
            f_noise = 0.0

        phi_drive = float(np.clip(phi + phi_thermal, p.phi_min, p.phi_max))
        f_true = coupling_force_n(p, phi_drive, h) + f_noise
        f_hat = f_hat + (dt / p.tau_force_s) * (f_true - f_hat)

        # Impulsive air-current / vibration → velocity kick
        for t_imp in p.impulse_times:
            if enable_disturbances and t_imp not in impulses_done and t >= t_imp:
                v += p.impulse_force_n / mass
                impulses_done.add(t_imp)

        # --- outer position/velocity + force residual ---
        e_h = (h_meas - p.h_star) / p.h_star
        v_n = v / p.v_scale
        r_force = f_hat - weight
        r = r_force + p.kp_pos * weight * e_h + p.kd_vel * weight * v_n
        r_n = r / weight
        # Filtered residual for corridor / lock (inner update still uses r_n)
        alpha_f = dt / (p.tau_residual_s + dt)
        r_n_filt = (1.0 - alpha_f) * r_n_filt + alpha_f * r_n
        delta_e = compute_delta_e(r_n_filt)
        sat_r = sat(r_n, p.alpha)

        # --- lock-in (filtered ΔE + low velocity + low gap error) ---
        if locked:
            if delta_e > p.unlock_de_gate or abs(e_h) > p.unlock_eh_gate:
                locked = False
        else:
            if (
                delta_e < p.lock_de_gate
                and abs(v) < p.lock_v_gate
                and abs(e_h) < p.lock_eh_gate
            ):
                locked = True

        # --- safety interlocks ---
        interlock = 0
        if h <= p.h_floor:
            interlock = -1
        elif h >= p.h_ceil:
            interlock = 1

        phi_prev = phi
        if closed_loop and not locked and interlock == 0:
            # unconstrained sector step
            phi_cmd = phi - p.k_gain * sat_r
            # anti-windup back-calculation toward feasible set
            phi_sat = float(np.clip(phi_cmd, p.phi_min, p.phi_max))
            phi_cmd = phi_cmd - p.kaw * (phi_cmd - phi_sat)
            # hard phase-rate limit
            dphi_max = p.phi_rate_max * dt
            phi = float(np.clip(phi_cmd, phi - dphi_max, phi + dphi_max))
            phi = float(np.clip(phi, p.phi_min, p.phi_max))
        elif interlock == -1:
            # approaching contact: raise coupling
            phi = float(np.clip(phi + p.phi_rate_max * dt, p.phi_min, p.phi_max))
        elif interlock == 1:
            # escaping field: reduce coupling
            phi = float(np.clip(phi - p.phi_rate_max * dt, p.phi_min, p.phi_max))

        # --- plant integrate ---
        acc = (f_true - weight - p.damping_ns_m * v) / mass
        v = v + dt * acc
        h = h + dt * v
        # soft contact model
        if h < 1.5 * p.a_max:
            h = 1.5 * p.a_max
            v = max(v, 0.0)
        if h > p.h_ceil * 1.2:
            h = p.h_ceil * 1.2
            v = min(v, 0.0)

        log.append(
            {
                "t": t,
                "h_um": h * 1e6,
                "h_m": h,
                "h_meas_um": h_meas * 1e6,
                "v": v,
                "phi": phi,
                "phi_deg": float(np.degrees(phi)),
                "phi_thermal_deg": float(np.degrees(phi_thermal)),
                "dphi": phi - phi_prev,
                "f_true": f_true,
                "f_hat": f_hat,
                "mg": weight,
                "mass_g": mass * 1e3,
                "r_force": r_force,
                "r": r,
                "r_n": r_n,
                "r_n_filt": r_n_filt,
                "e_h": e_h,
                "delta_e": delta_e,
                "sat_r": sat_r,
                "locked": float(locked),
                "interlock": float(interlock),
                "a_eff_um": p.a_max * float(np.sin(phi_drive)) * 1e6,
                "c_phi_h": coupling_force_n(p, phi_drive, h),
                "squeeze_number": squeeze_number(p, h),
                "p_bar_kpa": (f_true / p.area) / 1000.0,
            }
        )
        t += dt

    return log


def compute_metrics(
    history: list[dict[str, float]], params: NFALParams
) -> dict[str, float]:
    """Lock / hold / recovery metrics for a usable levitator."""
    dt = params.dt_s
    t = np.array([row["t"] for row in history])
    h_um = np.array([row["h_um"] for row in history])
    v = np.array([row["v"] for row in history])
    delta_e = np.array([row["delta_e"] for row in history])
    locked = np.array([row["locked"] for row in history]) > 0.5
    e_h = np.array([row["e_h"] for row in history])
    r_n = np.array([row["r_n"] for row in history])

    # time-to-lock: first sample meeting lock conditions for ≥20 ms
    hold = max(1, int(round(0.02 / dt)))
    t_lock = float("nan")
    for i in range(len(t) - hold):
        if np.all(locked[i : i + hold]):
            t_lock = float(t[i])
            break

    # post-lock hold accuracy (after first lock, or last 1 s fallback)
    if not np.isnan(t_lock):
        post = t >= t_lock
    else:
        post = t >= (t[-1] - 1.0)
    h_rms_um = float(np.sqrt(np.mean((h_um[post] - params.h_star * 1e6) ** 2)))
    h_mean_um = float(np.mean(h_um[post]))

    # mass-step recovery (step ends at 2.5 s): time for |e_h|<0.05 and stay
    step_end = 2.5
    after = np.where(t >= step_end)[0]
    t_recover = float("nan")
    peak_exc_um = float("nan")
    if after.size:
        # peak |h-h*| during step window
        step = (t > 1.0) & (t < 2.5)
        if step.any():
            peak_exc_um = float(np.max(np.abs(h_um[step] - params.h_star * 1e6)))
        for i in after:
            if abs(e_h[i]) < 0.05 and abs(v[i]) < params.lock_v_gate * 5:
                # confirm short hold
                j = min(len(t), i + hold)
                if np.all(np.abs(e_h[i:j]) < 0.08):
                    t_recover = float(t[i] - step_end)
                    break

    # impulse recovery (first impulse)
    t_imp = params.impulse_times[0] if params.impulse_times else float("nan")
    t_imp_recover = float("nan")
    peak_imp_um = float("nan")
    if params.impulse_times:
        win = (t >= t_imp) & (t < t_imp + 0.5)
        if win.any():
            peak_imp_um = float(np.max(np.abs(h_um[win] - params.h_star * 1e6)))
        after_imp = np.where(t >= t_imp)[0]
        for i in after_imp:
            if abs(e_h[i]) < 0.05 and abs(v[i]) < params.lock_v_gate * 5:
                t_imp_recover = float(t[i] - t_imp)
                break

    n_tail = max(1, int(round(1.0 / dt)))
    corridor = delta_e < params.corridor_gate
    weight0 = params.mass_kg * G

    return {
        "time_to_lock_s": t_lock,
        "hold_rms_um": h_rms_um,
        "hold_mean_um": h_mean_um,
        "step_peak_excursion_um": peak_exc_um,
        "step_recovery_s": t_recover,
        "impulse_peak_excursion_um": peak_imp_um,
        "impulse_recovery_s": t_imp_recover,
        "fraction_locked": float(locked.mean()),
        "fraction_in_corridor": float(corridor.mean()),
        "fraction_in_corridor_tail": float(corridor[-n_tail:].mean()),
        "abs_rn_mean_tail": float(np.abs(r_n[-n_tail:]).mean()),
        "abs_eh_mean_tail": float(np.abs(e_h[-n_tail:]).mean()),
        "abs_eh_mean_step": float(
            np.abs(e_h[(t > 1.0) & (t < 2.5)]).mean()
        )
        if ((t > 1.0) & (t < 2.5)).any()
        else float("nan"),
        "final_h_um": float(h_um[-1]),
        "final_phi_deg": float(np.degrees(history[-1]["phi"])),
        "final_delta_e": float(delta_e[-1]),
        "mean_delta_e_tail": float(delta_e[-n_tail:].mean()),
        "mean_squeeze_number": float(
            np.mean([row["squeeze_number"] for row in history])
        ),
        "c0_over_mg": float(params.c0_at_hstar / weight0),
        "a_max_um": float(params.a_max * 1e6),
        "h_star_um": float(params.h_star * 1e6),
        "mass_g": float(params.mass_kg * 1e3),
        "freq_khz": float(params.freq_hz / 1e3),
        "theta_star_deg": float(np.degrees(params.theta_star)),
    }


def summarize(history: list[dict[str, float]], params: NFALParams) -> dict[str, float]:
    return compute_metrics(history, params)


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

        fig, axes = plt.subplots(5, 1, figsize=(9, 11), sharex=True)
        axes[0].plot(arrays["t"], arrays["h_um"], color="#1f4e5f", label="h")
        axes[0].axhline(params.h_star * 1e6, color="#c45c26", ls="--", lw=1, label="h*")
        axes[0].set_ylabel("gap (μm)")
        axes[0].legend(loc="upper right", fontsize=8)
        axes[0].set_title(
            "NFAL + outer position loop + QSD sector "
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

        axes[3].plot(arrays["t"], arrays["phi_deg"], color="#1f4e5f", label="φ")
        axes[3].plot(
            arrays["t"],
            arrays["phi_thermal_deg"],
            color="#888888",
            alpha=0.7,
            label="φ_thermal",
        )
        axes[3].axhline(
            np.degrees(params.theta_star), color="#c45c26", ls="--", lw=1, label="θ*"
        )
        axes[3].set_ylabel("φ (deg)")
        axes[3].legend(loc="upper right", fontsize=8)

        axes[4].plot(arrays["t"], arrays["locked"], color="#1f4e5f", label="locked")
        axes[4].plot(
            arrays["t"], arrays["interlock"], color="#c45c26", alpha=0.8, label="interlock"
        )
        axes[4].set_ylabel("flags")
        axes[4].set_xlabel("t (s)")
        axes[4].legend(loc="upper right", fontsize=8)

        fig.tight_layout()
        fig.savefig(fig_path, dpi=120)
        plt.close(fig)
    except Exception as exc:
        fig_path = out_dir / "qsd_sector_closed_loop_plot_skipped.txt"
        fig_path.write_text(f"Plot skipped: {exc}\n", encoding="utf-8")

    return {"csv": csv_path, "summary": summary_path, "figure": fig_path}


def self_test(seed: int = 42) -> dict[str, Any]:
    p = balanced_params()

    f_star = acoustic_force_n(p, p.h_star, p.theta_star)
    assert abs(f_star - p.mass_kg * G) / (p.mass_kg * G) < 1e-9
    assert squeeze_number(p, p.h_star) > 10.0
    # Gap dependence: doubling h cuts force by ~4× at fixed φ
    f1 = coupling_force_n(p, p.theta_star, p.h_star)
    f2 = coupling_force_n(p, p.theta_star, 2.0 * p.h_star)
    assert abs(f1 / f2 - 4.0) < 1e-9
    assert p.c0_at_hstar / (p.mass_kg * G) > 1.0  # margin over weight at sinφ=1

    closed = run_nfal_loop(p, seed=seed, closed_loop=True, phi0=0.30)
    open_ = run_nfal_loop(p, seed=seed, closed_loop=False, phi0=0.30)
    csum = summarize(closed, p)
    osum = summarize(open_, p)

    sat_vals = np.array([row["sat_r"] for row in closed])
    assert np.all(np.abs(sat_vals) <= p.alpha + 1e-12)
    assert csum["fraction_in_corridor_tail"] > 0.7
    assert csum["hold_rms_um"] < 5.0  # µm-class hold after lock
    assert csum["abs_eh_mean_step"] < 0.5 * osum["abs_eh_mean_step"]
    assert not np.isnan(csum["time_to_lock_s"])
    # phase-rate limit respected
    dphi = np.array([row["dphi"] for row in closed])
    assert np.all(np.abs(dphi) <= p.phi_rate_max * p.dt_s + 1e-12)

    return {"ok": True, "closed": csum, "open": osum, "params": p.to_dict()}


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    print(
        f"[{label}] f / a_max / h*  : {summary['freq_khz']:.0f} kHz, "
        f"{summary['a_max_um']:.2f} μm, {summary['h_star_um']:.1f} μm"
    )
    print(f"[{label}] C0/Mg margin    : {summary['c0_over_mg']:.2f}")
    print(f"[{label}] Time to lock    : {summary['time_to_lock_s']:.3f} s")
    print(f"[{label}] Hold RMS        : {summary['hold_rms_um']:.2f} μm")
    print(f"[{label}] Step peak / trec: {summary['step_peak_excursion_um']:.1f} μm / "
          f"{summary['step_recovery_s']:.3f} s")
    print(f"[{label}] Impulse pk/trec : {summary['impulse_peak_excursion_um']:.1f} μm / "
          f"{summary['impulse_recovery_s']:.3f} s")
    print(f"[{label}] Corridor (tail) : {summary['fraction_in_corridor_tail']:.3f}")
    print(f"[{label}] Locked fraction : {summary['fraction_locked']:.3f}")
    print(
        f"[{label}] Final φ / h     : {summary['final_phi_deg']:.2f}°, "
        f"{summary['final_h_um']:.1f} μm"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--phi0", type=float, default=0.30)
    parser.add_argument("--t-final", type=float, default=4.0)
    parser.add_argument(
        "--no-disturbances",
        action="store_true",
        help="Disable thermal walk / sensor noise / impulses",
    )
    args = parser.parse_args()

    if args.self_test:
        result = self_test(seed=args.seed)
        print("SELF_TEST: PASS")
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    params = balanced_params()
    history = run_nfal_loop(
        params,
        seed=args.seed,
        closed_loop=True,
        t_final=args.t_final,
        phi0=args.phi0,
        enable_disturbances=not args.no_disturbances,
    )
    summary = summarize(history, params)
    print_summary(summary, "closed")
    paths = save_outputs(history, summary, params, args.out_dir)
    print(f"Wrote {paths['csv']}")
    print(f"Wrote {paths['summary']}")
    print(f"Wrote {paths['figure']}")


if __name__ == "__main__":
    main()
