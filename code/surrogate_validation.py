from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def compute_metrics(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    dx = np.abs(np.diff(x, prepend=x[0]))

    med = np.nanmedian(dx)
    mad = np.nanmedian(np.abs(dx - med))
    scale = 1.4826 * mad if mad > 0 else np.nanstd(dx)
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0

    delta_e = np.clip((dx - med) / scale, 0.0, None)
    eta = 1.0 / (1.0 + np.exp(12.0 * (delta_e - 0.2248)))

    return {
        "delta_e_mean": float(np.nanmean(delta_e)),
        "delta_e_max": float(np.nanmax(delta_e)),
        "eta_mean": float(np.nanmean(eta)),
        "eta_min": float(np.nanmin(eta)),
        "signal_std": float(np.nanstd(x)),
    }


def shuffled_surrogates(x: np.ndarray, n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []

    for i in range(n):
        xs = np.array(x, copy=True)
        rng.shuffle(xs)
        m = compute_metrics(xs)
        m["surrogate_id"] = i + 1
        rows.append(m)

    return pd.DataFrame(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    results_dir = root / "results"
    figures_dir = results_dir / "figures_generated"
    figures_dir.mkdir(parents=True, exist_ok=True)

    goes_file = results_dir / "goes_qsd_timeseries.csv"
    kp_file = results_dir / "kp_qsd_timeseries.csv"
    ligo_file = results_dir / "ligo_qsd_timeseries.csv"

    inputs = [
        ("GOES", goes_file, "flux"),
        ("Kp", kp_file, "kp"),
        ("LIGO", ligo_file, "strain"),
    ]

    summary_rows = []

    for name, path, signal_col in inputs:
        if not path.exists():
            print(f"Skipping {name}: missing {path}")
            continue

        df = pd.read_csv(path)
        if signal_col not in df.columns:
            print(f"Skipping {name}: missing column '{signal_col}'")
            continue

        x = pd.to_numeric(df[signal_col], errors="coerce").dropna().to_numpy()
        if len(x) < 20:
            print(f"Skipping {name}: not enough samples")
            continue

        real = compute_metrics(x)
        sur = shuffled_surrogates(x, n=100, seed=42)

        out_sur = results_dir / f"{name.lower()}_surrogate_summary.csv"
        sur.to_csv(out_sur, index=False)

        row = {
            "domain": name,
            "real_delta_e_mean": real["delta_e_mean"],
            "null_delta_e_mean_avg": float(sur["delta_e_mean"].mean()),
            "real_eta_mean": real["eta_mean"],
            "null_eta_mean_avg": float(sur["eta_mean"].mean()),
            "real_eta_min": real["eta_min"],
            "null_eta_min_avg": float(sur["eta_min"].mean()),
            "real_vs_null_eta_mean_gap": float(real["eta_mean"] - sur["eta_mean"].mean()),
            "real_vs_null_delta_e_gap": float(real["delta_e_mean"] - sur["delta_e_mean"].mean()),
        }
        summary_rows.append(row)

        plt.figure(figsize=(8, 4.5))
        plt.hist(sur["eta_mean"], bins=20, alpha=0.8)
        plt.axvline(real["eta_mean"], linewidth=2, label="real")
        plt.xlabel("eta_mean")
        plt.ylabel("Count")
        plt.title(f"{name}: Real vs Shuffled-Surrogate eta_mean")
        plt.legend()
        plt.tight_layout()
        fig_path = figures_dir / f"fig_{name.lower()}_surrogate_eta_mean.png"
        plt.savefig(fig_path, dpi=200)
        plt.close()

        print(f"Saved: {out_sur}")
        print(f"Saved: {fig_path}")

    if not summary_rows:
        raise RuntimeError("No valid domain files found for surrogate validation.")

    summary = pd.DataFrame(summary_rows)
    out_summary = results_dir / "surrogate_validation_overview.csv"
    summary.to_csv(out_summary, index=False)

    print("Saved:", out_summary)
    print(summary)


if __name__ == "__main__":
    main()
