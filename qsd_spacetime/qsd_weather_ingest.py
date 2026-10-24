#!/usr/bin/env python3
"""
External weather → station switch advice (not link-telemetry KF).

Reroute sims showed margin trends add ≤2% vs a reactive buffer. Real early
warning must come from outside the link (radar / cloud imagery / all-sky).

Input JSON (file or stdin), one of:
  {
    "stations": [
      {"id": "gs-a", "cloud_od": 0.2, "rain_rate_mm_h": 0, "score": null},
      {"id": "gs-b", "cloud_od": 2.5, "rain_rate_mm_h": 12}
    ],
    "active_station": "gs-a",
    "horizon_s": 300
  }

Writes state/weather_advice.json for operators / NBI tooling:
  recommended_station, switch_now, reason, scores[], source=external_weather

Does NOT invent Spacetime RPCs — emit an intent fragment under
`nbi_hint` for a human or northbound client to submit.
"""
from __future__ import annotations

import argparse
import json
import sys

from common import WEATHER_ADVICE, now_rfc3339, save


def score_station(s):
    if s.get("score") is not None:
        return float(s["score"])
    # Higher is better. Optical depth and rain both hurt.
    od = float(s.get("cloud_od", 0.0))
    rain = float(s.get("rain_rate_mm_h", 0.0))
    return 10.0 - 3.0 * od - 0.15 * rain


def advise(payload, switch_margin=1.5):
    stations = payload.get("stations") or []
    if not stations:
        raise ValueError("stations required")
    scored = []
    for s in stations:
        sid = s.get("id")
        if not sid:
            raise ValueError("station.id required")
        scored.append({
            "id": sid,
            "score": score_station(s),
            "cloud_od": s.get("cloud_od"),
            "rain_rate_mm_h": s.get("rain_rate_mm_h"),
        })
    scored.sort(key=lambda x: -x["score"])
    best = scored[0]
    active = payload.get("active_station")
    active_score = next((x["score"] for x in scored if x["id"] == active), None)
    switch_now = False
    reason = "hold"
    if active is None:
        switch_now = True
        reason = "no_active_station"
    elif best["id"] != active and (
        active_score is None or best["score"] >= active_score + switch_margin
    ):
        switch_now = True
        reason = "external_weather_better_by_margin"
    advice = {
        "time": now_rfc3339(),
        "source": "external_weather",
        "active_station": active,
        "recommended_station": best["id"],
        "switch_now": switch_now,
        "reason": reason,
        "switch_margin": switch_margin,
        "horizon_s": payload.get("horizon_s"),
        "scores": scored,
        # Hint only — submit via NBI / operator tooling, not SBI telemetry.
        "nbi_hint": {
            "action": "prefer_ground_station",
            "station_id": best["id"],
            "because": reason,
        },
    }
    return advice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="-", help="weather JSON path or -")
    ap.add_argument("--out", default=WEATHER_ADVICE)
    ap.add_argument("--switch-margin", type=float, default=1.5)
    a = ap.parse_args()
    raw = sys.stdin.read() if a.inp == "-" else open(a.inp).read()
    payload = json.loads(raw)
    advice = advise(payload, switch_margin=a.switch_margin)
    save(a.out, advice)
    json.dump(advice, sys.stdout, indent=2)
    print(file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
