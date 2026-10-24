#!/usr/bin/env python3
"""
QSD gate daemon — runs at the terminal's control rate, next to the agent.

Pointing control is faster than Spacetime's telemetry period, so the gate runs
here continuously instead of inside the per-period extproc call. It:
  1. reads active beams (written by qsd_enact.py from Spacetime's schedule)
  2. reads each beam's pointing residual from the terminal
  3. steps the QSD gate; commands a local re-lock when it fires
  4. writes status.json for qsd_telemetry.py to export to Spacetime

Terminal I/O is behind the Terminal interface: SimTerminal for testing,
HardwareTerminal is where a real Tightbeam-class terminal plugs in.
"""
import argparse, time
import numpy as np
from common import BEAMS, STATUS, load, save, now_rfc3339, residual_from_azel, sinr_from_residual
from qsd_gate import QSDGate


class Terminal:
    def read_residual(self, beam):  raise NotImplementedError
    def command_relock(self, beam): raise NotImplementedError
    def relock_complete(self, beam): return False


class HardwareTerminal(Terminal):
    """Fill in for real hardware. Residual = angle between Spacetime's commanded
    AzEl and measured gimbal pointing, or the terminal's own tracking-sensor error."""
    def read_residual(self, beam):
        raise NotImplementedError("TODO: read gimbal encoders / fine-tracking sensor")
    def command_relock(self, beam):
        raise NotImplementedError("TODO: trigger the terminal's re-acquisition / fine-pointing reset")


class SimTerminal(Terminal):
    """Same plant as the Monte Carlo study: drifting residual, noisy sensor,
    re-lock lands after `latency` steps."""
    def __init__(self, sigma_meas=0.3, sigma_drift=0.02, latency=3, seed=0):
        self.sm, self.sa, self.lat = sigma_meas, sigma_drift, latency
        self.rng = np.random.default_rng(seed)
        self.s = {}
    def _st(self, b):
        return self.s.setdefault(b["id"], dict(r=self.rng.normal(0, 0.2), v=0.0, pend=-1, out=0, n=0))
    def read_residual(self, beam):
        s = self._st(beam)
        if s["pend"] == 0:
            s["r"], s["v"], s["pend"] = self.rng.normal(0, 0.2), 0.3*s["v"], -1
        elif s["pend"] > 0:
            s["pend"] -= 1
        s["r"] += s["v"]; s["v"] += self.rng.normal(0, self.sa)
        s["n"] += 1; s["out"] += abs(s["r"]) > 3.0
        return s["r"] + self.rng.normal(0, self.sm)
    def command_relock(self, beam):
        self._st(beam)["pend"] = self.lat - 1


def run(terminal, steps=None, dt=0.0, gate_kw=None, status_every=1):
    gates, gens = {}, {}
    k = 0
    while steps is None or k < steps:
        beams = load(BEAMS, {})
        status = {}
        for bid, b in beams.items():
            if "cmd_az" not in b:
                continue  # non-AzEl targets: residual must come from the terminal's tracker
            if bid not in gates or gens.get(bid) != b.get("generation"):
                gates[bid] = QSDGate(**(gate_kw or {}))   # new beam/target -> acquisition
                gens[bid] = b.get("generation")
            z = terminal.read_residual(b)
            out = gates[bid].step(z)
            if out["relock"]:
                terminal.command_relock(b)
            out.update(antenna_id=b.get("antenna_id", bid), time=now_rfc3339(),
                       sinr_db=sinr_from_residual(abs(out["r_hat"])))
            status[bid] = out
        for gone in set(gates) - set(beams):
            gates.pop(gone); gens.pop(gone, None)
        if k % status_every == 0:
            save(STATUS, status)
        k += 1
        if dt:
            time.sleep(dt)
    save(STATUS, status)
    return gates


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="use SimTerminal")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--dt", type=float, default=0.01, help="control period, s")
    ap.add_argument("--p-th", type=float, default=0.2)
    ap.add_argument("--mode", default="predictive", choices=["predictive", "reactive"])
    a = ap.parse_args()
    term = SimTerminal() if a.sim else HardwareTerminal()
    run(term, a.steps, a.dt, dict(p_th=a.p_th, mode=a.mode))
