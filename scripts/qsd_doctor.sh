#!/usr/bin/env bash
# Pre-bring-up checks for the QSD × Spacetime stack.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QS="$ROOT/qsd_spacetime"
STATE="${QSD_STATE_DIR:-$QS/state}"
FAIL=0
warn() { echo "WARN  $*"; }
ok() { echo "OK    $*"; }
bad() { echo "FAIL  $*"; FAIL=1; }

echo "==> QSD doctor (state=$STATE)"

# Merge order reminder
ok "safety + stack_v2 on main; next: local bringup then staging keys"

# Paths / hooks
for v in QSD_HW_SAMPLE_PATH QSD_HW_CMD_PATH QSD_HW_OFFLOAD_CMD QSD_HW_RELOCK_CMD QSD_HW_POINT_CMD; do
  val="${!v:-}"
  if [[ -z "$val" ]]; then
    warn "$v unset (source qsd_spacetime/bringup.env.example)"
  elif [[ "$v" == *_CMD && ! -x "$val" ]]; then
    bad "$v=$val not executable"
  else
    ok "$v=$val"
  fi
done

# Modem map (M2): without it, telemetry omits modem metrics
MODEM_MAP_PATH="${QSD_MODEM_MAP:-$STATE/modem_map.json}"
if [[ -f "$MODEM_MAP_PATH" ]]; then
  python3 - <<PY
import json, sys
p = "$MODEM_MAP_PATH"
try:
    m = json.load(open(p))
except Exception as e:
    print(f"FAIL  modem_map unreadable: {e}"); sys.exit(1)
if not isinstance(m, dict) or not m:
    print("WARN  modem_map empty — modem metrics will be omitted")
else:
    n = sum(1 for v in m.values() if isinstance(v, dict) and (v.get("rx_modem_id") or v.get("tx_modem_id")))
    print(f"OK    modem_map entries={len(m)} with_ids={n} ({p})")
PY
else
  warn "no modem_map at $MODEM_MAP_PATH — copy modem_map.json.example (modem metrics omitted)"
fi

# Sample freshness
SAMPLE="${QSD_HW_SAMPLE_PATH:-$STATE/hw_sample.json}"
if [[ -f "$SAMPLE" ]]; then
  python3 - <<PY
import json, time, os, sys
p = "$SAMPLE"
age = time.time() - os.path.getmtime(p)
try:
    d = json.load(open(p))
except Exception as e:
    print(f"FAIL  sample unreadable: {e}"); sys.exit(1)
unix = d.get("unix_s")
fresh = isinstance(unix, (int, float)) and abs(time.time() - unix) < 2.0
print(f"{'OK   ' if fresh else 'WARN '} sample mtime_age={age:.2f}s unix_age={None if unix is None else time.time()-unix:.2f}s seq={d.get('sequence')} locked={d.get('locked')}")
if not fresh:
    sys.exit(0)
PY
else
  warn "no sample at $SAMPLE — run qsd_hw_sample_pump.py or your driver"
fi

# Calibration age / predict verdict
CAL="$STATE/calibration.json"
if [[ -f "$CAL" ]]; then
  python3 - <<PY
import json, time, os
p = "$CAL"
age_h = (time.time() - os.path.getmtime(p)) / 3600
c = json.load(open(p))
print(f"OK    calibration age={age_h:.1f}h predict={c.get('predict')} verdict={c.get('holdout_verdict', c.get('notes','')).split(chr(10))[0][:80]}")
if age_h > 168:
    print("WARN  calibration older than 7 days — re-run scorecard on fresh recording")
PY
else
  warn "no $CAL — run scripts/qsd_terminal_pipeline.sh"
fi

# Status / local metrics
for f in status.json local_metrics.json; do
  if [[ -f "$STATE/$f" ]]; then
    ok "$f present"
  else
    warn "$f missing (daemon not running yet is fine)"
  fi
done

# Agent staging dry-run (SKIP is a warning, not OK — review M1)
if [[ -x "$ROOT/scripts/spacetime_staging_dryrun.sh" ]]; then
  if "$ROOT/scripts/spacetime_staging_dryrun.sh" >/tmp/qsd_doctor_staging.log 2>&1; then
    if grep -q '^SKIP' /tmp/qsd_doctor_staging.log; then
      warn "staging agent dry-run SKIPPED (see /tmp/qsd_doctor_staging.log)"
    else
      ok "staging agent --dry-run"
    fi
  else
    bad "staging dry-run failed (see /tmp/qsd_doctor_staging.log)"
  fi
else
  warn "spacetime_staging_dryrun.sh missing"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "DOCTOR PASS"
  exit 0
fi
echo "DOCTOR FAIL"
exit 1
