#!/usr/bin/env bash
# Regenerate qsd_spacetime/gen Python protobuf bindings from vendored
# aalyria/api + nmts + googleapis.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TP="$ROOT/third_party"
GEN="$ROOT/qsd_spacetime/gen"
AALY="$TP/aalyria-api"
NMTS="$TP/nmts"
GAPI="$TP/googleapis"
# Protos import "nmts/v1/...", so expose nmts under a synthetic include root.
INC="$TP/proto_include"
mkdir -p "$INC"
ln -sfn ../nmts "$INC/nmts"

for d in "$AALY" "$NMTS" "$GAPI"; do
  if [[ ! -d "$d" ]]; then
    echo "missing $d - run scripts/fetch_aalyria_spacetime.sh first" >&2
    exit 1
  fi
done

export PATH="${HOME}/.local/bin:${PATH}"
python3 -c "import grpc_tools.protoc" 2>/dev/null || pip install -q grpcio-tools 'protobuf>=5'
# google.rpc / google.type come from this package — do NOT emit them into gen/
# (a local google/ tree would shadow google.protobuf).
python3 -c "import google.rpc.status_pb2, google.type.quaternion_pb2" 2>/dev/null \
  || pip install -q 'googleapis-common-protos>=1.63'

rm -rf "$GEN"
mkdir -p "$GEN"

# Include paths match import statements in aalyria/api and nmts protos.
INCLUDES=(
  -I"$AALY"
  -I"$INC"
  -I"$GAPI"
  -I/usr/include
)

# Only emit Aalyria + NMTS Python; resolve google/* via -I + site-packages.
PROTOS=(
  "$AALY/api/common/field_mask.proto"
  "$AALY/api/scheduling/v1alpha/scheduling.proto"
  "$AALY/api/telemetry/v1alpha/telemetry.proto"
  "$AALY/agent/internal/configpb/config.proto"
  "$INC/nmts/v1/proto/types/geophys/coordinates.proto"
  "$INC/nmts/v1/proto/types/geophys/geodesy.proto"
)

echo "==> protoc -> $GEN"
python3 -m grpc_tools.protoc \
  "${INCLUDES[@]}" \
  --python_out="$GEN" \
  "${PROTOS[@]}"

# Package markers so imports like `from api.scheduling.v1alpha import scheduling_pb2` work.
find "$GEN" -type d -exec touch {}/__init__.py \;

# Drop anything accidental under gen that isn't Python.
find "$GEN" -type f ! -name '*.py' -delete 2>/dev/null || true

echo "==> smoke-import generated modules"
PYTHONPATH="$GEN" python3 - <<'PY'
from google.protobuf import text_format
from api.scheduling.v1alpha import scheduling_pb2 as sched
from api.telemetry.v1alpha import telemetry_pb2 as tele
from agent.internal.configpb import config_pb2
assert hasattr(sched, "CreateEntryRequest")
assert hasattr(tele, "ExportMetricsRequest")
# Top-level config message must expose sdn_agents.
top = next(
    getattr(config_pb2, n)
    for n in dir(config_pb2)
    if n[:1].isupper()
    and hasattr(getattr(config_pb2, n), "DESCRIPTOR")
    and "sdn_agents" in getattr(config_pb2, n).DESCRIPTOR.fields_by_name
)
print("OK:", top.__name__, "CreateEntryRequest, ExportMetricsRequest")
PY

echo "Regenerated $GEN"
