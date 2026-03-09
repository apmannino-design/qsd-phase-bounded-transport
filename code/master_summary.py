from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    figures = results / "figures_generated"
    figures.mkdir(parents=True, exist_ok=True)

    domain_file = results / "domain_comparison_summary.csv"
    surrogate_file = results / "surrogate_validation_overview.csv"

    if not domain_file.exists():
        raise FileNotFoundError(f"Missing {domain_file}")
    if not surrogate_file.exists():
        raise FileNotFoundError(f"Missing {surrogate_file}")

    dom = pd.read_csv(domain_file)
    sur = pd.read_csv(surrogate_file)

    merged = dom.merge(sur, on="domain", how="outer")
    out_csv = results / "master_summary_table.csv"
    merged.to_csv(out_csv, index=False)

    # Figure 1: eta mean comparison across domains
    plt.figure(figsize=(8, 4.5))
    plt.bar(merged["domain"], merged["eta_mean"])
    plt.ylabel("eta_mean")
    plt.title("Cross-Domain Mean Organization")
    plt.tight_layout()
    fig1 = figures / "fig_master_eta_mean.png"
    plt.savefig(fig1, dpi=200)
    plt.close()

    # Figure 2: real vs null eta gap
    plt.figure(figsize=(8, 4.5))
    plt.bar(merged["domain"], merged["real_vs_null_eta_mean_gap"])
    plt.ylabel("real_vs_null_eta_mean_gap")
    plt.title("Real vs Null Mean Organization Gap")
    plt.tight_layout()
    fig2 = figures / "fig_master_real_vs_null_gap.png"
    plt.savefig(fig2, dpi=200)
    plt.close()

    print("Saved:", out_csv)
    print("Saved:", fig1)
    print("Saved:", fig2)
    print("\nMaster summary table:\n")
    print(merged)


if __name__ == "__main__":
    main()
