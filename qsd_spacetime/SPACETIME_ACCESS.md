# Spacetime access (QSD bridge)

This folder is what Aalyria Spacetime talks to. The Go SDN agent (from
`third_party/aalyria-api`) loads `agent_config*.textproto` and calls into QSD
via extproc:

| Spacetime needs | File in this folder |
|---|---|
| Agent JWT auth (private key path) | `keys/agent_priv_key.pem` (local only) |
| Public cert to enroll with Aalyria | `keys/agent_pub_key.cer` |
| Production agent wiring | `agent_config.textproto` |
| Staging agent wiring | `agent_config.staging.textproto` |
| Enactment extproc | `qsd_enact.py` |
| Telemetry extproc | `qsd_telemetry.py` |
| Control loop (stack_v2) | `qsd_daemon.py` |
| Env / hook wiring | `bringup.env.example` → `bringup.env` |
| NBI CLI profile (optional) | `nbictl.profile.example` |

## One-time enrollment

```bash
# 1. Create the keypair Spacetime will trust
scripts/generate_spacetime_keys.sh

# 2. Share ONLY qsd_spacetime/keys/agent_pub_key.cer with Aalyria.
#    They return AGENT_EMAIL + PRIVATE_KEY_ID (+ staging domain).

# 3. Wire credentials (never commit bringup.env)
cp qsd_spacetime/bringup.env.example qsd_spacetime/bringup.env
# edit STAGING_* and STAGING_PRIVATE_KEY_PEM

# 4. Validate config without contacting Spacetime
set -a; source qsd_spacetime/bringup.env; set +a
scripts/spacetime_staging_dryrun.sh
```

## Runtime (after Aalyria enables the agent)

```bash
set -a; source qsd_spacetime/bringup.env; set +a
python3 qsd_spacetime/qsd_daemon.py --dt 0.001
# In another process: bazel-run //agent/cmd/agent -- --config <filled staging textproto>
```

Filled configs must replace `${STAGING_*}` / `${DOMAIN}` placeholders. The
staging dry-run script does that substitution for local checks.
