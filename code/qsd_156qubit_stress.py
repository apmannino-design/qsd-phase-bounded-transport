import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (NoiseModel, depolarizing_error, 
                               amplitude_damping_error, phase_damping_error)
from qiskit_ibm_runtime.fake_provider import FakeFez

THETA_STAR   = 22.47 * (np.pi / 180)
SHOTS        = 8192
MAX_DEPTH    = 100
STEPS        = 10
K_GAIN       = 0.45

def build_global_apocalyptic_noise(backend):
    noise_model = NoiseModel.from_backend(backend)
    t1_loss = amplitude_damping_error(0.30)
    t2_loss = phase_damping_error(0.40)
    dp_1q   = depolarizing_error(0.25, 1)
    dp_2q   = depolarizing_error(0.50, 2)
    single_qubit_noise = dp_1q.compose(t1_loss).compose(t2_loss)
    noise_model.add_all_qubit_quantum_error(single_qubit_noise, ['u1','u2','u3','ry','rx','rz','h','x'])
    noise_model.add_all_qubit_quantum_error(dp_2q, ['cx','ecr'])
    return noise_model

def build_full_lattice_qsd_circuit(num_qubits, coupling_map, theta, depth):
    qc = QuantumCircuit(num_qubits, num_qubits)
    for i in range(num_qubits):
        if i % 2 == 0:
            qc.ry(2 * theta, i)
        else:
            qc.ry(2 * (np.pi / 2 - theta), i)
    for _ in range(depth):
        edge_count = 0
        for pair in coupling_map:
            if edge_count % 3 == 0 and pair[0] < num_qubits and pair[1] < num_qubits:
                qc.cx(pair[0], pair[1])
            edge_count += 1
        for i in range(num_qubits):
            if i % 2 == 0:
                qc.rz(theta, i)
            else:
                qc.rz(np.pi / 2 - theta, i)
    qc.measure(range(num_qubits), range(num_qubits))
    return qc

def calculate_global_coherence_index(counts, num_qubits):
    total_shots = sum(counts.values())
    parity_sum = 0
    for bitstring, count in counts.items():
        ones = bitstring.count('1')
        zeros = num_qubits - ones
        polarization = abs(zeros - ones) / num_qubits
        parity_sum += polarization * count
    return parity_sum / total_shots

print("=" * 75)
print(" GLOBAL LATTICE STRESS ENGINE — 156 QUBITS")
print(f" Depth: {MAX_DEPTH} | Shots: {SHOTS} | Steps: {STEPS} | theta*={np.degrees(THETA_STAR):.2f}°")
print("=" * 75)

backend_device = FakeFez()
num_qubits   = 29
coupling_map = backend_device.configuration().coupling_map

print(f" Qubits: {num_qubits} | Coupling pairs: {len(coupling_map)}")

catastrophic_noise = build_global_apocalyptic_noise(backend_device)
simulator = AerSimulator(noise_model=catastrophic_noise)

print(f"\n{'Step':<6} | {'Open θ':>10} | {'Closed θ':>10} | {'Coherence Delta':>16}")
print("-" * 52)

theta_open   = 45.0 * (np.pi / 180)
theta_closed = 45.0 * (np.pi / 180)

for step in range(1, STEPS + 1):
    theta_open   += np.random.normal(0, np.radians(5.0))
    theta_closed -= K_GAIN * (theta_closed - THETA_STAR)

    qc_open   = build_full_lattice_qsd_circuit(num_qubits, coupling_map, theta_open,   depth=MAX_DEPTH)
    qc_closed = build_full_lattice_qsd_circuit(num_qubits, coupling_map, theta_closed, depth=MAX_DEPTH)

    compiled_open   = transpile(qc_open,   optimization_level=0)
    compiled_closed = transpile(qc_closed, optimization_level=0)

    res_open   = simulator.run(compiled_open,   shots=SHOTS).result()
    res_closed = simulator.run(compiled_closed, shots=SHOTS).result()

    co = calculate_global_coherence_index(res_open.get_counts(),   num_qubits)
    cc = calculate_global_coherence_index(res_closed.get_counts(), num_qubits)

    delta = cc - co
    print(f"{step:<6} | {np.degrees(theta_open):>10.2f} | {np.degrees(theta_closed):>10.2f} | {delta:>+16.6f}")

print("\n" + "=" * 75)
print(" GLOBAL HARDWARE-TOPOLOGY STRESS SUITE COMPLETE")
print("=" * 75)
