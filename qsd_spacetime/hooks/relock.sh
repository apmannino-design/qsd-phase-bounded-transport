#!/usr/bin/env bash
# QSD_HW_RELOCK_CMD example. Arg: beam_id
set -euo pipefail
beam_id="${1:?beam_id required}"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) RELOCK beam=${beam_id}" >> "${QSD_HW_HOOK_LOG:-/tmp/qsd_hw_hooks.log}"
# exec /opt/terminal/bin/relock --beam "$beam_id"
exit 0
