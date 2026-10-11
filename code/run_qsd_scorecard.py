"""
Unified QSD scorecard runner.

Headline metric: rms_ratio = closed_rms / open_rms (same stage clock where applicable).
Includes opto, lock-in, spatial, and cascaded plant.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qsd_control_core import (  # noqa: E402
    print_scorecard_table,
    save_gain_schedule,
    save_scorecards,
)
import qsd_cascaded_plant as casc  # noqa: E402
import qsd_opto_acoustic as opto  # noqa: E402
import qsd_sector_closed_loop as lockin  # noqa: E402
import qsd_spatial_match as spatial  # noqa: E402


def collect(seed_opto: int = 1, seed_lock: int = 42, seed_spatial: int = 42, seed_casc: int = 42):
    cards = []

    c = opto.run_loop(seed=seed_opto, closed_loop=True)
    o = opto.run_loop(seed=seed_opto, closed_loop=False)
    cards.append(opto.make_scorecard(c, o))

    c, o = lockin.paired_closed_open(seed=seed_lock)
    cards.append(lockin.make_scorecard(c, o))

    c = spatial.run_loop(seed=seed_spatial, closed_loop=True)
    o = spatial.run_loop(seed=seed_spatial, closed_loop=False)
    cards.append(spatial.make_scorecard(c, o))

    c, o = casc.paired_closed_open(seed=seed_casc)
    cards.append(casc.make_scorecard(c, o))

    return cards


def self_test() -> None:
    opto.self_test()
    lockin.self_test()
    spatial.self_test()
    casc.self_test()
    cards = collect()
    assert len(cards) == 4
    assert all(not c.diverged for c in cards)
    by_name = {c.demo: c for c in cards}
    assert by_name["opto_acoustic"].corridor_fraction > 0.9
    assert by_name["spatial_match"].corridor_fraction > 0.85
    assert by_name["lock_in"].lock_in and by_name["lock_in"].rms_ratio < 0.5
    assert by_name["cascaded"].lock_in and by_name["cascaded"].rms_ratio < 1.0
    print("SELF_TEST: PASS")
    print_scorecard_table(cards)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    cards = collect()
    print_scorecard_table(cards)
    path = save_scorecards(cards, args.out_dir / "qsd_scorecard.json")
    sched = save_gain_schedule(args.out_dir / "qsd_gain_schedule.csv")
    print(f"Wrote {path}")
    print(f"Wrote {sched}")


if __name__ == "__main__":
    main()
