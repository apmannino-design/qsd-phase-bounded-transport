#!/usr/bin/env bash
# Fetch Aalyria Spacetime open-source API (github.com/aalyria/api) plus the
# NMTS / googleapis proto deps needed to regenerate Python bindings.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TP="$ROOT/third_party"
PIN_FILE="$TP/AALYRIA_API_PIN.txt"
AALY_URL="${AALY_URL:-https://github.com/aalyria/api.git}"
AALY_REF="${AALY_REF:-main}"
NMTS_URL="${NMTS_URL:-https://github.com/outernetcouncil/nmts/archive/refs/tags/v1.21.0.tar.gz}"
GOOGLEAPIS_URL="${GOOGLEAPIS_URL:-https://github.com/googleapis/googleapis.git}"

mkdir -p "$TP"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> cloning aalyria/api ($AALY_REF)"
git clone --depth 1 --branch "$AALY_REF" "$AALY_URL" "$TMP/aalyria-api"
SHA="$(git -C "$TMP/aalyria-api" rev-parse HEAD)"
DATE="$(git -C "$TMP/aalyria-api" log -1 --format=%ci)"
rm -rf "$TMP/aalyria-api/.git"
rm -rf "$TP/aalyria-api"
mv "$TMP/aalyria-api" "$TP/aalyria-api"

echo "==> fetching nmts v1.21.0"
curl -fsSL "$NMTS_URL" | tar -xz -C "$TMP"
rm -rf "$TP/nmts"
mv "$TMP"/nmts-* "$TP/nmts"

echo "==> sparse-cloning googleapis (google/{rpc,type,api})"
git clone --depth 1 --filter=blob:none --sparse "$GOOGLEAPIS_URL" "$TMP/googleapis"
git -C "$TMP/googleapis" sparse-checkout set google/rpc google/type google/api
rm -rf "$TMP/googleapis/.git"
rm -rf "$TP/googleapis"
mv "$TMP/googleapis" "$TP/googleapis"

mkdir -p "$TP/proto_include"
ln -sfn ../nmts "$TP/proto_include/nmts"

cat > "$PIN_FILE" <<EOF
repo=https://github.com/aalyria/api
ref=$AALY_REF
commit=$SHA
date=$DATE
nmts=$NMTS_URL
googleapis=$GOOGLEAPIS_URL
EOF

echo "Pinned aalyria/api @$SHA -> $PIN_FILE"
echo "Done. Next: scripts/regen_qsd_spacetime_protos.sh"
