"""QSD preregistered constants and corridor geometry.

θ* = arctan(√2 − 1) = π/8 = 22.5° exactly (half-angle identity).
Earlier materials that quoted 22.47°–22.48° as “not π/8” are superseded;
those figures, when they appear, are platform-calibrated empirical settings.
"""

import numpy as np

TAN_THETA_STAR = np.sqrt(2.0) - 1.0
THETA_STAR = float(np.arctan(TAN_THETA_STAR))
THETA_STAR_DEG = float(np.degrees(THETA_STAR))

# Platform-calibrated empirical settings (not the design identity)
THETA_STAR_HW_DEG = 22.47
THETA_STAR_HW = float(np.radians(THETA_STAR_HW_DEG))
THETA_STAR_WILLOW_HW_DEG = 22.48
THETA_STAR_WILLOW_HW = float(np.radians(THETA_STAR_WILLOW_HW_DEG))

PHI = (1.0 + np.sqrt(5.0)) / 2.0
THETA_PHI = float(np.arctan(1.0 / PHI))
THETA_PHI_DEG = float(np.degrees(THETA_PHI))

BASIN_BOUNDARY_DEG = 3.0 * THETA_STAR_DEG  # 67.5° exactly

DEFAULT_K_GAIN = 0.45
DEFAULT_RHO = 0.85
DELTA_E_CRIT = 0.2248
