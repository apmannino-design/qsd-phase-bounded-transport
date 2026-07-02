"""
Example: Aurora-QSD AI applied to quantum circuit simulation.

Requires: pip install qiskit qiskit-aer
"""

from aurora_qsd import QSDAuroraAgent, THETA_STAR_DEG
from aurora_qsd.quantum.circuit_builder import build_qsd_cell, build_with_relock, parity_score


def main():
    agent = QSDAuroraAgent()

    print(f"=== Aurora-QSD AI Quantum Example (θ* = {THETA_STAR_DEG:.2f}°) ===\n")

    # 1. Plan re-preparation for deep circuit
    plan = agent.plan_relock(depth=1241)
    print(plan.message)
    print()

    # 2. Build and simulate QSD circuit (if qiskit available)
    try:
        from qiskit import transpile
        from qiskit_aer import AerSimulator

        sim = AerSimulator()
        shots = 8192

        # Standard QSD cell
        qc = build_qsd_cell()
        result = sim.run(transpile(qc, sim), shots=shots).result()
        counts = result.get_counts()
        analysis = agent.analyze_counts(counts)
        print(analysis.message)
        print()

        # Deep circuit with Aurora re-lock
        qc_deep = build_with_relock(total_layers=35, relock_interval=7)
        result_deep = sim.run(transpile(qc_deep, sim), shots=shots).result()
        counts_deep = result_deep.get_counts()
        score = parity_score(counts_deep)
        print(f"Deep circuit (35 layers, re-lock every 7): parity = {score:.4f}")

    except ImportError:
        print("(Install qiskit + qiskit-aer to run circuit simulation)")

    # 3. Natural-language query
    print("\n--- Agent Query ---")
    resp = agent.query("explain how Aurora principle sustains coherence at depth 1241")
    print(resp.message)


if __name__ == "__main__":
    main()
