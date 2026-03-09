from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from pandas.errors import EmptyDataError


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    results_dir = root / "results"
    figures_dir = results_dir / "figures_generated"
    figures_dir.mkdir(parents=True, exist_ok=True)

    ts_path = results_dir / "goes_qsd_timeseries.csv"
    ev_path = results_dir / "event_table.csv"

    if not ts_path.exists():
        raise FileNotFoundError(
            f"Missing {ts_path}. Run: python3 code/qsd_pipeline.py"
        )

    df = pd.read_csv(ts_path, parse_dates=["time_tag"])

    # Figure 1: flux + delta_e
    plt.figure(figsize=(10, 4.5))
    plt.plot(df["time_tag"], df["flux"], label="Flux")
    plt.plot(df["time_tag"], df["delta_e"], label="ΔE proxy")
    plt.xlabel("Time")
    plt.ylabel("Value")
    plt.title("GOES XRS Flux and ΔE Proxy")
    plt.legend()
    plt.tight_layout()
    fig1 = figures_dir / "fig1_flux_deltae.png"
    plt.savefig(fig1, dpi=200)
    plt.close()

    # Figure 2: eta + hazard + survival
    plt.figure(figsize=(10, 4.5))
    plt.plot(df["time_tag"], df["eta"], label="eta")
    plt.plot(df["time_tag"], df["hazard_signal"], label="hazard_signal")
    plt.plot(df["time_tag"], df["survival"], label="survival")
    plt.xlabel("Time")
    plt.ylabel("Value")
    plt.title("Organization, Hazard, and Survival")
    plt.legend()
    plt.tight_layout()
    fig2 = figures_dir / "fig2_eta_hazard_survival.png"
    plt.savefig(fig2, dpi=200)
    plt.close()

    # Figure 3: armed corridor markers
    plt.figure(figsize=(10, 4.5))
    plt.plot(df["time_tag"], df["corridor_armed"], label="corridor_armed")
    plt.xlabel("Time")
    plt.ylabel("Armed")
    plt.title("Corridor Armed State")
    plt.tight_layout()
    fig3 = figures_dir / "fig3_corridor_armed.png"
    plt.savefig(fig3, dpi=200)
    plt.close()

    # Safe event-table handling
    if ev_path.exists() and ev_path.stat().st_size > 0:
        try:
            ev = pd.read_csv(ev_path, parse_dates=["event_start", "event_end", "peak_time"])
            print(f"Events found: {len(ev)}")
        except EmptyDataError:
            print("Event table exists but is empty. No events detected.")
    else:
        print("No events detected in this run.")

    print("Saved:")
    print(fig1)
    print(fig2)
    print(fig3)


if __name__ == "__main__":
    main()
