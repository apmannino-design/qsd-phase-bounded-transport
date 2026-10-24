#!/usr/bin/env python3
"""
Spacetime agent extproc ENACTMENT backend.

The agent pipes one CreateEntryRequest (protojson) to stdin when a scheduled
change is due. This script records beam targets for the QSD gate daemon:
  update_beam -> store/refresh the beam (new beam => gate resets for acquisition)
  delete_beam -> remove it
Other change types are accepted and ignored (exit 0). In a real deployment,
chain to your existing terminal enactment here (see TODO).
Exit codes follow gRPC status codes, per the agent's extproc contract.
"""
import sys, json
from common import BEAMS, load, save, g

INVALID_ARGUMENT = 3

def main():
    try:
        req = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"bad CreateEntryRequest JSON: {e}", file=sys.stderr)
        return INVALID_ARGUMENT
    beams = load(BEAMS, {})
    ub = g(req, "updateBeam", "update_beam")
    db = g(req, "deleteBeam", "delete_beam")
    if ub:
        b = g(ub, "beam", default={})
        bid = g(b, "id")
        if not bid:
            print("update_beam without beam.id", file=sys.stderr)
            return INVALID_ARGUMENT
        target = g(b, "target", default={})
        azel = g(target, "azEl", "az_el")
        prev = beams.get(bid, {})
        entry = dict(prev)
        entry.update(
            id=bid,
            antenna_id=g(b, "antennaId", "antenna_id", default=prev.get("antenna_id", bid)),
            entry_id=g(req, "id"),
            time=g(req, "time"),
        )
        if azel is not None:
            entry["cmd_az"] = float(g(azel, "azDeg", "az_deg", default=0.0))
            entry["cmd_el"] = float(g(azel, "elDeg", "el_deg", default=0.0))
        elif target:
            entry["target_kind"] = next(iter(target))   # state_vector / chebyshev / etc.
        # A new beam or a changed target is a fresh acquisition for the gate.
        entry["generation"] = prev.get("generation", 0) + (
            0 if prev and prev.get("cmd_az") == entry.get("cmd_az")
            and prev.get("cmd_el") == entry.get("cmd_el") else 1)
        beams[bid] = entry
        # TODO: forward the beam command to the terminal's own pointing controller here.
    elif db:
        beams.pop(g(db, "id"), None)
    save(BEAMS, beams)
    return 0

if __name__ == "__main__":
    sys.exit(main())
