"""Packet-level optical terminal sitting on top of the simulated FSO hop."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.optical.fec import transmit_protected
from aurora_qsd.optical.modem import flip_bits
from aurora_qsd.optical.pat import ControllerName
from aurora_qsd.optical.simulate import OpticalLink, ScenarioName


@dataclass
class TransferResult:
    payload: bytes
    received: bytes
    n_flips: int
    n_bits: int
    empirical_ber: float
    model_ber: float
    intact: bool
    fec: bool = False
    n_corrected: int = 0


class OpticalTerminal:
    """
    Send bytes across a simulated LEO optical hop.

    Each call to ``transmit`` uses the current instantaneous model BER of the
    underlying ``OpticalLink`` (PAT + channel + OOK). Optional Hamming(7,4).
    This is a prototype of the service interface, not a CCSDS / SDA waveform.
    """

    def __init__(
        self,
        scenario: ScenarioName = ScenarioName.ISL,
        controller: ControllerName = ControllerName.QSD,
        seed: int = 0,
        duration_s: float = 2.0,
        fec: bool = False,
    ):
        self.link = OpticalLink(
            scenario=scenario,
            controller=controller,
            seed=seed,
            duration_s=duration_s,
        )
        self.rng = np.random.default_rng(seed + 99)
        self.controller = controller
        self.fec = fec

    def transmit(self, payload: bytes) -> TransferResult:
        ber = self.link.instantaneous_ber()
        if self.fec:
            received, n_flips, n_corr = transmit_protected(payload, ber, self.rng)
        else:
            received, n_flips = flip_bits(payload, ber, self.rng)
            n_corr = 0
        n_bits = 8 * len(payload)
        self.link.step()
        return TransferResult(
            payload=payload,
            received=received,
            n_flips=n_flips,
            n_bits=n_bits,
            empirical_ber=(n_flips / n_bits) if n_bits else 0.0,
            model_ber=ber,
            intact=received == payload,
            fec=self.fec,
            n_corrected=n_corr,
        )

    def ping(self, message: str = "QSD-ISL") -> TransferResult:
        return self.transmit(message.encode("utf-8"))
