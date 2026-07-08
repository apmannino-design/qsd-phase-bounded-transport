"""Command-line interface for the Aurora-QSD AI agent."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.agent.qsd_agent import QSDAuroraAgent
from aurora_qsd.core.constants import THETA_STAR_DEG


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aurora-QSD AI: QSD stabilization + Aurora principle for quantum computing",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # query
    q = sub.add_parser("query", help="Natural-language query to the agent")
    q.add_argument("text", nargs="+", help="Query text")

    # analyze
    a = sub.add_parser("analyze", help="Analyze measurement counts")
    a.add_argument("--counts", type=str, help='JSON counts, e.g. \'{"00":15000,"11":13000}\'')

    # aurora
    sub.add_parser("aurora", help="Check Aurora condition")

    # optimize
    sub.add_parser("optimize", help="Optimize partition angle near θ*")

    # relock
    r = sub.add_parser("relock", help="Plan re-preparation strategy")
    r.add_argument("--depth", type=int, default=1241, help="Circuit depth")

    # simulate
    sub.add_parser("simulate", help="Simulate ISS convergence")

    # demo
    sub.add_parser("demo", help="Run full demonstration")

    args = parser.parse_args(argv)
    agent = QSDAuroraAgent()

    if args.command == "query":
        resp = agent.query(" ".join(args.text))
    elif args.command == "analyze":
        counts = json.loads(args.counts) if args.counts else {"00": 14000, "01": 2500, "10": 2500, "11": 13000}
        resp = agent.analyze_counts(counts)
    elif args.command == "aurora":
        resp = agent.check_aurora()
    elif args.command == "optimize":
        resp = agent.optimize_theta()
    elif args.command == "relock":
        resp = agent.plan_relock(args.depth)
    elif args.command == "simulate":
        resp = agent.simulate_iss()
    elif args.command == "demo":
        _run_demo(agent)
        return 0
    else:
        parser.print_help()
        return 1

    print(resp.message)
    if resp.recommendations:
        print("\nRecommendations:")
        for rec in resp.recommendations:
            print(f"  • {rec}")
    return 0


def _run_demo(agent: QSDAuroraAgent) -> None:
    print("=" * 70)
    print(" Aurora-QSD AI — Quantum Computing Demonstration")
    print(f" θ* = {THETA_STAR_DEG:.4f}° | Aurora: phase-match faster than you dissipate")
    print("=" * 70)

    demos = [
        ("Explain θ* lock point", lambda: agent.query("explain the theta star lock point")),
        ("Check Aurora condition", lambda: agent.check_aurora()),
        ("Optimize partition angle", lambda: agent.optimize_theta()),
        ("Analyze sample counts", lambda: agent.analyze_counts(
            {"00": 15000, "01": 2000, "10": 2000, "11": 13000}
        )),
        ("Plan re-lock for depth 1241", lambda: agent.plan_relock(1241)),
        ("Simulate ISS convergence", lambda: agent.simulate_iss()),
    ]

    for title, fn in demos:
        print(f"\n--- {title} ---")
        resp = fn()
        print(resp.message)
        if resp.recommendations:
            for rec in resp.recommendations[:2]:
                print(f"  → {rec}")

    print("\n" + "=" * 70)
    print(" Demo complete. Use 'python -m aurora_qsd.cli <command>' for individual tools.")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
