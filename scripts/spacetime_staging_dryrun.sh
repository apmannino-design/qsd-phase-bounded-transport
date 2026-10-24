#!/usr/bin/env bash
# Validate staging agent_config against the vendored Go agent (--dry-run).
# Does not contact Spacetime. Requires bazelisk + built agent (or builds it).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AALY="$ROOT/third_party/aalyria-api"
TEMPLATE="$ROOT/qsd_spacetime/agent_config.staging.textproto"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

: "${STAGING_AGENT_ID:=qsd-staging-agent}"
: "${STAGING_DOMAIN:=staging.example.invalid}"
: "${STAGING_AGENT_EMAIL:=agent@staging.example.invalid}"
: "${STAGING_PRIVATE_KEY_ID:=STAGINGKEY}"
: "${STAGING_PRIVATE_KEY_PEM:=$TMP/staging.pem}"
: "${QSD_SPACETIME_ROOT:=$ROOT/qsd_spacetime}"

if [[ ! -f "$STAGING_PRIVATE_KEY_PEM" ]]; then
  openssl genrsa -out "$STAGING_PRIVATE_KEY_PEM" 2048 2>/dev/null
fi

sed -e "s|\${STAGING_AGENT_ID}|$STAGING_AGENT_ID|g" \
    -e "s|\${STAGING_DOMAIN}|$STAGING_DOMAIN|g" \
    -e "s|\${STAGING_AGENT_EMAIL}|$STAGING_AGENT_EMAIL|g" \
    -e "s|\${STAGING_PRIVATE_KEY_ID}|$STAGING_PRIVATE_KEY_ID|g" \
    -e "s|\${STAGING_PRIVATE_KEY_PEM}|$STAGING_PRIVATE_KEY_PEM|g" \
    -e "s|\${QSD_SPACETIME_ROOT}|$QSD_SPACETIME_ROOT|g" \
    "$TEMPLATE" > "$TMP/agent.staging.textproto"

echo "==> staging config written to $TMP/agent.staging.textproto"

# Python schema check (always)
PYTHONPATH="$ROOT/qsd_spacetime/gen" python3 - <<PY
from google.protobuf import text_format
from agent.internal.configpb import config_pb2
top = next(
    getattr(config_pb2, n)
    for n in dir(config_pb2)
    if n[:1].isupper()
    and hasattr(getattr(config_pb2, n), "DESCRIPTOR")
    and "sdn_agents" in getattr(config_pb2, n).DESCRIPTOR.fields_by_name
)
cfg = text_format.Parse(open("$TMP/agent.staging.textproto").read(), top())
assert cfg.sdn_agents[0].enactment_driver.HasField("external_command")
print("OK python AgentParams parse")
PY

BZL="$(command -v bazelisk || command -v bazel || true)"
if [[ -z "$BZL" || ! -d "$AALY" ]]; then
  echo "SKIP Go agent dry-run (bazelisk or third_party/aalyria-api missing)"
  exit 0
fi

cd "$AALY"
"$BZL" build //agent/cmd/agent
AGENT_BIN="bazel-bin/agent/cmd/agent/agent_/agent"
"$AGENT_BIN" --config "$TMP/agent.staging.textproto" --dry-run
echo "OK staging agent --dry-run"
