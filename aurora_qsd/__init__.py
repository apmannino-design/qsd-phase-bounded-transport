"""
Aurora-QSD: Quantum Stabilization Dynamics utilities.

This branch adds an exploratory satellite free-space optical (FSO) link
prototype under ``aurora_qsd.optical``. Core math (θ*, ISS bounds, third-
harmonic phase potential) is shared with the rest of the research program.

Nothing in ``aurora_qsd.optical`` is a hardware result. It is a simulation
prototype that applies Theorem 6 (ISS contraction) to pointing/phase-lock
control. See ``docs/SATELLITE_OPTICAL_LINK.md``.
"""

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG, PHI, TAN_THETA_STAR
from aurora_qsd.core.iss import iss_bound, contraction_rate
from aurora_qsd.core.phase_potential import phase_potential, phase_force, basin_boundary

__version__ = "0.2.0-optical"
__all__ = [
    "THETA_STAR",
    "THETA_STAR_DEG",
    "PHI",
    "TAN_THETA_STAR",
    "iss_bound",
    "contraction_rate",
    "phase_potential",
    "phase_force",
    "basin_boundary",
]
