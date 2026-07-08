#!/usr/bin/env bash
# IBM QSD retention + θ calibration (calibrate first, then 22.28° wall)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PHASE="${1:-help}"
shift || true

case "${PHASE}" in
  calibrate)
    python3 examples/qsd_ibm_retention_audit.py calibrate \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --shots "${SHOTS:-2048}" \
      "$@"
    ;;
  wall)
    python3 examples/qsd_ibm_retention_audit.py wall \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --calib-shots "${CALIB_SHOTS:-2048}" \
      --retention-shots "${RETENTION_SHOTS:-4096}" \
      --layers "${LAYERS:-1}" \
      "$@"
    ;;
  retention)
    python3 examples/qsd_ibm_retention_audit.py retention \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --theta-deg "${THETA:-22.28}" \
      --layers "${LAYERS:-1}" \
      --shots "${SHOTS:-4096}" \
      "$@"
    ;;
  ideals)
    python3 examples/qsd_ibm_retention_audit.py retention \
      --backend aer_sim --theta-deg 22.28 --layers 1 --ideals-only
    ;;
  help|*)
    cat <<'EOF'
IBM QSD Calibration + Wall Protocol
===================================

Run ONE command at a time.

Step 1 — θ calibration (1 layer, hardware):
  ./run_ibm_retention.sh calibrate

Step 2 — calibrate + retention @ 22.28° wall:
  ./run_ibm_retention.sh wall

Or step-by-step:
  ./run_ibm_retention.sh calibrate
  ./run_ibm_retention.sh retention

Theory θ* = 22.5° (π/8) unchanged. Wall = 22.28° operating point.
EOF
    ;;
esac
