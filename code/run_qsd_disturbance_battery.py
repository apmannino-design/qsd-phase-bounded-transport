"""
Disturbance battery for lock-in / cascaded plants.

Cases: nominal, step_force, chirp, bias_walk, dropout_burst.
Reports lock-hold rate, recoveries (drops), track RMS, rms_ratio.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qsd_cascaded_plant as casc  # noqa: E402
import qsd_sector_closed_loop as lockin  # noqa: E402

CASES = ("nominal", "step_force", "chirp", "bias_walk", "dropout_burst")


def run_battery(seed: int = 42) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for plant, mod in (("lock_in", lockin), ("cascaded", casc)):
        for case in CASES:
            closed, open_ = mod.paired_closed_open(seed=seed, disturbance=case)
            c = mod.compute_metrics(closed)
            card = mod.make_scorecard(closed, open_)
            rows.append(
                {
                    "plant": plant,
                    "case": case,
                    "lock_in": c["lock_in"],
                    "reached_track": c.get("reached_track", False),
                    "time_to_lock_s": c["time_to_lock_s"],
                    "time_to_track_s": c.get("time_to_track_s", float("nan")),
                    "lock_drop_count": c["lock_drop_count"],
                    "fraction_tracking": c.get("fraction_tracking", float("nan")),
                    "track_rms": card.hold_or_track_rms,
                    "open_rms": card.open_loop_rms,
                    "rms_ratio": card.rms_ratio,
                    "diverged": card.diverged,
                }
            )
    return {"rows": rows, "seed": seed}


def self_test(seed: int = 42) -> None:
    out = run_battery(seed=seed)
    by = {(r["plant"], r["case"]): r for r in out["rows"]}
    assert by[("lock_in", "nominal")]["reached_track"]
    assert by[("lock_in", "nominal")]["lock_drop_count"] <= 2
    assert by[("lock_in", "nominal")]["rms_ratio"] < 0.5
    assert by[("cascaded", "nominal")]["reached_track"]
    # Under stress, should still usually lock (allow drops)
    for case in CASES:
        assert by[("lock_in", case)]["lock_in"], f"lock_in failed {case}"
    print("SELF_TEST: PASS")
    _print(out)


def _print(out: dict[str, Any]) -> None:
    print("=" * 96)
    print("QSD DISTURBANCE BATTERY")
    print("=" * 96)
    print(
        f"{'plant':10} {'case':14} {'track':5} {'drops':5} "
        f"{'ratio':7} {'t_lock':7} {'t_track':7}"
    )
    for r in out["rows"]:
        print(
            f"{r['plant']:10} {r['case']:14} "
            f"{str(r['reached_track']):5} {r['lock_drop_count']:5d} "
            f"{r['rms_ratio']:7.3f} {r['time_to_lock_s']:7.3f} "
            f"{r['time_to_track_s']:7.3f}"
        )
    print("=" * 96)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(args.seed)
        return
    out = run_battery(args.seed)
    _print(out)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "qsd_disturbance_battery.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    # CSV
    rows = out["rows"]
    keys = list(rows[0].keys())
    csv = args.out_dir / "qsd_disturbance_battery.csv"
    csv.write_text(
        ",".join(keys)
        + "\n"
        + "\n".join(",".join(str(r[k]) for k in keys) for r in rows)
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {path}")
    print(f"Wrote {csv}")


if __name__ == "__main__":
    main()
