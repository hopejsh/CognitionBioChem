# CognitionBioChem

A structural pharmacology workbench for cognition-related CNS targets. It **runs real
structure prediction**, computes real chemical and physicochemical properties, validates
every record against a contract, and attaches a provenance record to every value.

[![Verification](https://img.shields.io/badge/verification-6_suites_passing-brightgreen?style=flat-square)](verify_all.py)
[![Studies](https://img.shields.io/badge/pre--registered_studies-7-blueviolet?style=flat-square)](prespec/)
[![Noise floor](https://img.shields.io/badge/pLDDT_noise_floor-2.66_units_measured-informational?style=flat-square)](platform/studies/inference_variance.py)
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

**Those deltas are now qualified against a measured noise floor** (see the variance study
below). Against an across-seed SD of 2.66 pLDDT units, 19 of the 22 deltas exceed 2 SD
(4.1×–17.4×) and are resolvable, so the overstatement finding stands. The three that looked
like agreement — +0.4, +1.0 and +3.4 — sit at 0.1, 0.4 and 1.3 SD and are **not
distinguishable from sampler noise**. No claim of agreement is licensed for those three.

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

## Inference variance — how large is a difference before it means anything?

`platform/studies/inference_variance.py`, plan hash `69e64d5c2f02`, registered before any
fold. **87 of 87 folds succeeded; the protocol audit returned CONFIRMATORY with no
deviation.** A two-level decomposition, with every metric reported separately because pLDDT,
pTM, ipTM and interface PAE have different distributions and an SD on one licenses no
inference about another.

| Hypothesis | Verdict |
|---|---|
| H1 across-seed SD of complex pLDDT < 2.0 units | **falsified** (2.66) |
| H2 same seed is bit-reproducible | **confirmed** |
| H3 MSA is immaterial for designed sequences | **confirmed** |

**The measured noise floor: SD = 2.66 pLDDT units, so the 2-SD resolution limit is 5.32.**
Any pLDDT difference smaller than that is not distinguishable from the sampler. Per-candidate
SD ranged from 0.13 (MicroAutophagy-Tag-M4) to 3.46 (BasalAChE-Abeta-B4) — the noise is not
uniform, and the least confident structures are the noisiest.

Reported separately, as registered:

| Metric | Across-seed SD |
|---|---|
| complex pLDDT | 2.66 units |
| pTM | 0.026 |
| **ipTM** | **0.095** |
| minimum interface PAE | **3.14 Å** |

The ipTM figure matters for binder work: an earlier pilot's three native replicates spanned
0.212–0.473, which is about 2.7 SD — that spread was **sampler noise, not signal**. Any ipTM
comparison below roughly 0.19 is unresolvable on this hardware.

**Determinism.** All six candidates returned bit-identical `complex_plddt` across three
same-seed replicates, spread exactly 0.0. The pre-registered caveat that Metal
floating-point reduction order might break this did not materialise at single-chain scale; it
remains untested for larger jobs.

**MSA.** Enabling the ColabFold MSA server shifted mean pLDDT by 0.33 units, far under seed
noise, paired t-test p = 0.978. **Four of six candidates were bit-identical with and without
MSA** — the search returned nothing usable, exactly as expected for hand-assembled motif
concatenations with no natural homologues. Single-sequence mode costs this candidate set
essentially nothing, which is a property of *these* sequences and does not generalise to
natural ones.

---

## Slate #4 — target construct and numbering registry

`platform/cbc/registry.py` fetches all 16 targets from UniProt and **derives** the
canonical↔mature offset from the CHAIN feature rather than assuming it. Every residue
annotation is resolved under both conventions, and fails only when wrong under **both** —
which is what separates a numbering problem from a wrong residue identity.

The AChE string `CAS (Trp84, Phe330, Tyr121) & PAS (Trp286, Tyr72, Tyr341)` decomposes into
three different situations, not one:

| Residues | Resolves in |
|---|---|
| Trp84, Tyr121 | **neither** convention — Torpedo numbering |
| Phe330 | canonical — **by coincidence** |
| Trp286, Tyr72, Tyr341 | mature |

The `Phe330` coincidence is the dangerous case: a naive check passes it. Resolving live
rather than against a static list raised detection from 8 to **45** fabricated residues, and
total gate violations from 91 to **124**. Independently confirmed against the earlier audit:
8/8 fabricated and 17/17 correct calls reproduce.

`PTAFR` deserves separate mention — P25105 has no signal peptide, so the two conventions
coincide and `His14` cannot be excused as a convention artifact.

---

## Slate #11 — can PRODIGY fill the empty affinity field?

`platform/studies/prodigy_falsification.py`, plan hash `b6b903d9ec37`. PRODIGY needs only a
structure, and structures now exist, so it is the obvious candidate. Scored on 15 peptide–AChE
complexes (3 candidates × 5 seeds).

| Hypothesis | Verdict |
|---|---|
| H1 no better than reseeding | **confirmed** (ratio 1.36) |
| H2 range collapses | **confirmed** (17.1% of fit range) |
| H3 %NIS drives the variation | **falsified** |

Between-candidate SD is **1.41 kcal/mol** against a within-candidate seed noise of **1.04** —
PRODIGY does not distinguish different peptides better than rerunning one peptide with a
different seed.

**H3 refutes the mechanism I proposed, not the conclusion.** I predicted the %NIS terms would
dominate, since they are computed over the whole complex and a 26–47mer barely perturbs a
583-residue receptor's surface. %NIS is indeed nearly constant (41.2–43.2% apolar), but it
accounts for only **10.6%** of the between-candidate variance. The variation comes from the
interface contacts, which differ genuinely between candidates.

So the operative conclusion is the confound stated in the registered plan **before** any
structure was scored: PRODIGY responds to the interfaces, but those interfaces are
seed-unstable — interface-PAE SD 3.14 Å, and contact counts swinging 13→52 across seeds for
one candidate. **This study cannot separate "PRODIGY cannot discriminate here" from "these
interfaces are not real."** PRODIGY is not wired in.

### Why retrieval beats recall, demonstrated

Two earlier memory-based retrievals of the PRODIGY regression produced **mutually
sign-flipped** forms — and both were faithful to a real source. The published eLife Equation 2
is the exact negation of the reference implementation, because the paper regresses against
|ΔG| while the code returns signed ΔG. Two further published-source corruptions: eLife Table 3
lists different weights in the 4th decimal, and the official method page misprints the
%NIS_charged coefficient as 0.3810 instead of 0.13810. Three published sources disagree; only
reading the installed code resolves it.

Applicability, established by retrieval: **"peptid" occurs zero times in the eLife full text.**
PRODIGY was fitted on 81 crystal structures of globular protein–protein complexes. Applying it
to 26–47mers is an out-of-domain extrapolation with no published validation.

---

## Slate #6 — pose accuracy, stratified by what the model had seen

`platform/studies/pose_accuracy.py`, plan hash `8457830a2c5e`. 16 protein–ligand X-ray
complexes predicted with Boltz-2; 12 scorable.

| Hypothesis | Verdict |
|---|---|
| H1 recall stratum > 50% within 2 Å | **falsified** (3/6 = 0.50) |
| H2 interpolation premium ≥ 0.2 | **falsified** — but underpowered |
| H3 PoseBusters validity > 0.8 | **not executed** (declared deviation) |

**The decisive separation.** Median pocket backbone RMSD is **0.454 Å** — the model
reproduces the binding-site fold essentially perfectly — yet it places the ligand wrongly in
7 of 12 cases. `23SI` is the clearest: pocket backbone **0.22 Å**, ligand **8.49 Å** away.
Folding ability and docking ability are distinguishable, and confidence in the first licenses
nothing about the second.

The RMSD distribution is sharply **bimodal**, exactly as the registered metric justification
predicted: hits at 0.31–0.81 Å, misses at 3.3–17.4 Å, nothing between.

**H2 is underpowered, not null.** Premium 0.167 (recall 0.50 vs congeneric 0.33), Fisher
p = 1.0, Wilson intervals [0.19, 0.81] and [0.10, 0.70] almost entirely overlapping. At n = 6
per stratum only a very large premium was detectable — stated as a known confound before any
prediction ran.

**The receptor-disjoint stratum does not exist**, and that is a finding about the PDB rather
than a shortfall. 14 distinct receptors from post-cutoff protein–ligand depositions were
checked and **every one already had pre-cutoff entries** — 13 to 1172 (lysozyme). So this
measures the step from "this exact complex was seen" to "this pocket was seen with other
ligands", the smaller of the two gaps. Nothing here bears on novel folds.

### Two scoring bugs that produced confident nonsense

Both were caught before the results were trusted, and both are now regression-tested.

1. **Residues paired by number, not sequence.** A model is numbered 1..N; a crystal uses
   author numbering with an offset and gaps. On `4XH6` only **4.2%** of number-matched pairs
   were even the same amino acid, and the pocket RMSD read **15.13 Å** where the truth is
   **0.56 Å**. Fixed by global sequence alignment, with a guard that refuses any pair whose
   residue types differ.
2. **Multi-copy ligands counted as one molecule**, giving reference atom counts that were
   exact multiples of the prediction (56 vs 14, 60 vs 30, 74 vs 37). Fixed by grouping copies
   and taking the best match, the standard redocking convention.

---

## Slate #7 — peptide interface benchmark, and the gate for #9

`platform/studies/peptide_interface.py`, plan `515be79a7d12`. 16 peptide–receptor X-ray
complexes, Boltz-2 + DockQ (CAPRI standard). **All three hypotheses confirmed.**

| Stratum | CAPRI acceptable | median DockQ |
|---|---|---|
| pre-cutoff (could be memorised) | **7/8 = 0.88** | 0.87 |
| post-cutoff | **3/8 = 0.38** | 0.18 |

A 0.50 drop in success rate and a **4.8× drop in median DockQ**. Unlike #6, this effect is
large enough to see at n = 8 per stratum.

**ipTM is well calibrated** for this task — Spearman ρ = **0.847**, p = 3×10⁻⁵. Against
AlphaFold3's published bands: 9 confident-and-acceptable, 1 confident-but-wrong, 4
failed-band-and-wrong, and **zero failed-band-but-acceptable**. So ipTM < 0.6 produced no
false negatives. This is the project's first calibrated interpretation key for any confidence
metric.

**Gate for #9: OPEN.** The pipeline recovers 7 of 8 memorisable interfaces, so it has
demonstrated sensitivity and a low score in #9 is evidence about the candidate, not the
method.

---

## Slate #8 — corrected references refute my own hypothesis

`platform/studies/affinity_corrected.py`, plan `0b098bfae805`. The **same** 14 predictions
from the earlier affinity study, re-scored against references that are medians over *all*
ChEMBL records instead of whichever single record a flat per-target budget captured. Only the
reference variable changed.

| Hypothesis | Verdict |
|---|---|
| H1 ranking works with good references | **falsified** (ρ = 0.191, CI spans zero) |
| H2 the reference fix matters | **falsified** — ρ went *down* from 0.304 |
| H3 the model is the larger error term | **confirmed** |

I predicted reference quality was the binding limit. **It was not.** The earlier claim that
~40% of the huperzine A discrepancy was a reference artifact holds for that compound
(2.41 → 1.44 log) but does not generalise.

The operative result is H3: model median error **1.047 log₁₀** against the references' own
measured dispersion of **0.444 log₁₀** — the model is the larger error term by ~2.4×, so it
is the term worth improving.

Measured in passing, and striking on its own: **donepezil × AChE has 176 ChEMBL records
spanning 5.00 log₁₀ units.** The published IC50 for a marketed drug against its primary target
disagrees by five orders of magnitude. Tacrine 201 records / 2.57, physostigmine 55 / 4.76.

---

## Slate #9 — the candidate screen

`platform/studies/candidate_screen.py`, plan `5a62fdf6d614`, audit **confirmatory**. Six
candidates co-folded with their declared receptors, each against three composition-matched
shuffles that preserve length, charge, pI and GRAVY exactly.

**Not one candidate beat its own null.**

| Candidate | Target | native ipTM | best decoy | band |
|---|---|---|---|---|
| PfcACh-PAM-P1 | CHRNA7 | 0.685 | **0.837** | grey |
| MicroTrem2-Agonist-M1 | TREM2 | 0.410 | **0.581** | failed |
| BasalAChE-Abeta-B4 | ACHE | 0.391 | **0.742** | failed |
| HippoAChE-AlkaPept-X2 | ACHE | 0.340 | 0.348 | failed |
| BasalAChE-GorgeBlock-B1 | ACHE | 0.340 | 0.348 | failed |
| BasalSuper-AChE-TrkA-B5 | ACHE | 0.265 | **0.499** | failed |

Mean native ipTM **0.405** against mean decoy **0.411** — the designed sequences score very
slightly *worse* than random rearrangements of their own amino acids.

**Why the null was necessary, demonstrated twice.** A shuffle of `PfcACh-PAM-P1` scored
**0.837** — inside the confident band, above every native — and a shuffle of
`BasalAChE-Abeta-B4` scored **0.742**. Reported without a null, either would have read as a
hit. These are Arg/Trp-rich cationic amphipathic peptides, the class most prone to scoring on
composition alone.

**An unplanned consistency check passed.** `HippoAChE-AlkaPept-X2` and
`BasalAChE-GorgeBlock-B1` returned byte-identical ipTM and identical decoy values, because
they are one of the duplicate sequence pairs the data gate flagged. Identical inputs giving
identical outputs confirms both that the pipeline is deterministic at fixed seed and that the
duplicate finding was real — the platform listed them as two distinct therapeutics against
different targets.

**Scope, registered in advance.** Three decoys give a minimum empirical p of 0.25, so no
individual candidate could reach significance; the design tests the set. A negative bounds
what *this pipeline at this configuration* detects, not what the molecules do in a cell. Only
6 of 25 candidates were screened — those whose receptor is in the registry and extracellular.

---

## Slate #10 — does the negative survive a full MSA?

`platform/studies/msa_specificity.py`, plan `048c532eb430`. Study #9 re-run with
`--use_msa_server`, same candidates, same RNG seed, **10 decoys each instead of 3**. The panel
classified this `needs-gpu` at 100–250 GPU-hours; it ran here in ~5 hours on Apple MPS, which
the 128 GB unified memory made possible by removing the VRAM ceiling.

| Hypothesis | Verdict |
|---|---|
| H1 natives separate from decoys | **falsified** (Δ = 0.019, p = 0.77, dz = 0.13) |
| H2 a candidate is confident *and* specific | **falsified** (0 candidates > 0.8) |
| H3 the MSA raises natives | **confirmed** (+0.219) |

**The result separates two things that looked identical.** The MSA genuinely raises ipTM —
+0.219 on average, up to **+0.42** on the AChE candidates — so #9's registered confound was
*real* and running this study was necessary. But the rise applies to natives and decoys alike:
mean native **0.624** against mean decoy **0.606**, a gap indistinguishable from zero. **The
MSA raises the level without creating specificity**, exactly as the pre-registered confound
predicted: it helps the receptor, which has thousands of homologues, not the peptide, which
has none.

| Candidate | #9 no-MSA | MSA native | Δ | decoy mean | **decoy max** | diff |
|---|---|---|---|---|---|---|
| BasalAChE-GorgeBlock-B1 | 0.340 | 0.759 | +0.42 | 0.594 | 0.757 | +0.165 |
| HippoAChE-AlkaPept-X2 | 0.340 | 0.759 | +0.42 | 0.596 | 0.757 | +0.163 |
| BasalSuper-AChE-TrkA-B5 | 0.265 | 0.584 | +0.32 | 0.532 | **0.826** | +0.052 |
| BasalAChE-Abeta-B4 | 0.391 | 0.570 | +0.18 | 0.562 | 0.778 | +0.008 |
| PfcACh-PAM-P1 | 0.685 | 0.526 | −0.16 | 0.580 | **0.856** | −0.054 |
| MicroTrem2-Agonist-M1 | 0.410 | 0.549 | +0.14 | 0.772 | **0.934** | −0.223 |

**Random sequences reach the confident band; no native does.** Four decoys scored 0.934,
0.856, 0.826 and 0.778, while **not one designed sequence reached 0.8**. Reported without a
null, any of those four would have read as a hit.

**The pilot was misleading, and that is the lesson.** A single native–decoy pair measured
before this study showed 0.759 against 0.299 — a +0.46 separation that looked decisive. With
ten decoys the same candidate's decoy mean is 0.594 and the separation collapses to +0.165.
The single decoy happened to be the weakest of ten. Raising decoys from 3 to 10 also flipped
the running mean's sign twice mid-run.

**Two stated limits.** The 2 of 6 candidates that beat all their decoys are
`HippoAChE-AlkaPept-X2` and `BasalAChE-GorgeBlock-B1` — the duplicate sequence pair the data
gate flagged. They are the same molecule, so the effective number of independent candidates
beating their null is **one**, at empirical p = 0.091, which cannot reach 0.05 with ten
decoys. One fold of 66 failed, so n = 65 and the audit flags the deviation.

**The slate is complete.** All 11 consensus items have now been executed.

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

- Structure predictions run in single-sequence mode (`msa: empty`). Boltz documents this as
  degrading accuracy in general, though it was measured to cost this candidate set nothing
  (see the variance study). Results remain a lower bound for natural sequences.
- Same-seed bit-reproducibility was **measured and confirmed** for single-chain folds on MPS.
  It is not claimed for larger jobs: Metal's floating-point reduction order is not fixed by
  the seed and there is a documented `aten::linalg_svd` CPU fallback.
- The variance estimate rests on 5 seeds per candidate, so the SD itself carries roughly 30%
  relative uncertainty.
- `corpus.py` draws a flat activity budget per target rather than retrieving every record per
  compound, which is why most benchmark references rest on one measurement.
- ChEMBL's `natural_product` flag is noisy: it labels donepezil and metoclopramide as
  NP-derived. `NP_DERIVED` means "ChEMBL asserts NP provenance", not "established".
- Legacy binding-site residue annotations mix organism numbering conventions and include
  **45** residue identities that are wrong in every convention, resolved live against
  `data/target_registry.json`.
- PoseBusters' paper states it uses RDKit `GetBestRMS`; its code has never used that for the
  pass/fail decision, and following the paper literally scores a pose translated 3 Å as
  perfect. Only `CalcRMS` is correct for docking.
- No wet-lab validation of anything.

---

## License

Private research. Not affiliated with, endorsed by, or connected to Google DeepMind or the
AlphaFold team. AlphaFold is a trademark of Google DeepMind.

© 2026 Seung H. Jung
