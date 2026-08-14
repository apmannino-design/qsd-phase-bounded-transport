"""Gaussian-beam FSO channel: link budget, pointing loss, scintillation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.optical.constants import (
    C_LIGHT,
    DEFAULT_APERTURE_M,
    DEFAULT_BIT_RATE,
    DEFAULT_NEP,
    DEFAULT_OPTICS_EFFICIENCY,
    DEFAULT_RX_BANDWIDTH_HZ,
    DEFAULT_TX_POWER_W,
    DEFAULT_ZENITH_TAU,
    H_PLANCK,
    HV_A,
    HV_WIND_MS,
    MIN_ELEVATION_DEG,
    WAVELENGTH_C_BAND,
)
from aurora_qsd.optical.orbits import LinkGeometry


@dataclass(frozen=True)
class TerminalSpec:
    name: str = "leo-smallsat"
    wavelength_m: float = WAVELENGTH_C_BAND
    tx_power_w: float = DEFAULT_TX_POWER_W
    tx_aperture_m: float = DEFAULT_APERTURE_M
    rx_aperture_m: float = DEFAULT_APERTURE_M
    tx_efficiency: float = DEFAULT_OPTICS_EFFICIENCY
    rx_efficiency: float = DEFAULT_OPTICS_EFFICIENCY
    bit_rate_hz: float = DEFAULT_BIT_RATE
    nep_w_rt_hz: float = DEFAULT_NEP
    rx_bandwidth_hz: float = DEFAULT_RX_BANDWIDTH_HZ
    zenith_optical_depth: float = DEFAULT_ZENITH_TAU


@dataclass(frozen=True)
class GaussianBeam:
    wavelength_m: float
    w0_m: float

    @property
    def half_angle_rad(self) -> float:
        """1/e² far-field half-angle, λ/(π w0)."""
        return self.wavelength_m / (np.pi * self.w0_m)

    def waist_at(self, range_m: float) -> float:
        z_r = np.pi * self.w0_m**2 / self.wavelength_m
        return float(self.w0_m * np.sqrt(1.0 + (range_m / z_r) ** 2))

    @classmethod
    def from_aperture(cls, wavelength_m: float, aperture_m: float) -> "GaussianBeam":
        # Fill the aperture at the 1/e² radius ≈ D/2
        return cls(wavelength_m=wavelength_m, w0_m=0.5 * aperture_m)


def pointing_loss(theta_err_rad: float, theta_div_rad: float) -> float:
    """Gaussian off-axis loss exp(−2 (θ_err / θ_div)²). 1.0 on boresight."""
    if theta_div_rad <= 0:
        raise ValueError("divergence must be positive")
    ratio = theta_err_rad / theta_div_rad
    arg = -2.0 * ratio * ratio
    return float(np.exp(np.clip(arg, -700.0, 0.0)))


def atmospheric_transmittance(elevation_deg: float, zenith_tau: float) -> float:
    """Beer-Lambert air mass. Zero below the horizon."""
    if elevation_deg <= 0.0:
        return 0.0
    am = 1.0 / max(np.sin(np.radians(elevation_deg)), 1e-3)
    return float(np.exp(-zenith_tau * am))


def _cn2_hufnagel_valley(h_m: np.ndarray, wind_ms: float = HV_WIND_MS, a: float = HV_A) -> np.ndarray:
    """Hufnagel–Valley 5/7 refractive-index structure constant (m^{-2/3})."""
    h = np.asarray(h_m, dtype=float)
    term_wind = 0.00594 * (wind_ms / 27.0) ** 2 * (1e-5 * h) ** 10 * np.exp(-h / 1000.0)
    term_trop = 2.7e-16 * np.exp(-h / 1500.0)
    term_ground = a * np.exp(-h / 100.0)
    return term_wind + term_trop + term_ground


def downlink_scintillation_index(
    wavelength_m: float,
    elevation_deg: float,
    rx_aperture_m: float,
    h_sat_m: float,
    h_gs_m: float = 3055.0,
) -> float:
    """
    Weak-turbulence Rytov variance for a downlink spherical wave, with a
    simple aperture-averaging factor. Returns σ_I² (scintillation index).

    This is an engineering approximation of the HV-5/7 integral, not a
    wave-optics propagator.
    """
    if elevation_deg < MIN_ELEVATION_DEG:
        return 1.0  # treat low-elevation as fully scintillated / out of spec
    k = 2.0 * np.pi / wavelength_m
    sec_zenith = 1.0 / np.sin(np.radians(elevation_deg))
    h = np.linspace(h_gs_m, h_sat_m, 256)
    dh = h[1] - h[0]
    cn2 = _cn2_hufnagel_valley(h)
    # Downlink: turbulence near the receiver. Path weighting ~(h-h0)^{5/6}
    weight = np.clip(h - h_gs_m, 0.0, None) ** (5.0 / 6.0)
    trapz = getattr(np, "trapezoid", None)
    if trapz is None:
        integral = float(np.sum(0.5 * (cn2[:-1] * weight[:-1] + cn2[1:] * weight[1:]) * dh))
    else:
        integral = float(trapz(cn2 * weight, dx=dh))
    rytov = 2.25 * (k ** (7.0 / 6.0)) * (sec_zenith ** (11.0 / 6.0)) * integral
    # Aperture averaging (Andrews): larger D reduces σ_I²
    d_scale = rx_aperture_m / 0.05
    aa = 1.0 / (1.0 + 1.1 * d_scale ** (7.0 / 6.0))
    return float(np.clip(rytov * aa, 0.0, 4.0))


@dataclass(frozen=True)
class LinkBudget:
    range_m: float
    elevation_deg: float
    p_rx_w: float
    pointing_loss: float
    atm_transmittance: float
    scintillation_index: float
    fade_linear: float
    snr_elec: float
    snr_db: float
    photons_per_second: float
    beam_half_angle_urad: float
    waist_m: float


def link_budget(
    geo: LinkGeometry,
    spec: TerminalSpec,
    theta_err_rad: float,
    fade_linear: float = 1.0,
    include_atmosphere: bool = False,
) -> LinkBudget:
    """Far-field Gaussian link budget for one sample."""
    beam = GaussianBeam.from_aperture(spec.wavelength_m, spec.tx_aperture_m)
    w = beam.waist_at(geo.range_m)
    l_point = pointing_loss(theta_err_rad, beam.half_angle_rad)
    if include_atmosphere:
        tau = atmospheric_transmittance(geo.elevation_deg, spec.zenith_optical_depth)
        sig_i = downlink_scintillation_index(
            spec.wavelength_m,
            geo.elevation_deg,
            spec.rx_aperture_m,
            h_sat_m=geo.range_m,  # slant range as a conservative upper height
        )
    else:
        tau = 1.0
        sig_i = 0.0

    # On-axis intensity of a collimated Gaussian; capture by the Rx aperture
    i_peak = 2.0 * spec.tx_power_w * spec.tx_efficiency / (np.pi * w**2)
    a_rx = np.pi * (0.5 * spec.rx_aperture_m) ** 2
    p_rx = i_peak * a_rx * spec.rx_efficiency * l_point * tau * max(fade_linear, 0.0)

    hf = H_PLANCK * C_LIGHT / spec.wavelength_m
    pps = p_rx / hf if hf > 0 else 0.0

    # Electrical SNR: shot + NEP thermal in the Rx bandwidth
    nep_var = (spec.nep_w_rt_hz**2) * spec.rx_bandwidth_hz
    # Shot noise in watts²: 2 h f P B
    shot_w2 = 2.0 * hf * max(p_rx, 0.0) * spec.rx_bandwidth_hz
    noise_w2 = nep_var + shot_w2
    snr = (p_rx**2) / noise_w2 if noise_w2 > 0 else 0.0
    snr_db = float(10.0 * np.log10(snr)) if snr > 0 else -80.0

    return LinkBudget(
        range_m=geo.range_m,
        elevation_deg=geo.elevation_deg,
        p_rx_w=float(p_rx),
        pointing_loss=l_point,
        atm_transmittance=tau,
        scintillation_index=float(sig_i),
        fade_linear=float(fade_linear),
        snr_elec=float(snr),
        snr_db=snr_db,
        photons_per_second=float(pps),
        beam_half_angle_urad=float(beam.half_angle_rad * 1e6),
        waist_m=w,
    )


def lognormal_fades(
    n: int,
    sigma_i: float,
    corr_samples: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Unit-mean temporally correlated lognormal intensity fades."""
    if sigma_i <= 0.0:
        return np.ones(n)
    # For lognormal I, σ_I² = exp(σ_ln²) − 1, E[I]=1 ⇒ μ_ln = −σ_ln²/2
    sig_ln = np.sqrt(np.log(1.0 + sigma_i))
    white = rng.normal(0.0, 1.0, size=n)
    if corr_samples <= 1:
        colored = white
    else:
        alpha = np.exp(-1.0 / corr_samples)
        colored = np.empty(n)
        colored[0] = white[0]
        for i in range(1, n):
            colored[i] = alpha * colored[i - 1] + np.sqrt(1.0 - alpha**2) * white[i]
    return np.exp(sig_ln * colored - 0.5 * sig_ln**2)
