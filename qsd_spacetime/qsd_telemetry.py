#!/usr/bin/env python3
"""
Spacetime agent extproc TELEMETRY driver.

Called once per collection_period; prints one ExportMetricsRequest (protojson)
to stdout. The v1alpha telemetry API has no pointing or custom fields, so gate
state is mapped onto what Spacetime already understands:
  - InterfaceMetrics.operational_state: UP inside the corridor,
    DORMANT while a re-lock is in flight, DOWN if outside and not re-locking
  - ModemMetrics.sinr_data_points: SINR implied by the estimated residual
    (swap in the modem's measured SINR when available)
The raw dE / p_exit values stay local in status.json.
"""
import sys, json
from common import STATUS, load

def oper_state(s):
    if s.get("relocking"):
        return "IF_OPER_STATUS_DORMANT"
    return "IF_OPER_STATUS_UP" if s.get("in_corridor") else "IF_OPER_STATUS_DOWN"

def main():
    status = load(STATUS, {})
    req = {"interfaceMetrics": [], "modemMetrics": []}
    for bid, s in sorted(status.items()):
        iface = s.get("antenna_id", bid)
        req["interfaceMetrics"].append({
            "interfaceId": iface,
            "operationalStateDataPoints": [{"time": s["time"], "value": oper_state(s)}],
        })
        req["modemMetrics"].append({
            "demodulatorId": f"{iface}-demod",
            "sinrDataPoints": [{"time": s["time"], "modulatorId": f"{bid}-remote",
                                "sinrDb": round(s["sinr_db"], 3)}],
        })
    if not req["interfaceMetrics"]:
        print("no active beams", file=sys.stderr)
        return 14  # UNAVAILABLE: agent logs it and retries next period
    json.dump(req, sys.stdout)
    return 0

if __name__ == "__main__":
    sys.exit(main())
