#!/usr/bin/env bash
# End-to-end: record (sim or existing file) → holdout calibrate/scorecard →
# optional weather→NBI fragment. Uses the dry plant when --sim is set.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/qsd_spacetime"
export QSD_STATE_DIR="${QSD_STATE_DIR:-$ROOT/qsd_spacetime/state}"
mkdir -p "$QSD_STATE_DIR"

SECONDS_REC="${SECONDS_REC:-3}"
BEAM_ID="${BEAM_ID:-beam-A}"
IFACE="${IFACE:-ant-1}"
RECORD="${RECORD:-$QSD_STATE_DIR/terminal_record.jsonl}"
SIM=0
WEATHER=""
SRC_NODE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sim) SIM=1; shift ;;
    --record) RECORD="$2"; shift 2 ;;
    --seconds) SECONDS_REC="$2"; shift 2 ;;
    --beam-id) BEAM_ID="$2"; shift 2 ;;
    --weather) WEATHER="$2"; shift 2 ;;
    --src-node) SRC_NODE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "$SIM" -eq 1 || ! -f "$RECORD" ]]; then
  echo "==> recording sim plant (${SECONDS_REC}s) -> $RECORD"
  rm -f "$RECORD"
  python3 qsd_record_replay.py record \
    --out "$RECORD" --seconds "$SECONDS_REC" \
    --beam-id "$BEAM_ID" --interface-id "$IFACE" \
    --via-supervisor --vib-amp 15 --vib-hz 5
fi

echo "==> holdout calibrate + equal-offload scorecard"
python3 qsd_scorecard_holdout.py \
  --record "$RECORD" --beam-id "$BEAM_ID" --interface-id "$IFACE" \
  --out-cal "$QSD_STATE_DIR/calibration.json" \
  --out-scorecard "$QSD_STATE_DIR/scorecard_holdout.json"

if [[ -n "$WEATHER" ]]; then
  echo "==> weather ingest + NBI fragment"
  python3 qsd_weather_ingest.py --in "$WEATHER" --out "$QSD_STATE_DIR/weather_advice.json"
  if [[ -z "$SRC_NODE" ]]; then
    echo "WARN: pass --src-node to emit NBI ServiceRequest fragment" >&2
  else
    python3 qsd_weather_to_nbi.py \
      --advice "$QSD_STATE_DIR/weather_advice.json" \
      --src-node "$SRC_NODE" \
      --out "$QSD_STATE_DIR/nbi_service_request.json"
  fi
fi

echo "==> done"
python3 - <<PY
import json
sc=json.load(open("$QSD_STATE_DIR/scorecard_holdout.json"))
print("recommend_predict=", sc["recommend_predict"], "|", sc["reason"])
PY
