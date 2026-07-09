#!/usr/bin/env bash
# QSD Robust Test Suite v2.0.0 — Mac wrapper
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PHASE="${1:-help}"
shift || true

case "${PHASE}" in
  sim)
    python3 examples/qsd_robust_test_suite_v200.py --mode sim "$@"
    ;;
  hw)
    python3 examples/qsd_robust_test_suite_v200.py --mode hw \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      "$@"
    ;;
  hw-t1)
    python3 examples/qsd_robust_test_suite_v200.py --mode hw \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --only T1 "$@"
    ;;
  hw-t2)
    python3 examples/qsd_robust_test_suite_v200.py --mode hw \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --only T2 "$@"
    ;;
  hw-report)
    python3 examples/qsd_robust_test_suite_v200.py --mode hw \
      --backend "${BACKEND:-ibm_fez}" \
      --qubits "${QUBITS:-20,21,36}" \
      --only T3,T4 "$@"
    ;;
  prereg)
    python3 examples/qsd_robust_test_suite_v200.py --show-prereg
    ;;
  help|*)
    cat <<'EOF'
QSD Robust Test Suite v2.0.0
============================

Run ONE command at a time.

Fast simulation (all T1–T4, no IBM token):
  ./run_robust_v200.sh sim

Real IBM hardware (needs QISKIT_IBM_TOKEN):
  ./run_robust_v200.sh hw-t1
  ./run_robust_v200.sh hw-t2
  ./run_robust_v200.sh hw-report

Full hardware queue (T1+T2 submit, ~30+ jobs):
  ./run_robust_v200.sh hw

Show frozen preregistration:
  ./run_robust_v200.sh prereg

Theory θ* = 22.5° (π/8). Wall = 22.28° @ 1L.
Circuits use fez_cells TriLock + QSD (not RY-only stubs).
EOF
    ;;
esac
