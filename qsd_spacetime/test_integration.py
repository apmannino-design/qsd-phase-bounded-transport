"""
End-to-end test of the QSD gate <-> Spacetime agent bridge, using messages
built and validated with protobuf classes generated from aalyria/api.
Run from this folder:  python3 test_integration.py   (needs ./gen, built by protoc)
"""
import os, sys, json, shutil, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "gen"))
from google.protobuf import json_format, text_format
from api.scheduling.v1alpha import scheduling_pb2 as sched
from api.telemetry.v1alpha import telemetry_pb2 as tele
from agent.internal.configpb import config_pb2

STATE = tempfile.mkdtemp(prefix="qsd_state_")
os.environ["QSD_STATE_DIR"] = STATE
sys.path.insert(0, HERE)
import common
common.STATE_DIR = STATE
common.BEAMS = os.path.join(STATE, "beams.json")
common.STATUS = os.path.join(STATE, "status.json")
import qsd_daemon
qsd_daemon.BEAMS, qsd_daemon.STATUS = common.BEAMS, common.STATUS

ok = True
def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg); ok &= bool(cond)

def enact(req):
    js = json_format.MessageToJson(req)          # canonical protojson, as the Go agent sends
    p = subprocess.run([sys.executable, os.path.join(HERE, "qsd_enact.py")],
                       input=js, text=True, capture_output=True, env=os.environ)
    return p.returncode, p.stderr

def update_beam(seq, bid, ant, az, el):
    r = sched.CreateEntryRequest(schedule_manipulation_token="tok", seqno=seq, id=f"e{seq}")
    r.time.GetCurrentTime()
    r.update_beam.beam.id = bid
    r.update_beam.beam.antenna_id = ant
    r.update_beam.beam.target.az_el.az_deg = az
    r.update_beam.beam.target.az_el.el_deg = el
    return r

# 1. agent config parses against the real config.proto
cfg = config_pb2.AppConfig() if hasattr(config_pb2, "AppConfig") else None
names = [n for n in dir(config_pb2) if n[0].isupper()]
top = next(getattr(config_pb2, n) for n in names
           if hasattr(getattr(config_pb2, n), "DESCRIPTOR")
           and "sdn_agents" in getattr(config_pb2, n).DESCRIPTOR.fields_by_name)
c = text_format.Parse(open(os.path.join(HERE, "agent_config.textproto")).read(), top())
check(len(c.sdn_agents) == 1 and c.sdn_agents[0].telemetry_driver.HasField("external_command"),
      f"agent_config.textproto parses as {top.__name__}")

# 2. enactment: two beams, then delete one, then retarget
check(enact(update_beam(1, "beam-A", "ant-1", 120.0, 35.0))[0] == 0, "update_beam A enacted (exit 0)")
check(enact(update_beam(2, "beam-B", "ant-2", 250.0, 20.0))[0] == 0, "update_beam B enacted (exit 0)")
d = sched.CreateEntryRequest(schedule_manipulation_token="tok", seqno=3, id="e3"); d.delete_beam.id = "beam-B"
check(enact(d)[0] == 0, "delete_beam B enacted (exit 0)")
beams = common.load(common.BEAMS, {})
check(list(beams) == ["beam-A"] and beams["beam-A"]["cmd_az"] == 120.0, "beam table = {A @ az 120}")
rc, err = subprocess.run([sys.executable, os.path.join(HERE, "qsd_enact.py")], input="{bad",
                         text=True, capture_output=True, env=os.environ).returncode, ""
check(rc == 3, "malformed request -> exit 3 (INVALID_ARGUMENT)")

# 3. daemon closes the loop on the beam Spacetime scheduled
def trial(mode, seed, steps=2000):
    term = qsd_daemon.SimTerminal(sigma_meas=0.3, sigma_drift=0.02, seed=seed)
    gates = qsd_daemon.run(term, steps=steps, gate_kw=dict(mode=mode, p_th=0.2), status_every=steps)
    s = term.s["beam-A"]
    return gates["beam-A"].relocks, 100*s["out"]/s["n"]
res = {m: [trial(m, sd) for sd in range(20)] for m in ("reactive", "predictive")}
for m, v in res.items():
    rl = sum(x for x, _ in v)/len(v); out = sum(y for _, y in v)/len(v)
    print(f"     {m:10s}: {rl:5.1f} re-locks / 2000 steps, {out:.2f}% time outside corridor")
check(sum(y for _, y in res["predictive"]) < sum(y for _, y in res["reactive"]),
      "predictive gate spends less time outside corridor through the agent path")

# 4. retarget resets the gate (new acquisition)
gen0 = common.load(common.BEAMS, {})["beam-A"]["generation"]
enact(update_beam(4, "beam-A", "ant-1", 121.5, 35.2))
check(common.load(common.BEAMS, {})["beam-A"]["generation"] == gen0 + 1, "retarget bumps generation -> gate reset")

# 5. telemetry output is a valid ExportMetricsRequest
qsd_daemon.run(qsd_daemon.SimTerminal(seed=99), steps=50)
p = subprocess.run([sys.executable, os.path.join(HERE, "qsd_telemetry.py")],
                   capture_output=True, text=True, env=os.environ)
check(p.returncode == 0, "telemetry extproc exit 0")
msg = json_format.Parse(p.stdout, tele.ExportMetricsRequest())   # strict: unknown fields raise
check(msg.interface_metrics[0].interface_id == "ant-1"
      and msg.modem_metrics[0].sinr_data_points[0].HasField("sinr_db"),
      "stdout parses as telemetry.v1alpha.ExportMetricsRequest")
print("     sample:", p.stdout[:220], "...")

shutil.rmtree(STATE)
print("\nALL PASS" if ok else "\nFAILURES")
sys.exit(0 if ok else 1)
