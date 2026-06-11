# QSD Manuscript v30 Updates — June 11, 2026 (IBM ibm_fez Full Validation)

This document provides the exact insertion text for the five additions requested for the Phase-Bounded Transport manuscript (current source: qsd_v24_arxiv.tex → v30 integration).

---

## 1. Updated Abstract (insert after the existing IBM pilot sentence)

**Insertion point:** Immediately after the sentence describing the 12-circuit × 600-shot CPTP pilot on ibm_fez.

**New sentence to append:**

"A subsequent full-chip campaign on ibm_fez (129 qubits, 43 ZZZ cells, 5000 shots) yields median ZZZ = +0.911 at the basin-optimized source angle, with a periodic re-preparation protocol sustaining median +0.672 at circuit depth 1241 (108,489 gates) without error correction."

**Full revised abstract paragraph (for reference):**

[Keep existing text up to the pilot sentence, then insert the new sentence above, then continue with the remainder of the abstract unchanged.]

---

## 2. Replacement for Section XXXII (IBM_fez CPTP Contraction)

**Action:** Delete the entire old Section XXXII (12 circuits × 600 shots CPTP material) and replace with the content of the accompanying file:

`paper/Section_XXXII_IBM_ibm_fez_Hardware_Validation.tex`

This new section contains three subsections (A. Basin Sweep, B. Optimized Full-Chip Run, C. Depth Scaling and Self-Stabilization Protocol) and two new tables (fez_fullchip and depth_scaling). It is written in the exact style and notation of the existing manuscript.

---

## 3. New Section after XXXII: Third-Harmonic Phase Potential

**Action:** Insert the entire content of the accompanying file immediately after the new Section XXXII:

`paper/Section_XXXIII_Third_Harmonic_Phase_Potential.tex`

Renumber subsequent sections accordingly (old XXXIII → XXXIV, etc.). The new section introduces the potential $V(\Theta) = -\cos\Theta - \frac13\sin(3\Theta)$, links it to the TriLock identity, and positions QSD within the broader context of nonlinear optics.

---

## 4. Update to Table 6 (Parameter Accounting)

**Action:** Add the following new rows to Table 6 (Parameter Accounting). Place them in the hardware-experiment block, immediately after the existing ibm_fez pilot row.

**Suggested new rows (LaTeX fragment):**

```latex
\midrule
\multicolumn{3}{l}{\textit{ibm\_fez full validation campaign (June 2026)}} \\
Basin sweep job set          & 5 cells, 20 pts/cell          & \texttt{ibm\_fez\_basin\_sweep\_20260610_\*} \\
Optimized source angle       & THETA\_SRC $-$ 20°            & Basin center from sweep \\
Full-chip production run     & 43 cells, 5000 shots          & Median ZZZ = +0.911 \\
Sunscreen reset interval     & Every 8--16 layers            & +1 layer overhead per cycle \\
Maximum validated depth      & 1241 layers (108489 gates)    & Median ZZZ = +0.672 (sustained) \\
\bottomrule
```

Adjust column alignment and caption as needed to maintain consistency with the existing table style.

---

## 5. Update to Conclusion (Section XXXIV, formerly XXXIII)

**Action:** Append the following paragraph to the end of the Conclusion section, immediately before the final outlook sentence or acknowledgments.

**New text:**

"The hardware basin sweep on \texttt{ibm\_fez} directly confirms the ISS corridor structure and escape/recovery dynamics predicted by Theorem~7. More importantly, the self-stabilizing sunscreen reset protocol demonstrates that QSD's contraction dynamics can be used as their own error-mitigation mechanism, sustaining usable signal at depths exceeding 1200 layers without ancilla overhead or explicit quantum error correction. This result carries implications well beyond the QSD framework itself: any near-term quantum algorithm whose state manifold can be projected into a comparable contraction basin may benefit from the same intrinsic stabilization technique. The convergence of this hardware phenomenology with the third-harmonic phase potential further suggests that the attractor geometry uncovered by QSD reflects a domain-independent organizing principle with potential applications in nonlinear optics, photonic computing, and hybrid quantum-classical control."

---

## Integration Checklist

- [ ] Replace Section XXXII with new three-subsection version
- [ ] Insert new Section XXXIII (Third-Harmonic Phase Potential)
- [ ] Update Abstract with the one-sentence addition
- [ ] Extend Table 6 with the five new parameter rows
- [ ] Append the new paragraph to the Conclusion
- [ ] Recompile and verify cross-references, table numbering, and citation consistency
- [ ] Update Zenodo metadata and push new reproducibility archive (v1.0.3)

All supporting data, job logs, and analysis notebooks for the June 11 campaign are committed in `RESULTS_JUNE11_2026_IBM_ibm_fez_Hardware_Validation.md` and the `data/ibm_fez_*` directories.

*These changes complete the empirical validation arc from theory → surrogate → small-scale hardware → full-chip, depth-extended hardware confirmation.*