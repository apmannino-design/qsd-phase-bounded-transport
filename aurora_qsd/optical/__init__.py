"""
Satellite free-space optical (FSO) link prototype.

Simulation only. Applies QSD ISS contraction (Theorem 6) and the
third-harmonic phase potential as a pointing/phase-lock controller.
Not a hardware result and not a claim that θ* is a physical beam angle.

Public entry points
-------------------
``python -m aurora_qsd.optical`` — run the campaign and write results.
``OpticalTerminal.transmit`` — send bytes across a simulated LEO optical hop.
"""

from aurora_qsd.optical.channel import (
    GaussianBeam,
    LinkBudget,
    TerminalSpec,
    atmospheric_transmittance,
    downlink_scintillation_index,
    link_budget,
    pointing_loss,
)
from aurora_qsd.optical.fec import decode, encode, transmit_protected
from aurora_qsd.optical.modem import (
    Modulation,
    bit_error_rate,
    coherent_ber,
    flip_bits,
    photons_per_bit,
)
from aurora_qsd.optical.orbits import (
    CircularOrbit,
    GroundStation,
    HALEAKALA,
    LinkGeometry,
    circular_orbit,
    intersat_geometry,
    leo_ground_geometry,
    station_under,
)
from aurora_qsd.optical.pat import (
    ControllerName,
    PATPlant,
    PIDController,
    QSDISSController,
)
from aurora_qsd.optical.pll import PLLResult, run_pll_campaign
from aurora_qsd.optical.relay import RelayResult, TwoHopRelay, run_relay_campaign
from aurora_qsd.optical.simulate import (
    OpticalLink,
    ScenarioName,
    SimulationResult,
    run_campaign,
    run_scenario,
)
from aurora_qsd.optical.terminal import OpticalTerminal

__all__ = [
    "CircularOrbit",
    "ControllerName",
    "GaussianBeam",
    "GroundStation",
    "HALEAKALA",
    "LinkBudget",
    "LinkGeometry",
    "Modulation",
    "OpticalLink",
    "OpticalTerminal",
    "PATPlant",
    "PIDController",
    "PLLResult",
    "QSDISSController",
    "RelayResult",
    "ScenarioName",
    "SimulationResult",
    "TerminalSpec",
    "TwoHopRelay",
    "station_under",
    "atmospheric_transmittance",
    "bit_error_rate",
    "circular_orbit",
    "coherent_ber",
    "decode",
    "downlink_scintillation_index",
    "encode",
    "flip_bits",
    "intersat_geometry",
    "leo_ground_geometry",
    "link_budget",
    "photons_per_bit",
    "pointing_loss",
    "run_campaign",
    "run_pll_campaign",
    "run_relay_campaign",
    "run_scenario",
    "transmit_protected",
]
