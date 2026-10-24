#!/usr/bin/env python3
"""Asserting tests for qsd_stack_v2 (gap robustness + forecast-off default).

Longer equal-budget sweeps live in bench_qsd_stack_v2.py (benchmark, not CI gate).
"""
import math
import time
import unittest

import numpy as np

import qsd_stack_v2 as q


class Clock:
    def __init__(self):
        self.t = 1000.0
    def monotonic(self):
        return self.t
    def time(self):
        return 1.7e9 + self.t
    def sleep(self, s):
        self.t += s


class MirrorPlant:
    def __init__(self, seed, rate_walk=0.2):
        self.rng = np.random.default_rng(seed)
        self.x = np.zeros(2)
        self.v = self.rng.normal(0, 10, 2)
        self.seq = 0
        self.pending = None
        self.lost_until = -1.0
        self.cur = (np.zeros(2), False)

    def step(self, clk):
        t = clk.monotonic()
        if self.pending is not None and t >= self.pending:
            self.x[:] = 0.0
            self.pending = None
        self.v = np.clip(self.v + self.rng.normal(0, 0.2, 2), -50, 50)
        self.x += self.v * 0.001
        sat = bool(np.any(np.abs(self.x) >= 100))
        self.cur = (self.x.copy(), sat)
        return self.cur

    def read(self, beam):
        pos, _ = self.cur
        self.seq += 1
        clk = q.time
        return q.Sample(
            clk.monotonic(), clk.time(), self.seq,
            tuple(np.concatenate([pos, self.rng.normal(0, 0.2, 2)])),
            bool(clk.monotonic() >= self.lost_until), True,
        )

    def offload(self, beam):
        self.pending = q.time.monotonic() + 0.02

    def relock(self, beam):
        self.lost_until = q.time.monotonic() + 0.05
        self.pending = q.time.monotonic() + 0.02


class StackV2Tests(unittest.TestCase):
    def setUp(self):
        self.clk = Clock()
        self._real_time = q.time
        q.time = self.clk

    def tearDown(self):
        q.time = self._real_time

    def test_config_predict_defaults_off(self):
        self.assertFalse(q.Config().predict)

    def test_brief_gap_does_not_latch_fault(self):
        """60 ms gap mid-run must not latch FAULT (regime 4)."""
        plant = MirrorPlant(1)
        beam = q.Beam("b0", "i0")
        cfg = q.Config(
            max_sample_gap_s=0.030,
            max_sample_age_s=0.050,
            fault_latch_s=5.0,
            degrade_after_bad_samples=1,
            recover_good_samples=20,
            period_s=0.001,
            publish_period_s=0.1,
            shape_gate_rms_urad=1e9,
            theta_warn=10.0,
            theta_trip=11.0,
            theta_clear=9.0,
        )
        sup = q.Supervisor(beam, cfg)
        latched = None
        for k in range(5000):  # 5 s
            if k == 3000:
                self.clk.t += 0.060  # 60 ms gap > max_sample_gap_s
            plant.step(self.clk)
            st = sup.tick(plant)
            if st["regime"] == 4 and latched is None:
                latched = st["reason"]
            self.clk.sleep(0.001)
        self.assertIsNone(latched, f"unexpected latched FAULT: {latched}")
        self.assertIn(sup.governor.regime, (0, 1, 2, 3, 5))

    def test_persistent_bad_data_can_latch(self):
        beam = q.Beam("b0", "i0")
        cfg = q.Config(
            fault_latch_s=0.05,
            degrade_after_bad_samples=1,
            max_sample_age_s=0.01,
            period_s=0.001,
        )
        sup = q.Supervisor(beam, cfg)

        class BadTerm:
            def read(self, beam):
                raise RuntimeError("sensor down")
            def offload(self, beam):
                pass
            def relock(self, beam):
                pass

        term = BadTerm()
        for _ in range(80):
            st = sup.tick(term)
            self.clk.sleep(0.001)
        self.assertEqual(st["regime"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
