#!/usr/bin/env bash
# Aurora-QSD Qiskit Aer simulator — one-command setup and run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=============================================="
echo " Aurora-QSD Qiskit Simulator Setup"
echo "=============================================="

# Install deps
pip install -e . -q
pip install qiskit qiskit-aer qiskit-ibm-runtime -q

echo ""
echo "Dependencies installed."
echo ""

# Run tests
SHOTS="${SHOTS:-8192}"
LAYERS="${LAYERS:-12}"

echo "=============================================="
echo " [1/3] Noisy simulator (hardware-faithful)"
echo "=============================================="
python3 examples/qiskit_sim_test.py --noise --sweep --depth-scale --shots "$SHOTS" --layers "$LAYERS"

echo ""
echo "=============================================="
echo " [2/3] Full 3-stage stress test"
echo "=============================================="
python3 examples/qiskit_sim_test.py --stress --shots "$SHOTS" --layers "$LAYERS"

echo ""
echo "=============================================="
echo " [3/3] Agent + example"
echo "=============================================="
python3 -m aurora_qsd.cli aurora
echo ""
python3 examples/aurora_qsd_quantum_example.py

echo ""
echo "=============================================="
echo " All simulator runs complete."
echo " Re-run anytime: ./run_qiskit_sim.sh"
echo "=============================================="
