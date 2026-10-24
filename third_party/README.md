# Vendored Spacetime dependencies

| Path | Source | Role |
|---|---|---|
| `aalyria-api/` | [github.com/aalyria/api](https://github.com/aalyria/api) (Apache-2.0) | Full Spacetime API protos + Go SBI `agent` |
| `nmts/` | [outernetcouncil/nmts](https://github.com/outernetcouncil/nmts) v1.21.0 | Coordinate / geodesy protos imported by Scheduling |
| `googleapis/` | sparse [googleapis/googleapis](https://github.com/googleapis/googleapis) | `google/rpc`, `google/type` for protoc includes |
| `proto_include/nmts` | symlink → `../nmts` | Makes `import "nmts/v1/..."` resolve for `protoc` |
| `AALYRIA_API_PIN.txt` | pin file | Commit SHA / URLs used for this vendor snapshot |

Refresh:

```bash
scripts/fetch_aalyria_spacetime.sh
scripts/regen_qsd_spacetime_protos.sh
scripts/verify_qsd_spacetime.sh
```

Build the reference Go agent (needs [bazelisk](https://github.com/bazelbuild/bazelisk)):

```bash
cd third_party/aalyria-api
bazelisk build //agent/cmd/agent
./bazel-bin/agent/cmd/agent/agent_/agent --config ../../qsd_spacetime/agent_config.textproto --dry-run
```
