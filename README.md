# CognitionBioChem

A structural pharmacology workbench for cognition-related CNS targets. It **runs real
structure prediction**, computes real chemical and physicochemical properties, validates
every record against a contract, and attaches a provenance record to every value.

[![Verification](https://img.shields.io/badge/verification-6_suites_passing-brightgreen?style=flat-square)](verify_all.py)
[![Data gate](https://img.shields.io/badge/data_gate-91_violations_on_legacy_data-orange?style=flat-square)](platform/validate.py)
[![Structure](https://img.shields.io/badge/structure-Boltz--2_2.2.1_(MIT)-blue?style=flat-square)](platform/cbc/compute/structure.py)
[![License](https://img.shields.io/badge/license-private_research-lightgrey?style=flat-square)](#license)

---

## Status disclosure — read this first

Structure prediction is **real**: Boltz-2 v2.2.1 (MIT) runs locally on Apple MPS and produced
every structure in `runs/`. ADMET prediction is **real** where it is in domain. Binding
affinity is **predicted but not calibrated**, and is never reported as a free energy.

The peptide sequences are **hand-assembled concatenations of published natural motifs** joined
by GGGGS linkers. They are a hypothesis catalogue, not de novo designs: no generative model
produced them.

Every value carries a provenance record. Fields marked *not computed* are honestly empty.

### What the rebuild established

An earlier version presented hand-typed numbers as AlphaFold3 output. A 12-discipline expert
panel with independent adversarial verification (97 findings, 96 surviving) established that
no AlphaFold3 existed anywhere in the codebase, that the "pLDDT" chart was
`93 + sin(i·0.4)·4 + (charCode % 5)·0.5`, and that all 25 ΔG/K<sub>d</sub> pairs were
thermodynamically impossible. Those renderers are gone; the numbers they produced are
preserved under `retracted_claims` rather than deleted.

**Then the fabricated values were replaced with computed ones and compared head to head.**
Boltz-2 was run on 22 candidates:

| Candidate | Legacy "AF3 pLDDT" | Real Boltz-2 | Δ |
|---|---|---|---|
| BasalSuper-AChE-TrkA-B5 | 95.2 | **49.0** | −46.2 |
| MicroTrem2-Agonist-M1 | 94.7 | **50.7** | −44.0 |
| PfcGluN2A-LTP-P3 | 93.9 | **50.0** | −43.9 |
| … 19 of 22 overstated by 10–46 units | | | |
| MicroAutophagy-Tag-M4 | 93.4 | 96.8 | +3.4 |

`ipTM = 0.00` for every candidate, because each was predicted as a lone chain. No legacy
candidate was ever predicted against its receptor, so no legacy number could have carried
binding information. Real backbone geometry: Cα–Cα 3.77–3.80 Å, against 7.55 Å for the
legacy parametric helix.

---

## What it does

| Capability | Implementation | Status |
|---|---|---|
| Structure prediction | Boltz-2 2.2.1 (MIT), local, Apple MPS | **real** |
| Predictor-output parsing | mmCIF + AF3 / AlphaFold DB / Boltz / Chai confidence files | real |
| All-atom physical validity | clashes, bond lengths, chirality, disulfides | real |
| Chemical structure validation | RDKit: parse, formula, InChIKey, stereochemistry | real |
| Peptide properties | MW, net charge pH 7.4, pI, GRAVY, cysteine parity | real |
| Thermodynamic consistency | ΔG = RT·ln(K<sub>d</sub>) at 298.15 K | real |
| ADMET | ADMET-AI 2.0.1, 104 endpoints, with an applicability-domain gate | real, in domain only |
| Corpus construction | ChEMBL/COCONUT under a versioned inclusion protocol | real |
| Pre-registration | hash-locked plans with reachability checking | real |
| Binding free energy | — | **not implemented, and see below** |

---

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/pip install rdkit numpy scipy certifi
```

Run everything:

```bash
python3 verify_all.py
```

Six suites. The data gate is **expected** to exit non-zero on the legacy dataset — a gate
that passed on it would be the defect.

For structure prediction, a separate Python 3.12 environment is required because Boltz pins
a scipy with no cp314 wheel:

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv312 && ./.venv312/bin/pip install boltz
```

---

## Why not AlphaFold 3

AF3 **source code is Apache 2.0**, but the model parameters are request-only from Google
DeepMind, non-commercial and non-redistributable, and require Linux with a CUDA 8.0+ GPU.
Separately, the AlphaFold Server's prohibited-use policy forbids automated prediction of
protein–ligand and protein–peptide binding, which is exactly what this platform would need.

Boltz-2 is used instead: an AF3-class architecture with **MIT licence on both code and
weights**. This is a licensing substitution, not a claim of scientific equivalence.

Note a parser-relevant difference: **AF2 pLDDT is per-residue, AF3 pLDDT is per-atom.** Same
name, different array rank.

---

## On the affinity head, and why no ΔG is emitted

`affinity_pred_value` is a single scalar on a learned log₁₀(µM) potency axis, fitted to
**pooled Ki/Kd/IC50/EC50/AC50/XC50 labels**. Its ordering is what the training objective
optimised; its absolute level is an uncalibrated corpus-average offset.

It must **never** be rendered as a binding free energy, and no qualified form ("apparent",
"effective") is permitted. Three grounds:

1. **Pooled referent — fatal.** Six endpoint types on one axis. The information needed to
   recover ΔG° (endpoint type, [S], K<sub>m</sub>, mechanism) was destroyed at label
   construction. That is an identifiability failure; no constant inverts a many-to-one map.
2. **IC50 ≠ K<sub>d</sub>.** Cheng–Prusoff gives `Ki = IC50/(1 + [S]/Km)`. Even at the most
   benign condition, [S] = K<sub>m</sub> competitive, IC50/Ki = 2 exactly — 0.411 kcal/mol of
   one-signed bias, more than half the 0.68 log inter-laboratory reproducibility floor for
   public IC50 data (Kalliokoski et al., *PLoS ONE* 8:e61007, 2013).
3. **Sign.** The documented conversion gives **+8.04** where `thermo.kd_to_dg` gives
   **−8.04**. A caveated "apparent ΔG = +8.04" is not a hedged claim; it states the wrong
   direction for a thermodynamic driving force.

Enforced by `platform/check_naming.py`, which runs in `verify_all.py` and is verified against
a negative control.

By contrast, ΔG° is defined as `−RT ln K°` at standard state c° = 1 M, is **negative** for
favourable binding, and **does not depend on assay conditions**. Any quantity that moves when
[S] changes is, by that fact alone, not ΔG°.

---

## Pre-registration

`platform/cbc/prespec.py` freezes a hypothesis, primary metric, threshold and analysis plan
under a content hash **before** any data is seen, and refuses to register a plan that is
broken. It rejects three defects at registration time:

- **unreachable verdicts** — a criterion whose smallest attainable adjusted p already exceeds
  α can never fire. A real proposal in review had exactly this defect.
- **unfalsifiable hypotheses** — `confirmed_if` identical to `falsified_if`.
- **non-discriminating plans** — every hypothesis predicted by the same position, so no
  outcome could distinguish rival positions.

The reachability arithmetic distinguishes permutation tests (floor `1/(B+1)`) from parametric
tests (no floor from n alone) — conflating the two makes the check wrong in both directions.

### The first pre-registered study

`platform/studies/ache_affinity_benchmark.py`, plan hash `cd955b3977b5`, registered before any
prediction ran. n = 15 of 17 planned.

| Hypothesis | Predicted by | Verdict |
|---|---|---|
| H1 ranking ability | "the head is usable" | **falsified** |
| H2 memorization signature | "the pair is memorized" | **falsified** |
| H3 the disputed result is representative | "it was cherry-picked" | **confirmed** |

Primary: Spearman ρ = 0.304, bootstrap 95% CI **[−0.329, 0.766]**, Holm p = 0.814. The
interval spans zero: on this set the affinity head shows **no demonstrated ability to rank**
AChE inhibitor potency.

The protocol audit automatically flagged the deviation `n_observed=15 ≠ n_planned=17` (two
salts the affinity head rejected). Without pre-registration that would have silently become
"we ran 15".

**Stated limitation, measured.** 13 of 17 reference values rest on a *single* ChEMBL record.
For huperzine A, ChEMBL holds 23 IC50 records spanning **3.99 log units** (0.54–5280 nM,
median 47 nM) and the one captured (5.0 nM) sits at the **17th percentile**. Measured against
the median the model's error falls from 2.41 to **1.43 log** — roughly 40% of the headline
discrepancy was an artifact of which literature value happened to be retrieved. With a
reference noise floor of σ ≈ 0.99 log for this pair and a mean absolute error of 1.36 log,
**model error and reference error are the same order of magnitude and this study cannot
separate them.**

---

## Applicability domain

A refusal to predict is principled only when **the stated ground is the computed ground**.

The original 1000 Da ADMET rule was **deleted** because it failed that test: the candidate at
4910 Da is *inside* the training molecular-weight bounding box (training max 5299.5 Da), so
molecular weight is not what places it outside the domain. The refusal survives on a counted
ground instead — the heaviest single covalent species among 53,525 training molecules is
2285.7 Da and the query is 2.16× that.

Also measured, and material: **20.9% of that training set are duplicate canonical SMILES**,
which breaks the exchangeability premise every conformal guarantee rests on.

---

## Repository layout

```
platform/
  cbc/chem.py         RDKit structure validation and descriptors
  cbc/peptide.py      sequence validation and physicochemical properties
  cbc/thermo.py       ΔG ↔ Kd consistency, honest method error bars
  cbc/predictor.py    mmCIF + confidence-file parser (protein and ligand atoms)
  cbc/physics.py      all-atom validity: clashes, bonds, chirality, disulfides
  cbc/provenance.py   the Value/Provenance types the UI is built on
  cbc/prespec.py      hash-locked pre-specification with reachability checks
  cbc/corpus.py       protocol-defined corpus construction
  cbc/compute/        structure.py (Boltz-2), admet.py (ADMET-AI)
  studies/            pre-registered studies
  validate.py         the data-integrity gate
  check_naming.py     build guard: no pooled score rendered as a free energy
runs/                 content-addressed prediction artefacts + manifest
prespec/              registered, hash-locked analysis plans
memory/               append-only provenance ledger (see memory/DESIGN.md)
reviews/              panel findings, adjudications, generated report
research/             database, algorithm and methodology surveys
data/                 validated, provenance-carrying data
```

---

## Provenance model

Every scientific value is `{value, units, provenance}`. The UI cannot render a number whose
status is `placeholder` or `not_computed` — those produce a label, never a figure.
`Provenance.__post_init__` rejects a `computed` value with no software recorded and a
`literature` value with no source id, so the constraint holds at construction.

---

## Known limitations

- Structure predictions run in single-sequence mode (`msa: empty`), which Boltz documents as
  degrading accuracy. Results are a lower bound on the method's capability.
- Seeding fixes the noise draw but **not** floating-point reduction order on Metal, and there
  is a documented `aten::linalg_svd` CPU fallback. Byte-reproducibility is not claimed.
- `corpus.py` draws a flat activity budget per target rather than retrieving every record per
  compound, which is why most benchmark references rest on one measurement.
- ChEMBL's `natural_product` flag is noisy: it labels donepezil and metoclopramide as
  NP-derived. `NP_DERIVED` means "ChEMBL asserts NP provenance", not "established".
- Legacy binding-site residue annotations mix organism numbering conventions and include
  eight residue identities that are wrong in every convention (see `data/residue_audit.json`).
- No wet-lab validation of anything.

---

## License

Private research. Not affiliated with, endorsed by, or connected to Google DeepMind or the
AlphaFold team. AlphaFold is a trademark of Google DeepMind.

© 2026 Seung H. Jung
