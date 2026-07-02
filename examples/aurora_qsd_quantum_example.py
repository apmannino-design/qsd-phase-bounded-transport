"""
Example: Aurora-QSD AI applied to quantum circuit simulation.

Requires: pip install qiskit qiskit-aer qiskit-ibm-runtime
"""

from aurora_qsd import QSDAuroraAgent
from aurora_qsd.core.constants import THETA_STAR_HW_DEG
from aurora_qsd.quantum.circuit_builder import build_deep_qsd_circuit, build_with_relock, zzz_score
from aurora_qsd.quantum.simulator import build_noisy_simulator, run_circuit, run_stress_test


def main():
    agent = QSDAuroraAgent()

    print(f"=== Aurora-QSD AI Quantum Example (θ*_hw = {THETA_STAR_HW_DEG}°) ===\n")

    plan = agent.plan_relock(depth=1241)
    print(plan.message)
    print()

    sim = build_noisy_simulator()
    shots = 8192

    counts = run_circuit(build_deep_qsd_circuit(layers=12), sim, shots)
    analysis = agent.analyze_counts(counts)
    print(f"QSD cell ZZZ: {zzz_score(counts):.4f}")
    print(analysis.message)
    print()

    counts_deep = run_circuit(build_with_relock(total_layers=35, relock_interval=7), sim, shots)
    print(f"Deep circuit (35L, re-lock /7) ZZZ: {zzz_score(counts_deep):.4f}")
    print()

    print("--- Stress Test (3 stages) ---")
    result = run_stress_test(shots=4096, layers=12, noisy=True)
    print(result.summary())

    print("\n--- Agent Query ---")
    resp = agent.query("explain how Aurora principle sustains coherence at depth 1241")
    print(resp.message[:400] + "...")


if __name__ == "__main__":
    main()
