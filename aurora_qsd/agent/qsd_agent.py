"""Main QSD/Aurora AI agent for quantum computing applications."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG, DEFAULT_K_GAIN, DEFAULT_RHO
from aurora_qsd.core.tridelta import decompose_covariance, TriDelta
from aurora_qsd.core.aurora import check_aurora_condition
from aurora_qsd.core.iss import iss_bound, iss_trajectory
from aurora_qsd.core.phase_potential import phase_potential, phase_force, basin_boundary_deg
from aurora_qsd.quantum.analyzer import QuantumQSDAnalyzer, AnalysisReport
from aurora_qsd.quantum.relock_advisor import RelockAdvisor, RelockPlan
from aurora_qsd.agent.prompts import QSD_KNOWLEDGE, INTENT_PATTERNS


@dataclass
class AgentResponse:
    """Structured response from the QSD/Aurora agent."""

    intent: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "intent": self.intent,
                "message": self.message,
                "data": self.data,
                "recommendations": self.recommendations,
            },
            indent=2,
            default=str,
        )


class QSDAuroraAgent:
    """
    AI agent applying QSD stabilization dynamics and Aurora principle to quantum computing.

    Capabilities:
      - Natural-language query routing
      - Covariance/measurement analysis via TriDelta
      - Aurora condition checking and re-lock planning
      - Circuit parameter optimization
      - ISS convergence prediction
      - Knowledge retrieval about QSD/Aurora framework
    """

    def __init__(
        self,
        theta_target: float = THETA_STAR,
        rho: float = DEFAULT_RHO,
        k_gain: float = DEFAULT_K_GAIN,
        t2_us: float = 100.0,
    ):
        self.theta_target = theta_target
        self.rho = rho
        self.k_gain = k_gain
        self.t2_us = t2_us
        self.analyzer = QuantumQSDAnalyzer(theta_target=theta_target, rho=rho, t2_us=t2_us)
        self.relock_advisor = RelockAdvisor(rho=rho)

    def query(self, text: str, context: dict[str, Any] | None = None) -> AgentResponse:
        """Process a natural-language query about QSD/Aurora quantum computing."""
        context = context or {}
        intent = self._classify_intent(text.lower())
        handler = getattr(self, f"_handle_{intent}", self._handle_explain)
        return handler(text, context)

    def analyze_counts(self, counts: dict[str, int]) -> AgentResponse:
        """Analyze measurement counts through QSD pipeline."""
        report = self.analyzer.from_counts(counts)
        return AgentResponse(
            intent="analyze",
            message=report.summary(),
            data={
                "theta_deg": report.theta_deg,
                "alignment_error_deg": report.alignment_error_deg,
                "parity": report.parity,
                "aurora_satisfied": report.aurora_satisfied,
                "tri_delta": {
                    "delta_j": report.tri_delta.delta_j,
                    "delta_l": report.tri_delta.delta_l,
                    "delta_x": report.tri_delta.delta_x,
                    "delta_e": report.tri_delta.delta_e,
                    "heron": report.tri_delta.heron,
                },
            },
            recommendations=report.recommendations,
        )

    def analyze_covariance(self, sigma: np.ndarray) -> AgentResponse:
        """Analyze a covariance matrix."""
        report = self.analyzer.from_covariance(sigma)
        return AgentResponse(
            intent="analyze",
            message=report.summary(),
            data={"theta_deg": report.theta_deg},
            recommendations=report.recommendations,
        )

    def plan_relock(self, depth: int, t2_us: float | None = None) -> AgentResponse:
        """Generate re-preparation plan for a circuit depth."""
        plan = self.relock_advisor.plan(depth, t2_us=t2_us or self.t2_us)
        return AgentResponse(
            intent="relock",
            message=plan.summary(),
            data={
                "relock_interval": plan.relock_interval_layers,
                "n_cycles": plan.n_relock_cycles,
                "expected_zzz": plan.expected_zzz_floor,
                "aurora_satisfied": plan.aurora_satisfied,
            },
            recommendations=[
                f"Re-prepare every {plan.relock_interval_layers} layers",
                f"Expected ZZZ floor: {plan.expected_zzz_floor:.3f}",
            ],
        )

    def optimize_theta(
        self,
        sweep_deg: tuple[float, float] = (-5.0, 5.0),
        n_points: int = 11,
    ) -> AgentResponse:
        """Recommend optimal θ near θ* based on phase potential landscape."""
        angles = np.linspace(
            self.theta_target + np.radians(sweep_deg[0]),
            self.theta_target + np.radians(sweep_deg[1]),
            n_points,
        )
        potentials = [float(phase_potential(a)) for a in angles]
        forces = [abs(float(phase_force(a))) for a in angles]
        best_idx = int(np.argmin(potentials))

        return AgentResponse(
            intent="optimize",
            message=(
                f"Optimal angle: {np.degrees(angles[best_idx]):.4f}° "
                f"(V={potentials[best_idx]:.4f}, nearest to θ*={THETA_STAR_DEG:.4f}°)"
            ),
            data={
                "optimal_theta_deg": float(np.degrees(angles[best_idx])),
                "theta_star_deg": THETA_STAR_DEG,
                "sweep": [
                    {"theta_deg": float(np.degrees(a)), "potential": p, "force": f}
                    for a, p, f in zip(angles, potentials, forces)
                ],
            },
            recommendations=[
                f"Set source angle to {np.degrees(angles[best_idx]):.4f}°",
                "Verify with ZZZ parity measurement on target hardware",
            ],
        )

    def check_aurora(self, t2_us: float | None = None, rho: float | None = None) -> AgentResponse:
        """Check Aurora condition for current hardware parameters."""
        cond = check_aurora_condition(
            rho=rho or self.rho,
            t2_us=t2_us or self.t2_us,
        )
        return AgentResponse(
            intent="analyze",
            message=cond.recommendation,
            data={
                "gamma_lock": cond.gamma_lock,
                "gamma_loss": cond.gamma_loss,
                "satisfied": cond.satisfied,
                "loss_fraction": cond.loss_fraction_bound,
            },
            recommendations=[cond.recommendation],
        )

    def simulate_iss(
        self,
        e0_deg: float = 10.0,
        steps: int = 15,
        disturbance_deg: float = 0.0,
    ) -> AgentResponse:
        """Simulate closed-loop ISS convergence toward θ*."""
        e0 = np.radians(e0_deg)
        disturbance = np.radians(disturbance_deg)
        open_loop = [e0 + np.random.normal(0, np.radians(4.5)) for _ in range(steps)]
        closed_loop = [e0]
        for _ in range(steps - 1):
            closed_loop.append(
                closed_loop[-1] - self.k_gain * (closed_loop[-1] - 0.0)
            )

        bounds = iss_trajectory(e0, steps, self.rho, disturbance)

        return AgentResponse(
            intent="simulate",
            message=(
                f"ISS simulation: {steps} steps, e₀={e0_deg}°, ρ={self.rho}\n"
                f"Final closed-loop error: {np.degrees(closed_loop[-1]):.4f}°\n"
                f"ISS bound at t={steps}: {np.degrees(bounds[-1]):.4f}°"
            ),
            data={
                "open_loop_deg": [float(np.degrees(e)) for e in open_loop],
                "closed_loop_deg": [float(np.degrees(e)) for e in closed_loop],
                "iss_bounds_deg": [float(np.degrees(b)) for b in bounds],
            },
            recommendations=[
                "Closed-loop feedback u̇ = -k·(θ - θ*) provides exponential convergence",
                f"Use k_gain={self.k_gain} for hardware-validated performance",
            ],
        )

    def get_knowledge(self) -> str:
        return QSD_KNOWLEDGE

    def _classify_intent(self, text: str) -> str:
        for intent, patterns in INTENT_PATTERNS.items():
            if any(p in text for p in patterns):
                return intent
        return "explain"

    def _handle_analyze(self, text: str, context: dict) -> AgentResponse:
        if "counts" in context:
            return self.analyze_counts(context["counts"])
        if "sigma" in context:
            return self.analyze_covariance(np.asarray(context["sigma"]))
        if "t2" in text.lower() or "aurora" in text.lower():
            t2 = self._extract_number(text, default=self.t2_us)
            return self.check_aurora(t2_us=t2)
        return AgentResponse(
            intent="analyze",
            message=(
                "Provide measurement counts or a covariance matrix for QSD analysis.\n"
                "Example: agent.analyze_counts({'00': 15000, '01': 2000, '10': 2000, '11': 13000})"
            ),
            recommendations=["Pass counts dict or 3×3 covariance matrix in context"],
        )

    def _handle_optimize(self, text: str, context: dict) -> AgentResponse:
        return self.optimize_theta()

    def _handle_circuit(self, text: str, context: dict) -> AgentResponse:
        depth = int(self._extract_number(text, default=35))
        plan = self.plan_relock(depth)
        return AgentResponse(
            intent="circuit",
            message=(
                f"QSD circuit design for depth {depth}:\n"
                f"  1. Initialize at θ* = {THETA_STAR_DEG:.2f}°\n"
                f"  2. QSD cell: RY(2θ*) → CX → RZ(θ*) → CX\n"
                f"  3. {plan.summary()}"
            ),
            data={"depth": depth, "relock_plan": plan.relock_interval_layers},
            recommendations=plan.summary().split("\n")[1:],
        )

    def _handle_relock(self, text: str, context: dict) -> AgentResponse:
        depth = int(context.get("depth", self._extract_number(text, default=1241)))
        return self.plan_relock(depth)

    def _handle_simulate(self, text: str, context: dict) -> AgentResponse:
        return self.simulate_iss()

    def _handle_explain(self, text: str, context: dict) -> AgentResponse:
        topic = self._identify_topic(text)
        explanations = {
            "theta_star": (
                f"θ* = arctan(√2 - 1) = {THETA_STAR_DEG:.4f}° is the QSD lock point — "
                "the deepest well of V(Θ) = -cos Θ - (1/3)sin(3Θ). "
                "At θ*, force F(Θ) = 0 and entropy production vanishes (Aurora zero-dissipation)."
            ),
            "aurora": (
                "The Aurora Principle: phase-match faster than you dissipate. "
                "When Γ_lock > Γ_loss, the QSD basin returns to θ* before decoherence "
                "extracts energy. Periodic re-preparation sustains coherence at arbitrary depth."
            ),
            "iss": (
                "Input-to-State Stability: ||e_t|| ≤ ρ^(t/2)||e_0|| + D/(1-√ρ). "
                "Guarantees exponential convergence to a disturbance ball around θ* "
                "under sector-bounded feedback u̇ = -k·(θ - θ*)."
            ),
            "tridelta": (
                "TriDelta (∆J, ∆L, ∆X) decomposes covariance Σ via orthogonal projectors. "
                "θ = arctan(∆J/R) is the partition angle. Heron closure certifies geometric consistency."
            ),
            "relock": (
                "Periodic re-preparation resets qubits to basin center every ℓ layers. "
                "ibm_fez validation: re-lock every 7 layers sustains ZZZ=+0.672 at depth 1241."
            ),
        }
        msg = explanations.get(topic, QSD_KNOWLEDGE[:500] + "...")
        return AgentResponse(
            intent="explain",
            message=msg,
            data={"topic": topic, "theta_star_deg": THETA_STAR_DEG, "basin_boundary_deg": basin_boundary_deg()},
        )

    def _identify_topic(self, text: str) -> str:
        if any(w in text for w in ["theta", "θ", "lock point", "22.48", "22.47"]):
            return "theta_star"
        if "aurora" in text:
            return "aurora"
        if "iss" in text or "stability" in text or "convergence" in text:
            return "iss"
        if "tridelta" in text or "tri-delta" in text or "covariance" in text:
            return "tridelta"
        if "relock" in text or "re-prepar" in text or "sunscreen" in text:
            return "relock"
        return "general"

    @staticmethod
    def _extract_number(text: str, default: float = 0.0) -> float:
        nums = re.findall(r"[\d.]+", text)
        return float(nums[0]) if nums else default
