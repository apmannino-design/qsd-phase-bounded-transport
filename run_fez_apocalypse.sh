#!/usr/bin/env bash
# Hardest FakeFez apocalypse stress — max noise, 43 cells, depth 1241, Aurora re-lock /3
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
pip install -e . -q
pip install qiskit qiskit-aer qiskit-ibm-runtime -q
echo "Running apocalypse-max (43 cells, depths 32-1241, ~15 min)..."
PYTHONUNBUFFERED=1 python3 examples/fez_apocalypse_max.py \
  --shots 2048 --cells 43 --lattice-qubits 7 \
  "$@"
