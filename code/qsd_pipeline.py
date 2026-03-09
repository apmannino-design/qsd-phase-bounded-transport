from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from goes_loader import download_goes_xrs_json, load_local_goes_csv
from trilock_detector import detect_trilock_events
from hazard_survival_engine import compute_hazard_survival


def robust_delta_e(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    dx = np.abs(np.diff(x, prepend=x[0]))

    med = np.nanmedian(dx)
    mad = np.nanmedian(np.abs(dx - med))
    scale = 1.4826 * mad if mad > 0 else np.nanstd(dx)

    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0

    delta_e = (dx - med) / scale
    delta_e = np.clip(delta_e, 0.0, None)
    return delta_e


def rolling_mass(x: np.ndarray, window: int) -> np.ndarray:
    s = pd.Series(x, dtype=float)
    return s.rolling(window=window, min_periods=1).sum().to_numpy()


def rolling_mismatch_std(x: np.ndarray, window: int) -> np.ndarray:
    s = pd.Series(x, dtype=float)
    return s.diff().abs().rolling(window=window, min_periods=2).std().to_numpy()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    results_dir = root / "results"
    figures_dir = results_dir / "figures_generated"

    data_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    local_csv = data_dir / "goes_xrs_7day.csv"

    try:
        if local_csv.exists():
            load_result = load_local_goes_csv(local_csv)
            print(f"Loaded local GOES CSV: {local_csv}")
        else:
            load_result = download_goes_xrs_json(save_csv_path=local_csv)
            print(f"Downloaded GOES JSON from: {load_result.source}")
            print(f"Saved normalized CSV to: {local_csv}")
    except Exception as e:
        raise RuntimeError(
            f"Failed to load GOES data. Update code/goes_loader.py if needed. Original error: {e}"
        ) from e

    df = load_result.dataframe.copy()

    flux = df["long_flux"].copy()
    if flux.isna().all():
        flux = df["short_flux"].copy()

    flux = pd.to_numeric(flux, errors="coerce")
    valid = flux.notna()

    work = df.loc[valid, ["time_tag"]].copy()
    work["flux"] = flux.loc[valid].to_numpy(dtype=float)

    if len(work) < 20:
        raise RuntimeError("Not enough valid GOES samples after cleaning.")

    work["delta_e"] = robust_delta_e(work["flux"].to_numpy())
    work["mass_12h"] = rolling_mass(work["delta_e"].to_numpy(), window=12 * 60)
    work["mismatch_std_60m"] = rolling_mismatch_std(work["flux"].to_numpy(), window=60)

    denom = np.where(work["mass_12h"].to_numpy() > 0, work["mass_12h"].to_numpy(), np.nan)
    ratio = work["mismatch_std_60m"].to_numpy() / denom
    finite_ratio = ratio[np.isfinite(ratio)]
    fill_value = np.nanmedian(finite_ratio) if finite_ratio.size else 0.0
    ratio = np.nan_to_num(ratio, nan=fill_value)

    delta_e_crit = 0.2248
    k = 12.0
    work["eta"] = 1.0 / (1.0 + np.exp(k * (work["delta_e"].to_numpy() - delta_e_crit)))

    hazard_df = compute_hazard_survival(
        time_tag=work["time_tag"],
        eta=work["eta"],
        delta_e=work["delta_e"],
    )

    events_df = detect_trilock_events(
        time_tag=work["time_tag"],
        eta=work["eta"],
        delta_e=work["delta_e"],
        hazard_signal=hazard_df["hazard_signal"],
        survival=hazard_df["survival"],
    )

    out_df = work.merge(hazard_df, on="time_tag", how="left")

    out_main = results_dir / "goes_qsd_timeseries.csv"
    out_events = results_dir / "event_table.csv"
    out_summary = results_dir / "goes_trilock_summary.csv"

    out_df.to_csv(out_main, index=False)
    events_df.to_csv(out_events, index=False)

    summary = pd.DataFrame(
        [
            {
                "n_samples": int(len(out_df)),
                "flux_min": float(np.nanmin(out_df["flux"])),
                "flux_max": float(np.nanmax(out_df["flux"])),
                "delta_e_mean": float(np.nanmean(out_df["delta_e"])),
                "eta_mean": float(np.nanmean(out_df["eta"])),
                "hazard_mean": float(np.nanmean(out_df["hazard_signal"])),
                "min_survival": float(np.nanmin(out_df["survival"])),
                "n_events": int(len(events_df)),
            }
        ]
    )
    summary.to_csv(out_summary, index=False)

    print("QSD pipeline executed.")
    print(f"Saved: {out_main}")
    print(f"Saved: {out_events}")
    print(f"Saved: {out_summary}")


if __name__ == "__main__":
    main()