#!/usr/bin/env bash
# Save IBM token to ~/.qiskit/ (NOT in repo). Usage:
#   export QISKIT_IBM_TOKEN="your_token"
#   ./setup_ibm_token.sh
set -euo pipefail
if [[ -z "${QISKIT_IBM_TOKEN:-}" ]]; then
  echo "Set QISKIT_IBM_TOKEN first. Do NOT paste tokens into git-tracked files."
  exit 1
fi
mkdir -p ~/.qiskit
python3 << 'PY'
import json, os
path = os.path.expanduser("~/.qiskit/qiskit-ibm.json")
cfg = {
    "default-ibm-quantum": {
        "channel": os.environ.get("QISKIT_IBM_CHANNEL", "ibm_quantum_platform"),
        "token": os.environ["QISKIT_IBM_TOKEN"],
        "url": "https://quantum.cloud.ibm.com",
        "instance": os.environ.get("QISKIT_IBM_INSTANCE", "open-instance"),
    }
}
with open(path, "w") as f:
    json.dump(cfg, f)
os.chmod(path, 0o600)
print(f"Saved IBM credentials to {path} (mode 600)")
PY
python3 -c "
from qiskit_ibm_runtime import QiskitRuntimeService
svc = QiskitRuntimeService()
print('Connected. Sample backends:', [b.name for b in svc.backends()[:5]])
"
