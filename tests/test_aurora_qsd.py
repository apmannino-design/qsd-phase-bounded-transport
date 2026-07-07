"""Tests for Aurora-QSD AI framework."""

import numpy as np
import pytest

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG, TAN_THETA_STAR
from aurora_qsd.core.tridelta import decompose_covariance, heron_penalty, TriDelta
from aurora_qsd.core.iss import iss_bound, contraction_rate
from aurora_qsd.core.aurora import check_aurora_condition, optimal_relock_interval
from aurora_qsd.core.phase_potential import phase_potential, phase_force, is_zero_dissipation
from aurora_qsd.agent.qsd_agent import QSDAuroraAgent


class TestConstants:
    def test_theta_star_value(self):
        assert abs(THETA_STAR_DEG - 22.5) < 0.01
        assert abs(TAN_THETA_STAR - (np.sqrt(2) - 1)) < 1e-10


class TestTriDelta:
    def test_toy_covariance(self):
        sigma = np.array([[1.2, 0.4, 0.1], [0.4, 0.8, 0.2], [0.1, 0.2, 0.5]])
        td = decompose_covariance(sigma)
        assert isinstance(td, TriDelta)
        assert td.delta_e > 0
        assert td.heron >= 0.0

    def test_heron_penalty_violation(self):
        h = heron_penalty(1.0, 1.0, 5.0)
        assert h > 0


class TestISS:
    def test_bound_decreases_with_convergence(self):
        e0 = 0.5
        b0 = iss_bound(e0, 0, rho=0.85)
        b10 = iss_bound(e0, 10, rho=0.85)
        assert b10 < b0

    def test_contraction_rate(self):
        gamma = contraction_rate(0.85)
        assert gamma > 0


class TestAurora:
    def test_condition_with_good_t2(self):
        cond = check_aurora_condition(rho=0.85, t2_us=100.0)
        assert cond.satisfied

    def test_relock_interval(self):
        interval = optimal_relock_interval(rho=0.85, t2_us=100.0)
        assert 3 <= interval <= 21


class TestPhasePotential:
    def test_zero_force_at_lock(self):
        assert is_zero_dissipation(THETA_STAR, tol=0.01)

    def test_potential_minimum_near_theta_star(self):
        v_star = phase_potential(THETA_STAR)
        v_offset = phase_potential(THETA_STAR + 0.1)
        assert v_star < v_offset


class TestAgent:
    def test_query_explain(self):
        agent = QSDAuroraAgent()
        resp = agent.query("explain the Aurora principle")
        assert resp.intent == "explain"
        assert "Aurora" in resp.message or "dissipate" in resp.message

    def test_analyze_counts(self):
        agent = QSDAuroraAgent()
        counts = {"00": 15000, "01": 2000, "10": 2000, "11": 13000}
        resp = agent.analyze_counts(counts)
        assert resp.intent == "analyze"
        assert resp.data["parity"] > 0.5

    def test_plan_relock(self):
        agent = QSDAuroraAgent()
        resp = agent.plan_relock(1241)
        assert resp.intent == "relock"
        assert resp.data["relock_interval"] > 0

    def test_optimize_theta(self):
        agent = QSDAuroraAgent()
        resp = agent.optimize_theta()
        assert abs(resp.data["optimal_theta_deg"] - THETA_STAR_DEG) < 2.0

    def test_simulate_iss(self):
        agent = QSDAuroraAgent()
        resp = agent.simulate_iss(steps=5)
        assert len(resp.data["closed_loop_deg"]) == 5
