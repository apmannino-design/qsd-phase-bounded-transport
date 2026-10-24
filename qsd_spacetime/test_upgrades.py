#!/usr/bin/env python3
"""Tests for record/replay, calibration, weather ingest, hardware forward."""
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

# --- weather ingest ---
from qsd_weather_ingest import advise
advice = advise({
    "active_station": "gs-a",
    "stations": [
        {"id": "gs-a", "cloud_od": 2.0, "rain_rate_mm_h": 5},
        {"id": "gs-b", "cloud_od": 0.1, "rain_rate_mm_h": 0},
    ],
})
check(advice["switch_now"] and advice["recommended_station"] == "gs-b",
      "weather ingest recommends clearer station")
check(advice["source"] == "external_weather" and "nbi_hint" in advice,
      "weather advice is external (not link KF) with nbi_hint")

# --- record + calibrate + replay ---
rec = os.path.join(STATE, "rec.jsonl")
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_record_replay.py"), "record",
     "--out", rec, "--seconds", "0.4", "--via-supervisor", "--beam-id", "beam-A"],
    cwd=HERE, capture_output=True, text=True,
)
check(p.returncode == 0 and os.path.exists(rec), f"record sim session ({p.stderr})")

cal_out = common.CALIBRATION
p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_calibrate.py"),
     "--record", rec, "--out", cal_out, "--beam-id", "beam-A"],
    cwd=HERE, capture_output=True, text=True,
)
check(p.returncode == 0, f"calibrate from recording ({p.stderr})")
cal = json.load(open(cal_out))
check("headroom_warn" in cal and cal.get("predict") is False,
      "calibration writes headroom/theta overrides, predict OFF")

p = subprocess.run(
    [sys.executable, os.path.join(HERE, "qsd_record_replay.py"), "replay",
     "--record", rec, "--beam-id", "beam-A",
     "--status", common.STATUS],
    cwd=HERE, capture_output=True, text=True, env={**os.environ, "QSD_STATE_DIR": STATE},
)
check(p.returncode == 0, f"replay through stack_v2 ({p.stderr})")
snap = json.load(open(common.STATUS))
check(snap.get("schema_version") == 1, "replay status schema_version=1")
local = json.load(open(common.LOCAL_METRICS))
check("headroom" in local["beams"]["beam-A"], "replay fills local_metrics side-channel")

# --- hardware sample path ---
from qsd_terminal import HardwareTerminal
import qsd_stack_v2 as stack
hw_sample = os.path.join(STATE, "hw_sample.json")
common.save(hw_sample, {
    "channels": [10.0, -5.0, 0.1, -0.2],
    "sequence": 1,
    "locked": True,
    "actuator_ready": True,
    "sinr_db": 17.5,
    "mono_s": __import__("time").monotonic(),
    "unix_s": __import__("time").time(),
})
os.environ["QSD_HW_SAMPLE_PATH"] = hw_sample
os.environ["QSD_HW_CMD_PATH"] = os.path.join(STATE, "hw_cmd.jsonl")
hw = HardwareTerminal(sample_path=hw_sample, cmd_path=os.environ["QSD_HW_CMD_PATH"])
s = hw.read(stack.Beam("b", "i"))
check(s.sinr_db == 17.5 and len(s.channels) == 4, "HardwareTerminal reads sample file")
hw.offload(stack.Beam("b", "i"))
hw.point("b", 10.0, 20.0)
cmds = open(os.environ["QSD_HW_CMD_PATH"]).read()
check("OFFLOAD" in cmds and "POINT" in cmds, "HardwareTerminal logs offload/point commands")

shutil.rmtree(STATE)
print("\nALL PASS" if ok else "\nFAILURES")
sys.exit(0 if ok else 1)
