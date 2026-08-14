"""CLI: python -m aurora_qsd.optical [--all | --scenario isl] [--seconds 4]."""

from __future__ import annotations

import argparse
from pathlib import Path

from aurora_qsd.optical.pat import ControllerName
from aurora_qsd.optical.simulate import ScenarioName, run_campaign, run_scenario, write_campaign
from aurora_qsd.optical.terminal import OpticalTerminal


def _print_result(res) -> None:
    print(f"\n=== {res.scenario} ===")
    print(res.notes)
    print(f"  PAT Aurora: {res.aurora['recommendation']}")
    print(
        f"  {'ctrl':<12} {'mean μrad':>10} {'rms μrad':>10} {'avail':>8} "
        f"{'BER':>10} {'SNR dB':>8} {'ISS cov':>8} {'acq':>6}"
    )
    for run in res.runs.values():
        print(
            f"  {run.name:<12} {run.mean_err_urad:10.3f} {run.rms_err_urad:10.3f} "
            f"{100 * run.availability:7.1f}% {run.mean_ber:10.2e} {run.mean_snr_db:8.2f} "
            f"{run.iss_coverage:8.3f} {run.acquisition_samples:6d}"
        )
    print("  Pre-registered tests:")
    for v in res.verdicts.values():
        print(f"    {v['test']}: {v['verdict']} — {v['detail']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="QSD satellite optical-link prototype (simulation)")
    p.add_argument("--scenario", choices=[s.value for s in ScenarioName], default=None)
    p.add_argument("--all", action="store_true", help="Run ISL + downlink + stress (default)")
    p.add_argument("--seconds", type=float, default=4.0)
    p.add_argument("--dt", type=float, default=0.002)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("results/optical"),
        help="Directory for CSV/PNG artifacts",
    )
    p.add_argument("--ping", type=str, default="HELLO FROM LEO-1", help="Packet demo payload")
    p.add_argument("--no-write", action="store_true")
    args = p.parse_args(argv)

    if args.scenario and not args.all:
        res = run_scenario(
            ScenarioName(args.scenario),
            duration_s=args.seconds,
            dt=args.dt,
            seed=args.seed,
        )
        results = {res.scenario: res}
        _print_result(res)
    else:
        results = run_campaign(duration_s=args.seconds, dt=args.dt, seed=args.seed)
        for res in results.values():
            _print_result(res)

    if not args.no_write:
        args.out.mkdir(parents=True, exist_ok=True)
        write_campaign(results, args.out)
        print(f"\nWrote artifacts to {args.out.resolve()}")

    print("\n--- packet demo ---")
    for ctrl in (ControllerName.OPEN, ControllerName.PID, ControllerName.QSD):
        term = OpticalTerminal(controller=ctrl, seed=args.seed, duration_s=min(args.seconds, 2.0))
        xfer = term.ping(args.ping)
        status = "intact" if xfer.intact else f"{xfer.n_flips} bit flips"
        print(
            f"  {ctrl.value:<10} model BER={xfer.model_ber:.2e}  "
            f"recv={xfer.received!r}  ({status})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
