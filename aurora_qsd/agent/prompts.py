"""QSD/Aurora knowledge base for agent reasoning."""

QSD_KNOWLEDGE = """
# Quantum Stabilization Dynamics (QSD) + Aurora Principle

## Core Concepts

**TriDelta Decomposition**: Any positive-semidefinite covariance Σ decomposes into
(∆J, ∆L, ∆X) via orthogonal projectors, yielding partition angle θ = arctan(∆J/R)
where R = √(∆L² + ∆X²).

**Lock Point θ***: θ* = arctan(√2 - 1) ≈ 22.48° — the deepest well of the third-harmonic
phase potential V(Θ) = -cos Θ - (1/3)sin(3Θ). At θ*, instantaneous entropy production
is zero (Aurora zero-dissipation point).

**ISS Bound (Theorem 6)**: ||e_t|| ≤ ρ^(t/2)||e_0|| + D/(1-√ρ) — exponential convergence
to disturbance ball around θ* under sector-bounded feedback.

**Aurora Principle**: Phase-match faster than you dissipate. When Γ_lock > Γ_loss
(contraction rate exceeds decoherence rate), periodic re-preparation sustains coherence
indefinitely without error correction.

## Quantum Hardware Application

1. Initialize qubits at θ* via RY(2θ*) gates (alternating θ and π/2-θ)
2. Apply QSD cell: RY → CX → RZ → CX with θ = θ*
3. Re-prepare (reset to basin center) every 7 layers for deep circuits
4. Monitor ZZZ parity as coherence proxy
5. Closed-loop: u̇ = -k·(θ - θ*) when drift detected

## Validated Results (ibm_fez, 129 qubits)
- Basin-optimized θ: 22.47° (|∆tan| = 0.0006)
- Median ZZZ: +0.911 (3× improvement)
- Depth 1241 with re-lock every 7: ZZZ = +0.672 sustained
"""

INTENT_PATTERNS = {
    "analyze": ["analyze", "analysis", "check", "evaluate", "measure", "diagnose"],
    "basin": ["basin", "basin sweep", "find peak", "empirical angle"],
    "optimize": ["optimize", "tune", "adjust", "calibrate", "improve", "sweep"],
    "circuit": ["circuit", "build", "construct", "generate", "design"],
    "relock": ["relock", "re-prepare", "reprepare", "sunscreen", "refresh", "reset"],
    "explain": ["explain", "what is", "how does", "describe", "tell me about"],
    "simulate": ["simulate", "run", "test", "stress", "benchmark"],
}
