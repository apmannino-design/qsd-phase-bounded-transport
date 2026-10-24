#!/usr/bin/env python3
"""
Spacetime agent extproc TELEMETRY driver.

Called once per collection_period; prints one ExportMetricsRequest (protojson)
to stdout. Honesty rules:
  - Only measured SINR / EsN0 from the terminal enter ModemMetrics.
  - Synthetic / model SINR stays in local_metrics.json, never here.
  - ΔE / θ / headroom / p_exit stay in local_metrics.json.

Supports status.json schema_version=1 (stack_v2) and the legacy flat map.
"""
import sys, json
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
        # Only export if explicitly measured (never synthetic).
        if s.get("sinr_source") == "measured" and s.get("sinr_db") is not None:
            req["modemMetrics"].append({
                "demodulatorId": f"{iface}-demod",
                "sinrDataPoints": [{
                    "time": s["time"],
                    "modulatorId": f"{bid}-remote",
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
            # legacy_docs schema
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
        # Ensure modem IDs exist so measured SINR can export.
        beams = status.get("beams") or {}
        for bid, st in beams.items():
            st.setdefault("rx_modem_id", f"{st.get('interface_id', bid)}-demod")
            st.setdefault("tx_modem_id", f"{bid}-remote")
        try:
            req = stack.build_export_request(
                status,
                max_age_s=float(status.get("max_export_age_s", 5.0)),
                schema=schema,
            )
            req = _camelize_export(req)
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
