"""QSD/Aurora preregistered constants and corridor geometry."""

import numpy as np

# Lock point: θ* = arctan(√2 - 1) ≈ 22.4794°
TAN_THETA_STAR = np.sqrt(2.0) - 1.0
THETA_STAR = float(np.arctan(TAN_THETA_STAR))
THETA_STAR_DEG = float(np.degrees(THETA_STAR))

# Hardware-validated source angle (ibm_fez, June 2026)
THETA_STAR_HW_DEG = 22.47
THETA_STAR_HW = float(np.radians(THETA_STAR_HW_DEG))

# Golden-ratio outer corridor: θ_φ = arctan(1/φ)
PHI = (1.0 + np.sqrt(5.0)) / 2.0
THETA_PHI = float(np.arctan(1.0 / PHI))
THETA_PHI_DEG = float(np.degrees(THETA_PHI))

# Basin boundary: 3θ* = 67.5°
BASIN_BOUNDARY_DEG = 3.0 * THETA_STAR_DEG

# Default control gains from hardware validation
DEFAULT_K_GAIN = 0.45
DEFAULT_RHO = 0.85
DEFAULT_SHOTS = 8192

# Preregistered energy gate (GOES/Kp pipelines)
DELTA_E_CRIT = 0.2248
