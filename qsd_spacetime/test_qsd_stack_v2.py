"""
Tests of the shared qsd_stack_v2.py supervisor, driven with a simulated clock
(so a 1 kHz loop runs faster than real time and is deterministic).

Test A  Robustness: one 60 ms sample gap (e.g. a Python GC pause) mid-run.
Test B  Performance at equal offload budget, microradian scale:
        fine-steering-mirror (FSM) position absorbs platform drift; if it hits
        its +/-100 urad limit the beam is lost (outage). Offload re-centres it.
        qsd_stack governor (headroom threshold + hold times)  vs
        Kalman predictive gate (P(hit limit within horizon) > p), same
        250 ms offload rate limit, same 20 ms offload latency.
"""
import math, sys
import numpy as np
import qsd_stack_v2 as q

class Clock:
    def __init__(self): self.t = 1000.0
    def monotonic(self): return self.t
    def time(self): return 1.7e9 + self.t
    def sleep(self, s): self.t += s
CLK = Clock()
q.time = CLK          # supervisor reads time.monotonic()/time.time() from here

DT, LIMIT = 0.001, 100.0

class MirrorPlant:
    """2-axis FSM position (urad). Drift: slewing bias whose rate random-walks.
    Optional platform vibration the FSM must follow. Offload moves the bias
    to the gimbal (FSM re-centres) after 20 ms."""
    def __init__(self, seed, vib_amp=0.0, vib_hz=5.0, rate_walk=0.4):
        self.rng = np.random.default_rng(seed)
        self.x = np.zeros(2); self.v = self.rng.normal(0, 20, 2)   # urad/s
        self.vib_amp, self.vib_hz, self.rw = vib_amp, vib_hz, rate_walk
        self.pending = None; self.seq = 0; self.out = 0; self.n = 0
        self.offloads = 0; self.relocks = 0; self.lost_until = -1
        self.phase = self.rng.uniform(0, 2*np.pi, 2)
    def step(self):
        t = CLK.monotonic()
        if self.pending is not None and t >= self.pending:
            self.x[:] = 0.0; self.pending = None
        self.v += self.rng.normal(0, self.rw, 2)
        self.v = np.clip(self.v, -200, 200)
        self.x += self.v*DT
        pos = self.x + self.vib_amp*np.sin(2*np.pi*self.vib_hz*t + self.phase)
        sat = np.any(np.abs(pos) >= LIMIT)
        self.n += 1; self.out += sat
        if sat and t >= self.lost_until:
            self.lost_until = t + 0.15          # lock lost; needs re-lock
        return pos, sat
    # Terminal protocol for qsd_stack
    def read(self, beam):
        pos, sat = self.cur
        self.seq += 1
        meas = np.clip(pos + self.rng.normal(0, 0.5, 2), -LIMIT, LIMIT)
        quad = self.rng.normal(0, 0.3, 2)
        return q.Sample(CLK.monotonic(), CLK.time(), self.seq,
                        tuple(np.concatenate([meas, quad])),
                        bool(CLK.monotonic() >= self.lost_until), True)
    def offload(self, beam):
        self.offloads += 1
        if self.pending is None: self.pending = CLK.monotonic() + 0.020
    def relock(self, beam):
        self.relocks += 1; self.x[:] = 0.0; self.lost_until = CLK.monotonic() + 0.15

def run_stack(plant, seconds, cfg, gap_at=None):
    sup = q.Supervisor(q.Beam("b", "i"), cfg); up = 0; n = 0; first_fault = None
    for k in range(int(seconds/DT)):
        if gap_at is not None and k == int(gap_at/DT):
            CLK.sleep(0.060)                     # one 60 ms hiccup
        CLK.sleep(DT); plant.cur = plant.step()
        st = sup.tick(plant)
        up += st["oper_status"] == "IF_OPER_STATUS_UP"; n += 1
        if st["regime"] == 4 and first_fault is None:
            first_fault = (round(k*DT, 3), st["reason"][:60])
    return 100*up/n, first_fault

def run_predictive(plant, seconds, p_th, horizon_s=0.030, rate_limit=0.250):
    """Per-axis 2-state KF on FSM position; offload when P(|x| >= LIMIT within horizon) > p."""
    H = int(horizon_s/DT)
    F = np.array([[1, DT], [0, 1]]); qv = (plant.rw)**2
    Q = qv*np.array([[DT**2/3, DT/2], [DT/2, 1.0]]); Rm = 0.5**2
    FH = np.linalg.matrix_power(F, H)
    QH = sum(np.linalg.matrix_power(F, k) @ Q @ np.linalg.matrix_power(F, k).T for k in range(H))
    x = np.zeros((2, 2)); P = np.tile(np.diag([25.0, 400.0]), (2, 1, 1))
    last = -1e9; was_pending = False
    for k in range(int(seconds/DT)):
        CLK.sleep(DT); pos, sat = plant.step()
        now = CLK.monotonic()
        if was_pending and plant.pending is None:          # offload landed -> FSM re-centred
            x[:, 0] = 0.0; P[:, 0, 0] = 1.0; was_pending = False
        z = np.clip(pos + plant.rng.normal(0, 0.5, 2), -LIMIT, LIMIT)
        for a in range(2):
            x[a] = F @ x[a]; P[a] = F @ P[a] @ F.T + Q
            S = P[a, 0, 0] + Rm; K = P[a, :, 0]/S
            x[a] = x[a] + K*(z[a] - x[a, 0]); P[a] = P[a] - np.outer(K, P[a, 0])
        pe = 0.0
        for a in range(2):
            mu = FH[0] @ x[a]; sd = math.sqrt(FH[0] @ P[a] @ FH[0] + QH[0, 0])
            pe = max(pe, 0.5*math.erfc((LIMIT - mu)/(sd*math.sqrt(2))) +
                         0.5*math.erfc((LIMIT + mu)/(sd*math.sqrt(2))))
        if pe > p_th and now - last >= rate_limit and plant.pending is None:
            plant.offload(None); last = now; was_pending = True
        if sat:                                            # same lock-loss handling as stack
            plant.relock(None); x[:] = 0.0; P[:] = np.diag([1.0, 400.0])

def summary(plant, seconds):
    return 100*plant.out/plant.n, 60*plant.offloads/seconds, 60*plant.relocks/seconds

if __name__ == "__main__":
    print("== Test A: one 60 ms sample gap at t = 3 s (20 s run, gentle drift) ==")
    for gap in (None, 3.0):
        p = MirrorPlant(1, rate_walk=0.2)
        up, ff = run_stack(p, 20, q.Config(), gap_at=gap)
        print(f"  gap={gap}:  time UP {up:5.1f}%   first latched fault: {ff}")

    print("\n== Test B: equal-offload-budget comparison (60 s per point, 3 seeds) ==")
    regimes = [("drift only", dict()), ("drift + 15 urad 5 Hz vibration", dict(vib_amp=15.0, vib_hz=5.0)),
               ("drift + 40 urad 2 Hz vibration", dict(vib_amp=40.0, vib_hz=2.0))]
    S = 60
    for name, kw in regimes:
        rows_s, rows_p = [], []
        for hw in (0.10, 0.20, 0.30, 0.45, 0.60):
            res = []
            for seed in range(3):
                cfg = q.Config(headroom_warn=hw, headroom_clear=min(hw + 0.15, 1.0),
                               headroom_trip=min(0.05, hw/2), theta_warn=10.0, theta_trip=20.0,
                               theta_clear=5.0, shape_gate_rms_urad=1e9,
                               max_sample_gap_s=1.0, max_sample_age_s=1.0)
                p = MirrorPlant(seed, **kw); run_stack(p, S, cfg); res.append(summary(p, S))
            rows_s.append((hw, *np.mean(res, axis=0)))
        for pth in (0.5, 0.2, 0.05, 0.01, 0.001):
            res = []
            for seed in range(3):
                p = MirrorPlant(seed, **kw); run_predictive(p, S, pth); res.append(summary(p, S))
            rows_p.append((pth, *np.mean(res, axis=0)))
        print(f"\n  [{name}]")
        print("   qsd_stack  headroom_warn | outage % | offloads/min | relocks/min")
        for r in rows_s: print(f"               {r[0]:5.2f}       | {r[1]:7.3f}  | {r[2]:9.1f}    | {r[3]:7.2f}")
        print("   predictive p_th          | outage % | offloads/min | relocks/min | stack outage @ same offloads")
        so = np.array([[r[2], r[1]] for r in rows_s]); so = so[np.argsort(so[:, 0])]
        for r in rows_p:
            same = (f"{np.interp(r[2], so[:,0], so[:,1]):.3f}%" if so[0,0] <= r[2] <= so[-1,0] else "out of range")
            print(f"               {r[0]:6.3f}      | {r[1]:7.3f}  | {r[2]:9.1f}    | {r[3]:7.2f}     | {same}")
