#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PHASE="${1:-help}"
shift || true

case "${PHASE}" in
  willow)
    python3 examples/qsd_entanglement_theta_sweep.py --backend willow "$@"
    ;;
  willow-quick)
    python3 examples/qsd_entanglement_theta_sweep.py --backend willow --quick "$@"
    ;;
  aer)
    python3 examples/qsd_entanglement_theta_sweep.py --backend aer_fez --el "${EL:-2}" "$@"
    ;;
  ibm)
    python3 examples/qsd_entanglement_theta_sweep.py \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --el "${EL:-2}" \
      "$@"
    ;;
  cascade-quick)
    python3 examples/willow_cascade_entanglement.py --quick "$@"
    ;;
  cascade-max)
    python3 examples/willow_cascade_entanglement.py --max "$@"
    ;;
  help|*)
    cat <<'EOF'
Entanglement corridor θ sweep (22.5° → 90°)
===========================================

Run ONE command at a time.

Willow sim (5 angles, fast):
  ./run_entanglement_theta.sh willow-quick

Willow full corridor:
  ./run_entanglement_theta.sh willow

IBM noisy Aer (FakeFez):
  ./run_entanglement_theta.sh aer

IBM hardware [20,21,36] @ El=2:
  ./run_entanglement_theta.sh ibm

Full-chip cascade (max qubits × depth):
  ./run_entanglement_theta.sh cascade-quick

Angles: 22.5, 22.49, 27.61, 45, 67.5, 90 (default)
El=2  galaxy-propagation probe (May 2026 G rises El=1→2)
EOF
    ;;
esac
