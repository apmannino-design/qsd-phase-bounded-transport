#!/usr/bin/env python3
"""
QSD control daemon — runs at the terminal's control rate, next to the agent.

Default controller: qsd_stack_v2 Supervisor (forecast OFF). The bare Kalman
qsd_gate path is available as --legacy-gate for the ideal-plant demo only;
do not deploy it on vibrating platforms.

  1. reads active beams (written by qsd_enact.py from Spacetime's schedule)
  2. steps stack_v2 supervisors (or legacy QSDGate)
  3. writes status.json for qsd_telemetry.py (Spacetime-facing)
  4. writes local_metrics.json (ΔE / θ / headroom / regime — never exported)
"""
from __future__ import annotations

import argparse
import time
from dataclasses import replace

import numpy as np

from common import (
    BEAMS,
    MODEM_MAP,
    CALIBRATION,
    LOCAL_METRICS,
    STATUS,
    load,
    now_rfc3339,
    save,
    sinr_from_residual,
)
from qsd_gate import QSDGate
import qsd_stack_v2 as stack
from qsd_terminal import HardwareTerminal, RecordingTerminal, SimStackTerminal


# ---------------------------------------------------------------------------
# Legacy gate terminal (ideal random-walk plant) — demo / regression only
# ---------------------------------------------------------------------------

class Terminal:
    def read_residual(self, beam):  raise NotImplementedError
    def command_relock(self, beam): raise NotImplementedError
    def relock_complete(self, beam): return False


class LegacyHardwareTerminal(Terminal):
    def read_residual(self, beam):
        raise NotImplementedError("Use HardwareTerminal + stack_v2, not legacy gate")
    def command_relock(self, beam):
        raise NotImplementedError("Use HardwareTerminal + stack_v2, not legacy gate")


class SimTerminal(Terminal):
    """Same plant as the Monte Carlo study: drifting residual, noisy sensor."""
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


def run_legacy_gate(terminal, steps=None, dt=0.0, gate_kw=None, status_every=1):
    """Ideal-plant QSDGate loop. Kept for test_integration / demos."""
    gates, gens = {}, {}
    k = 0
    status, local = {}, {}
    while steps is None or k < steps:
        beams = load(BEAMS, {})
        status, local = {}, {}
        for bid, b in beams.items():
            if "cmd_az" not in b:
                continue
            if bid not in gates or gens.get(bid) != b.get("generation"):
                gates[bid] = QSDGate(**(gate_kw or {}))
                gens[bid] = b.get("generation")
            z = terminal.read_residual(b)
            out = gates[bid].step(z)
            if out["relock"]:
                terminal.command_relock(b)
            # Synthetic SINR stays in local metrics only — not for Spacetime.
            synth = sinr_from_residual(abs(out["r_hat"]))
            status[bid] = dict(
                antenna_id=b.get("antenna_id", bid),
                time=now_rfc3339(),
                in_corridor=out.get("in_corridor"),
                relocking=out.get("relocking"),
                relock=out.get("relock"),
                r_hat=out.get("r_hat"),
                # omit sinr_db → telemetry will not invent modem metrics
            )
            local[bid] = dict(
                dE=out.get("dE"),
                p_exit=out.get("p_exit"),
                r_hat=out.get("r_hat"),
                in_corridor=out.get("in_corridor"),
                relocking=out.get("relocking"),
                sinr_db_synthetic=synth,
                controller="legacy_gate",
            )
        for gone in set(gates) - set(beams):
            gates.pop(gone); gens.pop(gone, None)
        if k % status_every == 0:
            save(STATUS, status)
            save(LOCAL_METRICS, {"time": now_rfc3339(), "beams": local})
        k += 1
        if dt:
            time.sleep(dt)
    save(STATUS, status)
    save(LOCAL_METRICS, {"time": now_rfc3339(), "beams": local})
    return gates


# Alias used by older tests
run = run_legacy_gate


def _config_from_calibration(predict: bool) -> stack.Config:
    cfg = stack.Config(predict=predict)
    cal = load(CALIBRATION, None)
    if not isinstance(cal, dict):
        return cfg
    allowed = {
        "window", "min_samples", "channel_scale_to_urad", "fsm_limits_urad",
        "r_eff_urad", "shape_gate_rms_urad", "shape_warn", "shape_trip",
        "shape_clear", "theta_warn", "theta_trip", "theta_clear",
        "headroom_warn", "headroom_trip", "headroom_clear",
        "warn_hold_s", "clear_hold_s", "offload_interval_s", "relock_timeout_s",
        "max_sample_age_s", "max_sample_gap_s", "max_export_age_s",
        "period_s", "publish_period_s", "degrade_after_bad_samples",
        "recover_good_samples", "fault_latch_s", "predict", "predict_window_s",
        "predict_horizon_s", "predict_every", "envelope_margin", "jump_sigma",
        "telemetry_schema",
    }
    kw = {k: cal[k] for k in allowed if k in cal}
    if "fsm_limits_urad" in kw:
        kw["fsm_limits_urad"] = tuple(kw["fsm_limits_urad"])
    if "channel_scale_to_urad" in kw:
        kw["channel_scale_to_urad"] = tuple(kw["channel_scale_to_urad"])
    if "predict" not in kw:
        kw["predict"] = predict
    return replace(cfg, **kw)


def _beams_from_state():
    raw = load(BEAMS, {})
    modem_map = load(MODEM_MAP, {})
    beams = []
    for bid, b in raw.items():
        iface = b.get("antenna_id", bid)
        m = modem_map.get(bid) or modem_map.get(iface) or {}
        # Modem IDs only from schedule payload or QSD_MODEM_MAP; never invented.
        beams.append(stack.Beam(
            beam_id=bid,
            interface_id=iface,
            rx_modem_id=b.get("rx_modem_id") or m.get("rx_modem_id"),
            tx_modem_id=b.get("tx_modem_id") or m.get("tx_modem_id"),
        ))
    return beams, raw


def _local_from_stack_states(states):
    local = {}
    for bid, st in states.items():
        c = st.get("coordinates") or {}
        local[bid] = {
            "regime": st.get("regime"),
            "reason": st.get("reason"),
            "oper_status": st.get("oper_status"),
            "dE": c.get("dE"),
            "theta_rad": c.get("theta_rad"),
            "headroom": c.get("headroom"),
            "predicted_headroom": c.get("predicted_headroom"),
            "total_rms_urad": c.get("total_rms_urad"),
            "command_events": st.get("command_events"),
            "sample_valid": st.get("sample_valid"),
            "sinr_db_measured": st.get("sinr_db"),
            "controller": "stack_v2",
        }
    return local


def run_stack(
    terminal,
    steps=None,
    seconds=None,
    dt=None,
    predict=False,
    status_path=None,
    publish_every=1,
):
    """
    Production control loop: stack_v2 supervisors driven by BEAMS schedule.
    Recreates supervisors when beam set / generation changes.
    """
    cfg = _config_from_calibration(predict=predict)
    # dt=0 means "as fast as possible" for tests without violating Config(period_s>0).
    sleep_s = cfg.period_s if dt is None else float(dt)
    if dt is not None and dt > 0:
        cfg = replace(cfg, period_s=float(dt))
    status_path = status_path or STATUS
    supervisors = {}
    gens = {}
    k = 0
    t0 = time.monotonic()
    last_snapshot = {}

    while True:
        if steps is not None and k >= steps:
            break
        if seconds is not None and time.monotonic() - t0 >= seconds:
            break

        beam_list, raw = _beams_from_state()
        active_ids = {b.beam_id for b in beam_list}
        for gone in set(supervisors) - active_ids:
            supervisors.pop(gone); gens.pop(gone, None)

        # One beam per interface (stack_v2 invariant)
        seen_if = set()
        states = {}
        for b in beam_list:
            if b.interface_id in seen_if:
                continue
            seen_if.add(b.interface_id)
            gen = raw.get(b.beam_id, {}).get("generation")
            if b.beam_id not in supervisors or gens.get(b.beam_id) != gen:
                supervisors[b.beam_id] = stack.Supervisor(b, cfg)
                gens[b.beam_id] = gen
            states[b.beam_id] = supervisors[b.beam_id].tick(terminal)

        snapshot = {
            "schema_version": 1,
            "published_unix_s": time.time(),
            "beams": states,
            "controller": "stack_v2",
            "predict": cfg.predict,
        }
        last_snapshot = snapshot
        if k % publish_every == 0:
            stack.atomic_json(status_path, snapshot)
            save(LOCAL_METRICS, {
                "time": now_rfc3339(),
                "controller": "stack_v2",
                "predict": cfg.predict,
                "beams": _local_from_stack_states(states),
            })
        k += 1
        if sleep_s > 0:
            time.sleep(sleep_s)

    if last_snapshot:
        stack.atomic_json(status_path, last_snapshot)
        save(LOCAL_METRICS, {
            "time": now_rfc3339(),
            "controller": "stack_v2",
            "predict": last_snapshot.get("predict"),
            "beams": _local_from_stack_states(last_snapshot.get("beams", {})),
        })
    return last_snapshot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="use simulated terminal")
    ap.add_argument("--legacy-gate", action="store_true",
                    help="use bare qsd_gate (ideal plant demo only)")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--dt", type=float, default=None, help="control period, s")
    ap.add_argument("--predict", action="store_true",
                    help="enable stack_v2 forecast (OFF by default)")
    ap.add_argument("--record", default=None, help="NDJSON path to record samples")
    ap.add_argument("--p-th", type=float, default=0.2, help="legacy gate only")
    ap.add_argument("--mode", default="predictive",
                    choices=["predictive", "reactive"], help="legacy gate only")
    a = ap.parse_args()

    if a.legacy_gate:
        term = SimTerminal() if a.sim else LegacyHardwareTerminal()
        run_legacy_gate(
            term, a.steps, a.dt or 0.01,
            dict(p_th=a.p_th, mode=a.mode),
        )
    else:
        if a.sim:
            term = SimStackTerminal()
        else:
            term = HardwareTerminal()
        if a.record:
            term = RecordingTerminal(term, a.record)
        run_stack(
            term,
            steps=a.steps,
            seconds=a.seconds,
            dt=a.dt,
            predict=a.predict,
        )
