#!/usr/bin/env bash
# IBM QSD retention audit — Mac-friendly wrapper (no venv required if deps installed)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

pip install -e . -q 2>/dev/null || pip3 install -e . -q 2>/dev/null || true
pip3 install qiskit qiskit-aer qiskit-ibm-runtime numpy -q 2>/dev/null || true

PHASE="${1:-help}"
shift || true

case "${PHASE}" in
  ideals)
    python3 examples/qsd_ibm_retention_audit.py --backend aer_sim --ideals-only "$@"
    ;;
  aer-fez)
    python3 examples/qsd_ibm_retention_audit.py --backend aer_fez --shots 2048 --layers 14 --sweep "$@"
    ;;
  hw)
    BACKEND="${BACKEND:-ibm_fez}"
    QUBITS="${QUBITS:-20,21,36}"
    python3 examples/qsd_ibm_retention_audit.py \
      --backend "${BACKEND}" --qubits "${QUBITS}" --shots 4096 --layers 14 --theta-deg 22.5 --sweep "$@"
    ;;
  diagnostic)
    BACKEND="${BACKEND:-ibm_fez}"
    python3 examples/qsd_ibm_retention_audit.py --backend "${BACKEND}" --diagnostic --shots 2048 "$@"
    ;;
  help|*)
    cat <<'EOF'
IBM QSD Retention Audit
=======================

Run ONE command at a time (do not paste lines starting with # in zsh).

  ./run_ibm_retention.sh ideals
  ./run_ibm_retention.sh aer-fez
  BACKEND=ibm_fez QUBITS=20,21,36 ./run_ibm_retention.sh hw
  BACKEND=ibm_fez ./run_ibm_retention.sh diagnostic

Or directly:
  python3 examples/qsd_ibm_retention_audit.py --backend aer_sim --ideals-only
EOF
    ;;
esac
