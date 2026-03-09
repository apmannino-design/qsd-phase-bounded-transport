from __future__ import annotations

import pandas as pd


EVENT_COLUMNS = [
    "event_start",
    "event_end",
    "duration_samples",
    "peak_time",
    "peak_hazard",
    "min_survival",
    "mean_eta",
    "mean_delta_e",
]


def detect_trilock_events(
    time_tag: pd.Series,
    eta: pd.Series,
    delta_e: pd.Series,
    hazard_signal: pd.Series,
    survival: pd.Series,
    survival_threshold: float = 0.35,
    min_run: int = 3,
) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "time_tag": pd.to_datetime(time_tag, utc=True),
            "eta": pd.to_numeric(eta, errors="coerce"),
            "delta_e": pd.to_numeric(delta_e, errors="coerce"),
            "hazard_signal": pd.to_numeric(hazard_signal, errors="coerce"),
            "survival": pd.to_numeric(survival, errors="coerce"),
        }
    )

    cond = (
        (df["eta"] < 0.55)
        & (df["delta_e"] > 0.2248)
        & (df["survival"] < survival_threshold)
    )

    df["trigger"] = cond.astype(int)

    events = []
    run_start = None

    for i, flag in enumerate(df["trigger"].to_numpy()):
        if flag and run_start is None:
            run_start = i
        elif not flag and run_start is not None:
            run_len = i - run_start
            if run_len >= min_run:
                seg = df.iloc[run_start:i]
                peak_idx = seg["hazard_signal"].idxmax()
                peak_row = df.loc[peak_idx]
                events.append(
                    {
                        "event_start": seg["time_tag"].iloc[0],
                        "event_end": seg["time_tag"].iloc[-1],
                        "duration_samples": int(run_len),
                        "peak_time": peak_row["time_tag"],
                        "peak_hazard": float(peak_row["hazard_signal"]),
                        "min_survival": float(seg["survival"].min()),
                        "mean_eta": float(seg["eta"].mean()),
                        "mean_delta_e": float(seg["delta_e"].mean()),
                    }
                )
            run_start = None

    if run_start is not None:
        run_len = len(df) - run_start
        if run_len >= min_run:
            seg = df.iloc[run_start:]
            peak_idx = seg["hazard_signal"].idxmax()
            peak_row = df.loc[peak_idx]
            events.append(
                {
                    "event_start": seg["time_tag"].iloc[0],
                    "event_end": seg["time_tag"].iloc[-1],
                    "duration_samples": int(run_len),
                    "peak_time": peak_row["time_tag"],
                    "peak_hazard": float(peak_row["hazard_signal"]),
                    "min_survival": float(seg["survival"].min()),
                    "mean_eta": float(seg["eta"].mean()),
                    "mean_delta_e": float(seg["delta_e"].mean()),
                }
            )

    return pd.DataFrame(events, columns=EVENT_COLUMNS)
