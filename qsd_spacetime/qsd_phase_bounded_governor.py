#!/usr/bin/env python3
"""
Compatibility facade: PhaseBoundedTransportGovernor.

Wraps qsd_stack_v2 TriDeltaCovarianceEstimator + TriLockGovernor behind a
simple update(channels) → status-dict API used by the Aalyria×QSD full-suite
validation harness. Production Spacetime deploy path remains qsd_daemon +
qsd_stack_v2 Supervisor; this module is for demos and harnesses.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

import qsd_stack_v2 as stack


class PhaseBoundedTransportGovernor:
    """Four-channel FSM/quad residual → tri-ΔE coordinates + tri-lock regimes."""

    def __init__(
        self,
        window_size: int = 40,
        n_channels: int = 4,
        r_eff_urad: float = 15.0,
        de_low: float = 0.25,
        de_high: float = 0.75,
        theta_crit: float = math.pi / 8,
        de_c: float = 0.85,
        eta_max: float = 0.985,
        dwell_steps: int = 10,
        period_s: float = 0.005,
        fsm_limits_urad=(100.0, 100.0),
    ):
        if n_channels < 4:
            raise ValueError("n_channels must be >= 4")
        scale = tuple(1.0 for _ in range(n_channels))
        # Map legacy dwell / threshold knobs onto stack_v2 consecutive-time holds.
        warn_hold_s = max(period_s, dwell_steps * period_s * 0.3)
        clear_hold_s = max(period_s, dwell_steps * period_s)
        self.cfg = stack.Config(
            window=window_size,
            min_samples=min(20, window_size),
            channel_scale_to_urad=scale,
            fsm_limits_urad=tuple(fsm_limits_urad),
            r_eff_urad=r_eff_urad,
            shape_clear=de_low,
            shape_warn=min(de_high, 0.64),
            shape_trip=min(max(de_c, de_high + 0.05), 0.74),
            theta_warn=theta_crit,
            # Wider trip than production 1.4× so a secular slew can dwell in
            # CORRIDOR (regime 2 / OFFLOAD) without immediately BREAKOUT-tripping.
            theta_trip=max(1.4 * theta_crit, 1.15),
            theta_clear=0.6 * theta_crit,
            warn_hold_s=warn_hold_s,
            clear_hold_s=clear_hold_s,
            period_s=period_s,
            offload_interval_s=max(period_s, 0.05),
            predict=False,
        )
        self.eta_max = float(eta_max)
        self.period_s = float(period_s)
        self.estimator = stack.TriDeltaCovarianceEstimator(self.cfg)
        self.governor = stack.TriLockGovernor(self.cfg)
        self.t = 0.0
        self.seq = 0
        self.total_relocks = 0
        self._last_action = "HOLD"
        self._last_coords: Optional[stack.Coordinates] = None

    def reset(self):
        self.estimator.reset()
        self.governor.reset()
        self.t = 0.0
        self.seq = 0
        self.total_relocks = 0
        self._last_action = "HOLD"
        self._last_coords = None

    def update(self, channels) -> dict:
        meas = np.asarray(channels, dtype=float).reshape(-1)
        n = len(self.cfg.channel_scale_to_urad)
        if meas.size < n:
            meas = np.pad(meas, (0, n - meas.size))
        elif meas.size > n:
            meas = meas[:n]

        self.seq += 1
        self.t += self.period_s
        coords = self.estimator.update(meas, t=self.t)
        self._last_coords = coords

        # Light / lock proxy: treat extreme channel magnitudes as unlocked only
        # when clearly past the FSM mechanical limit (breakout path uses trip).
        locked = bool(np.all(np.isfinite(meas)))
        sample = stack.Sample(
            mono_s=self.t,
            unix_s=1.7e9 + self.t,
            sequence=self.seq,
            channels=tuple(float(x) for x in meas),
            locked=locked,
            actuator_ready=True,
        )
        commands = self.governor.step(coords, sample, self.t)

        action = "HOLD"
        if "RELOCK" in commands:
            action = "TRIGGER_HARD_RELOCK"
            self.total_relocks += 1
        elif "OFFLOAD" in commands:
            action = "OFFLOAD_FSM_TO_COARSE_GIMBAL"
        elif self.governor.regime == 3:
            action = "TRIGGER_HARD_RELOCK"
        elif self.governor.regime == 2:
            action = "OFFLOAD_FSM_TO_COARSE_GIMBAL"
        self._last_action = action

        # Dimensionless lock-quality proxies for harness / demos (not exported
        # to Spacetime). Lambda ~ coherence (1 − dE); eta ~ remaining headroom.
        lam = float(max(0.0, min(1.0, 1.0 - coords.dE)))
        eta = float(max(0.0, min(self.eta_max, max(0.0, coords.headroom))))
        if coords.ready and self.governor.regime in (1, 2) and not self.governor.coasting:
            # Nominal locked tracking keeps η near eta_max when headroom is high.
            eta = max(eta, min(self.eta_max, 0.90 + 0.10 * lam))

        return {
            "regime": int(self.governor.regime),
            "reason": self.governor.reason,
            "action": action,
            "oper_status": self.governor.oper_status,
            "dE": float(coords.dE),
            "Lambda": lam,
            "theta_rad": float(coords.theta_rad),
            "delta_j": float(coords.delta_j_urad2),
            "delta_l": float(coords.delta_l_urad2),
            "delta_x": float(coords.delta_x_urad2),
            "eta": eta,
            "headroom": float(coords.headroom),
            "total_relocks": int(self.total_relocks),
            "commands": list(commands),
            "t": self.t,
        }
