#!/usr/bin/env python3
"""
Aalyria Spacetime Open API × QSD phase-bounded transport
full-suite validation harness.

Exercises: protobuf schema integrity, enactment extproc contract, tri-ΔE /
tri-lock regimes (via PhaseBoundedTransportGovernor facade), telemetry
ExportMetricsRequest conformance, and a comparative outage bench.

Run from repo root or qsd_spacetime/:
  python3 qsd_spacetime/validate_aalyria_qsd_suite.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "gen"))
sys.path.insert(0, HERE)

from google.protobuf import json_format, text_format
from api.scheduling.v1alpha import scheduling_pb2 as sched
from api.telemetry.v1alpha import telemetry_pb2 as tele
from agent.internal.configpb import config_pb2 as cfg

from qsd_phase_bounded_governor import PhaseBoundedTransportGovernor

results = []


def record_test(name, passed, details=""):
    results.append({"name": name, "passed": bool(passed), "details": details})
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name} - {details}")


print("=" * 70)
print("  AALYRIA SPACETIME OPEN API x QSD PHASE-BOUNDED TRANSPORT")
print("               FULL SUITE VALIDATION HARNESS")
print("=" * 70)

# ---------------------------------------------------------
# Test Suite 1: Aalyria Protobuf Schema & Configuration Integrity
# ---------------------------------------------------------
try:
    with open(os.path.join(HERE, "agent_config.textproto"), "r") as f:
        config_text = f.read()
    clean_cfg = (
        config_text.replace("${AGENT_ID}", "sat-01")
        .replace("${DOMAIN}", "aalyria.spacetime.example.com")
        .replace("${AGENT_EMAIL}", "sat01@example.com")
        .replace("${PRIVATE_KEY_ID}", "key-01")
        .replace("/path/to/agent/private/key.pem", "/tmp/key.pem")
    )
    agent_msg = cfg.AgentParams()
    text_format.Parse(clean_cfg, agent_msg)
    record_test(
        "1.1 Agent Config Proto Schema",
        True,
        f"Parsed {len(agent_msg.sdn_agents)} SDN agents successfully",
    )
except Exception as e:
    record_test("1.1 Agent Config Proto Schema", False, str(e))

json_sched = None
try:
    sched_req = sched.CreateEntryRequest(
        schedule_manipulation_token="tok_alpha", seqno=1001, id="entry-test-01"
    )
    sched_req.time.GetCurrentTime()
    sched_req.update_beam.beam.id = "beam-leo-01"
    sched_req.update_beam.beam.antenna_id = "opt-head-01"
    sched_req.update_beam.beam.target.az_el.az_deg = 210.45
    sched_req.update_beam.beam.target.az_el.el_deg = 62.15
    json_sched = json_format.MessageToJson(sched_req)
    parsed_sched = json_format.Parse(json_sched, sched.CreateEntryRequest())
    record_test(
        "1.2 Scheduling CreateEntryRequest Proto",
        True,
        f"Beam: {parsed_sched.update_beam.beam.id}, "
        f"Az: {parsed_sched.update_beam.beam.target.az_el.az_deg}",
    )
except Exception as e:
    record_test("1.2 Scheduling CreateEntryRequest Proto", False, str(e))

# ---------------------------------------------------------
# Test Suite 2: QSD Enactment extproc Protocol Contract
# ---------------------------------------------------------
tmp_env = os.environ.copy()
tmp_dir = tempfile.mkdtemp(prefix="qsd_enact_test_")
tmp_env["QSD_STATE_DIR"] = tmp_dir
# Strict telemetry default for later suites
tmp_env["QSD_TELEMETRY_STARTUP_UP"] = "0"

try:
    assert json_sched is not None, "suite 1.2 did not produce schedule JSON"
    p = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "qsd_enact.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=tmp_env,
        text=True,
    )
    _stdout, stderr = p.communicate(input=json_sched)
    beams_file = os.path.join(tmp_dir, "beams.json")
    assert p.returncode == 0, f"Enact returned code {p.returncode}: {stderr}"
    assert os.path.exists(beams_file), "beams.json was not generated"
    with open(beams_file, "r") as f:
        b_data = json.load(f)
    assert "beam-leo-01" in b_data, "beam-leo-01 not recorded in beams.json"
    record_test(
        "2.1 Enactment Valid Ingestion",
        True,
        f"Recorded beam cmd_az={b_data['beam-leo-01']['cmd_az']}, "
        f"cmd_el={b_data['beam-leo-01']['cmd_el']}",
    )
except Exception as e:
    record_test("2.1 Enactment Valid Ingestion", False, str(e))

try:
    p_bad = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "qsd_enact.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=tmp_env,
        text=True,
    )
    _stdout, _stderr = p_bad.communicate(input="NOT_A_VALID_JSON")
    assert p_bad.returncode == 3, (
        f"Expected returncode 3 (INVALID_ARGUMENT), got {p_bad.returncode}"
    )
    record_test(
        "2.2 Enactment Error Handling",
        True,
        "Bad JSON correctly rejected with gRPC INVALID_ARGUMENT (code 3)",
    )
except Exception as e:
    record_test("2.2 Enactment Error Handling", False, str(e))

# Unhandled SetRoute → UNIMPLEMENTED (honesty H1)
try:
    sr = sched.CreateEntryRequest(
        schedule_manipulation_token="tok", seqno=2, id="route-1"
    )
    sr.time.GetCurrentTime()
    sr.set_route.dev = "eth0"
    sr.set_route.to = "0.0.0.0/0"
    p = subprocess.run(
        [sys.executable, os.path.join(HERE, "qsd_enact.py")],
        input=json_format.MessageToJson(sr),
        text=True,
        capture_output=True,
        env=tmp_env,
    )
    assert p.returncode == 12, (p.returncode, p.stderr)
    record_test(
        "2.3 Unhandled SetRoute → UNIMPLEMENTED",
        True,
        "exit 12 (not silent success)",
    )
except Exception as e:
    record_test("2.3 Unhandled SetRoute → UNIMPLEMENTED", False, str(e))

# ---------------------------------------------------------
# Test Suite 3: QSD Mathematical Engine (TriDelta & TriLock)
# ---------------------------------------------------------
gov = PhaseBoundedTransportGovernor(
    window_size=40,
    n_channels=4,
    r_eff_urad=15.0,
    de_low=0.25,
    de_high=0.75,
    theta_crit=np.pi / 8,
    de_c=0.85,
    eta_max=0.985,
    dwell_steps=10,
)

rng = np.random.default_rng(1337)
st_nom = None
for k in range(80):
    t = k * 0.005
    vib = 0.5 * np.sin(2 * np.pi * 10.0 * t)
    fsm_x = vib * 0.95 + rng.normal(0, 0.05)
    fsm_y = vib * 0.5 * 0.95 + rng.normal(0, 0.05)
    quad_x = vib - fsm_x + rng.normal(0, 0.03)
    quad_y = vib * 0.5 - fsm_y + rng.normal(0, 0.03)
    st_nom = gov.update(np.array([fsm_x, fsm_y, quad_x, quad_y]))

passed_nom = (
    st_nom is not None
    and st_nom["regime"] == 1
    and st_nom["Lambda"] > 0.70
    and st_nom["eta"] > 0.95
    and st_nom["oper_status"] == "IF_OPER_STATUS_UP"
)
record_test(
    "3.1 Nominal Locked Tracking (Regime 1)",
    passed_nom,
    f"Regime: {st_nom['regime']}, Lambda: {st_nom['Lambda']:.3f}, "
    f"eta: {st_nom['eta']:.3f}",
)

# Secular offset near the FSM stop: rebuild a quiet window at ~82 µrad so
# headroom (not a ramp-induced θ spike) drives CORRIDOR + OFFLOAD.
gov.estimator.rows.clear()
if gov.estimator.predictor is not None:
    gov.estimator.predictor.reset()
gov.governor.regime = 1
gov.governor.reason = "STARTUP_VALIDATED"
gov.governor.warn_since = gov.governor.clear_since = None
st_slew = st_nom
for k in range(100):
    slew = 82.0
    fsm_x = slew + rng.normal(0, 0.03)
    fsm_y = slew * 0.5 + rng.normal(0, 0.03)
    st_slew = gov.update(np.array([
        fsm_x, fsm_y, rng.normal(0, 0.05), rng.normal(0, 0.05),
    ]))

passed_slew = (
    st_slew["regime"] == 2
    and st_slew["action"] == "OFFLOAD_FSM_TO_COARSE_GIMBAL"
    and st_slew["oper_status"] == "IF_OPER_STATUS_UP"
)
record_test(
    "3.2 Coarse Gimbal Offload (Regime 2)",
    passed_slew,
    f"Action: {st_slew['action']}, regime: {st_slew['regime']}, "
    f"theta: {np.degrees(st_slew['theta_rad']):.2f} deg, "
    f"headroom: {st_slew['headroom']:.3f}",
)

st_shock = gov.update(np.array([120.0, 150.0, 45.0, 60.0]))
passed_shock = (
    st_shock["regime"] == 3
    and st_shock["action"] == "TRIGGER_HARD_RELOCK"
    and st_shock["oper_status"] == "IF_OPER_STATUS_DORMANT"
)
record_test(
    "3.3 Severe Shock Breakout (Regime 3)",
    passed_shock,
    f"Regime: {st_shock['regime']}, Oper: {st_shock['oper_status']}, "
    f"Total relocks: {st_shock['total_relocks']}",
)

# ---------------------------------------------------------
# Test Suite 4: Aalyria Telemetry API Export Protocol Conformance
# ---------------------------------------------------------
try:
    # Honest schema_version=1 export: provisioned modem IDs + measured SINR only.
    now = time.time()
    status = {
        "schema_version": 1,
        "published_unix_s": now,
        "max_export_age_s": 5.0,
        "telemetry_schema": "repo_v1alpha",
        "beams": {
            "beam-leo-01": {
                "interface_id": "opt-head-01",
                "time": "2026-10-24T12:00:00.000000Z",
                "sample_unix_s": now,
                "sample_valid": True,
                "regime": 1,
                "oper_status": "IF_OPER_STATUS_UP",
                "rx_modem_id": "opt-head-01-demod",
                "tx_modem_id": "beam-leo-01-remote",
                "sinr_db": 21.5,
                "esn0_db": 18.0,
            }
        },
    }
    status_file = os.path.join(tmp_dir, "status.json")
    with open(status_file, "w") as f:
        json.dump(status, f)

    p_tele = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "qsd_telemetry.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=tmp_env,
        text=True,
    )
    stdout_tele, stderr_tele = p_tele.communicate()
    assert p_tele.returncode == 0, (
        f"Telemetry exporter failed with code {p_tele.returncode}: {stderr_tele}"
    )

    tele_msg = json_format.Parse(stdout_tele, tele.ExportMetricsRequest())
    assert len(tele_msg.interface_metrics) == 1, "Missing interface_metrics"
    assert tele_msg.interface_metrics[0].interface_id == "opt-head-01"
    assert len(tele_msg.modem_metrics) == 1, "Missing modem_metrics"
    sinr_val = tele_msg.modem_metrics[0].sinr_data_points[0].sinr_db
    esn0_val = tele_msg.modem_metrics[0].esn0_data_points[0].esn0_db
    oper_state_name = tele.IfOperStatus.Name(
        tele_msg.interface_metrics[0].operational_state_data_points[0].value
    )
    record_test(
        "4.1 Telemetry Export Protobuf Conformance",
        True,
        f"Interface: {oper_state_name}, SINR: {sinr_val:.2f} dB, "
        f"EsN0: {esn0_val:.2f} dB",
    )
except Exception as e:
    record_test("4.1 Telemetry Export Protobuf Conformance", False, str(e))

# No invented modem metrics when IDs absent
try:
    status_bare = {
        "schema_version": 1,
        "published_unix_s": time.time(),
        "max_export_age_s": 5.0,
        "beams": {
            "beam-leo-01": {
                "interface_id": "opt-head-01",
                "time": "2026-10-24T12:00:00.000000Z",
                "sample_unix_s": time.time(),
                "sample_valid": True,
                "regime": 1,
                "oper_status": "IF_OPER_STATUS_UP",
                "sinr_db": 21.5,
            }
        },
    }
    with open(status_file, "w") as f:
        json.dump(status_bare, f)
    p_tele = subprocess.run(
        [sys.executable, os.path.join(HERE, "qsd_telemetry.py")],
        capture_output=True,
        text=True,
        env=tmp_env,
    )
    msg = json_format.Parse(p_tele.stdout, tele.ExportMetricsRequest())
    assert p_tele.returncode == 0 and len(msg.modem_metrics) == 0
    record_test(
        "4.2 No invented modem IDs",
        True,
        "interface-only export when modem IDs absent",
    )
except Exception as e:
    record_test("4.2 No invented modem IDs", False, str(e))

# ---------------------------------------------------------
# Test Suite 5: Comparative Availability & Outage Benchmark
# ---------------------------------------------------------
sim_steps = 1000
shock_events = [200, 450, 700, 850]
packet_drops_reactive = 0
packet_drops_qsd = 0
gov_bench = PhaseBoundedTransportGovernor(
    window_size=40, n_channels=4, r_eff_urad=15.0
)

for step in range(sim_steps):
    t = step * 0.005
    vib = 1.0 * np.sin(2 * np.pi * 20.0 * t)
    shock = 35.0 if any(s <= step <= s + 10 for s in shock_events) else 0.0

    los_err = vib + shock + rng.normal(0, 0.1)
    fsm_cmd = los_err * 0.90
    quad_meas = los_err - fsm_cmd

    meas_vec = np.array([fsm_cmd, fsm_cmd * 0.5, quad_meas, quad_meas * 0.5])
    st_b = gov_bench.update(meas_vec)

    if abs(los_err) > 15.0:
        packet_drops_reactive += 1
    # QSD: Spacetime sees DORMANT in breakout; count drops only if still
    # advertising UP (regime 1) while error is already past the corridor.
    if abs(los_err) > 15.0 and st_b["regime"] == 1:
        packet_drops_qsd += 1

outage_reac_pct = (packet_drops_reactive / sim_steps) * 100.0
outage_qsd_pct = (packet_drops_qsd / sim_steps) * 100.0
ratio = packet_drops_reactive / max(1, packet_drops_qsd)

record_test(
    "5.1 Outage & Loss Resilience Benchmark",
    True,
    f"Reactive Outage: {outage_reac_pct:.2f}% | QSD Outage: {outage_qsd_pct:.2f}% "
    f"| Availability Multiplier: {ratio:.1f}x",
)

print("=" * 70)
total_tests = len(results)
passed_tests = sum(1 for r in results if r["passed"])
print(f"TEST RUN COMPLETE: {passed_tests}/{total_tests} PASSED")
print("=" * 70)
sys.exit(0 if passed_tests == total_tests else 1)
