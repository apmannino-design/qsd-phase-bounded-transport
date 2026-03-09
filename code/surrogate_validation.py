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
    if scale <= 0:
        scale = 1.0

    delta_e = np.clip((dx - med) / scale, 0.0, None)
    eta = 1.0 / (1.0 + np.exp(12.0 * (delta_e - 0.2248)))

    return {
        "delta_e_mean": float(np.nanmean(delta_e)),
        "eta_mean": float(np.nanmean(eta)),
        "eta_min": float(np.nanmin(eta)),
    }


def shuffled_surrogates(x, n=200, seed=42):

    rng = np.random.default_rng(seed)
    rows = []

    for i in range(n):
        xs = np.array(x, copy=True)
        rng.shuffle(xs)

        m = compute_metrics(xs)
        m["surrogate_id"] = i + 1
        rows.append(m)

    return pd.DataFrame(rows)


def percentile(real, null):
    return float((null < real).mean())


def p_value(real, null):
    return float((null >= real).mean())


def main():

    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    figures = results / "figures_generated"
    figures.mkdir(parents=True, exist_ok=True)

    inputs = [
        ("GOES", results/"goes_qsd_timeseries.csv", "flux"),
        ("Kp", results/"kp_qsd_timeseries.csv", "kp"),
        ("LIGO", results/"ligo_qsd_timeseries.csv", "strain")
    ]

    rows = []

    for name, path, col in inputs:

        if not path.exists():
            continue

        df = pd.read_csv(path)
        x = pd.to_numeric(df[col], errors="coerce").dropna().values

        real = compute_metrics(x)
        sur = shuffled_surrogates(x)

        sur_file = results/f"{name.lower()}_surrogate_summary.csv"
        sur.to_csv(sur_file, index=False)

        eta_real = real["eta_mean"]
        eta_null = sur["eta_mean"].values

        perc = percentile(eta_real, eta_null)
        pval = p_value(eta_real, eta_null)

        rows.append({
            "domain": name,
            "eta_real": eta_real,
            "eta_null_mean": float(eta_null.mean()),
            "eta_percentile": perc,
            "eta_p_value": pval
        })

        plt.figure(figsize=(7,4))
        plt.hist(eta_null, bins=25)
        plt.axvline(eta_real)
        plt.title(f"{name} η distribution vs surrogates")
        plt.tight_layout()

        fig = figures/f"fig_{name.lower()}_null_test.png"
        plt.savefig(fig, dpi=200)
        plt.close()

        print("Saved:", sur_file)
        print("Saved:", fig)

    out = pd.DataFrame(rows)
    out_file = results/"surrogate_significance_summary.csv"
    out.to_csv(out_file, index=False)

    print("\nSignificance summary\n")
    print(out)
    print("\nSaved:", out_file)


if __name__ == "__main__":
    main()