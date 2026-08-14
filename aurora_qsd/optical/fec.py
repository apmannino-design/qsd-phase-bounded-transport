"""Hamming(7,4) FEC for the packet prototype. Not a CCSDS code."""

from __future__ import annotations


def _encode_nibble(nibble: int) -> int:
    d = [(nibble >> i) & 1 for i in (3, 2, 1, 0)]  # d1..d4
    p1 = d[0] ^ d[1] ^ d[3]
    p2 = d[0] ^ d[2] ^ d[3]
    p3 = d[1] ^ d[2] ^ d[3]
    # p1 p2 d1 p3 d2 d3 d4
    return (p1 << 6) | (p2 << 5) | (d[0] << 4) | (p3 << 3) | (d[1] << 2) | (d[2] << 1) | d[3]


def _decode_word(word: int) -> tuple[int, bool]:
    bits = [(word >> i) & 1 for i in range(6, -1, -1)]  # b1..b7
    s1 = bits[0] ^ bits[2] ^ bits[4] ^ bits[6]
    s2 = bits[1] ^ bits[2] ^ bits[5] ^ bits[6]
    s3 = bits[3] ^ bits[4] ^ bits[5] ^ bits[6]
    syn = s1 + 2 * s2 + 4 * s3
    corrected = syn != 0
    if corrected and 1 <= syn <= 7:
        bits[syn - 1] ^= 1
    nibble = (bits[2] << 3) | (bits[4] << 2) | (bits[5] << 1) | bits[6]
    return nibble, corrected


def encode(payload: bytes) -> bytes:
    """Encode bytes → Hamming(7,4) bitstream packed into bytes (padded)."""
    nibbles = []
    for b in payload:
        nibbles.append((b >> 4) & 0xF)
        nibbles.append(b & 0xF)
    words = [_encode_nibble(n) for n in nibbles]
    bits: list[int] = []
    for w in words:
        for i in range(6, -1, -1):
            bits.append((w >> i) & 1)
    while len(bits) % 8:
        bits.append(0)
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for bit in bits[i : i + 8]:
            v = (v << 1) | bit
        out.append(v)
    return bytes(out)


def decode(coded: bytes, n_payload_bytes: int) -> tuple[bytes, int]:
    """Decode Hamming(7,4). Returns (payload, n_words_corrected)."""
    bits = []
    for b in coded:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    n_words = 2 * n_payload_bytes
    nibbles = []
    n_corr = 0
    for w in range(n_words):
        chunk = bits[7 * w : 7 * (w + 1)]
        if len(chunk) < 7:
            chunk = chunk + [0] * (7 - len(chunk))
        word = 0
        for bit in chunk:
            word = (word << 1) | bit
        nibble, corr = _decode_word(word)
        n_corr += int(corr)
        nibbles.append(nibble)
    out = bytearray()
    for i in range(0, len(nibbles), 2):
        hi = nibbles[i]
        lo = nibbles[i + 1] if i + 1 < len(nibbles) else 0
        out.append((hi << 4) | lo)
    return bytes(out[:n_payload_bytes]), n_corr


def transmit_protected(
    payload: bytes,
    ber: float,
    rng: np.random.Generator,
) -> tuple[bytes, int, int]:
    """Encode, flip coded bits, decode. Returns (received, n_channel_flips, n_corrected)."""
    from aurora_qsd.optical.modem import flip_bits

    coded = encode(payload)
    noisy, n_flips = flip_bits(coded, ber, rng)
    recovered, n_corr = decode(noisy, len(payload))
    return recovered, n_flips, n_corr
