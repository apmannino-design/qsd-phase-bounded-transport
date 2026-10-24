#!/usr/bin/env bash
# Build (and optionally submit) the weather→NBI ServiceRequest fragment.
#
# Default is dry-run: writes state/nbi_service_request.json and prints it.
# Live submit requires nbictl configured with Aalyria credentials:
#   QSD_NBI_LIVE=1 scripts/qsd_nbi_submit.sh --weather weather.json --src-node NODE
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QS="$ROOT/qsd_spacetime"
STATE="${QSD_STATE_DIR:-$QS/state}"
mkdir -p "$STATE"

WEATHER=""
SRC_NODE=""
LIVE="${QSD_NBI_LIVE:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --weather) WEATHER="$2"; shift 2 ;;
    --src-node) SRC_NODE="$2"; shift 2 ;;
    --live) LIVE=1; shift ;;
    *) echo "usage: $0 --weather FILE --src-node NODE [--live]" >&2; exit 2 ;;
  esac
done
[[ -n "$WEATHER" && -n "$SRC_NODE" ]] || {
  echo "usage: $0 --weather FILE --src-node NODE [--live]" >&2; exit 2
}

python3 "$QS/qsd_weather_ingest.py" --in "$WEATHER" --out "$STATE/weather_advice.json"
python3 "$QS/qsd_weather_to_nbi.py" \
  --advice "$STATE/weather_advice.json" \
  --src-node "$SRC_NODE" \
  --out "$STATE/nbi_service_request.json"

echo "==> wrote $STATE/nbi_service_request.json"
python3 - <<PY
import json
d=json.load(open("$STATE/nbi_service_request.json"))
print("submit=", d.get("submit"), "reason=", d.get("reason"))
if d.get("submit"):
    print("dstNodeId=", d["service_request"]["dstNodeId"])
PY

if [[ "$LIVE" != "1" ]]; then
  echo "DRY-RUN only. Set QSD_NBI_LIVE=1 or pass --live after nbictl is configured."
  echo "Merge order reminder: land PR #14 then #15 before staging bring-up on main."
  exit 0
fi

if ! command -v nbictl >/dev/null 2>&1; then
  echo "FAIL: nbictl not on PATH (build from third_party/aalyria-api/tools/nbictl)" >&2
  exit 1
fi

# Live path: exact Model API subcommand varies by nbictl version — print payload
# and invoke create-entity only if the operator has wired a wrapper.
WRAPPER="${QSD_NBI_SUBMIT_WRAPPER:-}"
if [[ -n "$WRAPPER" ]]; then
  exec "$WRAPPER" "$STATE/nbi_service_request.json"
fi
echo "FAIL: set QSD_NBI_SUBMIT_WRAPPER to your nbictl/Model submit script." >&2
echo "Payload ready at $STATE/nbi_service_request.json" >&2
exit 1
