import numpy as np
import pandas as pd
from pathlib import Path

from ligo_loader import load_ligo_data
from hazard_survival_engine import compute_hazard_survival
from trilock_detector import detect_trilock_events


def robust_delta_e(x):
    x = np.asarray(x, dtype=float)
    dx = np.abs(np.diff(x, prepend=x[0]))
    med = np.nanmedian(dx)
    mad = np.nanmedian(np.abs(dx - med))
    scale = 1.4826 * mad if mad > 0 else np.nanstd(dx)
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    z = (dx - med) / scale
    return np.clip(z, 0.0, None)


def main():
    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    figures = results / "figures_generated"

    results.mkdir(exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    df = load_ligo_data()

    # Convert GPS-like float seconds into UTC datetimes for compatibility
    df["time_tag"] = pd.to_datetime(df["time"], unit="s", utc=True)

    df["delta_e"] = robust_delta_e(df["strain"].values)

    delta_e_crit = 0.2248
    k = 12.0
    df["eta"] = 1.0 / (1.0 + np.exp(k * (df["delta_e"] - delta_e_crit)))

    hazard = compute_hazard_survival(
        time_tag=df["time_tag"],
        eta=df["eta"],
        delta_e=df["delta_e"]
    )

    events = detect_trilock_events(
        time_tag=df["time_tag"],
        eta=df["eta"],
        delta_e=df["delta_e"],
        hazard_signal=hazard["hazard_signal"],
        survival=hazard["survival"]
    )

    df_out = df.merge(hazard, on="time_tag", how="left")

    out_ts = results / "ligo_qsd_timeseries.csv"
    out_ev = results / "ligo_event_table.csv"

    df_out.to_csv(out_ts, index=False)
    events.to_csv(out_ev, index=False)

    print("LIGO validation complete")
    print("Saved:", out_ts)
    print("Saved:", out_ev)


if __name__ == "__main__":
    main()
