"""
Redesigned equal-budget benchmark for qsd_stack_v2.

Same supervisor, two modes: forecast ON (predict=True) vs OFF (reactive
headroom rule, i.e. the original logic). Only the headroom path is active
(theta/shape gates disabled) so the comparison isolates the forecast.
Harder plant than before: fast slews, slow and fast vibration, and steps.
Score: % of time WITHOUT LOCK (FSM saturated -> lock lost for 150 ms until
re-lock), compared at equal offloads/minute (each mode's threshold swept).
"""
import numpy as np
import qsd_stack_v2 as q

class Clock:
    def __init__(self): self.t = 1000.0
    def monotonic(self): return self.t
    def time(self): return 1.7e9 + self.t
    def sleep(self, s): self.t += s
CLK = Clock(); q.time = CLK
DT, LIMIT = 0.001, 100.0

class Plant:
    def __init__(self, seed, rate_walk=1.0, vib=(), jump_rate=0.0, jump_size=(20, 40)):
        self.rng = np.random.default_rng(seed)
        self.x = np.zeros(2); self.v = self.rng.normal(0, 30, 2)
        self.rw, self.vib, self.jr, self.js = rate_walk, vib, jump_rate, jump_size
        self.ph = self.rng.uniform(0, 2*np.pi, (max(1, len(vib)), 2))
        self.pending = None; self.seq = 0; self.n = 0; self.nolock = 0
        self.offloads = 0; self.relocks = 0; self.lost_until = -1.0
    def step(self):
        t = CLK.monotonic()
        if self.pending is not None and t >= self.pending:
            self.x[:] = 0.0; self.pending = None
        self.v = np.clip(self.v + self.rng.normal(0, self.rw, 2), -250, 250)
        self.x += self.v*DT
        if self.jr and self.rng.random() < self.jr*DT:
            self.x += self.rng.choice([-1, 1], 2)*self.rng.uniform(*self.js, 2)
        pos = self.x.copy()
        for i, (a, f) in enumerate(self.vib):
            pos += a*np.sin(2*np.pi*f*t + self.ph[i])
        if np.any(np.abs(pos) >= LIMIT) and t >= self.lost_until:
            self.lost_until = t + 0.150
        self.n += 1; self.nolock += t < self.lost_until
        self.pos = pos
    def read(self, beam):
        self.seq += 1
        meas = np.clip(self.pos + self.rng.normal(0, 0.5, 2), -LIMIT, LIMIT)
        return q.Sample(CLK.monotonic(), CLK.time(), self.seq,
                        (meas[0], meas[1], *self.rng.normal(0, 0.3, 2)),
                        bool(CLK.monotonic() >= self.lost_until), True)
    def offload(self, beam):
        self.offloads += 1
        if self.pending is None: self.pending = CLK.monotonic() + 0.020
    def relock(self, beam):
        self.relocks += 1; self.x[:] = 0.0; self.v *= 0.5

def run(seed, predict, hw, seconds, **pk):
    cfg = q.Config(predict=predict, headroom_warn=hw, headroom_trip=0.02,
                   headroom_clear=min(hw + 0.15, 1.0),
                   theta_warn=10.0, theta_trip=20.0, theta_clear=5.0,
                   shape_gate_rms_urad=1e9)
    p = Plant(seed, **pk); sup = q.Supervisor(q.Beam("b", "i"), cfg)
    for _ in range(int(seconds/DT)):
        CLK.sleep(DT); p.step(); sup.tick(p)
    return 100*p.nolock/p.n, 60*p.offloads/seconds

REGIMES = [
    ("fast slews only",                   dict(rate_walk=1.5)),
    ("slews + slow vibration 40 urad 2 Hz", dict(rate_walk=1.0, vib=((40, 2.0),))),
    ("slews + fast vibration 15 urad 8 Hz", dict(rate_walk=1.0, vib=((15, 8.0),))),
    ("slews + steps 20-40 urad, 0.5/s",     dict(rate_walk=1.0, jump_rate=0.5)),
]
HW = [0.15, 0.25, 0.35, 0.50]

if __name__ == "__main__":
    S, SEEDS = 20, 3
    for name, pk in REGIMES:
        curves = {}
        for mode in (False, True):
            pts = []
            for hw in HW:
                r = np.mean([run(s, mode, hw, S, **pk) for s in range(SEEDS)], axis=0)
                pts.append((hw, r[1], r[0]))
            curves[mode] = pts
        print(f"\n[{name}]")
        print("  headroom_warn | reactive: offl/min  no-lock% | forecast: offl/min  no-lock% | reactive no-lock% @ same offloads")
        rc = np.array([[o, nl] for _, o, nl in curves[False]]); rc = rc[np.argsort(rc[:, 0])]
        for (hw, ro, rn), (_, po, pn) in zip(curves[False], curves[True]):
            same = (f"{np.interp(po, rc[:,0], rc[:,1]):.3f}" if rc[0,0] <= po <= rc[-1,0] else "out of range")
            print(f"     {hw:4.2f}       |  {ro:7.1f}  {rn:8.3f}      |  {po:7.1f}  {pn:8.3f}      |  {same}")
