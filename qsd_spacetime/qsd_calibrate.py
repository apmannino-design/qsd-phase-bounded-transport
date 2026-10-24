#!/usr/bin/env python3
"""
Fit stack_v2 Config thresholds from a terminal recording (NDJSON).

Uses RMS of FSM channels and observed headroom distribution. Writes
state/calibration.json (or --out) for the daemon to load.

  python3 qsd_calibrate.py --record logs/terminal.jsonl --out state/calibration.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

from common import CALIBRATION, save


def load_samples(path, beam_id=None):
    xs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("kind") != "sample":
                continue
            if beam_id and rec.get("beam_id") != beam_id:
                continue
            ch = np.asarray(rec["sample"]["channels"], dtype=float)
            if ch.shape[0] < 2 or not np.all(np.isfinite(ch)):
                continue
            xs.append(ch[:2])
    if len(xs) < 50:
        raise SystemExit(f"need >=50 FSM samples, got {len(xs)}")
    return np.stack(xs)


def fit(channels, fsm_limit=100.0, r_eff=None):
    """
    Return Config overrides.
    headroom = 1 - max(|axis|/limit); fit warn/trip/clear from percentiles
    of (1-headroom) during locked-ish operation (exclude saturated samples).
    theta_warn from dominant-axis RMS via atan(rms / r_eff).
    """
    limits = np.array([fsm_limit, fsm_limit], dtype=float)
    abs_x = np.abs(channels)
    saturated = np.any(abs_x >= 0.98 * limits, axis=1)
    use = channels[~saturated]
    if len(use) < 30:
        use = channels
    rms = np.sqrt(np.mean(use**2, axis=0))
    dom = float(np.max(rms))
    headroom = 1.0 - np.max(np.abs(use) / limits, axis=1)
    # Stress levels of *used* headroom (1-headroom): warn at p70, trip at p90
    used = 1.0 - headroom
    p70, p90, p40 = np.percentile(used, [70, 90, 40])
    headroom_warn = float(np.clip(1.0 - p70, 0.05, 0.5))
    headroom_trip = float(np.clip(1.0 - p90, 0.02, headroom_warn - 0.02))
    headroom_clear = float(np.clip(1.0 - p40, headroom_warn + 0.05, 0.9))
    if r_eff is None:
        r_eff = max(dom * 2.0, 5.0)  # placeholder scale if not provided
    # theta such that r_eff * tan(theta) ~= dominant RMS (warn at ~1x RMS)
    theta_warn = float(np.arctan(dom / r_eff))
    theta_warn = float(np.clip(theta_warn, 0.05, 0.6))
    theta_trip = float(min(1.5 * theta_warn, 0.9))
    theta_clear = float(0.6 * theta_warn)
    return {
        "fsm_limits_urad": [float(fsm_limit), float(fsm_limit)],
        "r_eff_urad": float(r_eff),
        "headroom_warn": headroom_warn,
        "headroom_trip": headroom_trip,
        "headroom_clear": headroom_clear,
        "theta_warn": theta_warn,
        "theta_trip": theta_trip,
        "theta_clear": theta_clear,
        "shape_gate_rms_urad": float(max(0.5, 0.25 * dom)),
        "fit_stats": {
            "n": int(len(channels)),
            "n_used": int(len(use)),
            "dominant_rms_urad": dom,
            "rms_urad": [float(x) for x in rms],
            "headroom_p10": float(np.percentile(headroom, 10)),
            "headroom_p50": float(np.percentile(headroom, 50)),
        },
        "predict": False,
        "notes": "Fitted from recording; confirm on held-out data before deploy.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True, help="NDJSON from RecordingTerminal")
    ap.add_argument("--beam-id", default=None)
    ap.add_argument("--fsm-limit", type=float, default=100.0)
    ap.add_argument("--r-eff", type=float, default=None, help="urad; default = 2*dom_rms")
    ap.add_argument("--out", default=CALIBRATION)
    a = ap.parse_args()
    ch = load_samples(a.record, a.beam_id)
    cal = fit(ch, fsm_limit=a.fsm_limit, r_eff=a.r_eff)
    save(a.out, cal)
    print(json.dumps(cal, indent=2))
    print(f"wrote {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
