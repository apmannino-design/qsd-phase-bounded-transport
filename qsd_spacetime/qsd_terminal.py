#!/usr/bin/env python3
"""
Terminal hardware contract for qsd_stack_v2.

Drivers implement read / offload / relock. This module provides:
  - HardwareTerminal: file/command backed I/O (env-configured)
  - RecordingTerminal: wraps any terminal, appends NDJSON samples + commands
  - ReplayTerminal: plays a recording back into the supervisor
  - SimStackTerminal: microradian FSM plant for tests (measured SINR optional)

Env for HardwareTerminal:
  QSD_HW_SAMPLE_PATH   JSON file the driver writes with latest Sample fields
  QSD_HW_CMD_PATH      JSONL file this process appends offload/relock/point cmds to
  QSD_HW_OFFLOAD_CMD   optional shell to run on offload (beam_id as $1)
  QSD_HW_RELOCK_CMD    optional shell to run on relock
  QSD_HW_POINT_CMD     optional shell on enact forward: az el beam_id
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Optional

import numpy as np

from common import append_jsonl, load, residual_from_azel
import qsd_stack_v2 as stack


class HardwareTerminal:
    """
    Real-hardware adapter. The terminal (or a thin driver process) writes the
    latest sample to QSD_HW_SAMPLE_PATH; this class reads it. Commands are
    appended to QSD_HW_CMD_PATH and optionally executed via shell hooks.
    """

    def __init__(
        self,
        sample_path: Optional[str] = None,
        cmd_path: Optional[str] = None,
        offload_cmd: Optional[str] = None,
        relock_cmd: Optional[str] = None,
        point_cmd: Optional[str] = None,
    ):
        self.sample_path = sample_path or os.environ.get(
            "QSD_HW_SAMPLE_PATH", os.path.join("state", "hw_sample.json")
        )
        self.cmd_path = cmd_path or os.environ.get(
            "QSD_HW_CMD_PATH", os.path.join("state", "hw_commands.jsonl")
        )
        self.offload_cmd = offload_cmd or os.environ.get("QSD_HW_OFFLOAD_CMD")
        self.relock_cmd = relock_cmd or os.environ.get("QSD_HW_RELOCK_CMD")
        self.point_cmd = point_cmd or os.environ.get("QSD_HW_POINT_CMD")

    def read(self, beam: stack.Beam) -> stack.Sample:
        raw = load(self.sample_path, None)
        if not isinstance(raw, dict):
            raise FileNotFoundError(f"no hardware sample at {self.sample_path}")
        # Allow per-beam samples nested under beam_id, or a flat latest sample.
        if "channels" not in raw and beam.beam_id in raw:
            raw = raw[beam.beam_id]
        ch = raw.get("channels")
        if ch is None and "fsm_urad" in raw:
            fsm = list(raw["fsm_urad"])
            quad = list(raw.get("quad_urad", [0.0, 0.0]))
            ch = fsm + quad
        if ch is None and all(k in raw for k in ("meas_az", "meas_el", "cmd_az", "cmd_el")):
            # Deg residual mapped into a 2-axis urad proxy for stack channels.
            r_deg = residual_from_azel(
                raw["cmd_az"], raw["cmd_el"], raw["meas_az"], raw["meas_el"]
            )
            # Dominant-axis encoding: residual on axis 0, zeros elsewhere.
            urad = float(r_deg) * 1e6 * np.pi / 180.0
            ch = (urad, 0.0, 0.0, 0.0)
        if ch is None:
            raise ValueError("hardware sample missing channels / fsm_urad / azel")
        mono = float(raw.get("mono_s", time.monotonic()))
        unix = float(raw.get("unix_s", time.time()))
        seq = int(raw["sequence"])
        return stack.Sample(
            mono_s=mono,
            unix_s=unix,
            sequence=seq,
            channels=tuple(float(x) for x in ch),
            locked=bool(raw.get("locked", True)),
            actuator_ready=bool(raw.get("actuator_ready", True)),
            sinr_db=_opt_float(raw.get("sinr_db")),
            esn0_db=_opt_float(raw.get("esn0_db")),
        )

    def offload(self, beam: stack.Beam) -> None:
        self._command("OFFLOAD", beam)

    def relock(self, beam: stack.Beam) -> None:
        self._command("RELOCK", beam)

    def point(self, beam_id: str, az_deg: float, el_deg: float) -> None:
        """Called from enact forward when Spacetime retargets az/el."""
        rec = {
            "t": time.time(),
            "cmd": "POINT",
            "beam_id": beam_id,
            "az_deg": az_deg,
            "el_deg": el_deg,
        }
        append_jsonl(self.cmd_path, rec)
        if self.point_cmd:
            subprocess.run(
                [self.point_cmd, str(az_deg), str(el_deg), beam_id],
                check=True,
                timeout=5,
            )

    def _command(self, name: str, beam: stack.Beam) -> None:
        append_jsonl(
            self.cmd_path,
            {"t": time.time(), "cmd": name, "beam_id": beam.beam_id},
        )
        hook = self.offload_cmd if name == "OFFLOAD" else self.relock_cmd
        if hook:
            subprocess.run([hook, beam.beam_id], check=True, timeout=5)


def _opt_float(v):
    if v is None:
        return None
    x = float(v)
    return x if np.isfinite(x) else None


class RecordingTerminal:
    """Wrap a stack Terminal; append every sample and command to NDJSON."""

    def __init__(self, inner, path: str):
        self.inner = inner
        self.path = path

    def read(self, beam: stack.Beam) -> stack.Sample:
        sample = self.inner.read(beam)
        append_jsonl(
            self.path,
            {
                "kind": "sample",
                "beam_id": beam.beam_id,
                "interface_id": beam.interface_id,
                "sample": {
                    "mono_s": sample.mono_s,
                    "unix_s": sample.unix_s,
                    "sequence": sample.sequence,
                    "channels": list(sample.channels),
                    "locked": sample.locked,
                    "actuator_ready": sample.actuator_ready,
                    "sinr_db": sample.sinr_db,
                    "esn0_db": sample.esn0_db,
                },
            },
        )
        return sample

    def offload(self, beam: stack.Beam) -> None:
        append_jsonl(
            self.path,
            {"kind": "command", "cmd": "OFFLOAD", "beam_id": beam.beam_id, "t": time.time()},
        )
        self.inner.offload(beam)

    def relock(self, beam: stack.Beam) -> None:
        append_jsonl(
            self.path,
            {"kind": "command", "cmd": "RELOCK", "beam_id": beam.beam_id, "t": time.time()},
        )
        self.inner.relock(beam)


class ReplayExhausted(RuntimeError):
    """Raised when ReplayTerminal has no samples left (not caught as a soft fault)."""


class ReplayTerminal:
    """
    Replay recorded samples for one beam. Advances one sample per read().
    Offload/relock are no-ops (already in the log for offline analysis).
    """

    def __init__(self, path: str, beam_id: Optional[str] = None, clock_shift: bool = True):
        self.samples = []
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
                self.samples.append(rec)
        if not self.samples:
            raise ValueError(f"no samples in {path}")
        self.i = 0
        self.clock_shift = clock_shift
        self._t0_mono = None
        self._t0_rec = None

    @property
    def remaining(self) -> int:
        return max(0, len(self.samples) - self.i)

    def read(self, beam: stack.Beam) -> stack.Sample:
        if self.i >= len(self.samples):
            raise ReplayExhausted("replay exhausted")
        rec = self.samples[self.i]
        self.i += 1
        s = rec["sample"]
        mono = float(s["mono_s"])
        unix = float(s["unix_s"])
        if self.clock_shift:
            now = time.monotonic()
            if self._t0_mono is None:
                self._t0_mono = now
                self._t0_rec = mono
            mono = self._t0_mono + (float(s["mono_s"]) - self._t0_rec)
            unix = time.time() - (time.monotonic() - mono)
        return stack.Sample(
            mono_s=mono,
            unix_s=unix,
            sequence=int(s["sequence"]),
            channels=tuple(s["channels"]),
            locked=bool(s["locked"]),
            actuator_ready=bool(s["actuator_ready"]),
            sinr_db=_opt_float(s.get("sinr_db")),
            esn0_db=_opt_float(s.get("esn0_db")),
        )

    def offload(self, beam: stack.Beam) -> None:
        return None

    def relock(self, beam: stack.Beam) -> None:
        return None


class SimStackTerminal:
    """
    2-axis FSM plant in urad for stack_v2 tests. Provides measured SINR from
    headroom (modem-like), labeled as calibrated measurement for export tests.
    """

    def __init__(
        self,
        seed=0,
        limit=100.0,
        rate_walk=0.4,
        vib_amp=0.0,
        vib_hz=5.0,
        sinr_clear_db=20.0,
    ):
        self.rng = np.random.default_rng(seed)
        self.limit = float(limit)
        self.rw = rate_walk
        self.vib_amp = vib_amp
        self.vib_hz = vib_hz
        self.sinr_clear_db = sinr_clear_db
        self.x = np.zeros(2)
        self.v = self.rng.normal(0, 20, 2)
        self.phase = self.rng.uniform(0, 2 * np.pi, 2)
        self.seq = 0
        self.pending = None
        self.lost_until = -1.0
        self.offloads = 0
        self.relocks = 0
        self.stats = {"n": 0, "nolock": 0}

    def _pos(self, t):
        vib = self.vib_amp * np.sin(2 * np.pi * self.vib_hz * t + self.phase)
        return self.x + vib

    def read(self, beam: stack.Beam) -> stack.Sample:
        t = time.monotonic()
        if self.pending is not None and t >= self.pending:
            self.x[:] = 0.0
            self.pending = None
        self.v = np.clip(self.v + self.rng.normal(0, self.rw, 2), -200, 200)
        self.x += self.v * 0.001
        pos = self._pos(t)
        sat = bool(np.any(np.abs(pos) >= self.limit))
        self.stats["n"] += 1
        self.stats["nolock"] += int(sat)
        if sat and t >= self.lost_until:
            self.lost_until = t + 0.15
        locked = t >= self.lost_until
        meas = np.clip(pos + self.rng.normal(0, 0.5, 2), -self.limit, self.limit)
        quad = self.rng.normal(0, 0.3, 2)
        headroom = float(np.min(1.0 - np.abs(meas) / self.limit))
        # Measured-modem-style SINR: clear minus pointing loss from headroom.
        sinr = self.sinr_clear_db - 3.0 * max(0.0, 1.0 - headroom) ** 2 * 4.0
        self.seq += 1
        return stack.Sample(
            mono_s=t,
            unix_s=time.time(),
            sequence=self.seq,
            channels=tuple(np.concatenate([meas, quad])),
            locked=locked,
            actuator_ready=True,
            sinr_db=float(sinr),
            esn0_db=None,
        )

    def offload(self, beam: stack.Beam) -> None:
        self.offloads += 1
        self.pending = time.monotonic() + 0.020

    def relock(self, beam: stack.Beam) -> None:
        self.relocks += 1
        self.lost_until = time.monotonic() + 0.05
        self.pending = time.monotonic() + 0.020
