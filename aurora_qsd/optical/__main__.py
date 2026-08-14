"""CLI: python -m aurora_qsd.optical [--all | --scenario isl] [--seconds 4]."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from aurora_qsd.optical.pat import ControllerName
from aurora_qsd.optical.pll import compare_feedforward, run_pll_campaign
from aurora_qsd.optical.relay import TwoHopRelay, run_relay_campaign
from aurora_qsd.optical.simulate import ScenarioName, run_campaign, run_scenario, write_campaign
from aurora_qsd.optical.terminal import OpticalTerminal


def _print_result(res) -> None:
    print(f"\n=== {res.scenario} ===")
    print(res.notes)
    print(f"  PAT Aurora: {res.aurora['recommendation']}")
    print(
        f"  {'ctrl':<12} {'mean μrad':>10} {'rms μrad':>10} {'avail':>8} "
        f"{'BER':>10} {'SNR dB':>8} {'ISS1':>8} {'acq':>6}"
    )
    for run in res.runs.values():
        print(
            f"  {run.name:<12} {run.mean_err_urad:10.3f} {run.rms_err_urad:10.3f} "
            f"{100 * run.availability:7.1f}% {run.mean_ber:10.2e} {run.mean_snr_db:8.2f} "
            f"{run.one_step_iss:8.3f} {run.acquisition_samples:6d}"
        )
    print("  Pre-registered tests:")
    for v in res.verdicts.values():
        print(f"    {v['test']}: {v['verdict']} — {v['detail']}")


def _print_pll(res) -> None:
    print(f"\n=== pll ===")
    print(res.notes)
    print(
        f"  {'ctrl':<12} {'rms rad':>10} {'slips':>8} {'BPSK BER':>10} {'ISS1':>8}"
    )
    for run in res.runs.values():
        print(
            f"  {run.name:<12} {run.rms_rad:10.3f} {run.cycle_slips:8d} "
            f"{run.mean_bpsk_ber:10.2e} {run.one_step_iss:8.3f}"
        )
    for v in res.verdicts.values():
        print(f"    {v['test']}: {v['verdict']} — {v['detail']}")


def _write_pll_artifacts(pll, ff_cmp: dict, out_dir: Path) -> None:
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    q = pll.runs["qsd"]
    p = pll.runs["pid"]
    o = pll.runs["open"]
    with (out_dir / "timeseries_pll.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "qsd_phase_rad", "pid_phase_rad", "open_phase_rad"])
        for i in range(len(q.t)):
            w.writerow([q.t[i], q.phase_err_rad[i], p.phase_err_rad[i], o.phase_err_rad[i]])
    rows = []
    for run in pll.runs.values():
        rows.append(
            {
                "controller": run.name,
                "rms_rad": run.rms_rad,
                "cycle_slips": run.cycle_slips,
                "mean_bpsk_ber": run.mean_bpsk_ber,
                "one_step_iss": run.one_step_iss,
                "feedforward": run.feedforward,
            }
        )
    with (out_dir / "optical_pll_summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    vrows = [{"suite": "pll", **v} for v in pll.verdicts.values()]
    vrows.append(
        {
            "suite": "pll",
            "test": ff_cmp["test"],
            "passed": ff_cmp["passed"],
            "verdict": ff_cmp["verdict"],
            "detail": ff_cmp["detail"],
        }
    )
    with (out_dir / "optical_pll_verdicts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(vrows[0].keys()))
        w.writeheader()
        w.writerows(vrows)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9.0, 3.6))
        ax.plot(o.t * 1e3, o.phase_err_rad, label="open", color="#888888", lw=1.0)
        ax.plot(p.t * 1e3, p.phase_err_rad, label="pid", color="#1f77b4", lw=1.0)
        ax.plot(q.t * 1e3, q.phase_err_rad, label="qsd", color="#d62728", lw=1.0)
        ax.set_xlabel("t (ms)")
        ax.set_ylabel("carrier phase error (rad)")
        ax.set_title("Optical PLL residual (Costas-rate, Doppler FF on)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_dir / "pll_phase.png", dpi=140)
        plt.close(fig)
    except ImportError:
        print("matplotlib not installed; skipping PLL figure")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="QSD satellite optical-link prototype (simulation)")
    p.add_argument("--scenario", choices=[s.value for s in ScenarioName], default=None)
    p.add_argument("--all", action="store_true", help="Run ISL + downlink + stress + PLL + relay")
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

    pll = run_pll_campaign(seed=args.seed, feedforward=True)
    _print_pll(pll)
    ff_cmp = compare_feedforward(seed=args.seed)
    print(f"    {ff_cmp['test']}: {ff_cmp['verdict']} — {ff_cmp['detail']}")

    relay = run_relay_campaign(message=args.ping, seed=args.seed, duration_s=min(args.seconds, 1.5))
    print(f"\n=== relay ===")
    print(relay["notes"])
    for row in relay["rows"]:
        tag = "FEC" if row["fec"] else "raw"
        flag = "intact" if row["intact"] else f"e2e BER={row['e2e_empirical_ber']:.2e}"
        print(f"  {row['controller']:<10} {tag:<4}  {flag}")
    for v in relay["verdicts"].values():
        print(f"    {v['test']}: {v['verdict']} — {v['detail']}")

    if not args.no_write:
        args.out.mkdir(parents=True, exist_ok=True)
        write_campaign(results, args.out)
        _write_pll_artifacts(pll, ff_cmp, args.out)
        with (args.out / "optical_relay_summary.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(relay["rows"][0].keys()))
            w.writeheader()
            w.writerows(relay["rows"])
        with (args.out / "optical_relay_verdicts.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["test", "passed", "verdict", "detail"])
            w.writeheader()
            w.writerows(relay["verdicts"].values())
        print(f"\nWrote artifacts to {args.out.resolve()}")

    print("\n--- packet demo (on-station ISL, Hamming off/on) ---")
    for fec in (False, True):
        for ctrl in (ControllerName.OPEN, ControllerName.PID, ControllerName.QSD):
            term = OpticalTerminal(
                controller=ctrl,
                seed=args.seed,
                duration_s=min(args.seconds, 2.0),
                fec=fec,
            )
            xfer = term.ping(args.ping)
            status = "intact" if xfer.intact else f"{xfer.n_flips} channel flips"
            print(
                f"  {ctrl.value:<10} fec={str(fec):<5} model BER={xfer.model_ber:.2e}  "
                f"recv={xfer.received!r}  ({status})"
            )
    print("\n--- two-hop QSD+FEC ---")
    hop = TwoHopRelay(controller=ControllerName.QSD, seed=args.seed, fec=True)
    xfer = hop.send(args.ping.encode("utf-8"))
    print(
        f"  intact={xfer.intact}  recv={xfer.received!r}  "
        f"ISL BER={xfer.hops[0].model_ber:.2e}  down BER={xfer.hops[1].model_ber:.2e}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
