# Spacetime access keys

Aalyria Spacetime authenticates the SDN agent with a JWT signed by an RSA
private key. The matching public key must be delivered inside a self-signed
x509 certificate.

| File | Commit? | Who sees it |
|---|---|---|
| `agent_priv_key.pem` | **No** (gitignored) | Only your operator host |
| `agent_pub_key.cer` | Optional | Share with Aalyria to get API access |

## Generate

From the repo root:

```bash
scripts/generate_spacetime_keys.sh
```

That writes both files into this directory. Then:

1. Email / upload **only** `agent_pub_key.cer` to your Aalyria contact.
2. Receive `AGENT_EMAIL` (user id) and `PRIVATE_KEY_ID` (key id).
3. Put those values into `../bringup.env` (copied from `bringup.env.example`).
4. Point `STAGING_PRIVATE_KEY_PEM` at `agent_priv_key.pem` (absolute path).
5. Dry-run: `../scripts/spacetime_staging_dryrun.sh`

Do **not** put the `.pem` in git, Slack, or email.
