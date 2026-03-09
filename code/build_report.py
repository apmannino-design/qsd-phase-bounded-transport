from pathlib import Path
import pandas as pd


def safe_read_csv(path):
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return None


def df_to_md(df, index=False):
    if df is None or df.empty:
        return "_No data available._"
    try:
        return df.to_markdown(index=index)
    except Exception:
        return df.to_string(index=index)


def main():

    root = Path(__file__).resolve().parents[1]
    results = root / "results"
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    domain = safe_read_csv(results / "domain_comparison_summary.csv")
    surrogate = safe_read_csv(results / "surrogate_significance_summary.csv")
    spectral = safe_read_csv(results / "spectral_null_summary.csv")
    master = safe_read_csv(results / "master_summary_table.csv")

    report_path = report_dir / "qsd_report.md"

    lines = []

    lines.append("# QSD Cross-Domain Validation Report\n")

    lines.append("## Included domains\n")
    lines.append("- GOES solar X-ray flux")
    lines.append("- Planetary K-index")
    lines.append("- LIGO strain\n")

    lines.append("## 1. Domain Comparison Summary\n")
    lines.append(df_to_md(domain))

    lines.append("\n## 2. Surrogate Significance Summary\n")
    lines.append(df_to_md(surrogate))

    lines.append("\n## 3. Spectral Null Summary (IAAFT)\n")
    lines.append(df_to_md(spectral))

    lines.append("\n## 4. Master Summary Table\n")
    lines.append(df_to_md(master))

    lines.append("\n## 5. Reproducibility\n")
    lines.append("Run the full pipeline with:\n")
    lines.append("```bash")
    lines.append("python3 scripts/run_all.py")
    lines.append("```")

    report_path.write_text("\n".join(lines))

    print("Saved:", report_path)


if __name__ == "__main__":
    main()
