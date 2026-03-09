from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from iaaft_surrogates import generate_surrogates


def compute_eta(x):

    dx = np.abs(np.diff(x, prepend=x[0]))

    med = np.median(dx)
    mad = np.median(np.abs(dx - med))
    scale = 1.4826 * mad if mad > 0 else np.std(dx)
    if scale <= 0:
        scale = 1.0

    delta_e = np.clip((dx - med) / scale, 0, None)
    eta = 1/(1 + np.exp(12*(delta_e - 0.2248)))

    return np.mean(eta)


def main():

    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    figs = results / "figures_generated"
    figs.mkdir(parents=True, exist_ok=True)

    inputs = [
        ("GOES", results/"goes_qsd_timeseries.csv", "flux"),
        ("Kp", results/"kp_qsd_timeseries.csv", "kp"),
        ("LIGO", results/"ligo_qsd_timeseries.csv", "strain")
    ]

    rows = []

    for name, file, col in inputs:

        if not file.exists():
            continue

        df = pd.read_csv(file)
        x = pd.to_numeric(df[col], errors="coerce").dropna().values

        real_eta = compute_eta(x)

        sur = generate_surrogates(x, n=50)

        eta_null = [compute_eta(s) for s in sur]

        eta_null = np.array(eta_null)

        percentile = (eta_null < real_eta).mean()
        p_value = (eta_null >= real_eta).mean()

        rows.append({
            "domain": name,
            "eta_real": real_eta,
            "eta_null_mean": eta_null.mean(),
            "eta_percentile": percentile,
            "eta_p_value": p_value
        })

        plt.figure(figsize=(7,4))
        plt.hist(eta_null, bins=20)
        plt.axvline(real_eta)
        plt.title(f"{name} IAAFT spectral null test")
        plt.tight_layout()

        fig = figs/f"fig_{name.lower()}_iaaft_null.png"
        plt.savefig(fig, dpi=200)
        plt.close()

        print("Saved:", fig)

    out = pd.DataFrame(rows)
    out_file = results/"spectral_null_summary.csv"
    out.to_csv(out_file, index=False)

    print("\nSpectral null summary\n")
    print(out)
    print("\nSaved:", out_file)


if __name__ == "__main__":
    main()
