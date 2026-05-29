# QSD TriDelta Experimental Results
## May 28-29, 2026 — ibm_kingston, ibm_fez, ibm_marrakesh

### Summary

TriDelta phase initialization at theta* = 22.47439231 deg produces
measurable error suppression on 156-qubit IBM Heron r2 hardware,
confirmed across 3 backends in a single session.

### Key Results

#### 1. Geometric Initialization (depth=5, no entanglement)
- Ry(2*theta*) initialization biases p(|0>) = cos²(theta*) = 0.8539
- Majority vote on 51-qubit basin: p_fail -> 0
- G = infinity (p_fail_QSD = 0.000, 20000 shots)
- Confirmed: ibm_kingston, ibm_fez (G=inf), ibm_marrakesh (G=44x)
- Job: d8cmals7avuc73dr7dc0

Note: G=inf at this depth reflects initialization bias.
The scientific claim is that theta* = 22.47439231 deg is the
correct attractor angle — not fitted to hardware, derived from
octahedral geometry — and produces the predicted p(|0>) = 0.8539.

#### 2. Entanglement Stress Test (CX layers 1-13)
- TriDelta initialization survives real quantum entanglement
- ibm_fez:       G>1 at all 7 depths tested (crossover >13 layers)
- ibm_marrakesh: G>1 at all 7 depths tested (crossover >13 layers)
- ibm_kingston:  G>1 at 6/7 depths (crossover at 13 layers)
- Peak G = 1.65x at El=2 on ibm_kingston
- G increases at El=2 vs El=1 — consistent with phase propagation
- Job: d8cmkvb8amns73bjpk70 (kingston)
- Job: d8cmlr38amns73bjpmag (fez)
- Job: d8cmmk38amns73bjpo3g (marrakesh)

This result is NOT initialization bias. G>1 under entanglement
means the TriDelta phase structure partially survives CX noise.

#### 3. E_lock Suppression (earlier runs)
- Peak G = 1.94x at depth 8, ibm_kingston
- TriDelta 3-basin: G=1.77x kingston, 1.35x fez, 1.06x marrakesh
- Confirmed 3/3 backends simultaneously
- Job: d8cf36** series

### Reproducibility

All jobs verifiable:
```python
from qiskit_ibm_runtime import QiskitRuntimeService
svc = QiskitRuntimeService()
job = svc.job("d8cmals7avuc73dr7dc0")
print(job.result())
```

### What Is Claimed

- theta* = 22.47439231 deg encodes a natural phase attractor
- Ry(2theta) initialization produces predicted p(|0>) on IBM hardware
- TriDelta phase structure partially survives entanglement (G>1 to 13+ layers)
- Result confirmed across 3 independent backends

### What Is NOT Claimed

- This is not quantum error correction
- G=inf does not mean infinite computational advantage
- The GR/wormhole connection is theoretical, not experimentally confirmed
- This does not replace surface codes

### Patent

USPTO Provisional App. #64/035,024
Filed: April 10, 2026
Non-provisional deadline: April 2027

### Scripts

- qsd_entangle_test.py  — entanglement stress test
- qsd_ibm_architect.py  — full 156-qubit architect run
- qsd_maximum.py        — depth sweep all backends
- qsd_geometric.py      — geometric initialization test