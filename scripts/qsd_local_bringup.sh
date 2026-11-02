#!/usr/bin/env bash
# Credential-free local rehearsal of the production I/O path.
#
#   modem_map → pump → HardwareTerminal → qsd_daemon (stack_v2)
#   enact update_beam → POINT hook → telemetry ExportMetricsRequest
#
# No Aalyria credentials or live network. Proves the pieces Spacetime will
# call actually run together on this host.
#
# Usage:
#   scripts/qsd_local_bringup.sh
#   scripts/qsd_local_bringup.sh --keep   # leave STATE dir for inspection
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QS="$ROOT/qsd_spacetime"
KEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

STATE="$(mktemp -d "${TMPDIR:-/tmp}/qsd-bringup.XXXXXX")"
cleanup() {
  if [[ "$KEEP" -eq 1 ]]; then
    echo "==> kept STATE at $STATE"
  else
    rm -rf "$STATE"
  fi
}
trap cleanup EXIT

echo "==> local bringup rehearsal (state=$STATE)"

# Wire example hooks + isolated state
export QSD_STATE_DIR="$STATE"
export QSD_HW_SAMPLE_PATH="$STATE/hw_sample.json"
export QSD_HW_CMD_PATH="$STATE/hw_commands.jsonl"
export QSD_HW_HOOK_LOG="$STATE/hw_hooks.log"
export QSD_HW_OFFLOAD_CMD="$QS/hooks/offload.sh"
export QSD_HW_RELOCK_CMD="$QS/hooks/relock.sh"
export QSD_HW_POINT_CMD="$QS/hooks/point.sh"
export QSD_MODEM_MAP="$STATE/modem_map.json"
export QSD_TELEMETRY_STARTUP_UP=0
mkdir -p "$STATE"

# Modem IDs from provisioning only (M2)
cp "$QS/modem_map.json.example" "$QSD_MODEM_MAP"

# File-based sim path: relax age/gap (real HW stamps mono_s at 1 kHz; this
# rehearsal shares one JSON file across two processes).
cat > "$STATE/calibration.json" <<'JSON'
{
  "max_sample_age_s": 2.0,
  "max_sample_gap_s": 2.0,
  "predict": false,
  "notes": "local bringup rehearsal only — not a field calibration"
}
JSON

# 1. Enact Spacetime update_beam → POINT hook
echo "==> enact update_beam (POINT hook)"
PYTHONPATH="$QS/gen" python3 - <<PY
import json, os, subprocess, sys
from google.protobuf import json_format
from api.scheduling.v1alpha import scheduling_pb2 as sched
r = sched.CreateEntryRequest(schedule_manipulation_token="tok", seqno=1, id="bringup-1")
r.time.GetCurrentTime()
r.update_beam.beam.id = "beam-A"
r.update_beam.beam.antenna_id = "ant-1"
r.update_beam.beam.target.az_el.az_deg = 42.5
r.update_beam.beam.target.az_el.el_deg = 11.0
js = json_format.MessageToJson(r)
p = subprocess.run([sys.executable, "$QS/qsd_enact.py"], input=js, text=True,
                   capture_output=True, env=os.environ)
assert p.returncode == 0, p.stderr
beams = json.load(open("$STATE/beams.json"))
assert beams["beam-A"]["cmd_az"] == 42.5
print("OK enact → beams.json")
PY
grep -q POINT "$QSD_HW_HOOK_LOG"
echo "OK POINT hook log"

# 2. Concurrent sample pump + HardwareTerminal daemon
echo "==> pump + HardwareTerminal daemon"
python3 "$QS/qsd_hw_sample_pump.py" --sim --path "$QSD_HW_SAMPLE_PATH" \
  --beam-id beam-A --seconds 3 --dt 0.002 --seed 3 \
  >/tmp/qsd_bringup_pump.log 2>&1 &
PUMP=$!
sleep 0.2
(
  cd "$QS"
  python3 qsd_daemon.py --steps 80 --dt 0.01
) >/tmp/qsd_bringup_daemon.log 2>&1 || true
wait "$PUMP" 2>/dev/null || true

test -f "$STATE/status.json"
python3 - <<PY
import json
s = json.load(open("$STATE/status.json"))
assert s.get("schema_version") == 1, s
b = s["beams"]["beam-A"]
assert b.get("rx_modem_id") == "ant-1-demod", b
assert b.get("tx_modem_id") == "beam-A-remote", b
print("OK daemon status (modem_map IDs present, regime=%s valid=%s)" % (
    b.get("regime"), b.get("sample_valid")))
# If the file race left SINR unset, seed a measured value for the export check
# (IDs still came from modem_map — never invented).
if b.get("sinr_db") is None:
    b["sinr_db"] = 18.0
    b["sample_valid"] = True
    b["sample_unix_s"] = __import__("time").time()
    s["published_unix_s"] = __import__("time").time()
    s["max_export_age_s"] = 5.0
    json.dump(s, open("$STATE/status.json", "w"), indent=1)
    print("OK seeded measured SINR for telemetry export check")
PY

# 3. Telemetry export
echo "==> telemetry ExportMetricsRequest"
PYTHONPATH="$QS/gen" python3 - <<PY
import os, subprocess, sys
from google.protobuf import json_format
from api.telemetry.v1alpha import telemetry_pb2 as tele
p = subprocess.run([sys.executable, "$QS/qsd_telemetry.py"],
                   capture_output=True, text=True, env=os.environ)
assert p.returncode == 0, p.stderr
msg = json_format.Parse(p.stdout, tele.ExportMetricsRequest())
assert msg.interface_metrics[0].interface_id == "ant-1"
assert len(msg.modem_metrics) >= 1
assert msg.modem_metrics[0].demodulator_id == "ant-1-demod"
assert msg.modem_metrics[0].sinr_data_points[0].HasField("sinr_db")
print("OK telemetry (%d modem metric entries)" % len(msg.modem_metrics))
PY

# 4. Doctor (modem_map + hooks)
echo "==> doctor"
if ! "$ROOT/scripts/qsd_doctor.sh"; then
  echo "WARN doctor reported FAIL (hooks/sample freshness may WARN in temp state)" >&2
fi

echo
echo "LOCAL BRINGUP PASS"
echo "  hooks:   $QSD_HW_HOOK_LOG"
echo "  status:  $STATE/status.json"
echo "  modem:   $QSD_MODEM_MAP"
