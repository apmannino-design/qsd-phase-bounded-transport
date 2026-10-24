#!/usr/bin/env bash
# Generate the RSA keypair Spacetime (Aalyria) needs for JWT auth.
# Share only the public .cer with Aalyria. Never commit or email the .pem.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYS="${QSD_SPACETIME_KEYS:-$ROOT/qsd_spacetime/keys}"
ORG="${QSD_SPACETIME_ORG:-apmannino-design}"
CN="${QSD_SPACETIME_CN:-qsd-spacetime-agent}"
DAYS="${QSD_SPACETIME_CERT_DAYS:-36500}"

mkdir -p "$KEYS"
PRIV="$KEYS/agent_priv_key.pem"
PUB="$KEYS/agent_pub_key.cer"

if [[ -f "$PRIV" || -f "$PUB" ]]; then
  echo "Refusing to overwrite existing key material in $KEYS" >&2
  echo "Remove agent_priv_key.pem / agent_pub_key.cer first if you intend to rotate." >&2
  exit 1
fi

openssl genrsa -out "$PRIV" 4096
chmod 600 "$PRIV"
openssl req -new -x509 -key "$PRIV" -out "$PUB" -days "$DAYS" \
  -subj "/O=${ORG}/CN=${CN}"

echo
echo "Wrote:"
echo "  private (KEEP SECRET): $PRIV"
echo "  public  (share w/ Aalyria): $PUB"
echo
echo "Next:"
echo "  1. Send $PUB to your Aalyria representative (public cert only)."
echo "  2. They return USER_ID / AGENT_EMAIL and KEY_ID / PRIVATE_KEY_ID."
echo "  3. Fill qsd_spacetime/bringup.env from bringup.env.example,"
echo "     pointing STAGING_PRIVATE_KEY_PEM at $PRIV."
echo "  4. Run: scripts/spacetime_staging_dryrun.sh"
