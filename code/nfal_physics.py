"""
Near-field acoustic levitation (NFAL) physics helpers.

Radiation-pressure model follows the near-field squeeze-film reduction of
Lee & Wang / Chu–Apfel (see e.g. Appl. Phys. Lett. 120, 034103 (2022)
and the NFAL bearing review, Int. J. Extrem. Manuf. 2019):

    p̄ = (γ + 1) / 8 · (a₀² c² ρ) / h²
       = γ(γ + 1) / 8 · (a₀² p₀) / h²

for micrometer gaps (cos 2kh ≈ 1). Levitation force F = p̄ · A_eff.

Coupling / match angle φ enters as an effective vibration amplitude
a_eff = a_max · sin φ (simultaneous output-and-match sketch).

This is a reduced-order scientific model for control studies — not a
substitute for full Reynolds-equation CFD.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# --- ambient air (SI) ---
P0 = 101_325.0  # Pa
RHO_AIR = 1.204  # kg/m³
GAMMA = 1.4  # —
ETA_AIR = 1.81e-5  # Pa·s
C_AIR = float(np.sqrt(GAMMA * P0 / RHO_AIR))  # m/s ≈ 343
G = 9.80665  # m/s²


@dataclass(frozen=True)
class NFALParams:
    """Physical plant parameters for a circular near-field plate pair."""

    # Acoustics / drive
    freq_hz: float = 28_000.0  # typical ultrasonic NFAL drive
    a_max: float = 8e-6  # m, peak piston amplitude (~8 μm)
    radius_m: float = 0.020  # m, 20 mm plate radius

    # Mechanics
    mass_kg: float = 0.012  # kg, 12 g levitated plate / payload
    h_star: float = 80e-6  # m, design levitation gap (80 μm)
    damping_ns_m: float = 8.0  # N·s/m, effective squeeze-film damping

    # Sensing / discrete control
    tau_force_s: float = 0.005  # s, force-estimate lag
    dt_s: float = 0.0005  # s, control sample (0.5 ms)

    # Sector / QSD controller (same sketch as the paper)
    theta_star: float = np.pi / 8
    alpha: float = 0.15
    k_gain: float = 0.08  # discrete sector gain (rad per unit e_h)
    rho: float = 0.85
    phi_min: float = 0.05
    phi_max: float = np.pi / 2 - 0.05

    # Scenario
    mass_step_kg: float = 0.003  # +3 g load step
    force_noise_std_n: float = 5e-4  # N, process / estimate noise
    corridor_gate: float = 0.08  # on ΔE = log(1+|e_h|)

    @property
    def omega(self) -> float:
        return 2.0 * np.pi * self.freq_hz

    @property
    def area(self) -> float:
        return np.pi * self.radius_m**2

    @property
    def wavelength_m(self) -> float:
        return C_AIR / self.freq_hz

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(
            {
                "p0_pa": P0,
                "rho_air": RHO_AIR,
                "gamma": GAMMA,
                "c_air": C_AIR,
                "eta_air": ETA_AIR,
                "g": G,
                "area_m2": self.area,
                "wavelength_m": self.wavelength_m,
            }
        )
        return d


def radiation_pressure_pa(a_eff_m: float, gap_m: float) -> float:
    """
    Time-averaged excess radiation pressure [Pa] (Lee–Wang near-field form).

    p̄ = γ(γ+1)/8 · a_eff² · p0 / h²
    """
    h = max(gap_m, 1e-7)
    a = max(a_eff_m, 0.0)
    return (GAMMA * (GAMMA + 1.0) / 8.0) * (a * a) * P0 / (h * h)


def squeeze_number(params: NFALParams, gap_m: float) -> float:
    """
    Squeeze number σ = 12 η ω R² / (p0 h²).

    Large σ ⇒ gas trapped in the film (NFAL regime).
    """
    h = max(gap_m, 1e-7)
    return 12.0 * ETA_AIR * params.omega * params.radius_m**2 / (P0 * h * h)


def acoustic_force_n(params: NFALParams, gap_m: float, phi: float) -> float:
    """
    Levitation force [N]: F = p̄(a_eff, h) · A with a_eff = a_max sin φ.
    """
    a_eff = params.a_max * float(np.sin(phi))
    return radiation_pressure_pa(a_eff, gap_m) * params.area


def design_a_max_for_balance(params: NFALParams) -> float:
    """
    Choose a_max so that at (h*, φ=θ*) the Lee–Wang force equals mg.

        mg = [γ(γ+1)/8 · (a_max sin θ*)² p0 / h*²] · A
        a_max = (h*/sinθ*) · sqrt( 8 mg / (γ(γ+1) p0 A) )
    """
    weight = params.mass_kg * G
    s = np.sin(params.theta_star)
    if s <= 0:
        raise ValueError("theta_star must lie in (0, π)")
    inside = 8.0 * weight / (GAMMA * (GAMMA + 1.0) * P0 * params.area)
    return float(params.h_star / s * np.sqrt(inside))


def balanced_params(**overrides) -> NFALParams:
    """Return params with a_max solved for force balance at (h*, θ*)."""
    base = NFALParams(**overrides) if overrides else NFALParams()
    a_max = design_a_max_for_balance(base)
    return NFALParams(**{**asdict(base), "a_max": a_max})


def equilibrium_gap(params: NFALParams, phi: float, mass_kg: float) -> float:
    """
    Quasi-steady gap solving F(h, φ) = m g:

        h = a_eff · sqrt( γ(γ+1) p0 A / (8 m g) )
    """
    weight = mass_kg * G
    a_eff = params.a_max * float(np.sin(phi))
    if weight <= 0 or a_eff <= 0:
        return np.inf
    return float(a_eff * np.sqrt(GAMMA * (GAMMA + 1.0) * P0 * params.area / (8.0 * weight)))
