#!/usr/bin/env bash
# IBM QSD stabilization campaign
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

pip install -e . -q 2>/dev/null || pip3 install -e . -q
pip install qiskit qiskit-aer qiskit-ibm-runtime matplotlib -q 2>/dev/null \
  || pip3 install qiskit qiskit-aer qiskit-ibm-runtime matplotlib -q

BACKEND="${BACKEND:-ibm_fez}"
BUDGET="${BUDGET:-mini}"
PHASE="${1:-help}"
NOWAIT="${NOWAIT:-}"

EXTRA=()
if [[ "${NOWAIT}" == "1" ]]; then
  EXTRA+=(--nowait)
fi

case "${PHASE}" in
  prereg|discover|sweep|fullchip|control|depth|sunscreen|collect|analyze|all)
    PYTHONUNBUFFERED=1 python3 examples/qsd_stabilization_campaign.py \
      "${PHASE}" --backend "${BACKEND}" --budget "${BUDGET}" "${EXTRA[@]}" "${@:2}"
    ;;
  aer-test)
    PYTHONUNBUFFERED=1 python3 examples/qsd_stabilization_campaign.py all \
      --backend aer --budget mini
    ;;
  hw-mini)
    # Typical Open Plan session: prereg once, then submit with --nowait
    python3 examples/qsd_stabilization_campaign.py prereg || true
    for p in discover sweep fullchip control depth sunscreen; do
      echo "=== ${p} ==="
      NOWAIT=1 BACKEND="${BACKEND}" BUDGET=mini "$0" "${p}"
    done
    echo "Submitted. When queue clears:  ./run_ibm_campaign.sh collect"
    ;;
  help|*)
    cat <<EOF
IBM QSD Stabilization Campaign
==============================

Prerequisites:
  ibm-quantum-login   (or save token in ~/.qiskit/qiskit-ibm.json)

Quick Aer plumbing test (no IBM minutes):
  ./run_ibm_campaign.sh aer-test

Real hardware (mini budget, queue-safe):
  BACKEND=ibm_fez ./run_ibm_campaign.sh hw-mini
  BACKEND=ibm_fez ./run_ibm_campaign.sh collect
  ./run_ibm_campaign.sh analyze

Phase by phase:
  ./run_ibm_campaign.sh prereg
  BACKEND=ibm_fez ./run_ibm_campaign.sh discover
  BACKEND=ibm_fez NOWAIT=1 ./run_ibm_campaign.sh sweep
  ...

State: results/state.json
Report: results/campaign_report.json
EOF
    ;;
esac
