from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from kp_loader import download_kp_json, load_local_kp_csv
from hazard_survival_engine import compute_hazard_survival
from trilock_detector import detect_trilock_events


def robust_delta_e(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    dx = np.abs(np.diff(x, prepend=x[0]))
    med = np.nanmedian(dx)
    mad = np.nanmedian(np.abs(dx - med))
    scale = 1.4826 * mad if mad > 0 else np.nanstd(dx)
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    z = (dx - med) / scale
    return np.clip(z, 0.0, None)


def run_kp_validation(root: Path) -> None:
    data_dir = root / "data"
    results_dir = root / "results"
    figures_dir = results_dir / "figures_generated"

    data_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    local_csv = data_dir / "planetary_k_index_1m.csv"

    if local_csv.exists():
        load_result = load_local_kp_csv(local_csv)
        print(f"Loaded local Kp CSV: {local_csv}")
    else:
        load_result = download_kp_json(save_csv_path=local_csv)
        print(f"Downloaded Kp JSON from: {load_result.source}")
        print(f"Saved normalized CSV to: {local_csv}")

    df = load_result.dataframe.copy()
    if len(df) < 20:
        raise RuntimeError("Not enough Kp samples after cleaning.")

    df["delta_e"] = robust_delta_e(df["kp"].to_numpy())
    delta_e_crit = 0.2248
    k = 12.0
    df["eta"] = 1.0 / (1.0 + np.exp(k * (df["delta_e"].to_numpy() - delta_e_crit)))

    hazard_df = compute_hazard_survival(
        time_tag=df["time_tag"],
        eta=df["eta"],
        delta_e=df["delta_e"],
    )

    events_df = detect_trilock_events(
        time_tag=df["time_tag"],
        eta=df["eta"],
        delta_e=df["delta_e"],
        hazard_signal=hazard_df["hazard_signal"],
        survival=hazard_df["survival"],
    )

    out_df = df.merge(hazard_df, on="time_tag", how="left")

    out_main = results_dir / "kp_qsd_timeseries.csv"
    out_events = results_dir / "kp_event_table.csv"
    out_summary = results_dir / "kp_validation_summary.csv"

    out_df.to_csv(out_main, index=False)
    events_df.to_csv(out_events, index=False)

    summary = pd.DataFrame([{
        "n_samples": int(len(out_df)),
        "kp_min": float(np.nanmin(out_df["kp"])),
        "kp_max": float(np.nanmax(out_df["kp"])),
        "delta_e_mean": float(np.nanmean(out_df["delta_e"])),
        "eta_mean": float(np.nanmean(out_df["eta"])),
        "hazard_mean": float(np.nanmean(out_df["hazard_signal"])),
        "min_survival": float(np.nanmin(out_df["survival"])),
        "n_events": int(len(events_df)),
    }])
    summary.to_csv(out_summary, index=False)

    plt.figure(figsize=(10, 4.5))
    plt.plot(out_df["time_tag"], out_df["kp"], label="Kp")
    plt.plot(out_df["time_tag"], out_df["delta_e"], label="ΔE proxy")
    plt.xlabel("Time")
    plt.ylabel("Value")
    plt.title("Planetary K-index and ΔE Proxy")
    plt.legend()
    plt.tight_layout()
    fig1 = figures_dir / "fig_kp_deltae.png"
    plt.savefig(fig1, dpi=200)
    plt.close()

    plt.figure(figsize=(10, 4.5))
    plt.plot(out_df["time_tag"], out_df["eta"], label="eta")
    plt.plot(out_df["time_tag"], out_df["hazard_signal"], label="hazard_signal")
    plt.plot(out_df["time_tag"], out_df["survival"], label="survival")
    plt.xlabel("Time")
    plt.ylabel("Value")
    plt.title("Kp Validation: Organization, Hazard, and Survival")
    plt.legend()
    plt.tight_layout()
    fig2 = figures_dir / "fig_kp_eta_hazard_survival.png"
    plt.savefig(fig2, dpi=200)
    plt.close()

    print("Kp validation complete.")
    print(f"Saved: {out_main}")
    print(f"Saved: {out_events}")
    print(f"Saved: {out_summary}")
    print(f"Saved: {fig1}")
    print(f"Saved: {fig2}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    run_kp_validation(root)


if __name__ == "__main__":
    main()
