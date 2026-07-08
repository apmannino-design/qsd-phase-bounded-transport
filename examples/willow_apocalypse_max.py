#!/usr/bin/env python3
"""Max noise + max depth hold test — apocalypse 1241L + Willow 1241L."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.willow_apocalypse import run_max_max_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Max noise max depth QSD hold")
    parser.add_argument("--shots-apocalypse", type=int, default=2048)
    parser.add_argument("--shots-willow", type=int, default=500)
    parser.add_argument("--out", default="results/willow_max_max_hold.json")
    args = parser.parse_args()

    result = run_max_max_campaign(
        shots_apocalypse=args.shots_apocalypse,
        shots_willow=args.shots_willow,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    print(f"\nVERDICT: {result['verdict']}")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
