from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

DEFAULT_XRAY_JSON_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"


@dataclass
class GOESLoadResult:
    dataframe: pd.DataFrame
    source: str
    saved_path: Optional[Path] = None


def _normalize_goes_json(df: pd.DataFrame) -> pd.DataFrame:
    required = {"time_tag", "energy", "flux"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected JSON columns: {sorted(missing)}")

    work = df.copy()
    work["time_tag"] = pd.to_datetime(work["time_tag"], utc=True, errors="coerce")
    work["energy"] = work["energy"].astype(str).str.strip().str.lower()
    work["flux"] = pd.to_numeric(work["flux"], errors="coerce")
    work = work.dropna(subset=["time_tag", "flux"])

    pivot = (
        work.pivot_table(
            index="time_tag",
            columns="energy",
            values="flux",
            aggfunc="last",
        )
        .sort_index()
        .reset_index()
    )

    short_candidates = [c for c in pivot.columns if "0.05" in str(c) and "0.4" in str(c)]
    long_candidates = [c for c in pivot.columns if "0.1" in str(c) and "0.8" in str(c)]

    short_col = short_candidates[0] if short_candidates else None
    long_col = long_candidates[0] if long_candidates else None

    out = pd.DataFrame({"time_tag": pivot["time_tag"]})
    out["short_flux"] = pd.to_numeric(pivot[short_col], errors="coerce") if short_col else pd.NA
    out["long_flux"] = pd.to_numeric(pivot[long_col], errors="coerce") if long_col else pd.NA

    return out.sort_values("time_tag").reset_index(drop=True)


def download_goes_xrs_json(
    url: str = DEFAULT_XRAY_JSON_URL,
    save_csv_path: Optional[Path] = None,
    timeout: int = 30,
) -> GOESLoadResult:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    raw = pd.DataFrame(payload)
    norm = _normalize_goes_json(raw)

    saved_path = None
    if save_csv_path is not None:
        save_csv_path.parent.mkdir(parents=True, exist_ok=True)
        norm.to_csv(save_csv_path, index=False)
        saved_path = save_csv_path

    return GOESLoadResult(dataframe=norm, source=url, saved_path=saved_path)


def load_local_goes_csv(csv_path: Path) -> GOESLoadResult:
    df = pd.read_csv(csv_path)
    if "time_tag" not in df.columns:
        raise ValueError("Local CSV must contain a 'time_tag' column.")

    df["time_tag"] = pd.to_datetime(df["time_tag"], utc=True, errors="coerce")
    for col in ["short_flux", "long_flux"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.NA

    df = df.sort_values("time_tag").reset_index(drop=True)
    return GOESLoadResult(dataframe=df, source=str(csv_path), saved_path=csv_path)