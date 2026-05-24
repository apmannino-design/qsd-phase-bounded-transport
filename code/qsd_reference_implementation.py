import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (NoiseModel, depolarizing_error, 
                               amplitude_damping_error, phase_damping_error)
from qiskit_ibm_runtime.fake_provider import FakeFez

THETA_STAR   = 22.47 * (np.pi / 180)
SHOTS        = 32768
STEPS        = 15
K_GAIN       = 0.45

def build_apocalyptic_noise_model():
    base_backend = FakeFez()
    noise_model = NoiseModel.from_backend(base_backend)
    t1_loss = amplitude_damping_error(0.25)
    t2_loss = phase_damping_error(0.35)
    dp_1q   = depolarizing_error(0.20, 1)
    dp_2q   = depolarizing_error(0.40, 2)
    single_qubit_noise = dp_1q.compose(t1_loss).compose(t2_loss)
    noise_model.add_all_qubit_quantum_error(single_qubit_noise, ['u1','u2','u3','ry','rx','rz','h','x'])
    noise_model.add_all_qubit_quantum_error(dp_2q, ['cx','ecr'])
    return noise_model

def build_deep_qsd_circuit(theta, layers=12):
    qc = QuantumCircuit(2, 2)
    for _ in range(layers):
        qc.ry(2 * theta, 0)
        qc.ry(2 * (np.pi / 2 - theta), 1)
        qc.cx(0, 1)
        qc.rz(theta, 0)
        qc.rz(np.pi / 2 - theta, 1)
        qc.cx(1, 0)
    qc.measure([0, 1], [0, 1])
    return qc

def build_unmanaged_baseline(layers=12):
    qc = QuantumCircuit(2, 2)
    for _ in range(layers):
        qc.h(0)
        qc.h(1)
        qc.cx(0, 1)
        qc.rz(np.pi / 4, 0)
        qc.rz(np.pi / 4, 1)
        qc.cx(1, 0)
    qc.measure([0, 1], [0, 1])
    return qc

def score(counts):
    total = sum(counts.values())
    return (counts.get('00', 0) + counts.get('11', 0)) / total

print("=" * 70)
print(" APOCALYPTIC STRESS TEST — FakeFez + 20/25/35/40% noise stack")
print(f" theta* = {np.degrees(THETA_STAR):.2f}° | shots = {SHOTS} | layers = 12")
print("=" * 70)

nm  = build_apocalyptic_noise_model()
sim = AerSimulator(noise_model=nm)

print("\n[STAGE 1] Baseline...")
b_scores = []
for i in range(5):
    qc = transpile(build_unmanaged_baseline(), sim, optimization_level=0)
    b_scores.append(score(sim.run(qc, shots=SHOTS).result().get_counts()))
bs = np.mean(b_scores)
print(f" Baseline: {bs:.6f} ± {np.std(b_scores):.6f}")

print("\n[STAGE 2] Sweep...")
print(f"  {'Angle':>10} | {'Score':>10} | {'Gain':>10} | Status")
print("  " + "-" * 48)
sweep_results = []
for d in np.linspace(-8, 8, 17):
    theta = THETA_STAR + np.radians(d)
    ss = []
    for _ in range(3):
        qc = transpile(build_deep_qsd_circuit(theta), sim, optimization_level=0)
        ss.append(score(sim.run(qc, shots=SHOTS).result().get_counts()))
    s = np.mean(ss)
    g = s - bs
    marker = " [TARGET LOCK]" if abs(d) < 0.1 else ""
    print(f"  {np.degrees(theta):>10.2f} | {s:>10.6f} | {g:>+10.6f} | {'✅' if g>0 else '❌'}{marker}")
    sweep_results.append((theta, s, g))

print("\n[STAGE 3] ISS Convergence...")
print(f"  {'Step':<6} | {'Open θ':>10} | {'Closed θ':>10} | {'Gain':>12}")
print("  " + "-" * 46)
theta_open   = 45.0 * (np.pi / 180)
theta_closed = 45.0 * (np.pi / 180)
for k in range(1, STEPS + 1):
    theta_open += np.random.normal(0, np.radians(4.5))
    theta_closed -= K_GAIN * (theta_closed - THETA_STAR)
    os_, cs_ = [], []
    for _ in range(2):
        qo = transpile(build_deep_qsd_circuit(theta_open),   sim, optimization_level=0)
        qc = transpile(build_deep_qsd_circuit(theta_closed), sim, optimization_level=0)
        os_.append(score(sim.run(qo, shots=SHOTS).result().get_counts()))
        cs_.append(score(sim.run(qc, shots=SHOTS).result().get_counts()))
    g = np.mean(cs_) - np.mean(os_)
    print(f"  {k:<6} | {np.degrees(theta_open):>10.2f} | {np.degrees(theta_closed):>10.2f} | {g:>+12.6f}")

best = max(sweep_results, key=lambda x: x[2])
passed = sum(1 for _,_,g in sweep_results if g > 0)
print("\n" + "=" * 70)
print(f" Best angle  : {np.degrees(best[0]):.4f}°  (locked: {np.degrees(THETA_STAR):.2f}°)")
print(f" Best gain   : {best[2]:+.6f}")
print(f" Sweep passes: {passed}/17")
print(f" VERDICT     : {'✅ COHERENCE RECOVERED' if passed >= 8 else '❌ UNABLE TO RECOVER'}")
print("=" * 70)
