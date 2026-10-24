"""
Predictive vs reactive REROUTING across optical ground stations under weather.
Pure NumPy (Juno-compatible).

Question: if Spacetime gets an early warning that the active optical link is
about to fade (cloud moving in), and switches ground stations BEFORE the fade,
how much traffic outage does that save at the same number of handovers?

Plant (per run, K ground stations, dt = 0.2 s, 1 hour):
  link margin m_k(t) [dB] = clear-sky margin
                          - cloud attenuation (Poisson events: ramp in over
                            20-120 s to 10-30 dB, hold 30-300 s, ramp out)
                          + scintillation (fast fades, sigma 1-2.5 dB)
  Outage: active link margin < 0 dB, or a handover in progress (3 s reacquisition).
  Every station's margin is observable (beacons / ground-station sensors).

Both policies use the SAME Kalman estimate of [margin, trend] per station:
  reactive(th):    switch when filtered margin < th dB            (th = safety buffer)
  predictive(p):   switch when P(margin < 0 within 6 s) > p
Same target choice (best station, 2 dB hysteresis) and 10 s minimum dwell.
Each knob is swept, then outage is compared at EQUAL handovers/hour.
"""
import numpy as np

DT, T_S, K = 0.2, 3600.0, 4
T = int(T_S/DT)
HO = int(3.0/DT)            # handover (reacquisition) time, steps
DWELL = int(10.0/DT)        # min time on a station before switching again
HYST = 2.0                  # dB a target must beat the current link by
HZN = 6.0                   # prediction horizon, s (handover + buffer)

def norm_cdf(x):
    z = x/np.sqrt(2.0); t = 1.0/(1.0 + 0.5*np.abs(z))
    y = t*np.exp(-z*z - 1.26551223 + t*(1.00002368 + t*(0.37409196 + t*(0.09678418 +
        t*(-0.18628806 + t*(0.27886807 + t*(-1.13520398 + t*(1.48851587 +
        t*(-0.82215223 + t*0.17087277)))))))))
    erfc = np.where(z >= 0, y, 2.0 - y)
    return 1.0 - 0.5*erfc

def make_margins(R, onset, scint, rate_per_min, seed):
    """True margins (R, K, T), float32."""
    rng = np.random.default_rng(seed)
    m = np.empty((R, K, T), np.float32)
    tt = np.arange(T)*DT
    for r in range(R):
        for k in range(K):
            att = np.zeros(T)
            n_ev = rng.poisson(rate_per_min*T_S/60)
            for _ in range(n_ev):
                t0 = rng.uniform(-300, T_S); on = rng.uniform(*onset)
                depth = rng.uniform(10, 30); hold = rng.uniform(30, 300)
                off = rng.uniform(*onset)
                a = np.clip((tt - t0)/on, 0, 1) * np.clip(1 - (tt - t0 - on - hold)/off, 0, 1)
                att = np.maximum(att, depth*a)
            sc = rng.normal(0, scint, T)
            m[r, k] = rng.uniform(4, 8) - att + sc
    return m

def kalman(meas, scint):
    """KF on [level, slope] for all (R, K) in parallel. Returns level, slope, P (per step)."""
    R = meas.shape[0]
    q = 0.03**2                      # slope random-walk (dB/s per step)^2
    F = np.array([[1, DT], [0, 1]]); Q = q*np.array([[DT**2/3, DT/2], [DT/2, 1.0]])
    Rm = scint**2 + 0.3**2
    x = np.zeros((R, K, 2)); x[..., 0] = meas[..., 0]
    P = np.tile(np.diag([4.0, 0.1]), (R, K, 1, 1))
    lev = np.empty_like(meas); slo = np.empty_like(meas)
    p00 = np.empty_like(meas); p01 = np.empty_like(meas); p11 = np.empty_like(meas)
    for t in range(meas.shape[2]):
        x = x @ F.T
        P = F @ P @ F.T + Q
        S = P[..., 0, 0] + Rm
        Kg = P[..., :, 0]/S[..., None]
        x = x + Kg*(meas[..., t] - x[..., 0])[..., None]
        P = P - Kg[..., :, None]*P[..., None, 0, :]
        lev[..., t], slo[..., t] = x[..., 0], x[..., 1]
        p00[..., t], p01[..., t], p11[..., t] = P[..., 0, 0], P[..., 0, 1], P[..., 1, 1]
    return lev, slo, p00, p01, p11

def simulate(true_m, est, mode, knob):
    lev, slo, p00, p01, p11 = est
    R = true_m.shape[0]
    h = HZN
    mu = lev + slo*h                                             # predicted margin at horizon
    sd = np.sqrt(np.maximum(p00 + 2*h*p01 + h*h*p11 + 0.03**2*h**3/3, 1e-6))
    score = mu if mode == "predictive" else lev                  # what each policy ranks stations by
    act = np.argmax(lev[..., 0], axis=1)
    busy = np.zeros(R, int); since = np.full(R, DWELL); hos = np.zeros(R); out = np.zeros(R)
    ri = np.arange(R)
    for t in range(T):
        in_ho = busy > 0
        out += in_ho | (true_m[ri, act, t] < 0)
        busy = np.maximum(busy - 1, 0); since += 1
        if mode == "reactive":
            want = lev[ri, act, t] < knob
        else:
            pf = norm_cdf((0 - mu[ri, act, t])/sd[ri, act, t])
            want = (pf > knob) | (lev[ri, act, t] < 0)
        sc = score[:, :, t].copy(); sc[ri, act] = -np.inf
        best = np.argmax(sc, axis=1)
        better = sc[ri, best] > score[ri, act, t] + HYST
        go = want & better & (busy == 0) & (since >= DWELL)
        act = np.where(go, best, act)
        busy = np.where(go, HO, busy); since = np.where(go, 0, since); hos += go
    return hos.mean(), 100*out.mean()/T

REACT_TH = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
PRED_P = [0.5, 0.2, 0.05, 0.01, 0.001]
REGIMES = [("fast clouds, mild scint", (20, 40), 1.0),
           ("fast clouds, strong scint", (20, 40), 2.5),
           ("slow clouds, mild scint", (60, 120), 1.0),
           ("slow clouds, strong scint", (60, 120), 2.5)]

if __name__ == "__main__":
    R = 40
    for name, onset, scint in REGIMES:
        true_m = make_margins(R, onset, scint, rate_per_min=0.15, seed=7)
        rng = np.random.default_rng(8)
        meas = true_m + rng.normal(0, 0.3, true_m.shape).astype(np.float32)
        est = kalman(meas, scint)
        rc = np.array([simulate(true_m, est, "reactive", th) for th in REACT_TH])
        o = np.argsort(rc[:, 0]); rh, ro = rc[o, 0], rc[o, 1]
        print(f"\n== {name} (onset {onset[0]}-{onset[1]} s, scint {scint} dB) ==")
        print("reactive curve (th dB: handovers/h, %outage): " +
              ", ".join(f"{th:.0f}: {a:.1f}, {b:.2f}%" for th, (a, b) in zip(REACT_TH, rc)))
        print(f"{'p_th':>6} | {'HO/h':>5} | {'%out P':>7} | {'%out R@same':>11} | {'saved':>6}")
        for p in PRED_P:
            hp, op = simulate(true_m, est, "predictive", p)
            if hp < rh[0] or hp > rh[-1]:
                print(f"{p:6.3f} | {hp:5.1f} | {op:7.2f} | {'out of range':>11} | {'-':>6}")
                continue
            orr = np.interp(hp, rh, ro)
            print(f"{p:6.3f} | {hp:5.1f} | {op:7.2f} | {orr:11.2f} | {100*(1-op/orr):5.0f}%")
