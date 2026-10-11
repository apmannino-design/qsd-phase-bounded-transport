"""
Unified QSD scorecard runner.

Runs opto-acoustic, realtime lock-in, and spatial-match demos against
qsd_control_core and prints / saves one comparable scorecard table.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qsd_control_core import print_scorecard_table, save_scorecards  # noqa: E402
import qsd_opto_acoustic as opto  # noqa: E402
import qsd_sector_closed_loop as lockin  # noqa: E402
import qsd_spatial_match as spatial  # noqa: E402


def collect(seed_opto: int = 1, seed_lock: int = 42, seed_spatial: int = 42):
    cards = []

    c = opto.run_loop(seed=seed_opto, closed_loop=True)
    o = opto.run_loop(seed=seed_opto, closed_loop=False)
    cards.append(opto.make_scorecard(c, o))

    c = lockin.run_loop(seed=seed_lock, closed_loop=True)
    o = lockin.run_loop(seed=seed_lock, closed_loop=False)
    cards.append(lockin.make_scorecard(c, o))

    c = spatial.run_loop(seed=seed_spatial, closed_loop=True)
    o = spatial.run_loop(seed=seed_spatial, closed_loop=False)
    cards.append(spatial.make_scorecard(c, o))

    return cards


def self_test() -> None:
    # Per-demo self-tests (assert thresholds)
    opto.self_test()
    lockin.self_test()
    spatial.self_test()
    cards = collect()
    assert len(cards) == 3
    assert all(not c.diverged for c in cards)
    by_name = {c.demo: c for c in cards}
    assert by_name["opto_acoustic"].corridor_fraction > 0.9
    assert by_name["spatial_match"].corridor_fraction > 0.85
    assert by_name["lock_in"].lock_in and by_name["lock_in"].time_to_lock_s < 1.0
    assert by_name["lock_in"].hold_or_track_rms < by_name["lock_in"].open_loop_rms
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
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
