"""
Near-field acoustic levitation (NFAL) physics helpers.

Radiation-pressure model follows the near-field squeeze-film reduction of
Lee & Wang / Chu–Apfel (micrometer-gap limit):

    p̄ = γ(γ+1)/8 · (a_eff² p₀) / h²
    a_eff = a_max · sin φ
    F_ac = C(φ, h) = p̄ · A

so coupling authority is explicitly gap-dependent (≈ 1/h²), not a
constant C₀ sin φ. Design a_max is solved so F(h*, θ*) = mg.

Reduced-order scientific model for control studies — not full Reynolds CFD.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# --- ambient air (SI) ---
P0 = 101_325.0  # Pa
RHO_AIR = 1.204  # kg/m³
GAMMA = 1.4
ETA_AIR = 1.81e-5  # Pa·s
C_AIR = float(np.sqrt(GAMMA * P0 / RHO_AIR))  # ≈ 343 m/s
G = 9.80665  # m/s²


@dataclass(frozen=True)
class NFALParams:
    """Physical plant + cascaded QSD / position-loop parameters."""

    # Acoustics / drive
    freq_hz: float = 28_000.0
    a_max: float = 8e-6  # overwritten by balanced_params()
    radius_m: float = 0.020

    # Mechanics
    mass_kg: float = 0.012
    h_star: float = 80e-6
    damping_ns_m: float = 8.0

    # Sensing / discrete control
    tau_force_s: float = 0.005
    dt_s: float = 0.0005

    # Inner QSD sector law on residual r
    theta_star: float = np.pi / 8
    alpha: float = 0.15
    k_gain: float = 0.06
    rho: float = 0.85
    phi_min: float = 0.05
    phi_max: float = np.pi / 2 - 0.05
    phi_rate_max: float = 2.0  # rad/s hard rate limit

    # Outer position / velocity loop (augments force residual)
    kp_pos: float = 1.5  # on (h-h*)/h* → force units of mg
    kd_vel: float = 1.2  # on v / v_scale
    v_scale: float = 5e-4  # m/s normalization (~0.5 mm/s)

    # Lock-in (freeze φ when filtered corridor + low velocity)
    lock_de_gate: float = 0.05
    lock_v_gate: float = 5e-5  # m/s
    unlock_de_gate: float = 0.12
    tau_residual_s: float = 0.015  # filter for ΔE / lock (keeps corridor on fast residual)

    # Anti-windup (back-calculation)
    kaw: float = 1.0

    # Safety interlocks
    h_floor: float = 20e-6  # m, contact proximity
    h_ceil: float = 500e-6  # m, field escape

    # Disturbances (physically small relative to μm-scale gaps)
    mass_step_kg: float = 0.003
    force_noise_std_n: float = 2e-4
    gap_sensor_noise_std_m: float = 0.15e-6  # 0.15 μm
    thermal_phase_walk_std: float = 2e-4  # rad/√s random-walk intensity
    impulse_times: tuple = (1.8,)  # s
    impulse_force_n: float = 1.5e-4  # N → Δv = F/m ≈ 1.25 cm/s

    # Corridor metric on filtered normalized residual
    corridor_gate: float = 0.10

    @property
    def omega(self) -> float:
        return 2.0 * np.pi * self.freq_hz

    @property
    def area(self) -> float:
        return np.pi * self.radius_m**2

    @property
    def wavelength_m(self) -> float:
        return C_AIR / self.freq_hz

    @property
    def c0_at_hstar(self) -> float:
        """Peak coupling force [N] at h* with sinφ=1."""
        return radiation_pressure_pa(self.a_max, self.h_star) * self.area

    def to_dict(self) -> dict:
        d = asdict(self)
        d["impulse_times"] = list(self.impulse_times)
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
                "c0_at_hstar_n": self.c0_at_hstar,
                "margin_c0_over_mg": self.c0_at_hstar / (self.mass_kg * G),
            }
        )
        return d


def radiation_pressure_pa(a_eff_m: float, gap_m: float) -> float:
    """Time-averaged excess radiation pressure [Pa] (Lee–Wang near-field)."""
    h = max(gap_m, 1e-7)
    a = max(a_eff_m, 0.0)
    return (GAMMA * (GAMMA + 1.0) / 8.0) * (a * a) * P0 / (h * h)


def squeeze_number(params: NFALParams, gap_m: float) -> float:
    """σ = 12 η ω R² / (p0 h²); ≫1 ⇒ trapped-film / NFAL regime."""
    h = max(gap_m, 1e-7)
    return 12.0 * ETA_AIR * params.omega * params.radius_m**2 / (P0 * h * h)


def coupling_force_n(params: NFALParams, phi: float, gap_m: float) -> float:
    """
    Gap-dependent coupling C(φ, h) [N].

        C(φ,h) = [γ(γ+1)/8 · (a_max sin φ)² p0 / h²] · A
    """
    a_eff = params.a_max * float(np.sin(phi))
    return radiation_pressure_pa(a_eff, gap_m) * params.area


# Back-compat alias
def acoustic_force_n(params: NFALParams, gap_m: float, phi: float) -> float:
    return coupling_force_n(params, phi, gap_m)


def design_a_max_for_balance(params: NFALParams) -> float:
    """a_max so C(θ*, h*) = mg."""
    weight = params.mass_kg * G
    s = np.sin(params.theta_star)
    if s <= 0:
        raise ValueError("theta_star must lie in (0, π)")
    inside = 8.0 * weight / (GAMMA * (GAMMA + 1.0) * P0 * params.area)
    return float(params.h_star / s * np.sqrt(inside))


def balanced_params(**overrides) -> NFALParams:
    base = NFALParams(**overrides) if overrides else NFALParams()
    a_max = design_a_max_for_balance(base)
    return NFALParams(**{**asdict(base), "a_max": a_max})


def equilibrium_gap(params: NFALParams, phi: float, mass_kg: float) -> float:
    """Quasi-steady gap from C(φ,h)=mg ⇒ h ∝ a_max sinφ / √(mg)."""
    weight = mass_kg * G
    a_eff = params.a_max * float(np.sin(phi))
    if weight <= 0 or a_eff <= 0:
        return np.inf
    return float(
        a_eff * np.sqrt(GAMMA * (GAMMA + 1.0) * P0 * params.area / (8.0 * weight))
    )
