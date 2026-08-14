"""OOK / coherent-BPSK bit-error models and packet bit flips."""

from __future__ import annotations

import math
from enum import Enum

import numpy as np

from aurora_qsd.optical.constants import C_LIGHT, H_PLANCK


class Modulation(str, Enum):
    OOK = "ook"
    BPSK = "bpsk"


def photons_per_bit(p_rx_w: float, wavelength_m: float, bit_rate_hz: float) -> float:
    hf = H_PLANCK * C_LIGHT / wavelength_m
    if hf <= 0 or bit_rate_hz <= 0:
        return 0.0
    return float(p_rx_w / (hf * bit_rate_hz))


def bit_error_rate(snr_elec: float, modulation: Modulation = Modulation.OOK) -> float:
    """
    Uncoded BER from electrical SNR.

    OOK (IM/DD, Gaussian):  ½ erfc(√(SNR/4))  — matched-filter On-Off
    BPSK (coherent):        ½ erfc(√SNR)
    """
    snr = max(float(snr_elec), 0.0)
    if modulation is Modulation.BPSK:
        arg = math.sqrt(snr) if snr > 0 else 0.0
    else:
        arg = math.sqrt(snr / 4.0) if snr > 0 else 0.0
    ber = 0.5 * math.erfc(arg)
    return float(min(max(ber, 0.0), 0.5))


def coherent_ber(snr_elec: float, phase_err_rad: float) -> float:
    """BPSK BER with residual carrier phase: SNR_eff = SNR · cos²(φ)."""
    snr_eff = max(float(snr_elec), 0.0) * (math.cos(phase_err_rad) ** 2)
    return bit_error_rate(snr_eff, Modulation.BPSK)


def flip_bits(
    payload: bytes,
    ber: float,
    rng: np.random.Generator,
) -> tuple[bytes, int]:
    """Flip each bit independently with probability ``ber``. Returns (bytes, n_flips)."""
    if not payload:
        return payload, 0
    arr = np.frombuffer(payload, dtype=np.uint8).copy()
    bits = np.unpackbits(arr)
    flips = rng.random(bits.shape[0]) < ber
    bits[flips] ^= 1
    out = np.packbits(bits)[: len(arr)]
    return out.tobytes(), int(flips.sum())
