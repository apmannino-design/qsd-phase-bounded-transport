from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_ar1(series: pd.Series, window: int = 60) -> np.ndarray:
    vals = series.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan, dtype=float)

    for i in range(window, len(vals) + 1):
        x = vals[i - window : i]
        x0 = x[:-1]
        x1 = x[1:]
        if np.nanstd(x0) == 0 or np.nanstd(x1) == 0:
            out[i - 1] = 0.0
        else:
            out[i - 1] = np.corrcoef(x0, x1)[0, 1]

    return out


def compute_hazard_survival(
    time_tag: pd.Series,
    eta: pd.Series,
    delta_e: pd.Series,
    eta_threshold: float = 0.55,
    delta_e_gate: float = 0.2248,
    refractory_minutes: int = 30,
) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "time_tag": pd.to_datetime(time_tag, utc=True),
            "eta": pd.to_numeric(eta, errors="coerce"),
            "delta_e": pd.to_numeric(delta_e, errors="coerce"),
        }
    )

    df["eta_std_60"] = df["eta"].rolling(60, min_periods=5).std()
    df["ar1_60"] = rolling_ar1(df["eta"], window=60)
    df["ar1_pos"] = np.clip(df["ar1_60"].fillna(0.0), 0.0, None)

    armed = (df["eta"] < eta_threshold) & (df["delta_e"] > delta_e_gate)
    df["corridor_armed"] = armed.astype(int)

    hazard = (
        0.50 * (1.0 - df["eta"].fillna(1.0))
        + 0.30 * df["ar1_pos"].fillna(0.0)
        + 0.20 * df["eta_std_60"].fillna(0.0)
    )
    hazard = np.clip(hazard, 0.0, None)
    df["hazard_signal"] = hazard

    lambda_rate = np.where(df["corridor_armed"].to_numpy() == 1, df["hazard_signal"].to_numpy(), 0.0)
    df["lambda_rate"] = lambda_rate

    survival = np.ones(len(df), dtype=float)
    cooldown = 0

    for i in range(1, len(df)):
        if cooldown > 0:
            survival[i] = 1.0
            cooldown -= 1
            continue

        if df["corridor_armed"].iat[i] == 1:
            survival[i] = survival[i - 1] * np.exp(-lambda_rate[i])
        else:
            survival[i] = 1.0

        if survival[i] < 0.20:
            cooldown = refractory_minutes
            survival[i] = 1.0

    df["survival"] = survival
    return df[["time_tag", "eta_std_60", "ar1_60", "hazard_signal", "lambda_rate", "survival", "corridor_armed"]]
