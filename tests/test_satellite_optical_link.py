"""Unit tests for the satellite optical-link prototype.

Run:  python -m unittest tests.test_satellite_optical_link
  or: python -m pytest tests/test_satellite_optical_link.py -q
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG
from aurora_qsd.core.iss import contraction_rate, iss_bound
from aurora_qsd.core.phase_potential import phase_force, phase_potential
from aurora_qsd.optical.channel import (
    GaussianBeam,
    TerminalSpec,
    atmospheric_transmittance,
    link_budget,
    pointing_loss,
)
from aurora_qsd.optical.constants import WAVELENGTH_C_BAND
from aurora_qsd.optical.modem import Modulation, bit_error_rate, flip_bits
from aurora_qsd.optical.orbits import circular_orbit, intersat_geometry, sample_geometry
from aurora_qsd.optical.pat import PATPlant, PIDController, QSDISSController, colored_jitter
from aurora_qsd.optical.simulate import ScenarioName, run_scenario
from aurora_qsd.optical.terminal import OpticalTerminal


class TestCoreIdentity(unittest.TestCase):
    def test_theta_star_is_pi_over_8(self):
        self.assertAlmostEqual(THETA_STAR, math.pi / 8, places=12)
        self.assertAlmostEqual(THETA_STAR_DEG, 22.5, places=10)

    def test_force_vanishes_at_well(self):
        self.assertLess(abs(phase_force(THETA_STAR)), 1e-9)

    def test_iss_bound_contracts(self):
        b0 = iss_bound(0.1, 0, 0.85, 0.0)
        b10 = iss_bound(0.1, 10, 0.85, 0.0)
        self.assertGreater(b0, b10)
        self.assertGreater(contraction_rate(0.85), 0.0)


class TestOrbits(unittest.TestCase):
    def test_leo_period_near_96_min(self):
        orb = circular_orbit(550.0)
        self.assertGreater(orb.period_s, 90 * 60)
        self.assertLess(orb.period_s, 100 * 60)

    def test_isl_range_for_20deg_offset(self):
        tx = circular_orbit(550.0, arg_lat0_deg=0.0)
        rx = circular_orbit(550.0, arg_lat0_deg=20.0)
        geo = intersat_geometry(tx, rx, 0.0, WAVELENGTH_C_BAND)
        # 2 a sin(10°) ≈ 2400 km
        self.assertGreater(geo.range_m, 2.0e6)
        self.assertLess(geo.range_m, 3.0e6)

    def test_downlink_near_zenith(self):
        geos = sample_geometry("downlink", np.array([0.0]), WAVELENGTH_C_BAND)
        self.assertGreater(geos[0].elevation_deg, 80.0)
        self.assertLess(geos[0].range_m, 600e3)

    def test_orbit_on_sphere(self):
        orb = circular_orbit(400.0)
        r, v = orb.position_velocity(12.3)
        self.assertAlmostEqual(np.linalg.norm(r), orb.radius_m, places=3)
        # circular: r · v ≈ 0
        self.assertLess(abs(np.dot(r, v)) / (np.linalg.norm(r) * np.linalg.norm(v)), 1e-6)


class TestChannel(unittest.TestCase):
    def test_pointing_loss_unity_on_boresight(self):
        self.assertAlmostEqual(pointing_loss(0.0, 12e-6), 1.0)

    def test_pointing_loss_drops_off_axis(self):
        beam = GaussianBeam.from_aperture(WAVELENGTH_C_BAND, 0.08)
        on = pointing_loss(0.0, beam.half_angle_rad)
        off = pointing_loss(beam.half_angle_rad, beam.half_angle_rad)
        self.assertGreater(on, off)
        self.assertAlmostEqual(off, math.exp(-2.0), places=6)

    def test_link_budget_falls_with_range(self):
        spec = TerminalSpec()
        geos = sample_geometry("isl", np.array([0.0]), spec.wavelength_m, anomaly_offset_deg=20.0)
        far = sample_geometry("isl", np.array([0.0]), spec.wavelength_m, anomaly_offset_deg=50.0)
        near_b = link_budget(geos[0], spec, 0.0, include_atmosphere=False)
        far_b = link_budget(far[0], spec, 0.0, include_atmosphere=False)
        self.assertGreater(near_b.p_rx_w, far_b.p_rx_w)

    def test_atmosphere_blocks_below_horizon(self):
        self.assertEqual(atmospheric_transmittance(-5.0, 0.22), 0.0)
        self.assertGreater(atmospheric_transmittance(90.0, 0.22), 0.5)


class TestModem(unittest.TestCase):
    def test_ber_decreases_with_snr(self):
        low = bit_error_rate(1.0, Modulation.OOK)
        high = bit_error_rate(100.0, Modulation.OOK)
        self.assertGreater(low, high)
        self.assertLess(high, 1e-10)

    def test_bpsk_better_than_ook_at_same_snr(self):
        snr = 10.0
        self.assertLess(bit_error_rate(snr, Modulation.BPSK), bit_error_rate(snr, Modulation.OOK))

    def test_flip_bits_zero_ber_is_identity(self):
        rng = np.random.default_rng(0)
        payload = b"QSD"
        out, n = flip_bits(payload, 0.0, rng)
        self.assertEqual(out, payload)
        self.assertEqual(n, 0)


class TestPAT(unittest.TestCase):
    def test_plant_tracks_step(self):
        plant = PATPlant(dt=0.002)
        plant.reset()
        cmd = 10e-6
        last = np.zeros(2)
        for _ in range(400):
            last = plant.step(cmd, 0.0)
        self.assertAlmostEqual(last[0], cmd, delta=0.5e-6)

    def test_pid_rejects_constant_disturbance(self):
        dt = 0.002
        plant = PATPlant(dt=dt)
        ctrl = PIDController(dt=dt)
        plant.reset()
        ctrl.reset()
        d = np.array([15e-6, -8e-6])
        fsm = np.zeros(2)
        for _ in range(800):
            e = d - fsm
            u = ctrl.update(e)
            fsm = plant.step(float(u[0]), float(u[1]))
        residual = np.linalg.norm(d - fsm)
        self.assertLess(residual, 2e-6)

    def test_qsd_rejects_constant_disturbance(self):
        dt = 0.002
        plant = PATPlant(dt=dt)
        ctrl = QSDISSController(dt=dt)
        plant.reset()
        ctrl.reset()
        d = np.array([15e-6, -8e-6])
        fsm = np.zeros(2)
        for _ in range(800):
            e = d - fsm
            u = ctrl.update(e)
            fsm = plant.step(float(u[0]), float(u[1]))
        residual = np.linalg.norm(d - fsm)
        self.assertLess(residual, 3e-6)

    def test_jitter_rms(self):
        rng = np.random.default_rng(1)
        j = colored_jitter(4000, 0.002, 12e-6, 0.05, rng)
        rms = np.sqrt(np.mean(j**2))
        self.assertGreater(rms, 8e-6)
        self.assertLess(rms, 16e-6)


class TestCampaign(unittest.TestCase):
    def test_isl_qsd_beats_open_loop(self):
        res = run_scenario(ScenarioName.ISL, duration_s=1.5, dt=0.002, seed=0)
        qsd = res.runs["qsd"].mean_err_urad
        open_ = res.runs["open"].mean_err_urad
        self.assertLess(qsd, open_)
        self.assertTrue(res.verdicts["T1_qsd_beats_openloop"]["passed"])

    def test_wrong_well_worse_than_qsd(self):
        res = run_scenario(ScenarioName.ISL, duration_s=1.5, dt=0.002, seed=1)
        self.assertLess(res.runs["qsd"].mean_err_urad, res.runs["qsd_wrong"].mean_err_urad)

    def test_packet_interface(self):
        term = OpticalTerminal(seed=0, duration_s=1.0)
        xfer = term.ping("HELLO")
        self.assertEqual(xfer.n_bits, 40)
        self.assertIsInstance(xfer.received, bytes)


if __name__ == "__main__":
    unittest.main()
