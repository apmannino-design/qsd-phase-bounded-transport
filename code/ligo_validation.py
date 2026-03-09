import numpy as np
import pandas as pd
from pathlib import Path

from ligo_loader import load_ligo_data
from hazard_survival_engine import compute_hazard_survival
from trilock_detector import detect_trilock_events


def robust_delta_e(x):
    dx = np.abs(np.diff(x, prepend=x[0]))
    med = np.median(dx)
    mad = np.median(np.abs(dx - med))
    scale = 1.4826 * mad if mad > 0 else np.std(dx)
    if scale == 0:
        scale = 1.0
    z = (dx - med) / scale
    return np.clip(z, 0, None)


def main():

    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    figures = results / "figures_generated"

    results.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)

    df = load_ligo_data()

    df["delta_e"] = robust_delta_e(df["strain"].values)

    delta_e_crit = 0.2248
    k = 12.0

    df["eta"] = 1/(1 + np.exp(k*(df["delta_e"] - delta_e_crit)))

    hazard = compute_hazard_survival(
        time_tag=df["time"],
        eta=df["eta"],
        delta_e=df["delta_e"]
    )

    events = detect_trilock_events(
        time_tag=df["time"],
        eta=df["eta"],
        delta_e=df["delta_e"],
        hazard_signal=hazard["hazard_signal"],
        survival=hazard["survival"]
    )

    df_out = df.merge(hazard, left_on="time", right_on="time_tag")

    df_out.to_csv(results/"ligo_qsd_timeseries.csv", index=False)
    events.to_csv(results/"ligo_event_table.csv", index=False)

    print("LIGO validation complete")
    print("Saved:", results/"ligo_qsd_timeseries.csv")
    print("Saved:", results/"ligo_event_table.csv")


if __name__ == "__main__":
    main()
