"""Shared state + helpers for the QSD gate <-> Spacetime agent bridge."""
import json, os, tempfile, datetime
import numpy as np

STATE_DIR = os.environ.get("QSD_STATE_DIR", os.path.join(os.path.dirname(__file__), "state"))
BEAMS = os.path.join(STATE_DIR, "beams.json")    # written by qsd_enact.py
STATUS = os.path.join(STATE_DIR, "status.json")  # written by qsd_daemon.py

def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save(path, obj):
    """Atomic write so the agent never reads a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)

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
    """Gaussian-beam pointing loss: 3 dB down at r = half_power_deg (the corridor edge)."""
    return sinr_clear_db - 3.0*(r_deg/half_power_deg)**2
