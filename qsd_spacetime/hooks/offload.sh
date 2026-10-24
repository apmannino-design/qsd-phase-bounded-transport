#!/usr/bin/env bash
# QSD_HW_OFFLOAD_CMD example. Arg: beam_id
# Replace the echo with your gimbal/FSM offload trigger.
set -euo pipefail
beam_id="${1:?beam_id required}"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) OFFLOAD beam=${beam_id}" >> "${QSD_HW_HOOK_LOG:-/tmp/qsd_hw_hooks.log}"
# exec /opt/terminal/bin/offload --beam "$beam_id"
exit 0
