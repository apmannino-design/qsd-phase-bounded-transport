#!/usr/bin/env python3
"""
Train/holdout calibration + equal-offload scorecard (forecast OFF vs ON).

  python3 qsd_scorecard_holdout.py --record logs/term.jsonl --beam-id beam-A

Splits the NDJSON recording (first --train-frac), fits calibration on train,
replays holdout under predict=False and predict=True, sweeps headroom_warn to
compare no-lock% at matched offload counts, and writes:
  - calibration.json (predict recommendation applied)
  - scorecard_holdout.json (full table + verdict)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import replace

import numpy as np

from common import CALIBRATION, save
from qsd_calibrate import fit, load_samples
from qsd_terminal import ReplayTerminal
import qsd_stack_v2 as stack


def split_record(path, train_frac, train_path, hold_path, beam_id=None):
    lines = []
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
            lines.append(line)
    if len(lines) < 100:
        raise SystemExit(f"need >=100 samples, got {len(lines)}")
    n_train = max(50, int(len(lines) * train_frac))
    n_train = min(n_train, len(lines) - 40)
    with open(train_path, "w") as f:
        f.write("\n".join(lines[:n_train]) + "\n")
    with open(hold_path, "w") as f:
        f.write("\n".join(lines[n_train:]) + "\n")
    return n_train, len(lines) - n_train


def replay_stats(record_path, beam_id, iface, cfg, max_samples=None):
    term = ReplayTerminal(record_path, beam_id=beam_id, clock_shift=True)
    beam = stack.Beam(beam_id, iface)
    # Disable theta/shape so headroom (+ optional forecast) dominates — matches bench_v2.
    cfg = replace(
        cfg,
        max_sample_age_s=2.0,
        max_sample_gap_s=2.0,
        theta_warn=1.0,
        theta_trip=1.2,
        theta_clear=0.8,
        shape_gate_rms_urad=1e9,  # never arm shape gate
    )
    sup = stack.Supervisor(beam, cfg)
    n = term.remaining if max_samples is None else min(term.remaining, max_samples)
    offloads = relocks = nolock = 0
    for _ in range(n):
        st = sup.tick(term)
        cmds = st.get("command_events") or []
        offloads += int("OFFLOAD" in cmds)
        relocks += int("RELOCK" in cmds)
        # proxy: regime 3 or not sample_valid while trying to run
        if st.get("regime") == 3:
            nolock += 1
        elif st.get("sample_valid") and st.get("coordinates"):
            # count near-limit from headroom if available
            h = (st.get("coordinates") or {}).get("headroom")
            if h is not None and h <= 0:
                nolock += 1
    dur_s = max(n * cfg.period_s, 1e-6)
    return {
        "samples": n,
        "offloads": offloads,
        "relocks": relocks,
        "nolock_steps": nolock,
        "nolock_pct": 100.0 * nolock / max(n, 1),
        "offloads_per_min": offloads / (dur_s / 60.0),
    }


def equal_offload_tables(hold_path, beam_id, iface, base_cal, warns):
    rows = []
    for predict in (False, True):
        for hw in warns:
            cfg = stack.Config(predict=predict)
            hw = float(hw)
            trip = float(base_cal.get("headroom_trip", 0.05))
            clear = float(base_cal.get("headroom_clear", 0.35))
            trip = min(trip, hw - 0.02)
            clear = max(clear, hw + 0.05)
            kw = {
                "predict": predict,
                "headroom_warn": hw,
                "headroom_trip": max(0.01, trip),
                "headroom_clear": min(0.95, clear),
                "r_eff_urad": float(base_cal.get("r_eff_urad", 15.0)),
            }
            if "fsm_limits_urad" in base_cal:
                kw["fsm_limits_urad"] = tuple(base_cal["fsm_limits_urad"])
            cfg = replace(cfg, **kw)
            stats = replay_stats(hold_path, beam_id, iface, cfg)
            rows.append({"predict": predict, "headroom_warn": hw, **stats})
    return rows


def match_reactive_at_budget(rows):
    """For each predictive row, find reactive nolock% at closest offload rate."""
    reac = [r for r in rows if not r["predict"]]
    pred = [r for r in rows if r["predict"]]
    reac = sorted(reac, key=lambda r: r["offloads_per_min"])
    out = []
    for p in pred:
        if not reac:
            out.append({**p, "reactive_nolock_pct_matched": None, "delta_nolock_pct": None})
            continue
        rates = np.array([r["offloads_per_min"] for r in reac])
        i = int(np.argmin(np.abs(rates - p["offloads_per_min"])))
        rn = reac[i]["nolock_pct"]
        out.append({
            **p,
            "reactive_nolock_pct_matched": rn,
            "reactive_offloads_per_min_matched": reac[i]["offloads_per_min"],
            "delta_nolock_pct": p["nolock_pct"] - rn,
            "offload_ratio": (
                p["offloads_per_min"] / reac[i]["offloads_per_min"]
                if reac[i]["offloads_per_min"] > 0 else None
            ),
        })
    return out


def verdict(matched):
    """
    Recommend predict=True only if it reduces no-lock at matched offloads
    without a large offload inflation. Default OFF (stress suite prior).
    """
    if not matched:
        return False, "no_predictive_rows"
    # best predictive delta (more negative = better)
    best = min(matched, key=lambda r: (r["delta_nolock_pct"] is None, r.get("delta_nolock_pct", 0)))
    d = best.get("delta_nolock_pct")
    ratio = best.get("offload_ratio") or 1.0
    if d is None:
        return False, "no_match"
    if d <= -0.05 and ratio <= 1.25:
        return True, f"holdout_gain delta_nolock={d:.3f}% offload_ratio={ratio:.2f}"
    return False, f"no_holdout_gain delta_nolock={d:.3f}% offload_ratio={ratio:.2f} (keep OFF)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", required=True)
    ap.add_argument("--beam-id", default="beam-A")
    ap.add_argument("--interface-id", default="ant-1")
    ap.add_argument("--train-frac", type=float, default=0.6)
    ap.add_argument("--fsm-limit", type=float, default=100.0)
    ap.add_argument("--out-cal", default=CALIBRATION)
    ap.add_argument("--out-scorecard", default=None)
    ap.add_argument("--warns", default="0.15,0.25,0.35,0.50")
    a = ap.parse_args()
    warns = [float(x) for x in a.warns.split(",")]

    tmp = tempfile.mkdtemp(prefix="qsd_hold_")
    train_path = os.path.join(tmp, "train.jsonl")
    hold_path = os.path.join(tmp, "hold.jsonl")
    n_tr, n_ho = split_record(a.record, a.train_frac, train_path, hold_path, a.beam_id)

    cal = fit(load_samples(train_path, a.beam_id), fsm_limit=a.fsm_limit)
    rows = equal_offload_tables(hold_path, a.beam_id, a.interface_id, cal, warns)
    matched = match_reactive_at_budget(rows)
    use_predict, reason = verdict(matched)
    cal["predict"] = use_predict
    cal["holdout_verdict"] = reason
    cal["holdout"] = {"train_samples": n_tr, "hold_samples": n_ho}
    save(a.out_cal, cal)

    score = {
        "train_samples": n_tr,
        "hold_samples": n_ho,
        "rows": rows,
        "matched_predictive": matched,
        "recommend_predict": use_predict,
        "reason": reason,
        "calibration_path": a.out_cal,
    }
    out_sc = a.out_scorecard or os.path.join(
        os.path.dirname(a.out_cal) or ".", "scorecard_holdout.json"
    )
    save(out_sc, score)
    print(json.dumps({
        "recommend_predict": use_predict,
        "reason": reason,
        "train_samples": n_tr,
        "hold_samples": n_ho,
        "calibration": a.out_cal,
        "scorecard": out_sc,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
