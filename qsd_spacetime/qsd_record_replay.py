#!/usr/bin/env python3
"""
Record a terminal session, or replay a recording through stack_v2.

  # Record from the sim plant
  python3 qsd_record_replay.py record --sim --seconds 2 --out /tmp/rec.jsonl

  # Replay through supervisor (forecast OFF/ON) and write status + metrics
  python3 qsd_record_replay.py replay --record /tmp/rec.jsonl --beam-id b0

Use real recordings the same way once HardwareTerminal is wired.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from common import LOCAL_METRICS, STATUS, save
import qsd_stack_v2 as stack
from qsd_terminal import (
    RecordingTerminal,
    ReplayExhausted,
    ReplayTerminal,
    SimStackTerminal,
)
from qsd_daemon import _local_from_stack_states


def cmd_record(a):
    term = SimStackTerminal(seed=a.seed, vib_amp=a.vib_amp, vib_hz=a.vib_hz)
    wrapped = RecordingTerminal(term, a.out)
    beam = stack.Beam(a.beam_id, a.interface_id)
    # Drive a short open-loop read loop so the recording has samples.
    # (Supervisor also records if --via-supervisor.)
    if a.via_supervisor:
        # Seed BEAMS-compatible run via direct supervisor ticks
        supervisors = [stack.Supervisor(beam, stack.Config(predict=a.predict))]
        t0 = time.monotonic()
        while time.monotonic() - t0 < a.seconds:
            supervisors[0].tick(wrapped)
            time.sleep(0.001)
    else:
        t0 = time.monotonic()
        while time.monotonic() - t0 < a.seconds:
            wrapped.read(beam)
            time.sleep(0.001)
    n = sum(1 for _ in open(a.out))
    print(f"wrote {n} lines -> {a.out}")
    return 0


def cmd_replay(a):
    term = ReplayTerminal(a.record, beam_id=a.beam_id, clock_shift=True)
    beam = stack.Beam(a.beam_id, a.interface_id)
    cfg = stack.Config(predict=a.predict)
    # Loosen age checks: replay clocks are remapped but gaps may be irregular.
    from dataclasses import replace
    cfg = replace(cfg, max_sample_age_s=1.0, max_sample_gap_s=1.0)
    sup = stack.Supervisor(beam, cfg)
    states = []
    # Drive from the recording length — Supervisor.tick swallows ordinary
    # exceptions as DEGRADED, so exhaustion is checked explicitly.
    n = term.remaining if a.max_samples is None else min(term.remaining, a.max_samples)
    for _ in range(n):
        try:
            st = sup.tick(term)
        except ReplayExhausted:
            break
        states.append(st)
    if not states:
        print("no states produced", file=sys.stderr)
        return 1
    snap = {
        "schema_version": 1,
        "published_unix_s": time.time(),
        "beams": {a.beam_id: states[-1]},
        "controller": "stack_v2_replay",
        "predict": a.predict,
        "replay_samples": len(states),
    }
    out_status = a.status or STATUS
    stack.atomic_json(out_status, snap)
    save(LOCAL_METRICS, {
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "controller": "stack_v2_replay",
        "predict": a.predict,
        "beams": _local_from_stack_states(snap["beams"]),
    })
    # Summary
    regimes = [s.get("regime") for s in states]
    offloads = sum("OFFLOAD" in (s.get("command_events") or []) for s in states)
    relocks = sum("RELOCK" in (s.get("command_events") or []) for s in states)
    print(json.dumps({
        "samples": len(states),
        "offloads": offloads,
        "relocks": relocks,
        "final_regime": regimes[-1],
        "status": out_status,
        "predict": a.predict,
    }, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record")
    r.add_argument("--out", required=True)
    r.add_argument("--seconds", type=float, default=2.0)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--vib-amp", type=float, default=0.0)
    r.add_argument("--vib-hz", type=float, default=5.0)
    r.add_argument("--beam-id", default="beam-A")
    r.add_argument("--interface-id", default="ant-1")
    r.add_argument("--via-supervisor", action="store_true")
    r.add_argument("--predict", action="store_true")
    r.add_argument("--sim", action="store_true", default=True)

    p = sub.add_parser("replay")
    p.add_argument("--record", required=True)
    p.add_argument("--beam-id", default="beam-A")
    p.add_argument("--interface-id", default="ant-1")
    p.add_argument("--predict", action="store_true")
    p.add_argument("--status", default=None)
    p.add_argument("--max-samples", type=int, default=None)

    a = ap.parse_args()
    if a.cmd == "record":
        return cmd_record(a)
    return cmd_replay(a)


if __name__ == "__main__":
    sys.exit(main())
