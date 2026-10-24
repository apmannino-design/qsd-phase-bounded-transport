"""
Stress test: predictive (Kalman) vs reactive re-lock gate when the plant does NOT
match the filter's constant-velocity random-walk model. Pure NumPy.

Disturbances added to the original drifting residual:
  vibration : platform jitter A*sin(2*pi*t/P + phase), not removed by re-lock
  steps     : sudden pointing jumps (Poisson rate, random sign, size range)
The gates are unchanged (filter still assumes random-walk drift only).
Comparison at matched re-lock budget, as in qsd_matched_budget.py.
"""
import numpy as np

R_MAX, LAT, H = 3.0, 3, 5
T, N = 2000, 300

def norm_sf(x):
    z = x/np.sqrt(2.0); t = 1.0/(1.0 + 0.5*np.abs(z))
    y = t*np.exp(-z*z - 1.26551223 + t*(1.00002368 + t*(0.37409196 + t*(0.09678418 +
        t*(-0.18628806 + t*(0.27886807 + t*(-1.13520398 + t*(1.48851587 +
        t*(-0.82215223 + t*0.17087277)))))))))
    return 0.5*np.where(z >= 0, y, 2.0 - y)

def run(mode, knob, sm=0.3, sa=0.02, vib_amp=0.0, vib_period=20.0,
        step_rate=0.0, step_size=(1.0, 2.5), seed=3):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.2, N); v = np.zeros(N)
    phase = rng.uniform(0, 2*np.pi, N)
    pending = np.full(N, -1); relocks = np.zeros(N); outside = np.zeros(N)
    F = np.array([[1, 1.0], [0, 1]]); Q = sa**2*np.array([[1/3, 1/2], [1/2, 1]])
    FH = np.linalg.matrix_power(F, H)
    QH = sum(np.linalg.matrix_power(F, k) @ Q @ np.linalg.matrix_power(F, k).T for k in range(H))
    x = np.zeros((N, 2)); P = np.tile(np.diag([1.0, 0.1]), (N, 1, 1))
    thr_eps = np.sin(np.radians(knob))**2 if mode == "reactive" else None
    eps = np.sin(np.radians(R_MAX))**2
    for t in range(T):
        land = pending == t
        r[land] = rng.normal(0, 0.2, land.sum()); v[land] *= 0.3; pending[land] = -1
        if land.any():
            x[land, 0] = 0.0; x[land, 1] *= 0.3
            P[land] = np.diag([0.2**2 + 0.05, 1e-3])
        r += v; v += rng.normal(0, sa, N)
        jump = rng.random(N) < step_rate
        r += jump*rng.choice([-1, 1], N)*rng.uniform(*step_size, N)
        vib = vib_amp*np.sin(2*np.pi*t/vib_period + phase)
        res = r + vib                                    # true pointing residual
        z = res + rng.normal(0, sm, N)
        outside += np.abs(res) > R_MAX
        # KF (same as deployed gate)
        x = x @ F.T; P = F @ P @ F.T + Q
        S = P[:, 0, 0] + sm**2; Kg = P[:, :, 0]/S[:, None]
        x = x + Kg*(z - x[:, 0])[:, None]; P = P - Kg[:, :, None]*P[:, None, 0, :]
        idle = pending < 0
        if mode == "reactive":
            trig = idle & (np.sin(np.radians(z))**2 > thr_eps)
        else:
            mu = x @ FH[0]
            sd = np.sqrt(np.einsum('i,nij,j->n', FH[0], P, FH[0]) + QH[0, 0])
            pe = norm_sf((R_MAX - mu)/sd) + norm_sf((R_MAX + mu)/sd)
            trig = idle & ((pe > knob) | (np.sin(np.radians(x[:, 0]))**2 > eps))
        relocks += trig; pending[trig] = t + LAT
    return relocks.mean(), 100*outside.mean()/T

THRS = [3.0, 2.8, 2.6, 2.4, 2.2, 2.0, 1.8, 1.6, 1.4, 1.2, 1.0, 0.8]
PTHS = [0.40, 0.20, 0.10, 0.05]
REGIMES = [
    ("baseline (no mismatch)",        dict()),
    ("vibration 0.5 deg, P=20",       dict(vib_amp=0.5, vib_period=20)),
    ("vibration 1.0 deg, P=20",       dict(vib_amp=1.0, vib_period=20)),
    ("vibration 1.0 deg, P=6 (fast)", dict(vib_amp=1.0, vib_period=6)),
    ("steps 1-2.5 deg, 1/200 steps",  dict(step_rate=0.005)),
    ("steps 1-2.5 deg, 1/50 steps",   dict(step_rate=0.02)),
    ("vib 1.0 P=20 + steps 1/100",    dict(vib_amp=1.0, vib_period=20, step_rate=0.01)),
]

if __name__ == "__main__":
    print(f"{'regime':32s} {'p_th':>5} | {'relocks':>7} | {'%out P':>7} | {'%out R@same':>11} | ratio")
    for name, kw in REGIMES:
        rc = np.array([run("reactive", th, **kw) for th in THRS])
        o = np.argsort(rc[:, 0]); rl, ro = rc[o, 0], rc[o, 1]
        for p in PTHS:
            b, po = run("predictive", p, **kw)
            if b < rl[0] or b > rl[-1]:
                tag = "R min %.1f@%.2f%%" % (rl[0], ro[0]) if b < rl[0] else "beyond R range"
                print(f"{name:32s} {p:5.2f} | {b:7.1f} | {po:7.2f} | {tag:>11} |")
                continue
            orr = np.interp(b, rl, ro)
            ratio = orr/po if po > 0 else float('inf')
            print(f"{name:32s} {p:5.2f} | {b:7.1f} | {po:7.2f} | {orr:11.2f} | {ratio:5.1f}x")
        print()
