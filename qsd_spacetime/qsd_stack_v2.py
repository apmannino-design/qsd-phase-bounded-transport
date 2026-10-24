#!/usr/bin/env python3
"""
QSD covariance supervisor and Spacetime telemetry adapter.

Dependencies:
    pip install numpy
    pip install protobuf   # Only required for protobuf export.

Run:
    python qsd_stack.py test
    python qsd_stack.py simulate --seconds 10 --status state/status.json
    python qsd_stack.py telemetry --status state/status.json

Integration:
    Implement Terminal using your hardware driver.
    Instantiate Supervisor with provisioned Beam IDs.
    Call run(...).
    Supply generated ExportMetricsRequest and an authenticated RPC callable
    to export_metrics().

This module does not claim:
    - a physical energy decomposition,
    - ISS certification,
    - hard-real-time execution,
    - zero-loss network handover.

v2 upgrades (2026-10-24):
    1. Recoverable faults. Bad samples (stale, gapped, malformed, out of
       order) or command failures put the beam in DEGRADED: no actuator
       commands, DORMANT reported. After `recover_good_samples` consecutive
       good samples it re-validates from STARTUP automatically. FAULT latches
       only if the beam stays bad for `fault_latch_s` (a transient glitch no
       longer takes a beam offline permanently).
    2. Optional predictive offload (predict=True; OFF by default). A trend +
       vibration-envelope forecast of FSM position that can only make offloads
       earlier, never later; it needs no vibration frequency, restarts after
       steps and after every offload/relock, and never blocks recovery.
       Benchmark (bench_v2.py, equal offload budget, slews / slow + fast
       vibration / steps): no scenario showed a lock-time benefit, and it cost
       5-170% more offloads. Kept for evaluation on real terminal data only.
    3. Telemetry in two schemas: "repo_v1alpha" (github.com/aalyria/api main:
       demodulator_id / sinr_data_points / esn0_data_points) and
       "legacy_docs" (docs.spacetime.aalyria.com legacy data model:
       modem_id / link_metrics_data_points). Confirm with Aalyria which one a
       deployment uses.
    4. Threshold honesty. theta thresholds are calibration values. The
       pi/8 default equals a dominant-axis jitter RMS of r_eff * tan(pi/8)
       (about 6.2 urad at r_eff = 15 urad); it is a placeholder, not a
       physical constant. Calibrate from recorded terminal data.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import tempfile
import threading
import time
import unittest

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol

import numpy as np


# ---------------------------------------------------------------------------
# Configuration and hardware contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Beam:
    beam_id: str
    interface_id: str
    rx_modem_id: Optional[str] = None
    tx_modem_id: Optional[str] = None


@dataclass(frozen=True)
class Config:
    window: int = 50
    min_samples: int = 20

    # All telemetry channels must first be converted to equivalent angular
    # displacement in urad. For four native angular channels, use ones.
    channel_scale_to_urad: tuple = (1.0, 1.0, 1.0, 1.0)

    fsm_limits_urad: tuple = (100.0, 100.0)
    r_eff_urad: float = 15.0

    # Gates covariance shape with absolute fluctuation amplitude.
    shape_gate_rms_urad: float = 2.0
    shape_warn: float = 0.40
    shape_trip: float = 0.65
    shape_clear: float = 0.25

    # Calibration placeholders: theta >= theta_warn  <=>  dominant-axis jitter
    # RMS >= r_eff_urad * tan(theta_warn)  (~6.2 urad with these defaults).
    theta_warn: float = math.pi / 8
    theta_trip: float = 1.4 * math.pi / 8
    theta_clear: float = 0.6 * math.pi / 8

    headroom_warn: float = 0.20
    headroom_trip: float = 0.05
    headroom_clear: float = 0.35

    warn_hold_s: float = 0.015
    clear_hold_s: float = 0.050
    offload_interval_s: float = 0.250
    relock_timeout_s: float = 2.0

    max_sample_age_s: float = 0.050
    max_sample_gap_s: float = 0.050
    max_export_age_s: float = 1.0

    period_s: float = 0.001
    publish_period_s: float = 0.100

    # --- v2: recoverable fault handling ---
    degrade_after_bad_samples: int = 1     # report DORMANT / stop commands
    recover_good_samples: int = 50         # consecutive good samples to re-validate
    fault_latch_s: float = 5.0             # continuously bad this long -> latched FAULT

    # --- v2: fail-safe predictive offload ---
    predict: bool = False    # OFF by default: benchmark showed extra offloads, no lock benefit
    predict_window_s: float = 0.5          # trend fit window (covers vibration >= 2 Hz)
    predict_horizon_s: float = 0.050       # >= offload latency + margin
    predict_every: int = 5                 # recompute every N samples
    envelope_margin: float = 1.0           # multiplier on observed vibration envelope
    jump_sigma: float = 6.0                # residual / envelope ratio that flags a step

    # --- v2: telemetry schema ---
    telemetry_schema: str = "repo_v1alpha"  # or "legacy_docs"

    def __post_init__(self):
        m = len(self.channel_scale_to_urad)
        if m < 4:
            raise ValueError("At least four channels are required.")
        if not 3 <= self.min_samples <= self.window:
            raise ValueError("Require 3 <= min_samples <= window.")
        if not all(math.isfinite(x) and x > 0
                   for x in self.channel_scale_to_urad):
            raise ValueError("Channel conversion factors must be positive.")
        if len(self.fsm_limits_urad) != 2:
            raise ValueError("Exactly two FSM limits are required.")
        if not all(math.isfinite(x) and x > 0
                   for x in self.fsm_limits_urad):
            raise ValueError("FSM limits must be positive.")
        if not 0 <= self.shape_clear < self.shape_warn < self.shape_trip < 1 - 1/m:
            raise ValueError("Covariance-shape thresholds are invalid.")
        if not 0 <= self.headroom_trip < self.headroom_warn < self.headroom_clear <= 1:
            raise ValueError("Headroom thresholds are invalid.")
        if not 0 <= self.theta_clear < self.theta_warn < self.theta_trip:
            raise ValueError("Theta thresholds are invalid.")
        positive = (
            self.r_eff_urad, self.shape_gate_rms_urad,
            self.warn_hold_s, self.clear_hold_s,
            self.offload_interval_s, self.relock_timeout_s,
            self.max_sample_age_s, self.max_sample_gap_s,
            self.max_export_age_s, self.period_s,
            self.publish_period_s,
        )
        if not all(math.isfinite(x) and x > 0 for x in positive):
            raise ValueError("Timing and amplitude parameters must be positive.")
        if self.degrade_after_bad_samples < 1 or self.recover_good_samples < 1:
            raise ValueError("Fault sample counts must be >= 1.")
        v2_positive = (self.fault_latch_s, self.predict_window_s,
                       self.predict_horizon_s, self.envelope_margin, self.jump_sigma)
        if not all(math.isfinite(x) and x > 0 for x in v2_positive) or self.predict_every < 1:
            raise ValueError("v2 parameters must be positive.")
        if self.telemetry_schema not in ("repo_v1alpha", "legacy_docs"):
            raise ValueError("telemetry_schema must be 'repo_v1alpha' or 'legacy_docs'.")


@dataclass(frozen=True)
class Sample:
    # mono_s must use the same monotonic clock domain as time.monotonic().
    # Drivers must translate hardware timestamps into that domain.
    mono_s: float
    unix_s: float
    sequence: int
    channels: tuple
    locked: bool
    actuator_ready: bool

    # Supply calibrated measurements, never synthetic covariance proxies.
    sinr_db: Optional[float] = None
    esn0_db: Optional[float] = None


class Terminal(Protocol):
    def read(self, beam: Beam) -> Sample:
        """Return a fresh sample or raise. Driver must bound blocking time."""
        ...

    def offload(self, beam: Beam) -> None:
        """Start one asynchronous offload operation or raise on rejection."""
        ...

    def relock(self, beam: Beam) -> None:
        """Start one asynchronous relock operation or raise on rejection."""
        ...


# ---------------------------------------------------------------------------
# Covariance coordinates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Coordinates:
    ready: bool
    samples: int
    delta_j_urad2: float
    delta_l_urad2: float
    delta_x_urad2: float
    dE: float
    theta_rad: float
    total_rms_urad: float
    headroom: float
    predicted_headroom: float = 1.0   # v2: forecast worst-case headroom (<= headroom when predicting)


class HeadroomPredictor:
    """
    v2 fail-safe forecast of FSM headroom.

    Per FSM axis, fit level + slope over the last predict_window_s; the
    largest fit residual in the window is the vibration envelope. Worst-case
    position at the horizon = |level + slope * H| + margin * envelope.
    No vibration frequency is needed. A sample far outside the envelope
    (a step, or the FSM re-centring after an offload) restarts the window.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.limits = np.asarray(cfg.fsm_limits_urad, dtype=float)
        n = max(8, int(round(cfg.predict_window_s / cfg.period_s)))
        self.t = deque(maxlen=n)
        self.x = deque(maxlen=n)
        self.min_fit = n          # full window only: a partial window mistakes vibration for trend
        self.count = 0
        self.fit = None              # (t_ref, level[2], slope[2], envelope[2])
        self.last = 1.0
        self.jumps = 0

    def reset(self):
        self.t.clear(); self.x.clear(); self.fit = None; self.last = 1.0; self.count = 0

    def update(self, t: float, pos2) -> float:
        pos2 = np.asarray(pos2, dtype=float)
        floor = 0.02 * self.limits                      # 2 % of range: noise floor
        if self.fit is not None:
            t_ref, level, slope, env = self.fit
            expected = level + slope * (t - t_ref)
            if np.any(np.abs(pos2 - expected) > self.cfg.jump_sigma * np.maximum(env, floor)):
                self.t.clear(); self.x.clear(); self.fit = None; self.jumps += 1
        self.t.append(t); self.x.append(pos2)
        self.count += 1
        if len(self.t) < self.min_fit:
            self.fit = None
            self.last = 1.0                             # no forecast yet: defer to measured
            return self.last
        if self.fit is None or self.count % self.cfg.predict_every == 0:
            tt = np.asarray(self.t) - t
            xx = np.stack(self.x)
            A = np.stack([np.ones_like(tt), tt], axis=1)
            coef, *_ = np.linalg.lstsq(A, xx, rcond=None)
            level, slope = coef[0], coef[1]
            env = np.max(np.abs(xx - A @ coef), axis=0)
            self.fit = (t, level, slope, env)
            worst = (np.abs(level + slope * self.cfg.predict_horizon_s)
                     + self.cfg.envelope_margin * env)
            self.last = float(np.min(1.0 - worst / self.limits))
        return self.last


class TriDeltaCovarianceEstimator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rows = deque(maxlen=cfg.window)
        self.scale = np.asarray(cfg.channel_scale_to_urad, dtype=float)
        self.limits = np.asarray(cfg.fsm_limits_urad, dtype=float)
        self.predictor = HeadroomPredictor(cfg) if cfg.predict else None

    def reset(self):
        self.rows.clear()
        if self.predictor is not None:
            self.predictor.reset()

    def update(self, channels, t: Optional[float] = None) -> Coordinates:
        raw = np.asarray(channels, dtype=float)
        if raw.shape != self.scale.shape or not np.all(np.isfinite(raw)):
            raise ValueError("Invalid channel vector.")

        y = raw * self.scale
        headroom = float(np.min(1.0 - np.abs(y[:2]) / self.limits))
        predicted = headroom
        if self.predictor is not None and t is not None:
            # Fail-safe: the forecast can only LOWER headroom (earlier offload).
            predicted = min(headroom, self.predictor.update(t, y[:2]))
        self.rows.append(y.copy())
        n = len(self.rows)

        if n < 3:
            return Coordinates(
                False, n, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, headroom, predicted
            )

        data = np.stack(self.rows)
        centered = data - data.mean(axis=0)
        cov = centered.T @ centered / (n - 1)
        eig = np.maximum(np.linalg.eigvalsh(cov), 0.0)

        j = float(eig[-1])
        l = float(eig[:-1].sum())
        trace = j + l
        x = float(np.linalg.norm(cov - np.diag(np.diag(cov)), "fro"))
        dE = l / trace if trace > 0 else 0.0
        theta = math.atan2(math.sqrt(j), self.cfg.r_eff_urad)

        result = Coordinates(
            n >= self.cfg.min_samples,
            n, j, l, x, dE, theta, math.sqrt(trace), headroom, predicted
        )
        if not all(math.isfinite(v) for v in (
            j, l, x, dE, theta, result.total_rms_urad, headroom, predicted
        )):
            raise ValueError("Nonfinite covariance result.")
        return result


# ---------------------------------------------------------------------------
# Consecutive-time governor
# ---------------------------------------------------------------------------

class TriLockGovernor:
    """
    Regime 0: STARTUP
    Regime 1: LOCKED
    Regime 2: CORRIDOR
    Regime 3: BREAKOUT
    Regime 4: FAULT, latched until explicit reset (v2: only after fault_latch_s
              of continuously bad data, or a relock timeout)
    Regime 5: DEGRADED (v2): bad samples or command failure; no commands,
              DORMANT reported, auto-recovers via STARTUP re-validation

    OFFLOAD and RELOCK are command events, not persistent action labels.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.reset()

    def reset(self):
        self.regime = 0
        self.reason = "STARTUP"
        self.warn_since = None
        self.clear_since = None
        self.relock_started = None
        self.last_offload = -math.inf

    @staticmethod
    def _hold(condition, since, now, duration):
        if not condition:
            return None, False
        since = now if since is None else since
        return since, now - since >= duration

    def fault(self, reason):
        self.regime = 4
        self.reason = reason
        self.warn_since = self.clear_since = None

    def degrade(self, reason):
        """v2: recoverable fault; Supervisor re-validates after good samples."""
        self.regime = 5
        self.reason = "DEGRADED: " + reason
        self.warn_since = self.clear_since = None

    def step(self, c: Coordinates, sample: Sample, now: float):
        cfg = self.cfg
        commands = []

        if self.regime == 4:
            return commands

        shaped = c.total_rms_urad >= cfg.shape_gate_rms_urad
        # v2: offload decisions use the forecast (never later than measured);
        # trips and relocks stay on measured headroom only.
        early = min(c.headroom, c.predicted_headroom)

        warn = (
            early <= cfg.headroom_warn
            or c.theta_rad >= cfg.theta_warn
            or (shaped and c.dE >= cfg.shape_warn)
        )
        trip = (
            c.headroom <= cfg.headroom_trip
            or c.theta_rad >= cfg.theta_trip
            or (shaped and c.dE >= cfg.shape_trip)
        )
        healthy = (
            c.ready
            and sample.locked
            and sample.actuator_ready
            and c.headroom >= cfg.headroom_clear   # measured only: a forecast must never block recovery
            and c.theta_rad <= cfg.theta_clear
            and (not shaped or c.dE <= cfg.shape_clear)
        )

        if self.regime == 3:
            # Recovery requires fresh lock acknowledgment AND healthy signals.
            self.clear_since, done = self._hold(
                healthy, self.clear_since, now, cfg.clear_hold_s
            )
            if done:
                self.regime = 1
                self.reason = "RELOCK_CONFIRMED"
                self.relock_started = None
                self.clear_since = None
            elif now - self.relock_started >= cfg.relock_timeout_s:
                self.fault("RELOCK_TIMEOUT")
            return commands

        # Mechanical and lock-loss protection applies even during warm-up.
        if trip or not sample.locked or not sample.actuator_ready:
            self.regime = 3
            self.reason = "LIMIT_OR_LOCK_LOSS"
            self.relock_started = now
            self.warn_since = self.clear_since = None
            return ["RELOCK"]

        if self.regime == 0:
            self.clear_since, done = self._hold(
                healthy, self.clear_since, now, cfg.clear_hold_s
            )
            if done:
                self.regime = 1
                self.reason = "STARTUP_VALIDATED"
                self.clear_since = None
            return commands

        if self.regime == 1:
            self.warn_since, done = self._hold(
                warn, self.warn_since, now, cfg.warn_hold_s
            )
            if done:
                self.regime = 2
                self.reason = "PERSISTENT_WARNING"
                self.warn_since = None

        elif self.regime == 2:
            self.clear_since, done = self._hold(
                healthy, self.clear_since, now, cfg.clear_hold_s
            )
            if done:
                self.regime = 1
                self.reason = "CORRIDOR_CLEARED"
                self.clear_since = None

        if (self.regime == 2 and warn
                and now - self.last_offload >= cfg.offload_interval_s):
            commands.append("OFFLOAD")
            self.last_offload = now

        return commands

    @property
    def oper_status(self):
        if self.regime in (1, 2):
            return "IF_OPER_STATUS_UP"
        return "IF_OPER_STATUS_DORMANT"


# ---------------------------------------------------------------------------
# Per-beam validation and command lifecycle
# ---------------------------------------------------------------------------

def rfc3339(unix_s):
    return datetime.fromtimestamp(
        unix_s, timezone.utc
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")


class Supervisor:
    def __init__(self, beam: Beam, cfg: Config):
        self.beam = beam
        self.cfg = cfg
        self.estimator = TriDeltaCovarianceEstimator(cfg)
        self.governor = TriLockGovernor(cfg)
        self.last_sequence = None
        self.last_sample_mono = None
        self.last_status = {}
        self.bad_since = None
        self.bad_count = 0
        self.good_count = 0

    def reset_fault(self):
        """Call explicitly after inspection/recovery; not from a 1 kHz loop."""
        self.estimator.reset()
        self.governor.reset()
        self.last_sequence = None
        self.last_sample_mono = None
        self.bad_since = None
        self.bad_count = 0
        self.good_count = 0

    def tick(self, terminal: Terminal):
        c = None
        sample = None
        commands = []
        now = time.monotonic()
        observed_unix = time.time()
        good = False
        problem = None

        try:
            sample = terminal.read(self.beam)
            now = time.monotonic()

            # --- format checks: a malformed sample is dropped entirely ---
            if not isinstance(sample, Sample):
                raise ValueError("Driver returned an invalid sample type.")
            if not all(math.isfinite(x) for x in
                       (sample.mono_s, sample.unix_s)):
                raise ValueError("Invalid timestamp.")
            if type(sample.locked) is not bool:
                raise ValueError("Invalid lock acknowledgment.")
            if type(sample.actuator_ready) is not bool:
                raise ValueError("Invalid actuator acknowledgment.")
            if type(sample.sequence) is not int:
                raise ValueError("Invalid sample sequence.")
            if (self.last_sequence is not None
                    and sample.sequence <= self.last_sequence):
                raise ValueError("Non-increasing sample sequence.")
            for value in (sample.sinr_db, sample.esn0_db):
                if value is not None and not math.isfinite(value):
                    raise ValueError("Invalid measured modem metric.")
            raw = np.asarray(sample.channels, dtype=float)
            if raw.shape != self.estimator.scale.shape or not np.all(np.isfinite(raw)):
                raise ValueError("Invalid channel vector.")

            # --- continuity checks: well-formed but stale/gapped (v2) ---
            # Bookkeeping advances so the NEXT sample is judged on its own
            # merits; the stale covariance window is discarded.
            age = now - sample.mono_s
            gap = (None if self.last_sample_mono is None
                   else sample.mono_s - self.last_sample_mono)
            self.last_sequence = sample.sequence
            self.last_sample_mono = sample.mono_s
            if age < 0 or age > self.cfg.max_sample_age_s:
                problem = "Stale or future monotonic timestamp."
            elif abs(time.time() - sample.unix_s) > self.cfg.max_sample_age_s:
                problem = "Invalid wall-clock timestamp."
            elif gap is not None and (gap <= 0 or gap > self.cfg.max_sample_gap_s):
                problem = "Sample gap out of range."
            if problem is not None:
                self.estimator.reset()
                raise ValueError(problem)

            observed_unix = sample.unix_s
            c = self.estimator.update(sample.channels, sample.mono_s)
            good = True

            if self.governor.regime == 5:
                # v2: recovering; keep estimator warm, issue no commands.
                self.good_count += 1
                if self.good_count >= self.cfg.recover_good_samples:
                    self.governor.reset()
                    self.governor.reason = "RECOVERED_REVALIDATING"
            elif self.governor.regime != 4:
                commands = self.governor.step(c, sample, now)
                for command in commands:
                    if command == "OFFLOAD":
                        terminal.offload(self.beam)
                    elif command == "RELOCK":
                        terminal.relock(self.beam)
                    # v2: an offload/relock moves the FSM; history from before
                    # it would corrupt the trend fit. Forecast restarts (and
                    # defers to measured headroom until its window refills).
                    if self.estimator.predictor is not None:
                        self.estimator.predictor.reset()

            self.bad_since = None
            self.bad_count = 0

        except Exception as exc:
            # Do not issue blind actuator commands on unknown/stale state.
            good = False
            commands = []
            self.good_count = 0
            self.bad_count += 1
            if self.bad_since is None:
                self.bad_since = now
            reason = f"{type(exc).__name__}: {exc}"
            if self.governor.regime != 4:
                if now - self.bad_since >= self.cfg.fault_latch_s:
                    self.governor.fault("PERSISTENT_" + reason)
                elif self.bad_count >= self.cfg.degrade_after_bad_samples:
                    self.governor.degrade(reason)

        valid = good and c is not None and self.governor.regime != 4

        status = {
            "beam_id": self.beam.beam_id,
            "interface_id": self.beam.interface_id,
            "rx_modem_id": self.beam.rx_modem_id,
            "tx_modem_id": self.beam.tx_modem_id,
            "time": rfc3339(observed_unix),
            "published_unix_s": time.time(),
            "sample_unix_s": observed_unix if valid else None,
            "sample_valid": valid,
            "regime": self.governor.regime,
            "reason": self.governor.reason,
            "oper_status": self.governor.oper_status,
            "command_events": commands,
            "coordinates": asdict(c) if c is not None else None,
            "sinr_db": sample.sinr_db if valid else None,
            "esn0_db": sample.esn0_db if valid else None,
        }
        self.last_status = status
        return status


# ---------------------------------------------------------------------------
# Atomic, asynchronous publication
# ---------------------------------------------------------------------------

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class StatusPublisher:
    def __init__(self, path, period_s):
        self.path = path
        self.period_s = period_s
        self.lock = threading.Lock()
        self.latest = None
        self.error = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._worker, daemon=True)

    def start(self):
        self.thread.start()

    def submit(self, status):
        with self.lock:
            self.latest = copy.deepcopy(status)

    def _worker(self):
        while not self.stop_event.wait(self.period_s):
            self._flush()

    def _flush(self):
        with self.lock:
            latest = self.latest
        if latest is not None:
            try:
                atomic_json(self.path, latest)
                self.error = None
            except Exception as exc:
                self.error = repr(exc)

    def close(self):
        self.stop_event.set()
        self.thread.join()
        self._flush()


def run(terminal, beams, cfg, status_path, seconds=None, stop_event=None):
    if not beams:
        raise ValueError("At least one beam is required.")
    if len({b.beam_id for b in beams}) != len(beams):
        raise ValueError("Duplicate beam IDs.")
    if len({b.interface_id for b in beams}) != len(beams):
        raise ValueError(
            "This reference implementation requires one beam per interface."
        )

    stop_event = stop_event or threading.Event()
    supervisors = [Supervisor(b, cfg) for b in beams]
    publisher = StatusPublisher(status_path, cfg.publish_period_s)
    publisher.start()

    started = time.monotonic()
    deadline = started
    iterations = missed = 0
    max_execution_s = 0.0
    max_start_lateness_s = 0.0

    try:
        while not stop_event.is_set():
            now = time.monotonic()
            if seconds is not None and now - started >= seconds:
                break

            remaining = deadline - now
            if remaining > 0 and stop_event.wait(remaining):
                break

            tick_start = time.monotonic()
            max_start_lateness_s = max(
                max_start_lateness_s, tick_start - deadline
            )

            states = {
                s.beam.beam_id: s.tick(terminal) for s in supervisors
            }

            execution = time.monotonic() - tick_start
            max_execution_s = max(max_execution_s, execution)
            iterations += 1

            deadline += cfg.period_s
            finished = time.monotonic()
            if finished > deadline:
                skipped = int((finished - deadline) // cfg.period_s) + 1
                missed += skipped
                deadline += skipped * cfg.period_s

            publisher.submit({
                "schema_version": 1,
                "published_unix_s": time.time(),
                "beams": states,
                "timing": {
                    "iterations": iterations,
                    "missed_schedule_slots": missed,
                    "max_execution_s": max_execution_s,
                    "max_start_lateness_s": max_start_lateness_s,
                    "publisher_error": publisher.error,
                },
            })
    finally:
        # Avoid leaving a cleanly stopped supervisor advertising UP.
        stopped_at = time.time()
        states = {}
        for s in supervisors:
            state = dict(s.last_status)
            state.update({
                "interface_id": s.beam.interface_id,
                "regime": 4,
                "reason": "SUPERVISOR_STOPPED",
                "oper_status": "IF_OPER_STATUS_DORMANT",
                "time": rfc3339(stopped_at),
                "sample_valid": False,
                "sinr_db": None,
                "esn0_db": None,
            })
            states[s.beam.beam_id] = state
        publisher.submit({
            "schema_version": 1,
            "published_unix_s": stopped_at,
            "beams": states,
        })
        publisher.close()


# ---------------------------------------------------------------------------
# Spacetime request construction and typed export
# ---------------------------------------------------------------------------

def build_export_request(snapshot, max_age_s=1.0, now_unix=None,
                         schema="repo_v1alpha"):
    """
    Return a protobuf-JSON-compatible dictionary.

    schema="repo_v1alpha": github.com/aalyria/api main
        ModemMetrics{demodulator_id, sinr_data_points[], esn0_data_points[]},
        each point {time, modulator_id, sinr_db | esn0_db}.
    schema="legacy_docs": docs.spacetime.aalyria.com (legacy data model)
        ModemMetrics{modem_id, link_metrics_data_points[]},
        each point {time, tx_modem_id, sinr_db?, esn0_db?}.

    Covariance diagnostics remain in local status/custom telemetry.
    Only actual calibrated measurements enter SINR and Es/N0 fields.
    """
    now = time.time() if now_unix is None else now_unix
    published = snapshot.get("published_unix_s")
    globally_fresh = (
        isinstance(published, (int, float))
        and math.isfinite(published)
        and 0 <= now - published <= max_age_s
    )
    request = {"interface_metrics": [], "modem_metrics": []}
    interfaces = set()

    for _, state in sorted(snapshot.get("beams", {}).items()):
        interface_id = state["interface_id"]
        if interface_id in interfaces:
            raise ValueError("Duplicate interface requires aggregation policy.")
        interfaces.add(interface_id)

        stamp = state.get("sample_unix_s")
        fresh = (
            globally_fresh
            and state.get("sample_valid") is True
            and isinstance(stamp, (int, float))
            and math.isfinite(stamp)
            and 0 <= now - stamp <= max_age_s
        )

        operational = (
            state.get("oper_status", "IF_OPER_STATUS_DORMANT")
            if fresh else "IF_OPER_STATUS_DORMANT"
        )

        request["interface_metrics"].append({
            "interface_id": interface_id,
            "operational_state_data_points": [{
                "time": state["time"] if fresh else rfc3339(now),
                "value": operational,
            }],
        })

        rx = state.get("rx_modem_id")
        tx = state.get("tx_modem_id")
        if not fresh or not rx or not tx:
            continue

        measured = {}
        for field in ("sinr_db", "esn0_db"):
            value = state.get(field)
            if value is not None:
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError(f"Invalid {field}.")
                measured[field] = value
        if not measured:
            continue

        if schema == "legacy_docs":
            point = {"time": state["time"], "tx_modem_id": tx, **measured}
            request["modem_metrics"].append({
                "modem_id": rx,
                "link_metrics_data_points": [point],
            })
        elif schema == "repo_v1alpha":
            entry = {"demodulator_id": rx}
            if "sinr_db" in measured:
                entry["sinr_data_points"] = [{"time": state["time"],
                    "modulator_id": tx, "sinr_db": measured["sinr_db"]}]
            if "esn0_db" in measured:
                entry["esn0_data_points"] = [{"time": state["time"],
                    "modulator_id": tx, "esn0_db": measured["esn0_db"]}]
            request["modem_metrics"].append(entry)
        else:
            raise ValueError(f"Unknown telemetry schema: {schema}")

    if not request["interface_metrics"]:
        raise ValueError("No provisioned interfaces to export.")
    return request


def export_metrics(
    snapshot,
    request_class,
    authenticated_export_rpc: Callable,
    max_age_s=1.0,
    timeout_s=2.0,
    schema="repo_v1alpha",
):
    """
    schema:
        "repo_v1alpha" or "legacy_docs"; must match the deployment's protos.

    request_class:
        Your deployed generated ExportMetricsRequest class.

    authenticated_export_rpc:
        Your configured stub.ExportMetrics callable, including whatever
        credentials/metadata your deployment requires.

    Unknown fields fail validation rather than being silently ignored.
    """
    from google.protobuf.json_format import ParseDict

    payload = build_export_request(snapshot, max_age_s=max_age_s, schema=schema)
    message = ParseDict(
        payload, request_class(), ignore_unknown_fields=False
    )
    return authenticated_export_rpc(message, timeout=timeout_s)


# ---------------------------------------------------------------------------
# Demonstration hardware
# ---------------------------------------------------------------------------

class SimulatedTerminal:
    """Demonstration only; not a physical link or modem model."""

    def __init__(self):
        self.rng = np.random.default_rng(7)
        self.started = time.monotonic()
        self.sequence = 0
        self.bias = 0.0
        self.locked_after = 0.0
        self.offload_commands = 0
        self.relock_commands = 0

    def read(self, beam):
        now = time.monotonic()
        elapsed = now - self.started
        self.sequence += 1

        self.bias += 0.015
        fsm = self.rng.normal(0, 0.2, 2) + [self.bias, 0.0]
        quad = self.rng.normal(0, 0.1, 2)
        locked = now >= self.locked_after

        # Introduce one simulated loss-of-lock interval.
        if 4.0 <= elapsed < 4.1:
            locked = False

        return Sample(
            mono_s=now,
            unix_s=time.time(),
            sequence=self.sequence,
            channels=tuple(np.concatenate([fsm, quad])),
            locked=bool(locked),
            actuator_ready=True,
            # No invented modem measurements.
        )

    def offload(self, beam):
        self.offload_commands += 1
        self.bias *= 0.25

    def relock(self, beam):
        self.relock_commands += 1
        self.locked_after = time.monotonic() + 0.15
        self.bias = 0.0


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

class Tests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def coords(self, **changes):
        values = dict(
            ready=True, samples=50,
            delta_j_urad2=0.01,
            delta_l_urad2=0.01,
            delta_x_urad2=0.0,
            dE=0.5,
            theta_rad=0.01,
            total_rms_urad=0.14,
            headroom=0.9,
        )
        values.update(changes)
        return Coordinates(**values)

    def sample(self):
        return Sample(0.0, 0.0, 1, (0, 0, 0, 0), True, True)

    def test_constant_limit_detected_despite_zero_covariance(self):
        estimator = TriDeltaCovarianceEstimator(self.cfg)
        for _ in range(50):
            c = estimator.update([100, 0, 0, 0])
        self.assertEqual(c.delta_j_urad2, 0)
        self.assertEqual(c.headroom, 0)
        governor = TriLockGovernor(self.cfg)
        self.assertEqual(governor.step(c, self.sample(), 0), ["RELOCK"])

    def test_shape_bound(self):
        estimator = TriDeltaCovarianceEstimator(self.cfg)
        rng = np.random.default_rng(1)
        for _ in range(200):
            c = estimator.update(rng.normal(size=4))
            self.assertLessEqual(c.dE, 0.75 + 1e-12)

    def test_relock_is_one_shot(self):
        governor = TriLockGovernor(self.cfg)
        c = self.coords(headroom=0)
        self.assertEqual(governor.step(c, self.sample(), 0), ["RELOCK"])
        self.assertEqual(governor.step(c, self.sample(), 0.01), [])
        self.assertEqual(governor.regime, 3)

    def test_low_amplitude_shape_does_not_warn(self):
        governor = TriLockGovernor(self.cfg)
        governor.regime = 1
        c = self.coords(dE=0.75, total_rms_urad=0.1)
        for i in range(100):
            governor.step(c, self.sample(), i * 0.001)
        self.assertEqual(governor.regime, 1)

    def test_warning_requires_consecutive_time(self):
        governor = TriLockGovernor(self.cfg)
        governor.regime = 1
        warning = self.coords(headroom=0.1)
        healthy = self.coords()
        governor.step(warning, self.sample(), 0)
        governor.step(healthy, self.sample(), 0.010)
        governor.step(warning, self.sample(), 0.020)
        self.assertEqual(governor.regime, 1)
        events = governor.step(warning, self.sample(), 0.036)
        self.assertEqual(governor.regime, 2)
        self.assertEqual(events, ["OFFLOAD"])

    def test_invalid_sample_degrades_not_latches(self):
        class BadTerminal:
            def read(self, beam):
                return Sample(
                    time.monotonic(), time.time(), 1,
                    (float("nan"), 0, 0, 0), True, True
                )
        supervisor = Supervisor(Beam("b", "i"), self.cfg)
        status = supervisor.tick(BadTerminal())
        self.assertEqual(status["regime"], 5)          # DEGRADED, recoverable
        self.assertFalse(status["sample_valid"])
        self.assertEqual(status["oper_status"], "IF_OPER_STATUS_DORMANT")

    # ---- v2 tests (simulated clock) ----
    class _Clock:
        def __init__(self): self.t = 100.0
        def monotonic(self): return self.t
        def time(self): return 1.7e9 + self.t
        def sleep(self, s): self.t += s

    class _GoodTerminal:
        def __init__(self, clock): self.clock, self.seq = clock, 0
        def read(self, beam):
            self.seq += 1
            return Sample(self.clock.monotonic(), self.clock.time(), self.seq,
                          (1.0, -1.0, 0.1, 0.1), True, True)
        def offload(self, beam): pass
        def relock(self, beam): pass

    def _run(self, sup, term, clock, steps, gap_at=None, stale=False):
        regimes = []
        for k in range(steps):
            clock.sleep(0.001 + (0.060 if k == gap_at else 0.0))
            if stale:
                orig = term.read
                smp = orig(None)
                term.read = lambda beam, s=smp: Sample(s.mono_s - 1.0, s.unix_s, s.sequence,
                                                      s.channels, True, True)
                st = sup.tick(term); term.read = orig
            else:
                st = sup.tick(term)
            regimes.append(st["regime"])
        return regimes

    def test_transient_gap_recovers(self):
        import unittest.mock as mock
        clock = self._Clock()
        with mock.patch(__name__ + ".time", clock):
            sup = Supervisor(Beam("b", "i"), self.cfg)
            term = self._GoodTerminal(clock)
            r = self._run(sup, term, clock, 600, gap_at=200)
        self.assertEqual(r[199], 1)
        self.assertEqual(r[200], 5)                      # glitch -> DEGRADED
        self.assertNotIn(4, r)                           # never latched
        self.assertEqual(r[-1], 1)                       # back to LOCKED

    def test_persistent_bad_data_latches(self):
        import unittest.mock as mock
        clock = self._Clock()
        cfg = Config(fault_latch_s=0.5)
        with mock.patch(__name__ + ".time", clock):
            sup = Supervisor(Beam("b", "i"), cfg)
            r = self._run(sup, self._GoodTerminal(clock), clock, 800, stale=True)
        self.assertEqual(r[10], 5)
        self.assertEqual(r[-1], 4)                       # latched after 0.5 s bad

    def test_forecast_never_later_than_measured(self):
        est = TriDeltaCovarianceEstimator(Config(predict=True))
        rng = np.random.default_rng(3)
        for k in range(2000):
            t = k * 0.001
            pos = 60 * np.sin(2 * np.pi * 1.3 * t) + rng.normal(0, 2, 2)
            c = est.update((pos[0], pos[1], 0.0, 0.0), t)
            self.assertLessEqual(c.predicted_headroom, c.headroom + 1e-12)

    def test_forecast_warns_earlier_on_ramp(self):
        est = TriDeltaCovarianceEstimator(Config(predict=True))
        first_pred = first_meas = None
        for k in range(3000):
            t = k * 0.001
            x = 40.0 * t                                  # 40 urad/s toward the 100 urad limit
            c = est.update((x, 0.0, 0.0, 0.0), t)
            if first_pred is None and c.predicted_headroom <= self.cfg.headroom_warn:
                first_pred = t
            if first_meas is None and c.headroom <= self.cfg.headroom_warn:
                first_meas = t
        self.assertLess(first_pred, first_meas)
        self.assertAlmostEqual(first_meas - first_pred,
                               self.cfg.predict_horizon_s, delta=0.01)

    def test_jump_restarts_forecast(self):
        p = HeadroomPredictor(self.cfg)
        for k in range(600):
            p.update(k * 0.001, (10.0, 0.0))
        p.update(0.6, (60.0, 0.0))
        self.assertEqual(p.jumps, 1)

    def test_both_telemetry_schemas(self):
        snap = {"published_unix_s": 10, "beams": {"b": {
            "interface_id": "i", "time": rfc3339(10), "sample_unix_s": 10,
            "sample_valid": True, "oper_status": "IF_OPER_STATUS_UP",
            "rx_modem_id": "rx", "tx_modem_id": "tx", "sinr_db": 18.0, "esn0_db": 12.0}}}
        repo = build_export_request(snap, now_unix=10, schema="repo_v1alpha")
        mm = repo["modem_metrics"][0]
        self.assertEqual(mm["demodulator_id"], "rx")
        self.assertEqual(mm["sinr_data_points"][0]["modulator_id"], "tx")
        self.assertEqual(mm["esn0_data_points"][0]["esn0_db"], 12.0)
        legacy = build_export_request(snap, now_unix=10, schema="legacy_docs")
        lp = legacy["modem_metrics"][0]["link_metrics_data_points"][0]
        self.assertEqual((lp["tx_modem_id"], lp["sinr_db"]), ("tx", 18.0))

    def test_stale_export_is_dormant(self):
        snapshot = {
            "published_unix_s": 1,
            "beams": {
                "b": {
                    "interface_id": "i",
                    "time": rfc3339(1),
                    "sample_unix_s": 1,
                    "sample_valid": True,
                    "oper_status": "IF_OPER_STATUS_UP",
                    "rx_modem_id": "rx",
                    "tx_modem_id": "tx",
                    "sinr_db": 20.0,
                }
            },
        }
        request = build_export_request(snapshot, now_unix=10)
        point = request["interface_metrics"][0][
            "operational_state_data_points"
        ][0]
        self.assertEqual(point["value"], "IF_OPER_STATUS_DORMANT")
        self.assertEqual(request["modem_metrics"], [])

    def test_no_synthetic_modem_metrics(self):
        snapshot = {
            "published_unix_s": 10,
            "beams": {
                "b": {
                    "interface_id": "i",
                    "time": rfc3339(10),
                    "sample_unix_s": 10,
                    "sample_valid": True,
                    "oper_status": "IF_OPER_STATUS_UP",
                    "rx_modem_id": "rx",
                    "tx_modem_id": "tx",
                    "sinr_db": None,
                    "esn0_db": None,
                }
            },
        }
        request = build_export_request(snapshot, now_unix=10)
        self.assertEqual(request["modem_metrics"], [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["test", "simulate", "telemetry"])
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--status", default="state/status.json")
    parser.add_argument("--schema", default="repo_v1alpha",
                        choices=["repo_v1alpha", "legacy_docs"])
    args = parser.parse_args()

    if args.mode == "test":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.mode == "simulate":
        terminal = SimulatedTerminal()
        beam = Beam(
            beam_id="demo-beam",
            interface_id="demo-interface",
            rx_modem_id="demo-rx",
            tx_modem_id="demo-tx",
        )
        try:
            run(
                terminal, [beam], Config(),
                args.status, seconds=args.seconds
            )
        except KeyboardInterrupt:
            pass
        print(json.dumps({
            "offload_commands": terminal.offload_commands,
            "relock_commands": terminal.relock_commands,
        }, indent=2))
        return 0

    with open(args.status) as stream:
        snapshot = json.load(stream)
    payload = build_export_request(snapshot, schema=args.schema)
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
