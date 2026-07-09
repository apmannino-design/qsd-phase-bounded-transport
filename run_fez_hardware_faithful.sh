#!/usr/bin/env bash
# Hardware-faithful FakeFez benchmark (improvements 1–4)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
pip install -e . -q
pip install qiskit qiskit-aer qiskit-ibm-runtime -q
PYTHONUNBUFFERED=1 python3 examples/fez_hardware_faithful.py \
  --shots "${SHOTS:-2048}" \
  --depth "${DEPTH:-140}" \
  --cells "${CELLS:-43}" \
  --noise "${NOISE:-native}" \
  "$@"
