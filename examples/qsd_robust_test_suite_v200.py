#!/usr/bin/env python3
"""
QSD Robust Test Suite v2.0.0 — CLI entry point.

Preregistered tests T1–T4 on IBM Quantum / Aer simulators.

Mac — run ONE command at a time:

  python3 examples/qsd_robust_test_suite_v200.py --mode sim

  python3 examples/qsd_robust_test_suite_v200.py --mode sim --only T1,T2

  python3 examples/qsd_robust_test_suite_v200.py --mode hw --backend ibm_fez --qubits 20,21,36 --only T1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from aurora_qsd.quantum.robust_test_suite import (
    load_prereg_v200,
    run_robust_suite,
    save_report,
)

RESULTS = Path("results")


def main() -> int:
    ap = argparse.ArgumentParser(description="QSD Robust Validation Protocol v2.0.0")
    ap.add_argument("--mode", choices=("sim", "hw"), default="sim", help="sim=aer ideal; hw=IBM Runtime")
    ap.add_argument("--backend", default="ibm_fez")
    ap.add_argument("--qubits", default="20,21,36")
    ap.add_argument("--only", default=None, help="Comma-separated subset: T1,T2,T3,T4")
    ap.add_argument("--campaign-state", default="results/state.json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--show-prereg", action="store_true")
    args = ap.parse_args()

    if args.show_prereg:
        print(json.dumps(load_prereg_v200(), indent=2))
        return 0

    qubits = tuple(int(x) for x in args.qubits.split(","))
    if len(qubits) != 3:
        print("Error: exactly 3 qubits required", file=sys.stderr)
        return 1

    skip: set[str] = set()
    if args.only:
        all_tests = {"T1", "T2", "T3", "T4"}
        skip = all_tests - {x.strip().upper() for x in args.only.split(",")}

    backend = "aer_sim" if args.mode == "sim" else args.backend
    campaign = Path(args.campaign_state) if Path(args.campaign_state).is_file() else None

    print("QSD Robust Validation Protocol v2.0.0")
    print(f"Mode: {args.mode}  backend={backend}  qubits={qubits}")
    print("")

    report = run_robust_suite(
        backend_name=backend,
        qubits=qubits,
        use_hardware=(args.mode == "hw"),
        campaign_state=campaign,
        skip=skip,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = Path(args.out or RESULTS / f"robust_v200_{backend}_{stamp}.json")
    save_report(report, out)

    print("=" * 60)
    print("PREREGISTERED VALIDATION REPORT")
    print("=" * 60)
    for name in ("T1", "T2", "T3", "T4"):
        if name in report.tests:
            t = report.tests[name]
            print(f"  {name}: {t['decision']}  — {t.get('notes', '')}")
    print("")
    print(f"OVERALL: {report.overall}  endorsable={report.endorsable}")
    print(f"Saved: {out}")
    return 0 if report.overall == "ALL_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
