from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

DEFAULT_KP_JSON_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"


@dataclass
class KPLoadResult:
    dataframe: pd.DataFrame
    source: str
    saved_path: Optional[Path] = None


def _normalize_kp_json(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}

    time_col = None
    for c in df.columns:
        lc = c.lower()
        if "time" in lc or "tag" in lc:
            time_col = c
            break

    kp_col = None
    for c in df.columns:
        lc = c.lower()
        if lc in {"kp", "k_index", "kindex", "planetary_k"} or "kp" in lc:
            kp_col = c
            break

    if time_col is None or kp_col is None:
        raise ValueError(f"Could not identify time/Kp columns from: {list(df.columns)}")

    out = pd.DataFrame({
        "time_tag": pd.to_datetime(df[time_col], utc=True, errors="coerce"),
        "kp": pd.to_numeric(df[kp_col], errors="coerce"),
    }).dropna(subset=["time_tag", "kp"])

    out = out.sort_values("time_tag").reset_index(drop=True)
    return out


def download_kp_json(
    url: str = DEFAULT_KP_JSON_URL,
    save_csv_path: Optional[Path] = None,
    timeout: int = 30,
) -> KPLoadResult:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    raw = pd.DataFrame(r.json())
    norm = _normalize_kp_json(raw)

    saved_path = None
    if save_csv_path is not None:
        save_csv_path.parent.mkdir(parents=True, exist_ok=True)
        norm.to_csv(save_csv_path, index=False)
        saved_path = save_csv_path

    return KPLoadResult(dataframe=norm, source=url, saved_path=saved_path)


def load_local_kp_csv(csv_path: Path) -> KPLoadResult:
    df = pd.read_csv(csv_path)
    if "time_tag" not in df.columns or "kp" not in df.columns:
        raise ValueError("Local Kp CSV must contain 'time_tag' and 'kp' columns.")
    df["time_tag"] = pd.to_datetime(df["time_tag"], utc=True, errors="coerce")
    df["kp"] = pd.to_numeric(df["kp"], errors="coerce")
    df = df.dropna(subset=["time_tag", "kp"]).sort_values("time_tag").reset_index(drop=True)
    return KPLoadResult(dataframe=df, source=str(csv_path), saved_path=csv_path)
