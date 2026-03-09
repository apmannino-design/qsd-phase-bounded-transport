from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    figs = results / "figures_generated"
    figs.mkdir(parents=True, exist_ok=True)

    domain = pd.read_csv(results / "domain_comparison_summary.csv")
    sig = pd.read_csv(results / "surrogate_significance_summary.csv")

    merged = domain.merge(sig, on="domain", how="left")

    plt.figure(figsize=(9, 5))
    plt.plot(merged["domain"], merged["eta_mean"], marker="o", label="eta_mean")
    plt.plot(merged["domain"], merged["hazard_mean"], marker="o", label="hazard_mean")
    plt.plot(merged["domain"], merged["min_survival"], marker="o", label="min_survival")
    plt.ylabel("Value")
    plt.title("Cross-Domain QSD Summary")
    plt.legend()
    plt.tight_layout()

    out = figs / "fig_cross_domain_summary.png"
    plt.savefig(out, dpi=200)
    plt.close()

    print("Saved:", out)


if __name__ == "__main__":
    main()
