"""Physical constants and default terminal parameters for the FSO prototype.

Numbers are engineering-class defaults for a smallsat 1550 nm terminal
(TESAT LCT / Mynaric / NASA TBIRD family), not a specific flight unit.
"""

from __future__ import annotations

# --- Earth / Kepler ---
GM_EARTH = 3.986004418e14  # m^3/s^2
R_EARTH = 6.371e6  # m, spherical mean
OMEGA_EARTH = 7.2921159e-5  # rad/s

# --- Optics ---
C_LIGHT = 2.99792458e8  # m/s
H_PLANCK = 6.62607015e-34  # J s
WAVELENGTH_C_BAND = 1550e-9  # m, standard FSO / fiber laser-comm band
WAVELENGTH_NDYAG = 1064e-9  # m, TESAT LCT heritage

# --- Default LEO smallsat terminal (ISL) ---
DEFAULT_TX_POWER_W = 1.0
DEFAULT_APERTURE_M = 0.080
DEFAULT_OPTICS_EFFICIENCY = 0.70
DEFAULT_BIT_RATE = 1.0e9  # 1 Gbps OOK-class prototype
DEFAULT_NEP = 2.0e-14  # W/sqrt(Hz), PIN/APD engineering NEP
DEFAULT_RX_BANDWIDTH_HZ = 1.0e9

# --- PAT ---
# 1/e² half-angle for an 8 cm, 1550 nm Gaussian is ~12 μrad.
# Fine-stage residual requirement is typically a few μrad RMS.
DEFAULT_PAT_DT = 0.002  # 500 Hz fine-stage sample
DEFAULT_FSM_WN_HZ = 200.0  # closed-loop FSM natural frequency
DEFAULT_FSM_ZETA = 0.7
DEFAULT_JITTER_RMS_URAD = 12.0
DEFAULT_JITTER_CORR_S = 0.05
DEFAULT_ACQ_FOV_URAD = 200.0  # coarse-stage field of view

# --- Atmosphere (1550 nm, high-altitude site, clear air) ---
DEFAULT_ZENITH_TAU = 0.22  # optical depth at zenith, 1550 nm, ~3 km site
HV_WIND_MS = 21.0  # Hufnagel-Valley 5/7
HV_A = 1.7e-14  # ground-layer Cn², m^{-2/3}

# --- Link thresholds (pre-registered) ---
MIN_ELEVATION_DEG = 20.0
SNR_OUTAGE_DB = 6.0  # electrical SNR below this is an outage
AVAILABILITY_NONINFERIOR_PP = 2.0  # T3: QSD may trail PID by at most 2 pp
ISS_COVERAGE_TARGET = 0.95  # T2/T6: fraction of samples under the ISS bound

# --- Optical PLL (Costas-loop rate; not the 500 Hz PAT loop) ---
DEFAULT_PLL_DT = 5.0e-5  # 20 kHz
DEFAULT_LINEWIDTH_HZ = 300.0  # loop-referred NPRO-class
DEFAULT_DOPPLER_RESIDUAL_HZ = 5.0e3  # no ephemeris feedforward
DEFAULT_DOPPLER_FF_RESIDUAL_HZ = 50.0  # after range-rate feedforward
