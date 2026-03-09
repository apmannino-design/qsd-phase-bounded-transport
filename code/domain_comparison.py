from pathlib import Path
import pandas as pd


def main():

    root = Path(__file__).resolve().parents[1]
    results = root / "results"

    goes_file = results / "goes_qsd_timeseries.csv"
    kp_file = results / "kp_qsd_timeseries.csv"

    if not goes_file.exists():
        raise FileNotFoundError("Missing GOES results file")

    if not kp_file.exists():
        raise FileNotFoundError("Missing Kp results file")

    goes = pd.read_csv(goes_file)
    kp = pd.read_csv(kp_file)

    summary = pd.DataFrame([
        {
            "domain": "GOES Solar X-ray",
            "samples": len(goes),
            "deltaE_mean": goes["delta_e"].mean(),
            "eta_mean": goes["eta"].mean(),
            "hazard_mean": goes["hazard_signal"].mean(),
            "min_survival": goes["survival"].min()
        },
        {
            "domain": "Planetary K-index",
            "samples": len(kp),
            "deltaE_mean": kp["delta_e"].mean(),
            "eta_mean": kp["eta"].mean(),
            "hazard_mean": kp["hazard_signal"].mean(),
            "min_survival": kp["survival"].min()
        }
    ])

    out = results / "domain_comparison_summary.csv"
    summary.to_csv(out, index=False)

    print("\nDomain comparison summary\n")
    print(summary)
    print("\nSaved:", out)


if __name__ == "__main__":
    main()