#!/usr/bin/env python3
"""
Spacetime agent extproc ENACTMENT backend.

The agent pipes one CreateEntryRequest (protojson) to stdin when a scheduled
change is due. This script records beam targets for the QSD daemon and
forwards az/el retargets to the terminal pointing controller:
  update_beam -> store/refresh the beam (new beam => supervisor resets)
               -> append enact_forward.jsonl + optional QSD_HW_POINT_CMD
  delete_beam -> remove it
Other change types (routes, BP entries, ...) are NOT handled here: they return
UNIMPLEMENTED (12) so Spacetime never records them as enacted. Configure this
backend only on agents whose node is a QSD-managed optical terminal, or set
QSD_ENACT_CHAIN to a command that enacts everything else (it receives the same
JSON on stdin and its exit code is returned).
A pointing command the terminal rejects returns UNAVAILABLE (14): the previous
target is kept so a retry re-sends it; Spacetime is told the change did not
take effect.

Exit codes follow gRPC status codes, per the agent's extproc contract.
"""
import os, subprocess, sys, json, time
from common import BEAMS, ENACT_FORWARD, append_jsonl, load, save, g
from qsd_terminal import HardwareTerminal

INVALID_ARGUMENT = 3
UNIMPLEMENTED = 12
UNAVAILABLE = 14

# CreateEntryRequest metadata — not configuration_change oneof members.
_META = {
    "scheduleManipulationToken", "schedule_manipulation_token",
    "seqno", "id", "time", "@type",
}


def forward_point(beam_id, az, el):
    """Notify the terminal of a new Spacetime az/el command. Returns False on hook failure."""
    rec = {
        "t": time.time(),
        "cmd": "POINT",
        "beam_id": beam_id,
        "az_deg": az,
        "el_deg": el,
        "source": "spacetime_update_beam",
    }
    append_jsonl(ENACT_FORWARD, rec)
    # A failure is reported to the caller: telling Spacetime "enacted" when the
    # terminal rejected the pointing command would make the network plan around
    # a beam that isn't there.
    try:
        HardwareTerminal().point(beam_id, az, el)
        return True
    except Exception as exc:
        print(f"point forward FAILED: {exc}", file=sys.stderr)
        return False


def chain(raw):
    """Hand an unhandled change type to the node's real enactment backend."""
    cmd = os.environ.get("QSD_ENACT_CHAIN")
    if not cmd:
        print("change type not handled by QSD enactment (no QSD_ENACT_CHAIN)",
              file=sys.stderr)
        return UNIMPLEMENTED
    return subprocess.run(cmd, shell=True, input=raw, text=True).returncode


def main():
    raw = sys.stdin.read()
    try:
        req = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"bad CreateEntryRequest JSON: {e}", file=sys.stderr)
        return INVALID_ARGUMENT
    if not isinstance(req, dict):
        print("CreateEntryRequest must be a JSON object", file=sys.stderr)
        return INVALID_ARGUMENT

    ub = g(req, "updateBeam", "update_beam")
    db = g(req, "deleteBeam", "delete_beam")
    if not ub and not db:
        other = [k for k in req if k not in _META]
        if other:
            return chain(raw)
        print("CreateEntryRequest missing configuration_change", file=sys.stderr)
        return INVALID_ARGUMENT

    beams = load(BEAMS, {})
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
        # Optional modem IDs from the schedule payload or prior state — never invented.
        for src, dst in (
            (("rxModemId", "rx_modem_id"), "rx_modem_id"),
            (("txModemId", "tx_modem_id"), "tx_modem_id"),
        ):
            val = g(b, *src, default=prev.get(dst))
            if val:
                entry[dst] = val
        if azel is not None:
            entry["cmd_az"] = float(g(azel, "azDeg", "az_deg", default=0.0))
            entry["cmd_el"] = float(g(azel, "elDeg", "el_deg", default=0.0))
        elif target:
            entry["target_kind"] = next(iter(target))
        entry["generation"] = prev.get("generation", 0) + (
            0 if prev and prev.get("cmd_az") == entry.get("cmd_az")
            and prev.get("cmd_el") == entry.get("cmd_el") else 1)

        need_point = azel is not None and (
            not prev
            or prev.get("cmd_az") != entry.get("cmd_az")
            or prev.get("cmd_el") != entry.get("cmd_el")
        )
        beams[bid] = entry
        if need_point:
            if not forward_point(bid, entry["cmd_az"], entry["cmd_el"]):
                # Keep the previous target so a retry forwards the command again.
                if prev:
                    beams[bid] = prev
                else:
                    beams.pop(bid, None)
                save(BEAMS, beams)
                return UNAVAILABLE
    elif db:
        beams.pop(g(db, "id"), None)

    save(BEAMS, beams)
    return 0

if __name__ == "__main__":
    sys.exit(main())
