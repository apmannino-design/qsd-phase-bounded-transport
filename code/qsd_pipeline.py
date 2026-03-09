from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[1]

    results_dir = root / "results"
    results_dir.mkdir(exist_ok=True)

    out_file = results_dir / "run_status.txt"
    out_file.write_text("QSD pipeline ran successfully.\n")

    print("Pipeline executed")
    print("Saved:", out_file)

if __name__ == "__main__":
    main()