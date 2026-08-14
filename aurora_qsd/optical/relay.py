"""Two-hop LEO-A → LEO-B → OGS store-and-forward relay."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.optical.fec import transmit_protected
from aurora_qsd.optical.modem import flip_bits
from aurora_qsd.optical.pat import ControllerName
from aurora_qsd.optical.simulate import OpticalLink, ScenarioName


@dataclass
class HopResult:
    name: str
    model_ber: float
    n_flips: int
    intact: bool
    received: bytes
    n_corrected: int = 0


@dataclass
class RelayResult:
    payload: bytes
    received: bytes
    controller: str
    fec: bool
    intact: bool
    hops: list[HopResult]
    e2e_empirical_ber: float


class TwoHopRelay:
    """
    LEO-A → LEO-B (ISL) then LEO-B → OGS (downlink).

    Each hop uses the on-station BER of a simulated PAT loop. Optional
    Hamming(7,4) is applied per hop (decode/re-encode at the relay).
    """

    def __init__(
        self,
        controller: ControllerName = ControllerName.QSD,
        seed: int = 0,
        duration_s: float = 1.5,
        fec: bool = True,
    ):
        self.controller = controller
        self.fec = fec
        self.rng = np.random.default_rng(seed + 7)
        self.isl = OpticalLink(
            ScenarioName.ISL, controller=controller, seed=seed, duration_s=duration_s
        )
        self.down = OpticalLink(
            ScenarioName.DOWNLINK, controller=controller, seed=seed + 1, duration_s=duration_s
        )

    def send(self, payload: bytes) -> RelayResult:
        hops = []
        current = payload
        for name, link in (("isl", self.isl), ("downlink", self.down)):
            ber = link.instantaneous_ber()
            link.step()
            if self.fec:
                rec, n_flips, n_corr = transmit_protected(current, ber, self.rng)
            else:
                rec, n_flips = flip_bits(current, ber, self.rng)
                n_corr = 0
            hops.append(
                HopResult(
                    name=name,
                    model_ber=ber,
                    n_flips=n_flips,
                    intact=rec == current,
                    received=rec,
                    n_corrected=n_corr,
                )
            )
            current = rec

        n_bits = 8 * len(payload)
        # empirical e2e: Hamming distance of final vs original
        if n_bits == 0:
            e2e = 0.0
        else:
            a = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
            b = np.unpackbits(np.frombuffer(current, dtype=np.uint8))
            n = min(a.size, b.size)
            e2e = float(np.mean(a[:n] != b[:n]))
        return RelayResult(
            payload=payload,
            received=current,
            controller=self.controller.value,
            fec=self.fec,
            intact=current == payload,
            hops=hops,
            e2e_empirical_ber=e2e,
        )


def run_relay_campaign(
    message: str = "HELLO FROM LEO-1",
    seed: int = 0,
    duration_s: float = 1.5,
) -> dict:
    """Compare open/PID/QSD, with and without FEC, on the two-hop path."""
    payload = message.encode("utf-8")
    rows = []
    for fec in (False, True):
        for ctrl in (ControllerName.OPEN, ControllerName.PID, ControllerName.QSD):
            relay = TwoHopRelay(
                controller=ctrl, seed=seed, duration_s=duration_s, fec=fec
            )
            res = relay.send(payload)
            rows.append(
                {
                    "controller": ctrl.value,
                    "fec": fec,
                    "intact": res.intact,
                    "e2e_empirical_ber": res.e2e_empirical_ber,
                    "isl_ber": res.hops[0].model_ber,
                    "down_ber": res.hops[1].model_ber,
                    "isl_flips": res.hops[0].n_flips,
                    "down_flips": res.hops[1].n_flips,
                    "n_corrected": res.hops[0].n_corrected + res.hops[1].n_corrected,
                    "received": res.received.decode("latin-1", errors="replace"),
                }
            )

    def _row(ctrl: str, fec: bool) -> dict:
        return next(r for r in rows if r["controller"] == ctrl and r["fec"] is fec)

    q_fec = _row("qsd", True)
    o_fec = _row("open", True)
    q_raw = _row("qsd", False)
    p_fec = _row("pid", True)

    def pack(tag, passed, detail):
        return {
            "test": tag,
            "passed": bool(passed),
            "verdict": "PASS" if passed else "NULL",
            "detail": detail,
        }

    verdicts = {
        "R1_fec_helps_qsd": pack(
            "R1",
            q_fec["e2e_empirical_ber"] <= q_raw["e2e_empirical_ber"],
            f"QSD e2e BER FEC {q_fec['e2e_empirical_ber']:.2e} vs raw {q_raw['e2e_empirical_ber']:.2e}",
        ),
        "R2_qsd_fec_beats_open_fec": pack(
            "R2",
            q_fec["intact"] or q_fec["e2e_empirical_ber"] <= o_fec["e2e_empirical_ber"],
            f"QSD FEC intact={q_fec['intact']} BER={q_fec['e2e_empirical_ber']:.2e} "
            f"vs open intact={o_fec['intact']} BER={o_fec['e2e_empirical_ber']:.2e}",
        ),
        "R3_pid_and_qsd_survive_or_null": pack(
            "R3",
            q_fec["intact"] or p_fec["intact"],
            f"QSD intact={q_fec['intact']} PID intact={p_fec['intact']} (PASS if either FEC hop-pair delivers)",
        ),
    }
    n_pass = sum(1 for v in verdicts.values() if v["passed"])
    return {
        "rows": rows,
        "verdicts": verdicts,
        "notes": f"Two-hop relay: {n_pass}/3 PASS. Hamming(7,4) per hop; store-and-forward.",
    }
