"""
QSD dE-gated predictive re-lock — core gate. Pure NumPy (Juno-compatible).

dE = sin^2(r)  (r = pointing residual, deg); corridor: dE <= sin^2(R_MAX).
A 2-state Kalman filter on [r, r_dot] predicts H steps ahead; the gate
commands a re-lock when P(|r_{t+H}| > R_MAX) > p_th, or when the current
estimate is already outside the corridor.

mode="reactive" gives the baseline: re-lock when dE(measurement) > eps.
"""
import numpy as np

def dE(r_deg):
    return np.sin(np.radians(r_deg))**2

def _norm_sf(x):
    """1 - Phi(x), scalar, pure numpy."""
    z = x / np.sqrt(2.0)
    t = 1.0 / (1.0 + 0.5*abs(z))
    y = t*np.exp(-z*z - 1.26551223 + t*(1.00002368 + t*(0.37409196 + t*(0.09678418 +
        t*(-0.18628806 + t*(0.27886807 + t*(-1.13520398 + t*(1.48851587 +
        t*(-0.82215223 + t*0.17087277)))))))))
    return 0.5*(y if z >= 0 else 2.0 - y)


class QSDGate:
    def __init__(self, r_max=3.0, sigma_meas=0.3, sigma_drift=0.02, dt=1.0,
                 latency_steps=3, p_th=0.2, mode="predictive"):
        self.r_max, self.dt, self.lat = float(r_max), float(dt), int(latency_steps)
        self.H, self.p_th, self.mode = self.lat + 2, float(p_th), mode
        self.eps = dE(self.r_max)
        sa, dt = sigma_drift, self.dt
        self.F = np.array([[1.0, dt], [0.0, 1.0]])
        self.Q = sa**2*np.array([[dt**3/3, dt**2/2], [dt**2/2, dt]])
        self.Rm = sigma_meas**2
        self.FH = np.linalg.matrix_power(self.F, self.H)
        self.QH = sum(np.linalg.matrix_power(self.F, k) @ self.Q @
                      np.linalg.matrix_power(self.F, k).T for k in range(self.H))
        self.reset()

    # -- lifecycle -----------------------------------------------------------
    def reset(self):
        """New beam / acquisition: forget history."""
        self.x = np.zeros(2)
        self.P = np.diag([1.0, 0.1])
        self.pending = -1          # steps until a commanded re-lock lands
        self.t = 0
        self.relocks = 0
        self.last = {}

    def relock_landed(self):
        """Terminal reports re-lock complete: residual near 0, rate damped."""
        self.x = np.array([0.0, 0.3*self.x[1]])
        self.P = np.diag([0.2**2 + 0.05, 0.09*self.P[1, 1] + 1e-4])

    # -- one control step ----------------------------------------------------
    def step(self, z):
        """z = measured residual (deg). Returns dict; 'relock' True => command it."""
        self.t += 1
        if self.pending > 0:
            self.pending -= 1
            if self.pending == 0:
                self.relock_landed()
                self.pending = -1
        # KF predict + update (cheap; run in both modes so status is comparable)
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        S = self.P[0, 0] + self.Rm
        K = self.P[:, 0] / S
        self.x = self.x + K*(z - self.x[0])
        self.P = self.P - np.outer(K, self.P[0])

        mu = float(self.FH[0] @ self.x)
        sd = float(np.sqrt(self.FH[0] @ self.P @ self.FH[0] + self.QH[0, 0]))
        p_exit = _norm_sf((self.r_max - mu)/sd) + _norm_sf((self.r_max + mu)/sd)
        idle = self.pending < 0
        if self.mode == "reactive":
            trig = idle and dE(z) > self.eps
        else:
            trig = idle and (p_exit > self.p_th or dE(self.x[0]) > self.eps)
        if trig:
            self.pending = self.lat
            self.relocks += 1
        self.last = dict(t=self.t, z=float(z), r_hat=float(self.x[0]),
                         rate_hat=float(self.x[1]), dE=float(dE(self.x[0])),
                         eps=float(self.eps), p_exit=float(p_exit),
                         in_corridor=bool(dE(self.x[0]) <= self.eps),
                         relocking=bool(not idle or trig), relock=bool(trig),
                         relocks=self.relocks)
        return self.last
