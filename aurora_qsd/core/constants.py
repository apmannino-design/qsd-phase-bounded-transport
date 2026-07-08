"""QSD/Aurora preregistered constants and corridor geometry."""

import numpy as np

# Design constant: θ* = arctan(√2 − 1) = π/8 = 22.5° exactly (half-angle identity).
TAN_THETA_STAR = np.sqrt(2.0) - 1.0
THETA_STAR = float(np.arctan(TAN_THETA_STAR))  # π/8
THETA_STAR_DEG = float(np.degrees(THETA_STAR))  # 22.5°

# Hardware-validated source angle (ibm_fez, June 2026)
THETA_STAR_HW_DEG = 22.47
THETA_STAR_HW = float(np.radians(THETA_STAR_HW_DEG))

# Willow QVM empirical optimum (platform-calibrated; distinct from design θ*)
THETA_STAR_WILLOW_HW_DEG = 22.49
THETA_STAR_WILLOW_HW = float(np.radians(THETA_STAR_WILLOW_HW_DEG))

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

# SO(2) peak-merger geometry (preregistered July 7, 2026)
# Projector rotation α at structural ratio lock ΔL/ΔX = tan(65.53°).
MERGER_PROJECTOR_ALPHA_DEG = 17.93
MERGER_STRUCTURAL_RATIO_LX = 2.1974  # ΔL/ΔX target at peak merger
MERGER_PARTITION_THETA_DEG = 27.61   # partition angle θ at peak merger

# April submission geometric reference: (90° − arccos(1/√3)) / 2
SUBMISSION_THETA_STAR_DEG = float((90.0 - np.degrees(np.arccos(1.0 / np.sqrt(3.0)))) / 2.0)
