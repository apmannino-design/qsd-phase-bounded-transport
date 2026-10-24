#!/usr/bin/env python3
"""
Turn weather_advice.json into a Spacetime NBI ServiceRequest fragment.

Does not call the live NBI (needs credentials). Writes a JSON document an
operator or nbictl/client can submit, preferring the recommended ground station
as dst_node_id when switch_now is true.

  python3 qsd_weather_ingest.py --in weather.json
  python3 qsd_weather_to_nbi.py --advice state/weather_advice.json \\
      --src-node gateway-1 --out state/nbi_service_request.json
"""
from __future__ import annotations

import argparse
import json
import sys

from common import WEATHER_ADVICE, load, now_rfc3339, save


def build_service_request(advice, src_node, bandwidth_bps=1e6, priority=10.0):
    if not advice.get("switch_now"):
        return {
            "submit": False,
            "reason": advice.get("reason", "hold"),
            "time": now_rfc3339(),
            "note": "No NBI submit — weather advice says hold.",
            "advice": advice,
        }
    station = advice["recommended_station"]
    # protojson-ish ServiceRequest (api/nbi/v1alpha/resources/service_request.proto)
    req = {
        "type": "qsd_weather_prefer_ground_station",
        "srcNodeId": src_node,
        "dstNodeId": station,
        "priority": priority,
        "requirements": [{
            "bandwidthBpsRequested": bandwidth_bps,
            "bandwidthBpsMinimum": bandwidth_bps * 0.1,
        }],
        "allowPartnerResources": False,
    }
    return {
        "submit": True,
        "time": now_rfc3339(),
        "reason": advice.get("reason"),
        "source": "external_weather",
        "nbi_hint": advice.get("nbi_hint"),
        "service_request": req,
        "operator_steps": [
            "Review dstNodeId matches a provisioned ground-station node id in your scenario.",
            "Submit via NBI Model/Provisioning API or nbictl (requires Aalyria credentials).",
            "Do not push this through SBI telemetry — northbound only.",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--advice", default=WEATHER_ADVICE)
    ap.add_argument("--src-node", required=True, help="source node id in Spacetime model")
    ap.add_argument("--bandwidth-bps", type=float, default=1e6)
    ap.add_argument("--priority", type=float, default=10.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    advice = load(a.advice, None)
    if not isinstance(advice, dict):
        print(f"missing advice at {a.advice}", file=sys.stderr)
        return 2
    doc = build_service_request(
        advice, a.src_node, bandwidth_bps=a.bandwidth_bps, priority=a.priority
    )
    out = a.out or ("state/nbi_service_request.json")
    save(out, doc)
    json.dump(doc, sys.stdout, indent=2)
    print(file=sys.stdout)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
