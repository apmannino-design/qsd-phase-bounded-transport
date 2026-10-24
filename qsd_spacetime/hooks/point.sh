#!/usr/bin/env bash
# QSD_HW_POINT_CMD example. Args: az_deg el_deg beam_id
set -euo pipefail
az="${1:?az_deg required}"
el="${2:?el_deg required}"
beam_id="${3:?beam_id required}"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) POINT beam=${beam_id} az=${az} el=${el}" \
  >> "${QSD_HW_HOOK_LOG:-/tmp/qsd_hw_hooks.log}"
# exec /opt/terminal/bin/point --az "$az" --el "$el" --beam "$beam_id"
exit 0
