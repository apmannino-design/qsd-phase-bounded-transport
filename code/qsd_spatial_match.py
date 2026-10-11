"""
Spatial match on a two-source standing field (uses qsd_control_core).

Lock-then-track:
  1) Acquire on a fixed mid-domain node (quiet-window on ΔE)
  2) After lock, track the moving target with FF + sector FB

Control = analytic phase feedforward (unwrapped) + sector feedback.
Amplitude ratio stays near 1 (contrast), not the primary actuator.
Richer sensing: lag/bias/dropout on measured node position.
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
    rms,
    sat,
    wiener_noise_array,
    wrap_pi,
)

# -------------------- Parameters --------------------
DT = 0.002
N_STEPS = 4000
L = 1.0
NX = 201
WAVELENGTH = 0.4
K_WAVE = 2 * np.pi / WAVELENGTH

ALPHA = 0.15
K_PHI = 40.0  # feedback rate (rad/s per sat unit), DT-scaled
FF_BLEND = 0.35  # fraction of phase error closed by feedforward each step
RATIO = 1.0

NOISE_STD = 0.01 / np.sqrt(DT)  # √DT Wiener intensity matching prior raw step
ERR_SCALE = 0.05
CORRIDOR = 0.25  # ΔE gate; ≈ |e| < 0.014

# Quiet-window acquisition on fixed mid node before outer track
DE_TH_LOCK = 0.08
QUIET_LEN = 80  # samples (~0.16 s)
X_ACQ = 0.5


def field(phi: float, ratio: float, x: np.ndarray) -> np.ndarray:
    """Superposition of two counter-propagating waves."""
    return np.cos(K_WAVE * x) + ratio * np.cos(K_WAVE * x + phi)


def phi_from_target(x_des: float) -> float:
    """
    Equal-amplitude node map (one branch near mid-domain):
        x ≈ (π/2 − φ/2) / k  ⇒  φ ≈ π − 2 k x
    """
    return float(np.pi - 2.0 * K_WAVE * x_des)


def track_node(p: np.ndarray, x: np.ndarray, x_prev: float) -> float:
    """Interpolated zero crossing nearest the previous node estimate."""
    crossings = np.where(np.diff(np.sign(p)))[0]
    if crossings.size == 0:
        return x_prev
    xs = []
    for idx in crossings:
        x0, x1 = x[idx], x[idx + 1]
        p0, p1 = p[idx], p[idx + 1]
        if abs(p1 - p0) < 1e-15:
            xs.append(x0)
        else:
            xs.append(float(x0 - p0 * (x1 - x0) / (p1 - p0)))
    xs = np.asarray(xs, dtype=float)
    return float(xs[np.argmin(np.abs(xs - x_prev))])


def target_node(t: np.ndarray | float) -> np.ndarray | float:
    return 0.5 + 0.12 * np.sin(2 * np.pi * 0.15 * t)


def run_loop(
    seed: int = 42,
    n_steps: int = N_STEPS,
    closed_loop: bool = True,
    rich_sensing: bool = True,
    lock_then_track: bool = True,
) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, L, NX)

    # Unwrapped phase state (field uses wrap_pi)
    phi_u = phi_from_target(X_ACQ)
    ratio = RATIO
    x_node = track_node(field(wrap_pi(phi_u), ratio, x), x, X_ACQ)

    locker = QuietWindowLock(
        de_th=DE_TH_LOCK,
        v_max=np.inf,
        quiet_len=QUIET_LEN,
        loss_mult=8.0,
        grace_s=0.3,
        dt=DT,
    )
    # If lock-then-track disabled, start already locked (legacy continuous track)
    if not lock_then_track:
        locker.locked = True
        locker.t_lock = 0.0

    sensor = SensorModel(
        tau_s=0.008 if rich_sensing else 0.0,
        bias=0.002 if rich_sensing else 0.0,
        dropout_prob=0.01 if rich_sensing else 0.0,
        noise_std=0.001 if rich_sensing else 0.0,
    )
    sensor.reset(x_node)

    log: list[dict[str, float]] = []
    for n in range(n_steps):
        t = n * DT

        # Lock-then-track: hold fixed mid node until quiet lock, then move
        if closed_loop and lock_then_track and not locker.locked:
            x_des = X_ACQ
        else:
            x_des = float(target_node(t))

        phi = wrap_pi(phi_u)
        noise = wiener_noise_array(rng, NOISE_STD, DT, NX)
        p = field(phi, ratio, x) + noise
        x_node = track_node(p, x, x_node)

        x_meas = sensor.measure(x_node, DT, rng)
        if np.isnan(x_meas):
            x_meas = x_node

        r_spatial = x_meas - x_des
        de = delta_e(r_spatial, scale=ERR_SCALE)

        if closed_loop:
            if lock_then_track:
                locker.update(t, de, 0.0)

            # Feedforward toward analytic phase for x_des (unwrapped)
            phi_des = phi_from_target(x_des)
            dff = wrap_pi(phi_des - wrap_pi(phi_u))
            # Feedback: ∂x_node/∂φ < 0 ⇒ φ̇ = +K sat(r)
            e = sat(r_spatial, ALPHA)
            # During acquisition use stronger FF to settle mid node quickly
            blend = FF_BLEND if locker.locked else min(1.0, FF_BLEND + 0.25)
            phi_u = phi_u + blend * dff + DT * K_PHI * e

        log.append(
            {
                "t": t,
                "phi": wrap_pi(phi_u),
                "phi_unwrapped": phi_u,
                "ratio": ratio,
                "x_node": x_node,
                "x_meas": x_meas,
                "x_des": x_des,
                "r_spatial": r_spatial,
                "delta_e": de,
                "abs_err": abs(r_spatial),
                "sat_e": sat(r_spatial, ALPHA),
                "ell": float(locker.locked),
            }
        )

    return log


def compute_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    de = np.array([h["delta_e"] for h in history])
    err = np.array([h["abs_err"] for h in history])
    ell = np.array([h["ell"] for h in history])
    t = np.array([h["t"] for h in history])
    locked = ell > 0.5
    t_lock = float(t[np.argmax(locked)]) if locked.any() else float("nan")
    n_tail = max(1, int(round(1.0 / DT)))
    # Track metrics after lock (or full run if always locked)
    if locked.any() and not np.isnan(t_lock):
        post = err[t >= t_lock]
        track_rms = rms(post) if post.size else float("nan")
    else:
        track_rms = rms(err)
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
        "ff_blend": float(FF_BLEND),
        "lock_in": bool(locked.any()),
        "time_to_lock_s": t_lock,
        "fraction_locked": float(locked.mean()),
        "track_rms": track_rms,
        "diverged": diverged_from_series(err, bound=0.25),
    }


def make_scorecard(
    closed: list[dict[str, float]], open_: list[dict[str, float]]
) -> Scorecard:
    c = compute_metrics(closed)
    o = compute_metrics(open_)
    return Scorecard(
        demo="spatial_match",
        lock_in=c["lock_in"],
        time_to_lock_s=c["time_to_lock_s"],
        corridor_fraction=c["corridor_fraction"],
        hold_or_track_rms=c["track_rms"],
        open_loop_rms=o["track_rms"],
        final_delta_e=c["final_delta_e"],
        diverged=c["diverged"],
        notes="unwrapped FF+FB; lock mid-node then track; sensor lag/bias/dropout",
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
        "ff_blend": FF_BLEND,
        "ratio": RATIO,
        "alpha": ALPHA,
        "corridor": CORRIDOR,
        "noise_std": NOISE_STD,
        "uses_core": True,
        "lock_then_track": True,
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
        ell = np.array([h["ell"] for h in history])
        locked = ell > 0.5
        lt = float(t[np.argmax(locked)]) if locked.any() else None

        fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        axs[0].plot(t, de, lw=1.2)
        axs[0].axhline(CORRIDOR, color="r", ls="--")
        if lt is not None:
            axs[0].axvline(lt, color="purple", ls=":", label="lock")
            axs[0].legend(frameon=False)
        axs[0].set_ylabel(r"$\Delta E$")
        axs[0].set_title("Spatial match (core): lock mid-node then track")
        axs[0].grid(alpha=0.3)

        axs[1].plot(t, node, label="measured node", lw=1.2)
        axs[1].plot(t, des, "--", label="target", lw=1.2)
        axs[1].set_ylabel("Node position")
        axs[1].legend(frameon=False)
        axs[1].grid(alpha=0.3)

        axs[2].plot(t, phi, label=r"$\phi$", color="orange", lw=1.2)
        axs[2].axhline(RATIO, color="green", ls="--", alpha=0.5, label="ratio=1")
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
    assert csum["lock_in"], "failed quiet-window lock"
    assert csum["time_to_lock_s"] < 2.0
    assert csum["mean_abs_err"] < 0.03
    assert csum["mean_abs_err_tail"] < 0.015
    assert csum["corridor_fraction"] > 0.85
    assert csum["mean_abs_err"] < 0.35 * osum["mean_abs_err"]

    return {
        "ok": True,
        "closed": csum,
        "open": osum,
        "scorecard": make_scorecard(closed, open_),
    }


def print_summary(summary: dict[str, float], label: str = "closed") -> None:
    lt = summary["time_to_lock_s"]
    lock_s = f" at {lt:.3f} s" if summary["lock_in"] and not np.isnan(lt) else ""
    print(f"[{label}] Lock-in{lock_s}")
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
        print(result["scorecard"].row())
        print_summary(result["closed"], "closed")
        print_summary(result["open"], "open")
        return

    history = run_loop(seed=args.seed, closed_loop=True)
    open_ = run_loop(seed=args.seed, closed_loop=False)
    card = make_scorecard(history, open_)
    summary = card.to_dict()
    print_summary(compute_metrics(history), "closed")
    print(card.row())
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
