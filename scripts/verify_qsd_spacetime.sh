#!/usr/bin/env bash
# Thorough verification of the QSD × Aalyria Spacetime bridge against the
# vendored github.com/aalyria/api tree.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/go/bin:${HOME}/.local/bin:${PATH}"
AALY="$ROOT/third_party/aalyria-api"
PIN="$ROOT/third_party/AALYRIA_API_PIN.txt"
CFG="$ROOT/qsd_spacetime/agent_config.textproto"
FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step() { echo; echo "==> $*"; }

step "pinned aalyria/api"
if [[ -f "$PIN" ]]; then cat "$PIN"; else echo "WARN: missing $PIN"; FAIL=1; fi

step "required trees present"
for d in "$AALY/api" "$AALY/agent" "$ROOT/third_party/nmts/v1" "$ROOT/third_party/googleapis/google/rpc"; do
  if [[ -d "$d" ]]; then echo "OK  $d"; else echo "MISS $d"; FAIL=1; fi
done

step "regen python protos from upstream"
"$ROOT/scripts/regen_qsd_spacetime_protos.sh"

step "python deps"
python3 -c "import numpy, google.protobuf, google.rpc.status_pb2, google.type.quaternion_pb2; print('OK protobuf', google.protobuf.__version__)"

step "integration test (extproc enact + daemon + telemetry)"
(cd "$ROOT/qsd_spacetime" && python3 test_integration.py)

step "agent config schema (textproto <-> config.proto)"
PYTHONPATH="$ROOT/qsd_spacetime/gen" python3 - <<PY
from google.protobuf import text_format
from agent.internal.configpb import config_pb2
top = next(
    getattr(config_pb2, n)
    for n in dir(config_pb2)
    if n[:1].isupper()
    and hasattr(getattr(config_pb2, n), "DESCRIPTOR")
    and "sdn_agents" in getattr(config_pb2, n).DESCRIPTOR.fields_by_name
)
cfg = text_format.Parse(open("$CFG").read(), top())
agent = cfg.sdn_agents[0]
assert agent.enactment_driver.HasField("external_command")
assert agent.telemetry_driver.HasField("external_command")
ec = agent.enactment_driver.external_command
assert list(ec.args)[:1] == ["python3"]
print("OK AgentParams: enactment+telemetry external_command wired")
PY

step "extproc contract: CreateEntryRequest JSON -> qsd_enact -> beams.json"
export QSD_STATE_DIR="$TMP/state"
mkdir -p "$QSD_STATE_DIR"
PYTHONPATH="$ROOT/qsd_spacetime/gen" python3 - <<PY
import json, os, subprocess, sys
from google.protobuf import json_format
from api.scheduling.v1alpha import scheduling_pb2 as sched
from api.telemetry.v1alpha import telemetry_pb2 as tele

env = os.environ.copy()

def enact(msg):
    js = json_format.MessageToJson(msg)
    return subprocess.run([sys.executable, "$ROOT/qsd_spacetime/qsd_enact.py"],
                          input=js, text=True, capture_output=True, env=env)

r = sched.CreateEntryRequest(schedule_manipulation_token="tok", seqno=1, id="e1")
r.time.GetCurrentTime()
r.update_beam.beam.id = "beam-live"
r.update_beam.beam.antenna_id = "ant-live"
r.update_beam.beam.target.az_el.az_deg = 45.0
r.update_beam.beam.target.az_el.el_deg = 10.0
p = enact(r)
assert p.returncode == 0, p.stderr
beams = json.load(open(os.path.join(env["QSD_STATE_DIR"], "beams.json")))
assert beams["beam-live"]["cmd_az"] == 45.0
print("OK enact CreateEntryRequest -> beams.json")

# H1: unhandled SetRoute must be UNIMPLEMENTED (12), not success
sr = sched.CreateEntryRequest(schedule_manipulation_token="tok", seqno=2, id="e2")
sr.time.GetCurrentTime()
sr.set_route.dev = "eth0"
sr.set_route.to = "0.0.0.0/0"
assert sr.WhichOneof("configuration_change") == "set_route"
p = enact(sr)
assert p.returncode == 12, (p.returncode, p.stderr)
print("OK unhandled set_route -> exit 12 (UNIMPLEMENTED)")

sys.path.insert(0, "$ROOT/qsd_spacetime")
import common, qsd_daemon
from qsd_terminal import SimStackTerminal
common.STATE_DIR = env["QSD_STATE_DIR"]
common.BEAMS = os.path.join(common.STATE_DIR, "beams.json")
common.STATUS = os.path.join(common.STATE_DIR, "status.json")
common.LOCAL_METRICS = os.path.join(common.STATE_DIR, "local_metrics.json")
qsd_daemon.BEAMS = common.BEAMS
qsd_daemon.STATUS = common.STATUS
qsd_daemon.LOCAL_METRICS = common.LOCAL_METRICS
# Configure real modem IDs so measured SINR can export (M2: never invent).
beams = common.load(common.BEAMS, {})
beams["beam-live"]["rx_modem_id"] = "ant-live-demod"
beams["beam-live"]["tx_modem_id"] = "beam-live-remote"
common.save(common.BEAMS, beams)
qsd_daemon.run_stack(SimStackTerminal(seed=1), steps=40, dt=0.0)
p = subprocess.run([sys.executable, "$ROOT/qsd_spacetime/qsd_telemetry.py"],
                   capture_output=True, text=True, env=env)
assert p.returncode == 0, p.stderr
msg = json_format.Parse(p.stdout, tele.ExportMetricsRequest())
assert msg.interface_metrics[0].interface_id
# Modem metrics only when IDs configured + measured SINR present
assert len(msg.modem_metrics) >= 1
assert msg.modem_metrics[0].sinr_data_points[0].HasField("sinr_db")
print("OK telemetry -> ExportMetricsRequest (measured SINR, configured modem IDs)")
PY

step "optional: build + dry-run Go agent (bazel)"
BZL="$(command -v bazelisk || command -v bazel || true)"
if [[ -n "$BZL" ]]; then
  DRY_CFG="$TMP/agent_dry.textproto"
  sed -e "s|\${AGENT_ID}|qsd-verify-agent|g" \
      -e "s|\${DOMAIN}|example.invalid|g" \
      -e "s|\${AGENT_EMAIL}|agent@example.invalid|g" \
      -e "s|\${PRIVATE_KEY_ID}|DEADBEEF|g" \
      -e "s|/opt/qsd_spacetime/|$ROOT/qsd_spacetime/|g" \
      -e "s|/path/to/agent/private/key.pem|$TMP/dummy.pem|g" \
      "$CFG" > "$DRY_CFG"
  openssl genrsa -out "$TMP/dummy.pem" 2048 2>/dev/null
  (
    cd "$AALY"
    if "$BZL" build //agent/cmd/agent; then
      AGENT_BIN="bazel-bin/agent/cmd/agent/agent_/agent"
      echo "agent binary: $AGENT_BIN"
      if "$AGENT_BIN" --config "$DRY_CFG" --dry-run; then
        echo "OK agent --dry-run accepts QSD agent_config.textproto"
      else
        echo "FAIL agent dry-run"; exit 1
      fi
      "$BZL" test \
        //agent/enactment/extproc:extproc_test \
        //agent/internal/extprocs:extprocs_test \
        //agent/internal/protofmt:protofmt_test \
        //agent/internal/agentcli:agentcli_test \
        --test_output=errors
      echo "OK aalyria agent extproc unit tests"
    else
      echo "WARN bazel build //agent/cmd/agent failed; Python path verified"
    fi
  )
else
  echo "SKIP bazel not installed"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "VERIFY PASS"
  exit 0
fi
echo "VERIFY FAIL"
exit 1
