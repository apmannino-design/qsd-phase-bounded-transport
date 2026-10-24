#!/usr/bin/env python3
"""Tests for record/replay, calibration, holdout scorecard, weather→NBI, HW pump."""
import json, os, sys, tempfile, shutil, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STATE = tempfile.mkdtemp(prefix="qsd_up_")
os.environ["QSD_STATE_DIR"] = STATE
import common
common.STATE_DIR = STATE
for name in ("BEAMS", "STATUS", "LOCAL_METRICS", "WEATHER_ADVICE",
             "ENACT_FORWARD", "CALIBRATION"):
    setattr(common, name, os.path.join(STATE, os.path.basename(getattr(common, name))))

ok = True
def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg); ok &= bool(cond)

# --- weather ingest + NBI fragment ---
from qsd_weather_ingest import advise
from qsd_weather_to_nbi import build_service_request
advice = advise({
    "active_station": "gs-a",
    "stations": [
        {"id": "gs-a", "cloud_od": 2.0, "rain_rate_mm_h": 5},
        {"id": "gs-b", "cloud_od": 0.1, "rain_rate_mm_h": 0},
    ],
})
check(advice["switch_now"] and advice["recommended_station"] == "gs-b",
      "weather ingest recommends clearer station")
doc = build_service_request(advice, src_node="gateway-1")
check(doc["submit"] and doc["service_request"]["dstNodeId"] == "gs-b",
      "weather_to_nbi emits ServiceRequest preferring gs-b")
hold = build_service_request({**advice, "switch_now": False, "reason": "hold"}, "gateway-1")
check(hold["submit"] is False, "weather_to_nbi holds when switch_now false")

# --- record + holdout scorecard ---
rec = os.path.join(STATE, "rec.jsonl")
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_record_replay.py"), "record",
     "--out", rec, "--seconds", "1.2", "--via-supervisor",
     "--beam-id", "beam-A", "--vib-amp", "15", "--vib-hz", "5"],
    cwd=HERE, capture_output=True, text=True,
)
check(p.returncode == 0 and os.path.exists(rec), f"record sim session ({p.stderr})")

sc_out = os.path.join(STATE, "scorecard_holdout.json")
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_scorecard_holdout.py"),
     "--record", rec, "--beam-id", "beam-A",
     "--out-cal", common.CALIBRATION, "--out-scorecard", sc_out],
    cwd=HERE, capture_output=True, text=True,
)
check(p.returncode == 0, f"holdout scorecard ({p.stderr})")
sc = json.load(open(sc_out))
cal = json.load(open(common.CALIBRATION))
check("recommend_predict" in sc and "reason" in sc, "scorecard has predict verdict")
check(cal.get("predict") == sc["recommend_predict"],
      "calibration.json predict matches holdout verdict")
check(sc["hold_samples"] >= 40 and sc["train_samples"] >= 50, "train/holdout split sized")

# --- replay ---
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_record_replay.py"), "replay",
     "--record", rec, "--beam-id", "beam-A", "--status", common.STATUS],
    cwd=HERE, capture_output=True, text=True, env={**os.environ, "QSD_STATE_DIR": STATE},
)
check(p.returncode == 0, f"replay through stack_v2 ({p.stderr})")
local = json.load(open(common.LOCAL_METRICS))
check("headroom" in local["beams"]["beam-A"], "replay fills local_metrics side-channel")

# --- hardware sample pump (short sim) ---
hw_sample = os.path.join(STATE, "hw_sample.json")
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_hw_sample_pump.py"),
     "--sim", "--path", hw_sample, "--seconds", "0.05", "--dt", "0.001"],
    cwd=HERE, capture_output=True, text=True,
)
check(p.returncode == 0 and os.path.exists(hw_sample), f"hw sample pump ({p.stderr})")
from qsd_terminal import HardwareTerminal
import qsd_stack_v2 as stack
hw = HardwareTerminal(sample_path=hw_sample, cmd_path=os.path.join(STATE, "hw_cmd.jsonl"))
s = hw.read(stack.Beam("beam-A", "ant-1"))
check(len(s.channels) == 4 and s.sequence >= 1, "HardwareTerminal reads pumped sample")

# --- startup telemetry: strict default DORMANT; opt-in UP for staging (H3) ---
os.environ["QSD_STATE_DIR"] = STATE
common.STATUS = os.path.join(STATE, "status.json")
import time
snap = {
    "schema_version": 1,
    "published_unix_s": time.time(),
    "max_export_age_s": 5.0,
    "beams": {
        "beam-A": {
            "interface_id": "ant-1",
            "time": "2026-10-24T00:00:00.000000Z",
            "sample_unix_s": time.time(),
            "sample_valid": True,
            "regime": 0,
            "oper_status": "IF_OPER_STATUS_DORMANT",
            "rx_modem_id": "ant-1-demod",
            "tx_modem_id": "beam-A-remote",
            "sinr_db": 18.0,
        }
    },
}
common.save(common.STATUS, snap)
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_telemetry.py")],
    cwd=HERE, capture_output=True, text=True,
    env={**os.environ, "QSD_STATE_DIR": STATE, "QSD_TELEMETRY_STARTUP_UP": "0"},
)
check(p.returncode == 0 and "IF_OPER_STATUS_DORMANT" in p.stdout,
      "H3 strict default keeps STARTUP as DORMANT")
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_telemetry.py")],
    cwd=HERE, capture_output=True, text=True,
    env={**os.environ, "QSD_STATE_DIR": STATE, "QSD_TELEMETRY_STARTUP_UP": "1"},
)
check(p.returncode == 0 and "IF_OPER_STATUS_UP" in p.stdout,
      "staging opt-in QSD_TELEMETRY_STARTUP_UP=1 maps STARTUP→UP")

shutil.rmtree(STATE)
print("\nALL PASS" if ok else "\nFAILURES")
sys.exit(0 if ok else 1)
