"""
Aurora-QSD AI: Quantum Stabilization Dynamics + Aurora Principle for quantum computing.

Applies TriDelta geometry, ISS bounds, and phase-match-faster-than-dissipate control
to quantum circuit design, analysis, and stabilization.
"""

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG, PHI, TAN_THETA_STAR
from aurora_qsd.core.tridelta import TriDelta, decompose_covariance, heron_penalty
from aurora_qsd.core.iss import iss_bound, contraction_rate
from aurora_qsd.core.aurora import AuroraCondition, check_aurora_condition
from aurora_qsd.agent.qsd_agent import QSDAuroraAgent

__version__ = "0.1.0"
__all__ = [
    "THETA_STAR",
    "THETA_STAR_DEG",
    "PHI",
    "TAN_THETA_STAR",
    "TriDelta",
    "decompose_covariance",
    "heron_penalty",
    "iss_bound",
    "contraction_rate",
    "AuroraCondition",
    "check_aurora_condition",
    "QSDAuroraAgent",
]
