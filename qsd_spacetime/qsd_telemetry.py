#!/usr/bin/env python3
"""
Spacetime agent extproc TELEMETRY driver.

Called once per collection_period; prints one ExportMetricsRequest (protojson)
to stdout. Honesty rules:
  - Only measured SINR / EsN0 from the terminal enter ModemMetrics.
  - Synthetic / model SINR stays in local_metrics.json, never here.
  - ΔE / θ / headroom / p_exit stay in local_metrics.json.
  - Modem IDs are never invented; without configured IDs, omit modem metrics.
  - Default: keep supervisor DORMANT during STARTUP/recovery (strict).
    Staging override QSD_TELEMETRY_STARTUP_UP=1 requires measured modem data.

Supports status.json schema_version=1 (stack_v2) and the legacy flat map.
"""
import os, sys, json, time as _time
from common import STATUS, LOCAL_METRICS, load
import qsd_stack_v2 as stack


def oper_state_legacy(s):
    if s.get("relocking"):
        return "IF_OPER_STATUS_DORMANT"
    return "IF_OPER_STATUS_UP" if s.get("in_corridor") else "IF_OPER_STATUS_DOWN"


def from_legacy(status):
    req = {"interfaceMetrics": [], "modemMetrics": []}
    for bid, s in sorted(status.items()):
        if not isinstance(s, dict) or "time" not in s:
            continue
        iface = s.get("antenna_id", bid)
        req["interfaceMetrics"].append({
            "interfaceId": iface,
            "operationalStateDataPoints": [{"time": s["time"], "value": oper_state_legacy(s)}],
        })
        if (
            s.get("sinr_source") == "measured"
            and s.get("sinr_db") is not None
            and s.get("rx_modem_id")
            and s.get("tx_modem_id")
        ):
            req["modemMetrics"].append({
                "demodulatorId": s["rx_modem_id"],
                "sinrDataPoints": [{
                    "time": s["time"],
                    "modulatorId": s["tx_modem_id"],
                    "sinrDb": round(float(s["sinr_db"]), 3),
                }],
            })
    return req


def _camelize_export(req):
    """stack_v2 emits snake_case; Go agent protojson expects camelCase JSON."""
    out = {"interfaceMetrics": [], "modemMetrics": []}
    for im in req.get("interface_metrics", req.get("interfaceMetrics", [])):
        pts = im.get("operational_state_data_points",
                     im.get("operationalStateDataPoints", []))
        out["interfaceMetrics"].append({
            "interfaceId": im.get("interface_id", im.get("interfaceId")),
            "operationalStateDataPoints": [
                {"time": p.get("time"), "value": p.get("value")} for p in pts
            ],
        })
    for mm in req.get("modem_metrics", req.get("modemMetrics", [])):
        if "sinr_data_points" in mm or "sinrDataPoints" in mm:
            pts = mm.get("sinr_data_points", mm.get("sinrDataPoints", []))
            entry = {
                "demodulatorId": mm.get("demodulator_id", mm.get("demodulatorId")),
                "sinrDataPoints": [{
                    "time": p.get("time"),
                    "modulatorId": p.get("modulator_id", p.get("modulatorId")),
                    "sinrDb": p.get("sinr_db", p.get("sinrDb")),
                } for p in pts],
            }
            es = mm.get("esn0_data_points", mm.get("esn0DataPoints"))
            if es:
                entry["esn0DataPoints"] = [{
                    "time": p.get("time"),
                    "modulatorId": p.get("modulator_id", p.get("modulatorId")),
                    "esn0Db": p.get("esn0_db", p.get("esn0Db")),
                } for p in es]
            out["modemMetrics"].append(entry)
        else:
            pts = mm.get("link_metrics_data_points",
                         mm.get("linkMetricsDataPoints", []))
            out["modemMetrics"].append({
                "modemId": mm.get("modem_id", mm.get("modemId")),
                "linkMetricsDataPoints": pts,
            })
    return out


def main():
    status = load(STATUS, {})
    if isinstance(status, dict) and status.get("schema_version") == 1:
        schema = status.get("telemetry_schema") or "repo_v1alpha"
        beams = status.get("beams") or {}
        # Do NOT invent modem IDs. build_export_request skips modem metrics
        # when rx/tx are missing — that is intentional.
        try:
            max_age = float(status.get("max_export_age_s", 5.0))
            req = stack.build_export_request(
                status, max_age_s=max_age, schema=schema,
            )
            req = _camelize_export(req)
            # Default: strict. A link in STARTUP / recovery (regime 0 or 5) is
            # reported DORMANT, because the supervisor has not validated it.
            # Staging-only override: QSD_TELEMETRY_STARTUP_UP=1 reports UP during
            # warm-up when the sample is valid AND measured modem data exists.
            if os.environ.get("QSD_TELEMETRY_STARTUP_UP", "0") in ("1", "true", "True"):
                now = _time.time()
                pub = status.get("published_unix_s")
                pub_fresh = isinstance(pub, (int, float)) and 0 <= now - pub <= max_age
                for im in req["interfaceMetrics"]:
                    iface = im["interfaceId"]
                    st = next((s for s in beams.values()
                               if s.get("interface_id") == iface), None)
                    if not st or not pub_fresh or not st.get("sample_valid"):
                        continue
                    if st.get("sinr_db") is None and st.get("esn0_db") is None:
                        continue                      # no measured modem data: stay DORMANT
                    if st.get("regime") in (0, 5):
                        for p in im["operationalStateDataPoints"]:
                            if p.get("value") == "IF_OPER_STATUS_DORMANT":
                                p["value"] = "IF_OPER_STATUS_UP"
        except ValueError as exc:
            print(f"export build failed: {exc}", file=sys.stderr)
            return 14
    elif isinstance(status, dict):
        req = from_legacy(status)
    else:
        req = from_legacy({})

    if not req.get("interfaceMetrics"):
        local = load(LOCAL_METRICS, {})
        print(
            f"no active beams for Spacetime export "
            f"(local_metrics beams={list((local.get('beams') or {}).keys())})",
            file=sys.stderr,
        )
        return 14  # UNAVAILABLE
    json.dump(req, sys.stdout)
    return 0

if __name__ == "__main__":
    sys.exit(main())
