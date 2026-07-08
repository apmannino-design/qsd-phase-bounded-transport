#!/usr/bin/env python3
"""
QSD Stabilization Campaign for IBM Quantum
==========================================
v1.0 — July 2026 — Aurora Unified Energy Systems

Implements the full stabilization pathway validated in the June 2026
ibm_fez campaign, as a reproducible, pre-registered harness.

Circuit builders default to aurora_qsd.quantum.fez_cells (TriLock 3Q ZZZ
cells + sunscreen re-prep). Pass --legacy-circuits for the June reference
source-bridge-source builder.

USAGE:
  python3 examples/qsd_stabilization_campaign.py prereg
  python3 examples/qsd_stabilization_campaign.py discover --backend ibm_fez
  python3 examples/qsd_stabilization_campaign.py sweep    --backend ibm_fez --budget mini
  python3 examples/qsd_stabilization_campaign.py fullchip --backend ibm_fez --budget mini --nowait
  python3 examples/qsd_stabilization_campaign.py collect --budget mini
  python3 examples/qsd_stabilization_campaign.py report-cells
  python3 examples/qsd_stabilization_campaign.py analyze

Full-budget D3/D4 (reuses mini sweep + fullchip + control):
  python3 examples/qsd_stabilization_campaign.py full-depth --backend ibm_fez --nowait
  python3 examples/qsd_stabilization_campaign.py collect --budget full
  python3 examples/qsd_stabilization_campaign.py analyze --budget full

ZERO-COST PLUMBING TEST:
  python3 examples/qsd_stabilization_campaign.py all --backend aer --budget mini
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

# Allow running without `pip install -e .` when executed from repo clone
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from aurora_qsd.quantum.fez_cells import (
        _append_3q_qsd_layer,
        append_sunscreen_reset,
        extract_zzz_triplets,
        zzz_correlator,
    )
except ModuleNotFoundError:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class ZZZCell:
        qubits: tuple[int, int, int]
        cell_id: int

    def extract_zzz_triplets(coupling_map, max_cells=128):
        edges = set()
        for a, b in coupling_map:
            edges.add((min(a, b), max(a, b)))
        adj: dict[int, set[int]] = {}
        for a, b in edges:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        cells, used = [], set()
        for a, b in sorted(edges):
            for c in sorted(adj.get(b, ())):
                if c == a:
                    continue
                if (a, b) in edges and (b, c) in edges:
                    line = (a, b, c)
                else:
                    continue
                if set(line) & used:
                    continue
                cells.append(ZZZCell(qubits=line, cell_id=len(cells)))
                used.update(line)
                if len(cells) >= max_cells:
                    return cells
        return cells

    def zzz_correlator(counts, n_qubits=3):
        total = sum(counts.values())
        if total == 0:
            return 0.0
        acc = 0.0
        for bitstring, count in counts.items():
            acc += (1.0 if bitstring.count("1") % 2 == 0 else -1.0) * count
        return float(acc / total)

    def _trilock_init(qc, qubits, theta):
        for i, q in enumerate(qubits):
            qc.ry(2.0 * theta if i % 2 == 0 else 2.0 * (np.pi / 2.0 - theta), q)

    def _append_2q_qsd_layer(qc, q0, q1, theta, with_init=True):
        if with_init:
            qc.ry(2.0 * theta, q0)
            qc.ry(2.0 * (np.pi / 2.0 - theta), q1)
        qc.cx(q0, q1)
        qc.rz(theta, q0)
        qc.rz(np.pi / 2.0 - theta, q1)
        qc.cx(q1, q0)

    def _append_3q_qsd_layer(qc, qubits, theta, with_init=True):
        q0, q1, q2 = qubits
        if with_init:
            _trilock_init(qc, qubits, theta)
        _append_2q_qsd_layer(qc, q0, q1, theta, with_init=False)
        qc.cx(q1, q2)
        qc.rz(theta if q2 % 2 == 0 else np.pi / 2.0 - theta, q2)
        qc.cx(q1, q2)

    def append_sunscreen_reset(qc, qubits, theta):
        _append_3q_qsd_layer(qc, (qubits[0], qubits[1], qubits[2]), theta, with_init=True)

    print("Note: aurora_qsd not installed — using bundled circuit fallbacks.", file=sys.stderr)

# ---------------------------------------------------------------- constants
THETA_STAR_DEG = 22.5          # THEORY: arctan(sqrt(2)-1) = pi/8 EXACT
BRIDGE_DEG = 67.5              # 3*theta* (basin edge reference)
TRIM_DEG = 11.25               # theta*/2 reference default
RESULTS = "results"
STATE = os.path.join(RESULTS, "state.json")
PREREG = os.path.join(RESULTS, "prereg.json")

BUDGETS = {
    "mini": dict(
        deltas=list(range(-40, 41, 10)),
        sweep_shots=1024,
        sweep_cells=4,
        chip_shots=2048,
        depth_layers=[1, 8, 16],
        sun=[(5, 5), (10, 5)],
    ),
    "full": dict(
        deltas=list(range(-40, 41, 4)),
        sweep_shots=2000,
        sweep_cells=5,
        chip_shots=5000,
        depth_layers=[1, 16, 32, 64],
        sun=[(5, 7), (20, 7), (40, 7)],  # 35/140/280 layers — targets D3 depth>=250
    ),
}


def _phase_key(phase: str, budget: str) -> str:
    """State/job key — full-budget depth/sunscreen kept separate from mini."""
    if budget == "full" and phase in ("depth", "sunscreen"):
        return f"{phase}_full"
    return phase


# ---------------------------------------------------------------- state I/O
def _load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _save(path, obj):
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def state():
    return _load(STATE, {})


def save_state(st):
    _save(STATE, st)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- Phase 0
def cmd_prereg(args):
    if os.path.exists(PREREG):
        print("prereg.json already exists — refusing to overwrite (that's the point).")
        return
    rules = {
        "written": now(),
        "theory_constant_deg": THETA_STAR_DEG,
        "note": (
            "Two-quantity rule: the sweep optimum is a PLATFORM-CALIBRATED "
            "setting. It does not confirm or move the theory constant "
            "theta* = pi/8 = 22.5 deg exactly."
        ),
        "expected_sign": +1,
        "rules": {
            "D1_angle_specificity": {
                "stmt": "median ZZZ(fullchip) - median ZZZ(random control) >= 0.20",
                "threshold": 0.20,
            },
            "D2_basin_structure": {
                "stmt": (
                    "sweep max-min contrast >= 0.50 AND peak Delta strictly "
                    "interior to the sweep range (not an edge point)"
                ),
                "threshold": 0.50,
            },
            "D3_stabilization": {
                "stmt": (
                    "sunscreen median ZZZ at depth>=250 >= 2.0 x no-reset "
                    "median at the nearest comparable depth"
                ),
                "threshold": 2.0,
            },
            "D4_persistence": {
                "stmt": (
                    "deepest sunscreen run median >= 0.50 x shallowest "
                    "sunscreen run median (asymptotic-floor check)"
                ),
                "threshold": 0.50,
            },
        },
        "verdicts": {
            "STABILIZED": "D1 and D2 and D3 and D4 all pass",
            "PARTIAL": "D1 and D2 pass; D3 or D4 fails",
            "NEGATIVE": "D1 or D2 fails",
        },
        "methodology": "no error mitigation, no post-selection, no fitting; signed ZZZ from raw counts",
    }
    rules["sha256"] = hashlib.sha256(
        json.dumps(rules["rules"], sort_keys=True).encode()
    ).hexdigest()
    _save(PREREG, rules)
    print(f"Pre-registration LOCKED -> {PREREG}")
    for k, v in rules["rules"].items():
        print(f"  {k}: {v['stmt']}")


def prereg_check():
    p = _load(PREREG, None)
    if p is None:
        sys.exit("REFUSING: run `prereg` first — decision rules must be locked before data.")
    h = hashlib.sha256(json.dumps(p["rules"], sort_keys=True).encode()).hexdigest()
    if h != p.get("sha256"):
        sys.exit("REFUSING: prereg.json was edited after locking (hash mismatch).")
    return p


# ---------------------------------------------------------------- backends
def get_backend(name):
    if name == "aer":
        from qiskit_aer import AerSimulator

        try:
            from qiskit_ibm_runtime import QiskitRuntimeService

            svc = QiskitRuntimeService()
            bk = AerSimulator.from_backend(svc.backend("ibm_fez"))
            print("Aer: noisy model of ibm_fez")
        except Exception:
            bk = AerSimulator()
            print("Aer: ideal simulator (no IBM credentials — plumbing test only)")
        return bk, "aer"
    from qiskit_ibm_runtime import QiskitRuntimeService

    svc = QiskitRuntimeService()
    return svc.backend(name), "hw"


def get_sampler(backend, mode):
    if mode == "aer":
        from qiskit_aer.primitives import SamplerV2

        return SamplerV2(), None
    from qiskit_ibm_runtime import Batch, SamplerV2

    batch = Batch(backend=backend)
    return SamplerV2(mode=batch), batch


def transpile_for(backend, mode, circuits):
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    if mode == "aer" and getattr(backend, "coupling_map", None) is None:
        return circuits
    pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
    return pm.run(circuits)


def counts_from_result(result):
    return [pub.data.c.get_counts() for pub in result]


# ---------------------------------------------------------------- Phase 1
def cmd_discover(args):
    backend, mode = get_backend(args.backend)
    st = state()

    if mode == "aer" and getattr(backend, "coupling_map", None) is None:
        cells = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(4)]
        st.update(
            backend=args.backend,
            mode=mode,
            cells=[list(c) for c in cells],
            champions=[list(c) for c in cells[: BUDGETS[args.budget]["sweep_cells"]]],
            discovered=now(),
            n_qubits=max(c for t in cells for c in t) + 1,
        )
        save_state(st)
        print(f"[aer-ideal] synthetic cells: {cells}")
        return

    cm = backend.coupling_map.get_edges() if hasattr(backend.coupling_map, "get_edges") else backend.coupling_map
    coupling = list(cm)
    zzz_cells = extract_zzz_triplets(coupling, max_cells=128)
    cells = [c.qubits for c in zzz_cells]

    # rank champions by calibration error
    tgt = backend.target
    twoq = next((g for g in ("cz", "ecr", "cx") if g in tgt.operation_names), "cx")

    def e2(a, b):
        try:
            p = tgt[twoq].get((a, b)) or tgt[twoq].get((b, a))
            return p.error if p and p.error is not None else 0.02
        except Exception:
            return 0.02

    def eread(q):
        try:
            p = tgt["measure"][(q,)]
            return p.error if p and p.error is not None else 0.02
        except Exception:
            return 0.02

    scored = []
    for a, b, c in cells:
        score = e2(a, b) + e2(b, c) + eread(a) + eread(b) + eread(c)
        scored.append((score, (a, b, c)))
    scored.sort()
    champions = [list(t) for _, t in scored[: BUDGETS[args.budget]["sweep_cells"]]]

    st.update(
        backend=args.backend,
        mode=mode,
        twoq_gate=twoq,
        n_qubits=backend.num_qubits,
        cells=[list(c) for c in cells],
        champions=champions,
        discovered=now(),
        legacy_circuits=bool(getattr(args, "legacy_circuits", False)),
    )
    save_state(st)
    print(f"backend={args.backend}  qubits={backend.num_qubits}  2Q gate={twoq}")
    print(
        f"discovered {len(cells)} disjoint ZZZ cells covering {3 * len(cells)} qubits "
        f"({100 * 3 * len(cells) / backend.num_qubits:.1f}% of chip)"
    )
    print(f"champions (lowest calibration error): {champions}")


# ---------------------------------------------------------------- circuits
def lock_layer_legacy(qc, a, b, c, theta_lock_rad):
    qc.cx(a, b)
    qc.rz(2 * theta_lock_rad, b)
    qc.cx(a, b)
    qc.cx(b, c)
    qc.rz(2 * theta_lock_rad, c)
    qc.cx(b, c)


def build_cell_legacy(qc, a, b, c, src_deg, bridge_deg, trim_deg, layers, reset_every=0):
    s, br, tr = (math.radians(x) for x in (src_deg, bridge_deg, trim_deg))

    def prep():
        qc.ry(2 * s, a)
        qc.ry(2 * br, b)
        qc.ry(2 * s, c)
        qc.cx(a, b)
        qc.cx(b, c)
        qc.rz(2 * tr, b)

    prep()
    qc.x(b)
    for layer in range(layers):
        if reset_every and layer > 0 and layer % reset_every == 0:
            for q in (a, b, c):
                qc.reset(q)
            prep()
            qc.x(b)
        qc.barrier(a, b, c)
        lock_layer_legacy(qc, a, b, c, s)


def build_cell_repo(qc, a, b, c, src_deg, _bridge_deg, _trim_deg, layers, reset_every=0):
    """TriLock 3Q cell from aurora_qsd (ibm_fez-validated)."""
    theta = math.radians(src_deg)
    for layer in range(layers):
        if reset_every and layer > 0 and layer % reset_every == 0:
            append_sunscreen_reset(qc, (a, b, c), theta)
        else:
            _append_3q_qsd_layer(qc, (a, b, c), theta, with_init=(layer == 0))


def make_chip_circuit(
    n_qubits,
    cells,
    src_deg_per_cell,
    bridge_deg,
    trim_deg,
    layers,
    reset_every=0,
    legacy=False,
):
    qr = QuantumRegister(n_qubits, "q")
    cr = ClassicalRegister(3 * len(cells), "c")
    qc = QuantumCircuit(qr, cr)
    builder = build_cell_legacy if legacy else build_cell_repo
    for (a, b, c), sd in zip(cells, src_deg_per_cell):
        builder(qc, a, b, c, sd, bridge_deg, trim_deg, layers, reset_every)
    for i, (a, b, c) in enumerate(cells):
        qc.measure(a, 3 * i)
        qc.measure(b, 3 * i + 1)
        qc.measure(c, 3 * i + 2)
    return qc


# ---------------------------------------------------------------- readout
def zzz_per_cell_from_counts(counts, ncells, expected_sign=+1):
    """Per-cell ZZZ using fez_cells correlator on each 3-bit block."""
    z = np.zeros(ncells)
    total = sum(counts.values())
    for bits, n in counts.items():
        bits = bits.replace(" ", "").zfill(3 * ncells)
        for i in range(ncells):
            trio = bits[3 * i : 3 * i + 3]
            sub = {trio: n}
            z[i] += zzz_correlator(sub, 3) * n
    return expected_sign * z / max(total, 1)


def run_pubs(backend, mode, circuits, shots, tag, nowait=False):
    isa = transpile_for(backend, mode, circuits)
    sampler, batch = get_sampler(backend, mode)
    job = sampler.run(isa, shots=shots)
    jid = getattr(job, "job_id", lambda: f"aer-local-{int(time.time())}")()
    if callable(jid):
        jid = jid()
    st = state()
    st.setdefault("jobs", {})[tag] = {"id": jid, "t": now(), "n_pubs": len(circuits), "shots": shots}
    save_state(st)
    print(f"[{tag}] job {jid}  ({len(circuits)} pubs x {shots} shots)")
    if nowait and mode == "hw":
        print("  --nowait: submitted; retrieve later with `collect`.")
        if batch:
            batch.close()
        return None
    res = job.result()
    if batch:
        batch.close()
    return counts_from_result(res)


def fetch_job(tag):
    from qiskit_ibm_runtime import QiskitRuntimeService

    st = state()
    info = st.get("jobs", {}).get(tag)
    if not info:
        sys.exit(f"no job recorded for tag '{tag}'")
    svc = QiskitRuntimeService()
    job = svc.job(info["id"])
    return counts_from_result(job.result())


def _legacy_flag(args):
    st = state()
    return bool(getattr(args, "legacy_circuits", False) or st.get("legacy_circuits"))


def _ensure_sweep_calibrated(args, auto_collect: bool = True) -> float:
    """Return platform-calibrated source angle; optionally fetch pending sweep job."""
    st = state()
    cal = st.get("sweep", {}).get("calibrated_src_deg")
    if cal is not None:
        return float(cal)

    sweep_job = st.get("jobs", {}).get("sweep")
    if auto_collect and sweep_job:
        print(f"[sweep] no calibrated angle in state — fetching job {sweep_job['id']} ...")
        try:
            counts = fetch_job("sweep")
            _finish_sweep(counts, BUDGETS[args.budget]["deltas"], len(st["champions"]))
            return float(state()["sweep"]["calibrated_src_deg"])
        except Exception as exc:
            sys.exit(
                "sweep job not finished yet (or fetch failed). "
                f"Wait for job {sweep_job['id']} then run:\n"
                "  python3 examples/qsd_stabilization_campaign.py collect --budget mini\n"
                f"Detail: {exc}"
            )

    sys.exit(
        "run `sweep` first (needs calibrated angle).\n"
        "If you used --nowait, wait for the sweep job to finish, then:\n"
        "  python3 examples/qsd_stabilization_campaign.py collect --budget mini"
    )


# ---------------------------------------------------------------- Phase 2
def cmd_sweep(args):
    prereg_check()
    st = state()
    B = BUDGETS[args.budget]
    backend, mode = get_backend(st.get("backend", args.backend))
    cells = [tuple(c) for c in st["champions"]]
    nq = st.get("n_qubits", getattr(backend, "num_qubits", 3 * len(cells)) or 3 * len(cells))
    deltas = B["deltas"]
    legacy = _legacy_flag(args)
    circs = [
        make_chip_circuit(
            nq,
            cells,
            [THETA_STAR_DEG + d] * len(cells),
            BRIDGE_DEG,
            TRIM_DEG,
            layers=1,
            legacy=legacy,
        )
        for d in deltas
    ]
    counts = run_pubs(backend, mode, circs, B["sweep_shots"], "sweep", nowait=args.nowait)
    if counts is None:
        return
    _finish_sweep(counts, deltas, len(cells))


def _finish_sweep(counts, deltas, ncells):
    rows = []
    for d, ct in zip(deltas, counts):
        z = zzz_per_cell_from_counts(ct, ncells)
        rows.append(
            dict(
                delta=d,
                mean=float(z.mean()),
                median=float(np.median(z)),
                min=float(z.min()),
                max=float(z.max()),
            )
        )
        print(f"  Delta={d:+4d}  mean ZZZ={z.mean():+.3f}  median={np.median(z):+.3f}")

    best = max(rows, key=lambda r: abs(r["mean"]))
    sign = +1 if best["mean"] >= 0 else -1
    for r in rows:
        for k in ("mean", "median", "min", "max"):
            r[k] = sign * r[k]
        if r["min"] > r["max"]:
            r["min"], r["max"] = r["max"], r["min"]

    interior = deltas[0] < best["delta"] < deltas[-1]
    st = state()
    st["sweep"] = dict(
        rows=rows,
        best_delta=best["delta"],
        peak_mean=abs(best["mean"]),
        sign=sign,
        interior=bool(interior),
        calibrated_src_deg=THETA_STAR_DEG + best["delta"],
        t=now(),
    )
    save_state(st)
    print(
        f"\nPLATFORM-CALIBRATED optimum: Delta={best['delta']:+d} deg "
        f"(source angle {THETA_STAR_DEG + best['delta']:.2f} deg)"
    )
    print("  [two-quantity rule] theory constant stays theta* = pi/8 = 22.5 deg exactly;")
    print("  the calibrated setting is a device parameter of THIS backend/session.")


# ---------------------------------------------------------------- Phase 3/4
def _chip_run(args, tag, random_angles=False):
    prereg_check()
    st = state()
    B = BUDGETS[args.budget]
    backend, mode = get_backend(st.get("backend", args.backend))
    cells = [tuple(c) for c in st["cells"]]
    nq = st.get("n_qubits", getattr(backend, "num_qubits", 3 * len(cells)) or 3 * len(cells))
    legacy = _legacy_flag(args)
    if random_angles:
        rng = random.Random(42)
        srcs = [THETA_STAR_DEG + rng.uniform(-40, 80) for _ in cells]
    else:
        cal = _ensure_sweep_calibrated(args)
        srcs = [cal] * len(cells)
    qc = make_chip_circuit(nq, cells, srcs, BRIDGE_DEG, TRIM_DEG, layers=1, legacy=legacy)
    counts = run_pubs(backend, mode, [qc], B["chip_shots"], tag, nowait=args.nowait)
    if counts is None:
        return
    sign = st.get("sweep", {}).get("sign", 1)
    z = sign * zzz_per_cell_from_counts(counts[0], len(cells))
    rec = dict(
        median=float(np.median(z)),
        mean=float(z.mean()),
        ge50=int((z >= 0.50).sum()),
        ge70=int((z >= 0.70).sum()),
        ncells=len(cells),
        per_cell=[float(x) for x in z],
        t=now(),
    )
    st = state()
    st[tag] = rec
    save_state(st)
    print(
        f"[{tag}] median ZZZ={rec['median']:+.3f}  mean={rec['mean']:+.3f}  "
        f">=0.50: {rec['ge50']}/{len(cells)}  >=0.70: {rec['ge70']}/{len(cells)}"
    )


def cmd_fullchip(args):
    _chip_run(args, "fullchip", random_angles=False)


def cmd_control(args):
    _chip_run(args, "control", random_angles=True)


# ---------------------------------------------------------------- Phase 5/6
def cmd_depth(args):
    prereg_check()
    st = state()
    B = BUDGETS[args.budget]
    backend, mode = get_backend(st.get("backend", args.backend))
    cells = [tuple(c) for c in st["cells"]]
    nq = st.get("n_qubits", getattr(backend, "num_qubits", 3 * len(cells)) or 3 * len(cells))
    cal = _ensure_sweep_calibrated(args)
    layers = B["depth_layers"]
    legacy = _legacy_flag(args)
    circs = [
        make_chip_circuit(nq, cells, [cal] * len(cells), BRIDGE_DEG, TRIM_DEG, L, legacy=legacy)
        for L in layers
    ]
    counts = run_pubs(backend, mode, circs, B["chip_shots"], _phase_key("depth", args.budget), nowait=args.nowait)
    if counts is None:
        return
    rows = []
    sgn = st["sweep"].get("sign", 1)
    for L, ct, qc in zip(layers, counts, circs):
        z = sgn * zzz_per_cell_from_counts(ct, len(cells))
        rows.append(dict(layers=L, depth=qc.depth(), median=float(np.median(z)), mean=float(z.mean())))
        print(f"  {L:3d} layers (depth {qc.depth():4d}): median ZZZ={np.median(z):+.3f}")
    st = state()
    st[_phase_key("depth", args.budget)] = dict(rows=rows, t=now(), budget=args.budget)
    save_state(st)


def cmd_sunscreen(args):
    prereg_check()
    st = state()
    B = BUDGETS[args.budget]
    backend, mode = get_backend(st.get("backend", args.backend))
    cells = [tuple(c) for c in st["cells"]]
    nq = st.get("n_qubits", getattr(backend, "num_qubits", 3 * len(cells)) or 3 * len(cells))
    cal = _ensure_sweep_calibrated(args)
    cfgs = B["sun"]
    legacy = _legacy_flag(args)
    circs = [
        make_chip_circuit(
            nq, cells, [cal] * len(cells), BRIDGE_DEG, TRIM_DEG, layers=k * l, reset_every=l, legacy=legacy
        )
        for (k, l) in cfgs
    ]
    counts = run_pubs(backend, mode, circs, B["chip_shots"], _phase_key("sunscreen", args.budget), nowait=args.nowait)
    if counts is None:
        return
    rows = []
    sgn = st["sweep"].get("sign", 1)
    for (k, l), ct, qc in zip(cfgs, counts, circs):
        z = sgn * zzz_per_cell_from_counts(ct, len(cells))
        rows.append(
            dict(
                cycles=k,
                per_cycle=l,
                total_layers=k * l,
                depth=qc.depth(),
                gates=sum(qc.count_ops().values()),
                median=float(np.median(z)),
                ge50=int((z >= 0.50).sum()),
                ncells=len(cells),
            )
        )
        print(
            f"  {k}x{l} reset (depth {qc.depth():4d}, {rows[-1]['gates']} gates): "
            f"median ZZZ={np.median(z):+.3f}  >=0.50: {rows[-1]['ge50']}/{len(cells)}"
        )
    st = state()
    st[_phase_key("sunscreen", args.budget)] = dict(rows=rows, t=now(), budget=args.budget)
    save_state(st)


# ---------------------------------------------------------------- Phase 7
def _finish_chip_tag(counts, tag, ncells):
    st = state()
    sign = st.get("sweep", {}).get("sign", 1)
    z = sign * zzz_per_cell_from_counts(counts[0], ncells)
    st[tag] = dict(
        median=float(np.median(z)),
        mean=float(z.mean()),
        ge50=int((z >= 0.50).sum()),
        ge70=int((z >= 0.70).sum()),
        ncells=ncells,
        per_cell=[float(x) for x in z],
        t=now(),
    )
    save_state(st)


def _finish_depth(counts, layers, ncells, budget="mini"):
    st = state()
    sgn = st["sweep"].get("sign", 1)
    rows = []
    for L, ct in zip(layers, counts):
        z = sgn * zzz_per_cell_from_counts(ct, ncells)
        rows.append(dict(layers=L, median=float(np.median(z)), mean=float(z.mean())))
    st[_phase_key("depth", budget)] = dict(rows=rows, t=now(), budget=budget)
    save_state(st)


def _finish_sunscreen(counts, cfgs, ncells, budget="mini"):
    st = state()
    sgn = st["sweep"].get("sign", 1)
    rows = []
    for (k, l), ct in zip(cfgs, counts):
        z = sgn * zzz_per_cell_from_counts(ct, ncells)
        rows.append(dict(cycles=k, per_cycle=l, total_layers=k * l, median=float(np.median(z)), ncells=ncells))
    st[_phase_key("sunscreen", budget)] = dict(rows=rows, t=now(), budget=budget)
    save_state(st)


def cmd_collect(args):
    st = state()
    B = BUDGETS[args.budget]
    n_champ = len(st.get("champions", []))
    n_all = len(st.get("cells", []))
    for tag, info in list(st.get("jobs", {}).items()):
        done_key = tag if tag != "sweep" else "sweep"
        if done_key in st and isinstance(st.get(done_key), dict) and st[done_key].get("t"):
            print(f"[{tag}] already in state — skip")
            continue
        print(f"fetching {tag} ({info['id']}) ...")
        try:
            counts = fetch_job(tag)
        except Exception as exc:
            print(f"  {tag} not ready: {exc}")
            continue
        if tag == "sweep":
            _finish_sweep(counts, B["deltas"], n_champ)
        elif tag in ("fullchip", "control"):
            _finish_chip_tag(counts, tag, n_all)
        elif tag == "depth" or tag == "depth_full":
            budget = "full" if tag.endswith("_full") else args.budget
            _finish_depth(counts, BUDGETS[budget]["depth_layers"], n_all, budget=budget)
        elif tag == "sunscreen" or tag == "sunscreen_full":
            budget = "full" if tag.endswith("_full") else args.budget
            _finish_sunscreen(counts, BUDGETS[budget]["sun"], n_all, budget=budget)
        print(f"  {tag} done.")


def cmd_status(args):
    st = state()
    print("=== QSD campaign status ===")
    print(f"backend: {st.get('backend')}  cells: {len(st.get('cells', []))}")
    if "sweep" in st:
        sw = st["sweep"]
        print(f"sweep DONE — calibrated_src_deg={sw.get('calibrated_src_deg'):.2f}  Delta={sw.get('best_delta'):+d}")
    else:
        print("sweep PENDING — need calibrated angle before fullchip/depth/sunscreen")
    for tag in ("fullchip", "control", "depth", "sunscreen", "depth_full", "sunscreen_full"):
        if tag in st:
            print(f"{tag} DONE")
        elif tag in st.get("jobs", {}):
            print(f"{tag} submitted — job {st['jobs'][tag]['id']}")
        else:
            print(f"{tag} not submitted")


def cmd_report_cells(args):
    """Per-cell ZZZ breakdown: optimized vs control, gap map."""
    st = state()
    cells = st.get("cells", [])
    fc = st.get("fullchip", {})
    ctrl = st.get("control", {})
    if not fc.get("per_cell") or not ctrl.get("per_cell"):
        sys.exit("need fullchip + control in state (run collect first)")

    fc_z = np.array(fc["per_cell"])
    ctrl_z = np.array(ctrl["per_cell"])
    gaps = fc_z - ctrl_z
    n = len(cells)

    rows = []
    for i, (cell, opt, rnd, gap) in enumerate(zip(cells, fc_z, ctrl_z, gaps)):
        rows.append(
            dict(
                cell_id=i,
                line=cell,
                zzz_optimized=float(opt),
                zzz_control=float(rnd),
                gap=float(gap),
                win=bool(gap > 0),
            )
        )

    rows.sort(key=lambda r: -r["gap"])
    wins = sum(1 for r in rows if r["win"])
    ge50 = sum(1 for z in fc_z if z >= 0.50)

    report = dict(
        n_cells=n,
        calibrated_src_deg=st.get("sweep", {}).get("calibrated_src_deg"),
        best_delta=st.get("sweep", {}).get("best_delta"),
        fullchip_median=fc.get("median"),
        control_median=ctrl.get("median"),
        d1_gap=float(np.median(gaps)),
        cells_winning=wins,
        cells_ge50_optimized=ge50,
        top10=rows[:10],
        bottom10=rows[-10:],
        all_cells=rows,
        t=now(),
    )
    out_path = os.path.join(RESULTS, "cell_report.json")
    _save(out_path, report)

    print("=== Per-cell ZZZ report ===")
    print(f"cells: {n}  calibrated_src: {report['calibrated_src_deg']:.2f}°  Δ={report['best_delta']:+d}")
    print(f"D1 median gap: {report['d1_gap']:+.3f}  wins: {wins}/{n}  optimized >=0.50: {ge50}/{n}")
    print("\nTop 10 cells (optimized - control):")
    for r in rows[:10]:
        print(f"  {r['line']}  opt={r['zzz_optimized']:+.3f}  ctrl={r['zzz_control']:+.3f}  gap={r['gap']:+.3f}")
    print(f"\nWrote {out_path}")


def cmd_full_depth(args):
    """Submit full-budget depth + sunscreen only (reuses mini sweep/fullchip/control)."""
    args.budget = "full"
    print("=== Full-budget depth + sunscreen (D3/D4 targets) ===")
    print(f"depth layers: {BUDGETS['full']['depth_layers']}")
    print(f"sunscreen cfgs: {BUDGETS['full']['sun']}")
    _ensure_sweep_calibrated(args)
    cmd_depth(args)
    cmd_sunscreen(args)


# ---------------------------------------------------------------- Phase 8
def cmd_analyze(args):
    p = prereg_check()
    st = state()
    depth_key = _phase_key("depth", args.budget)
    sun_key = _phase_key("sunscreen", args.budget)
    need = ["sweep", "fullchip", "control", depth_key, sun_key]
    missing = [k for k in need if k not in st]
    if missing:
        sys.exit(f"missing phases: {missing}  (for budget={args.budget})")
    R = p["rules"]
    out = {}

    d1 = st["fullchip"]["median"] - st["control"]["median"]
    out["D1"] = dict(value=round(d1, 3), passed=bool(d1 >= R["D1_angle_specificity"]["threshold"]))

    sw = st["sweep"]
    vals = [r["mean"] for r in sw["rows"]]
    contrast = max(vals) - min(vals)
    out["D2"] = dict(
        contrast=round(contrast, 3),
        interior=sw["interior"],
        passed=bool(contrast >= R["D2_basin_structure"]["threshold"] and sw["interior"]),
    )

    depth_data = st[depth_key]
    sun_data = st[sun_key]
    deep_sun = max(sun_data["rows"], key=lambda r: r.get("depth", r["total_layers"] * 10))
    base = min(
        depth_data["rows"],
        key=lambda r: abs(r.get("depth", r.get("layers", 0) * 10) - deep_sun.get("depth", 0)),
    )
    FLOOR = 0.05
    if abs(deep_sun["median"]) < FLOOR and abs(base["median"]) < FLOOR:
        out["D3"] = dict(
            passed=False,
            not_evaluable=True,
            note="both medians ~0 (ideal sim or no signal)",
        )
    else:
        ratio = deep_sun["median"] / max(abs(base["median"]), FLOOR)
        out["D3"] = dict(
            sun_median=deep_sun["median"],
            noreset_median=base["median"],
            ratio=round(ratio, 2),
            passed=bool(deep_sun.get("depth", 0) >= 250 and ratio >= R["D3_stabilization"]["threshold"]),
        )

    sun = sorted(sun_data["rows"], key=lambda r: r.get("depth", r["total_layers"]))
    if abs(sun[0]["median"]) < FLOOR:
        out["D4"] = dict(passed=False, not_evaluable=True, note="shallow sunscreen median ~0")
    else:
        pers = sun[-1]["median"] / sun[0]["median"]
        out["D4"] = dict(persistence=round(pers, 2), passed=bool(pers >= R["D4_persistence"]["threshold"]))

    if out["D1"]["passed"] and out["D2"]["passed"]:
        verdict = "STABILIZED" if (out["D3"]["passed"] and out["D4"]["passed"]) else "PARTIAL"
    else:
        verdict = "NEGATIVE"

    report = {
        "verdict": verdict,
        "rules": out,
        "budget": args.budget,
        "prereg_sha256": p["sha256"],
        "backend": st.get("backend"),
        "mode": st.get("mode"),
        "jobs": st.get("jobs", {}),
        "t": now(),
        "two_quantity_note": p["note"],
        "calibrated_src_deg": st["sweep"]["calibrated_src_deg"],
        "theory_constant_deg": THETA_STAR_DEG,
    }
    _save(os.path.join(RESULTS, "campaign_report.json"), report)

    print("\n" + "=" * 62)
    print(f"  VERDICT: {verdict}   (pre-registered rules, hash {p['sha256'][:12]})")
    print("=" * 62)
    for k in ("D1", "D2", "D3", "D4"):
        print(f"  {k}: {'PASS' if out[k]['passed'] else 'FAIL'}  {out[k]}")
    print(f"\n  platform-calibrated source angle: {st['sweep']['calibrated_src_deg']:.2f} deg")
    print(f"  theory constant (unchanged):      {THETA_STAR_DEG} deg = pi/8 exactly")
    print(f"  report -> {RESULTS}/campaign_report.json")
    _plots(st, budget=args.budget)


def _plots(st, budget="mini"):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    depth_key = _phase_key("depth", budget)
    sun_key = _phase_key("sunscreen", budget)
    if depth_key not in st or sun_key not in st:
        return
    NAVY, TEAL, RED = "#0D3B66", "#006D77", "#B3403A"
    fig, axs = plt.subplots(1, 3, figsize=(10, 2.8))
    sw = st["sweep"]["rows"]
    axs[0].plot([r["delta"] for r in sw], [r["mean"] for r in sw], "o-", color=NAVY)
    axs[0].axvline(st["sweep"]["best_delta"], color=RED, ls="--")
    axs[0].set_title("Basin sweep")
    axs[0].set_xlabel("Delta (deg)")
    axs[0].set_ylabel("mean ZZZ")
    dp = st[depth_key]["rows"]
    axs[1].plot([r.get("depth", r["layers"]) for r in dp], [r["median"] for r in dp], "s-", color=NAVY, label="no reset")
    sn = st[sun_key]["rows"]
    axs[1].plot([r.get("depth", r["total_layers"]) for r in sn], [r["median"] for r in sn], "^-", color=TEAL, label="sunscreen")
    axs[1].legend(fontsize=7)
    axs[1].set_title(f"Depth scaling ({budget})")
    axs[1].set_xlabel("circuit depth")
    axs[2].bar(["optimized", "random ctrl"], [st["fullchip"]["median"], st["control"]["median"]], color=[NAVY, RED])
    axs[2].set_title("Angle specificity (D1)")
    axs[2].set_ylabel("median ZZZ")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "campaign_plots.pdf"))
    print(f"  plots  -> {RESULTS}/campaign_plots.pdf")


# ---------------------------------------------------------------- orchestrate
def cmd_all(args):
    for fn in (cmd_prereg, cmd_discover, cmd_sweep, cmd_fullchip, cmd_control, cmd_depth, cmd_sunscreen, cmd_analyze):
        fn(args)


def main():
    ap = argparse.ArgumentParser(description="QSD stabilization campaign (IBM Quantum)")
    ap.add_argument(
        "phase",
        choices=[
            "prereg", "discover", "sweep", "fullchip", "control", "depth", "sunscreen",
            "full-depth", "collect", "status", "report-cells", "analyze", "all",
        ],
    )
    ap.add_argument("--backend", default="ibm_fez", help="ibm_fez | ibm_marrakesh | ibm_torino | aer")
    ap.add_argument("--budget", default="mini", choices=["mini", "full"])
    ap.add_argument("--nowait", action="store_true", help="submit and exit (retrieve with collect)")
    ap.add_argument(
        "--legacy-circuits",
        action="store_true",
        help="June reference source-bridge-source builder (default: aurora_qsd TriLock)",
    )
    args = ap.parse_args()
    {
        "prereg": cmd_prereg,
        "discover": cmd_discover,
        "sweep": cmd_sweep,
        "fullchip": cmd_fullchip,
        "control": cmd_control,
        "depth": cmd_depth,
        "sunscreen": cmd_sunscreen,
        "full-depth": cmd_full_depth,
        "collect": cmd_collect,
        "status": cmd_status,
        "report-cells": cmd_report_cells,
        "analyze": cmd_analyze,
        "all": cmd_all,
    }[args.phase](args)


if __name__ == "__main__":
    main()
