"""Shared state + helpers for the QSD gate <-> Spacetime agent bridge."""
import json, os, tempfile, datetime
import numpy as np

STATE_DIR = os.environ.get("QSD_STATE_DIR", os.path.join(os.path.dirname(__file__), "state"))
BEAMS = os.path.join(STATE_DIR, "beams.json")          # written by qsd_enact.py
STATUS = os.path.join(STATE_DIR, "status.json")        # written by qsd_daemon.py (Spacetime-facing)
LOCAL_METRICS = os.path.join(STATE_DIR, "local_metrics.json")  # side-channel; never sent to Spacetime
WEATHER_ADVICE = os.path.join(STATE_DIR, "weather_advice.json")
ENACT_FORWARD = os.path.join(STATE_DIR, "enact_forward.jsonl")  # beam cmds for terminal controller
CALIBRATION = os.path.join(STATE_DIR, "calibration.json")       # fitted Config overrides

def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save(path, obj):
    """Atomic write so the agent never reads a half-written file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1, allow_nan=False)
    os.replace(tmp, path)

def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, allow_nan=False) + "\n")

def now_rfc3339():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def g(d, *keys, default=None):
    """Get a protojson field accepting lowerCamelCase (Go protojson) or snake_case."""
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default

def residual_from_azel(cmd_az, cmd_el, meas_az, meas_el):
    """Angular separation (deg) between commanded and measured pointing."""
    a1, e1, a2, e2 = map(np.radians, (cmd_az, cmd_el, meas_az, meas_el))
    c = np.sin(e1)*np.sin(e2) + np.cos(e1)*np.cos(e2)*np.cos(a1 - a2)
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))

def sinr_from_residual(r_deg, sinr_clear_db=20.0, half_power_deg=3.0):
    """Gaussian-beam pointing loss model (synthetic). Do not export to Spacetime."""
    return sinr_clear_db - 3.0*(r_deg/half_power_deg)**2
