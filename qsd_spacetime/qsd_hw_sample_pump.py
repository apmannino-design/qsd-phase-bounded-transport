#!/usr/bin/env python3
"""
Write QSD_HW_SAMPLE_PATH at the control rate for HardwareTerminal.

Modes:
  --sim     drive SimStackTerminal (integration / dry plant)
  --stdin   read NDJSON Sample-like dicts from stdin (real driver)
  --udp PORT  same as stdin but from UDP datagrams (one JSON object each)

Real terminal integration: have your driver emit JSON matching HardwareTerminal
(read) fields at ~1 kHz, or point this pump at a socket your driver fills.

  QSD_HW_SAMPLE_PATH=state/hw_sample.json python3 qsd_hw_sample_pump.py --sim
  python3 qsd_daemon.py   # reads the same path via HardwareTerminal
"""
from __future__ import annotations

import argparse
import json
import os
import select
import socket
import sys
import time

from common import save
from qsd_terminal import SimStackTerminal
import qsd_stack_v2 as stack


def write_sample(path, sample: stack.Sample, beam_id: str):
    save(path, {
        "beam_id": beam_id,
        "channels": list(sample.channels),
        "sequence": sample.sequence,
        "locked": sample.locked,
        "actuator_ready": sample.actuator_ready,
        "sinr_db": sample.sinr_db,
        "esn0_db": sample.esn0_db,
        "mono_s": sample.mono_s,
        "unix_s": sample.unix_s,
    })


def run_sim(path, beam_id, dt, seconds, seed, vib_amp, vib_hz):
    term = SimStackTerminal(seed=seed, vib_amp=vib_amp, vib_hz=vib_hz)
    beam = stack.Beam(beam_id, beam_id)
    t0 = time.monotonic()
    n = 0
    while seconds is None or time.monotonic() - t0 < seconds:
        write_sample(path, term.read(beam), beam_id)
        n += 1
        if dt > 0:
            time.sleep(dt)
    print(f"sim pump wrote {n} samples -> {path}", file=sys.stderr)


def _parse_obj(obj, beam_id):
    if "channels" not in obj and "fsm_urad" in obj:
        fsm = list(obj["fsm_urad"])
        quad = list(obj.get("quad_urad", [0.0, 0.0]))
        obj = dict(obj, channels=fsm + quad)
    obj.setdefault("mono_s", time.monotonic())
    obj.setdefault("unix_s", time.time())
    obj.setdefault("locked", True)
    obj.setdefault("actuator_ready", True)
    if "sequence" not in obj:
        raise ValueError("sequence required")
    return obj


def run_stdin(path, beam_id):
    n = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        obj = _parse_obj(json.loads(line), beam_id)
        save(path, obj)
        n += 1
    print(f"stdin pump wrote {n} samples -> {path}", file=sys.stderr)


def run_udp(path, beam_id, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.setblocking(False)
    print(f"UDP pump listening on :{port} -> {path}", file=sys.stderr)
    n = 0
    while True:
        r, _, _ = select.select([sock], [], [], 1.0)
        if not r:
            continue
        data, _ = sock.recvfrom(65535)
        obj = _parse_obj(json.loads(data.decode()), beam_id)
        save(path, obj)
        n += 1
        if n % 1000 == 0:
            print(f"udp samples: {n}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=os.environ.get(
        "QSD_HW_SAMPLE_PATH", os.path.join("state", "hw_sample.json")))
    ap.add_argument("--beam-id", default="beam-A")
    ap.add_argument("--dt", type=float, default=0.001)
    ap.add_argument("--seconds", type=float, default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sim", action="store_true")
    mode.add_argument("--stdin", action="store_true")
    mode.add_argument("--udp", type=int, metavar="PORT")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--vib-amp", type=float, default=15.0)
    ap.add_argument("--vib-hz", type=float, default=5.0)
    a = ap.parse_args()
    os.environ["QSD_HW_SAMPLE_PATH"] = a.path
    if a.sim:
        run_sim(a.path, a.beam_id, a.dt, a.seconds or 5.0, a.seed, a.vib_amp, a.vib_hz)
    elif a.stdin:
        run_stdin(a.path, a.beam_id)
    else:
        run_udp(a.path, a.beam_id, a.udp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
