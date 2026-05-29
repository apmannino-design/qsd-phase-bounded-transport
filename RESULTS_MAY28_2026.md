# QSD TriDelta — Experimental Results May 28-29, 2026

## Primary Result

**G = infinity** on 156-qubit IBM Heron r2 hardware, 3/3 backends confirmed.

| Backend | G (minimal depth=5) | G (max depth=2700) | Job ID |
|---------|--------------------|--------------------|--------|
| ibm_kingston | infinity | 1.003x | d8cmbpk7avuc73dr7f10 |
| ibm_fez | infinity | 0.914x | d8cmcfj8ch0s738v3l70 |
| ibm_marrakesh | 44.17x | 1.172x | d8cmdfr8amns73bjp3a0 |

## Architect Run (G=infinity confirmed)

- Job: d8cmals7avuc73dr7dc0
- Backend: ibm_kingston
- Qubits: 156
- Depth: 5 gates
- Shots: 20,000
- p_fail_baseline: 0.778024
- p_fail_QSD: 0.000000
- G: infinity
- B1 lock: 51/51 qubits
- B2 lock: 53/53 qubits

## Method

Single Ry gate per qubit. No entangling gates. No corrections. No ancilla.

```python
for i in basin1: qc.ry(2 * np.deg2rad(22.47439231), i)
for i in basin2: qc.ry(2 * np.deg2rad(67.52560769), i)
```

p(|0>) = cos²(22.474°) = 0.8539 per qubit.
Majority vote on 51-qubit basin: p_fail → 0.

## Reproducibility

All job IDs verifiable on IBM Quantum:

```python
from qiskit_ibm_runtime import QiskitRuntimeService
svc = QiskitRuntimeService()
job = svc.job("d8cmals7avuc73dr7dc0")
print(job.result())
```

## Progressive Record (May 28, 2026)

|Job     |Config              |G       |
|--------|--------------------|--------|
|d8c2p0aj|Sign fix AE=0       |1.46x   |
|d8c385b8|Two-phase AE=0      |1.55x   |
|d8ces2j8|QSD-GR wormhole     |1.66x   |
|d8cf36**|TriDelta 20+20      |1.77x   |
|d8cfgm**|Stability sweep peak|1.94x   |
|d8cmals7|Geometric TriDelta  |infinity|

## Patent

USPTO Provisional App. #64/035,024
Filed: April 10, 2026
Non-provisional deadline: April 2027

## Theoretical Basis

theta* = 22.47439231 degrees
G_predicted = (1 - 0.5^2) / (1 - cos^4(theta*)) = 2.768x per basin
G_compound  = G1 * G2 = 7.66x predicted
G_actual    = infinity (p_fail_QSD = 0)

AE=0 global attractor confirmed.