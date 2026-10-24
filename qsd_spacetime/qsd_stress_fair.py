"""
Follow-up to qsd_stress_test.py: predictive gate with a vibration-aware Kalman
filter (drift [r, v] + oscillator [c, s] at the platform's known vibration
frequency). Re-lock resets drift only; vibration persists. Pure NumPy.
"""
import numpy as np
from qsd_stress_test import norm_sf, THRS, PTHS, run as run_basic, R_MAX, LAT, H, T, N

def run_va(knob, mode='pred', f_err=1.0, sm=0.3, sa=0.02, vib_amp=0.0, vib_period=20.0,
           step_rate=0.0, step_size=(1.0, 2.5), seed=3):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.2, N); v = np.zeros(N); phase = rng.uniform(0, 2*np.pi, N)
    pending = np.full(N, -1); relocks = np.zeros(N); outside = np.zeros(N)
    w = 2*np.pi/vib_period
    wf = w*f_err  # filter's assumed vibration frequency
    F = np.zeros((4, 4)); F[:2, :2] = [[1, 1], [0, 1]]
    F[2:, 2:] = [[np.cos(wf), -np.sin(wf)], [np.sin(wf), np.cos(wf)]]
    Q = np.zeros((4, 4)); Q[:2, :2] = sa**2*np.array([[1/3, 1/2], [1/2, 1]])
    Q[2, 2] = Q[3, 3] = (0.02*max(vib_amp, 0.1))**2
    Hm = np.array([1.0, 0, 1.0, 0])
    FH = np.linalg.matrix_power(F, H)
    QH = sum(np.linalg.matrix_power(F, k) @ Q @ np.linalg.matrix_power(F, k).T for k in range(H))
    x = np.zeros((N, 4)); P = np.tile(np.diag([1.0, 0.1, max(vib_amp, 0.1)**2, max(vib_amp, 0.1)**2]), (N, 1, 1))
    eps = np.sin(np.radians(R_MAX))**2
    for t in range(T):
        land = pending == t
        r[land] = rng.normal(0, 0.2, land.sum()); v[land] *= 0.3; pending[land] = -1
        if land.any():
            x[land, 0] = 0.0; x[land, 1] *= 0.3
            P[np.ix_(land, [0, 1], [0, 1])] = 0.0
            P[land, 0, 0] = 0.2**2 + 0.05; P[land, 1, 1] = 1e-3
            P[land, 0, 2:] = P[land, 2:, 0] = 0.0; P[land, 1, 2:] = P[land, 2:, 1] = 0.0
        r += v; v += rng.normal(0, sa, N)
        jump = rng.random(N) < step_rate
        r += jump*rng.choice([-1, 1], N)*rng.uniform(*step_size, N)
        res = r + vib_amp*np.sin(w*t + phase)
        z = res + rng.normal(0, sm, N)
        outside += np.abs(res) > R_MAX
        x = x @ F.T; P = F @ P @ F.T + Q
        S = np.einsum('i,nij,j->n', Hm, P, Hm) + sm**2
        Kg = (P @ Hm)/S[:, None]
        x = x + Kg*(z - x @ Hm)[:, None]
        P = P - Kg[:, :, None]*(Hm @ P)[:, None, :]
        idle = pending < 0
        # peak predicted |residual| over the horizon window (vibration swings through it)
        pe = np.zeros(N)
        for h in range(1, H + 1):
            Fh = np.linalg.matrix_power(F, h)
            Qh = sum(np.linalg.matrix_power(F, k) @ Q @ np.linalg.matrix_power(F, k).T for k in range(h))
            c = Hm @ Fh
            mu = x @ c; sd = np.sqrt(np.einsum('i,nij,j->n', c, P, c) + c @ Qh @ c)
            pe = np.maximum(pe, norm_sf((R_MAX - mu)/sd) + norm_sf((R_MAX + mu)/sd))
        est = x @ Hm
        if mode == 'react':
            trig = idle & (np.abs(est) > knob)
        else:
            trig = idle & ((pe > knob) | (np.sin(np.radians(est))**2 > eps))
        relocks += trig; pending[trig] = t + LAT
    return relocks.mean(), 100*outside.mean()/T

REG = [("vibration 1.0 deg, P=20", dict(vib_amp=1.0, vib_period=20)),
       ("vib 1.0 P=20 + steps 1/100", dict(vib_amp=1.0, vib_period=20, step_rate=0.01))]
if __name__ == "__main__":
    print(f"{'regime':28s} {'f_err':>5} {'p_th':>5} | {'relocks':>7} | {'%out P':>6} | {'%out R@same':>11} | ratio   (both gates use the vibration-aware filter)")
    for name, kw in REG:
        for fe in (1.0, 0.85, 1.15):
            rc = np.array([run_va(th, mode='react', f_err=fe, **kw) for th in THRS])
            o = np.argsort(rc[:, 0]); rl, ro = rc[o, 0], rc[o, 1]
            for p in PTHS:
                b, po = run_va(p, f_err=fe, **kw)
                if b < rl[0] or b > rl[-1]:
                    tag = "R min %.1f@%.2f%%" % (rl[0], ro[0]) if b < rl[0] else "beyond R"
                    print(f"{name:28s} {fe:5.2f} {p:5.2f} | {b:7.1f} | {po:6.2f} | {tag:>11} |"); continue
                orr = np.interp(b, rl, ro)
                print(f"{name:28s} {fe:5.2f} {p:5.2f} | {b:7.1f} | {po:6.2f} | {orr:11.2f} | {orr/max(po,1e-9):5.1f}x")
            print()
