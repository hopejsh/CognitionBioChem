# CognitionBioChem

A structural pharmacology workbench for cognition-related CNS targets. It **runs real
structure prediction**, computes real chemical and physicochemical properties, validates
every record against a contract, and attaches a provenance record to every value.

[![Verification](https://img.shields.io/badge/verification-8_suites_passing-brightgreen?style=flat-square)](verify_all.py)
[![Studies](https://img.shields.io/badge/pre--registered_studies-9-blueviolet?style=flat-square)](prespec/)
[![Noise floor](https://img.shields.io/badge/pLDDT_noise_floor-2.66_units_measured-informational?style=flat-square)](platform/studies/inference_variance.py)
[![Data gate](https://img.shields.io/badge/data_gate-114_violations_on_legacy_data-orange?style=flat-square)](platform/validate.py)
[![Structure](https://img.shields.io/badge/structure-Boltz--2_2.2.1_(MIT)-blue?style=flat-square)](platform/cbc/compute/structure.py)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22032684.svg)](https://doi.org/10.5281/zenodo.22032684)
[![License](https://img.shields.io/badge/code-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Data](https://img.shields.io/badge/data-see_NOTICE-lightgrey?style=flat-square)](NOTICE)

---

## Status disclosure — read this first

Structure prediction is **real**: Boltz-2 v2.2.1 (MIT) runs locally on Apple MPS and produced
every **predicted** structure in `runs/`; `runs/` also holds 32 RCSB crystal depositions
used as experimental ground truth by studies #6 and #7, which no predictor made. ADMET prediction is **real** where it is in domain. Binding
affinity is **predicted but not calibrated**, and is never reported as a free energy.

The peptide sequences are **chimeric peptides** — published natural motifs, motif-like
segments with no identifiable natural source, and one de novo amphipathic helix,
**concatenated head to tail with GGGGS linkers**.
No generative model, sequence optimisation or structure-based design software was used at any
stage; the composition of each construct reflects manual curation, not an optimised design
objective. Per-segment attribution lives in `data/dataset.json` → `motif_provenance`,
and it is thinner than the word *attribution* suggests: of 16 motif entries only **7 carry a
UniProt accession**. The other 9 describe themselves in that record as chimeras, pastiches, a de
novo helix, a linker, and in one case not a peptide sequence at all, and 12 further unattributed
segments are listed separately. Scanning for all 22 unattributed fragments, **31 of 35**
candidates carry at least one. An earlier version of this paragraph counted every motif entry as
attributed and reported the carrier count as fourteen; both were hand-typed, both were wrong in
the flattering direction, and the sentence is now generated from the record by
`platform/build_dataset.py`.
Among them is `KWWKFLRRFWRRLKKYFEELWKKLAEKYFELLKKYG`, which
that record calls a *de novo cationic amphipathic (membranolytic-class) helix* with zero exact
hits in SwissProt — and which is the sequence of the duplicate AChE pair screened in #9 and #10.
An earlier version of this paragraph said "published natural motifs … not de novo designs",
which the repository's own provenance record contradicted on both counts.

Every value carries a provenance record. Fields marked *not computed* are honestly empty.

### What the rebuild established

An earlier version presented hand-typed numbers as AlphaFold3 output. A **multi-agent LLM
review** — 12 role-played domain reviewers, 12 independent adversarial verifiers, a chair and 2
completeness critics, all language models and **not human peer review** (see
`reviews/REVIEW_REPORT.md`, and `reviews/panel_raw.json`, where every reviewer is a
`reviewer_persona` string) — produced 97 findings of which 96 survived verification. It
established that no AlphaFold3 existed anywhere in the codebase, that the "pLDDT" chart was `93
+ sin(i·0.4)·4 + (charCode % 5)·0.5`, and that all 25 ΔG/K<sub>d</sub> pairs were
thermodynamically impossible. Those renderers are gone; the numbers they produced are preserved
under `retracted_claims` rather than deleted.

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
| Predictor-output parsing | mmCIF + AF3 / AlphaFold DB / Boltz confidence files | real (no Chai reader; see `platform/cbc/predictor.py`) |
| Structure gallery | 13 candidate–receptor complexes, 22 peptide folds, 16 AlphaFold DB receptors | real — every entry opens a file under `runs/` or `data/alphafold_db/`, with its own pLDDT, PAE and interface PAE |
| Study reporting | 9 pre-registered studies, 28 hypotheses of which 27 are decided | real — verdicts copied from artefacts, never recomputed for display |
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

**Prerequisites:** Python 3.14 (and 3.12 for the structure environment), plus **Node** — one
front-end check shells out to `node --check` to parse `app.js`. Without Node that single check
is skipped with a stated reason rather than failing the suite.

Three environments, because their pins genuinely conflict — DockQ hard-pins `numpy<2` while
the analysis stack needs `numpy>=2`, and Boltz pins a SciPy with no cp314 wheel. Installing
them together silently downgrades numpy and leaves SciPy outside its supported range.

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

The analysis environment above runs the test suites, the data gate, ADMET and the dataset
build. Structure prediction needs the second; only study #7 needs the third.

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv312 && ./.venv312/bin/pip install -r requirements-boltz.txt
```

```bash
python3 -m venv .venvdockq && ./.venvdockq/bin/pip install -r requirements-dockq.txt
```

Run everything:

```bash
./.venv/bin/python verify_all.py
```

Eight suites. The last two are the guards that hold a generated document to the artefacts,
and both **skip — saying so — when there is nothing built to read**, which is the state of
every clone. The data gate is **expected** to exit non-zero on the legacy dataset: a gate
that passed on it would be the defect.

## What this repository publishes

The study. The pre-registered plans and their hashes, the artefacts with their rows and
verdicts, the folds behind them, the code that produced all of it, and the guards that hold
those to each other. Every number this README states is traceable in `data/`, by a reader who
clones this and runs the suites.

Long-form writing about the study is not published here, in either language, and neither are
the documents built from it. `paper/` is ignored, and `docs/*.docx`, `docs/*.pptx`,
`docs/*.pdf` and `docs/*.html` are ignored with it, so the prose is excluded on the same terms
as the files it renders into — publishing the sentences is the same disclosure as publishing
the document. (Those globs are scoped to `docs/`; the workbench page at the repository root is
tracked and is not one of them.) Writing about a study is the author's, and the author places
it. What a clone carries is the study and the machinery, and that is the whole of what is
offered here.

`platform/check_paper.py` is the guard that binds prose to artefacts. It does not read a fact
sheet; it walks `data/` directly, collects every value the repository actually holds, and
requires every numeral a text states about this study to trace to one of them or to arithmetic
on one — with the study's central quantities anchored to the artefact field they come from, so
a transposition fails even though it would pass a membership test. It runs in `verify_all.py`
and **skips, reporting that it skipped, when there is no prose to read**, which is the state of
every clone. A guard that cannot reach its subject has not passed, and saying so is the honest
report.

### The document generators

`platform/` holds the generators that turn artefacts into long-form documents, and they are
part of the platform in the same way `build_dataset.py` is: code, tracked, runnable, guarded.
**Their output is not.** Every path they write is ignored, so cloning this repository gives you
the generators and none of the documents — you can produce a set on your own machine, and you
will not find that set committed here.

| Code | What it reads, and what holds it |
| --- | --- |
| `cbc/report_data.py` | The single dict both report editions unpack: the artefacts and the quantities derived from them. Nothing downstream types a number |
| `build_report.py`, `build_report_ko.py` | The English and Korean editions of the written account. The Korean is not the English with the strings swapped — both read that same dict, so re-run a study and both change together or neither does. References resolve against `docs/REFERENCES.json`; a key that is not in it raises rather than being cited |
| `check_reports.py` | The guard between the two editions: same figure count, same table count, same paragraph count, and **no number stated in English missing from the Korean**. It runs in `verify_all.py`, and with nothing built to compare it exits 0 saying it skipped — the word it means |
| `build_deck.py` | The conference deck, every slide's numbers read from `data/` at build time, figures inlined as data URIs so the deck is one file. PDF export needs Google Chrome; without it the generator writes the HTML and reports that it skipped the PDF rather than leaving a stale one beside it |
| `build_pptx.py` | The PowerPoint renderer. It parses the HTML `build_deck.py` just produced rather than re-authoring the slides, so the deck's prose lives in exactly one place, and it raises rather than silently dropping markup it does not recognise |
| `build_paper.py`, `build_paper_deck.py`, `cbc/paper.py` | One renderer per output, serving both language editions from one block list, so the editions cannot disagree about a citation number or a figure number. Their input is the prose, which is not in this repository; in a clone they have nothing to render, and they are kept because the author rebuilds from their own working copy |
| `build_figures.py` | The exception, and the reason it is one: figures drawn from the artefacts, whose **output is tracked**. They were once committed as PNGs with no generator behind them, which is exactly the defect this repository's own guard names elsewhere |

The report and deck chain runs from a fresh clone — it reads only tracked inputs — and writes
into `docs/`, where every path it touches is ignored:

```bash
./.venv/bin/python platform/build_figures.py \
  && ./.venv/bin/python platform/build_report.py \
  && ./.venv/bin/python platform/build_report_ko.py \
  && ./.venv/bin/python platform/build_deck.py \
  && ./.venv/bin/python platform/build_pptx.py
```

What IS tracked is what those generators read: [`docs/REFERENCES.json`](docs/REFERENCES.json),
every citation with its PMID, DOI and the record of how it was checked, and
[`docs/figures/`](docs/figures/), where `fig*.png` are drawn by `build_figures.py` from the
artefacts and `ui*.png` are browser captures of the running page, which no script can
regenerate.

`docs/REFERENCES.json` is the smaller, tracked library those generators cite from — 23 entries,
not the 190 above, which belong to writing held elsewhere. Nineteen of the 23 were resolved
through the PubMed E-utilities; three through Consensus/Semantic Scholar (two 2026 papers and
the Boltz-2 preprint, none of them PubMed-indexed); and Holm 1979 is marked as not
PubMed-indexed with the venue it was checked against. Bibliographic metadata retrieved from PubMed (NLM/NCBI).

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
   one-signed bias — 44% of the 0.68 log10 (0.93 kcal/mol) inter-laboratory reproducibility floor for
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

**On the numbering.** The slate runs #1, #2, #4, #6–#12. Two of those are not experiments:
**#4** is the target-construct registry, which has no hypothesis and no plan hash, and this
section (#1) sits inside the pre-registration chapter because it is what the mechanism was
built for. **#3 and #5 do not exist** — they were allocated to studies that were never
registered and never run, and the numbers were not reused so that every citation in this
document keeps pointing at the same thing. Nothing has been withdrawn: `prespec/` holds 27
registered plans across 9 study families, `data/` holds an artefact for all 9, and
`data/slate.json` is built by joining those two against this file.

### Slate #1 — the first pre-registered study

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
For huperzine A, ChEMBL holds **23 IC50 records carrying a pChEMBL value** for this pair, drawn from 23 distinct documents (32 activity records in total across all endpoint types; `research/memorization.json` also reports a direct SD of 0.93–0.96 log over a broader 25-value pChEMBL selection, which is a different set and a different statistic). Those 23 span **3.99 log units** (0.54–5280 nM,
median 47 nM) and the one captured (5.0 nM) is the **3rd most potent** of the 25 pChEMBL values `research/memorization.json` records. Measured against
the median the model's error falls from 2.41 to **1.44 log** — roughly 40% of the headline
discrepancy was an artifact of which literature value happened to be retrieved. With a
reference noise floor of σ ≈ 0.99 log for this pair and a mean absolute error of 1.36 log,
**model error and reference error are the same order of magnitude and this study cannot
separate them.**

---

## Slate #2 — inference variance: how large is a difference before it means anything?

`platform/studies/inference_variance.py`, plan `8242c485e46a` (v3; supersedes v2 and v1, all retained), registered before any fold. **87 of 87 folds succeeded. The protocol audit reports two deviations, both machine-detected.**

1. The registered secondary metric `per_residue_plddt_sd` is absent from the result. It was
   dropped silently; no reason was recorded at the time and one cannot be reconstructed now.
2. The Holm family registered three comparisons and the executed family holds zero, because
   round-2 re-classified all three hypotheses as threshold criteria rather than tests. That is
   the right call — a 0/1 indicator is not a p-value — but it changed the inferential procedure
   after the data were seen, so it is on the record rather than in the code alone.

Both are found by `verify_result` without being told. A third deviation, arm-D membership, was
found by hand in audit round 3 and has since been **fixed rather than declared**: see the floors
above.

A two-level decomposition, with every metric reported separately because pLDDT, pTM, ipTM and
interface PAE have different distributions and an SD on one licenses no inference about
another.

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
| **ipTM** | **0.149** |
| minimum interface PAE | **4.62 Å** |

The ipTM figure matters for binder work: an earlier pilot's three native replicates spanned
0.212–0.473, which is about 1.7 SD — that spread was **sampler noise, not signal**. Any ipTM
comparison below roughly **0.30** is unresolvable on this hardware.

**Correcting arm D widened these floors by half, and that strengthens every negative in the
project.** v1's arm D deviated from its own registered selection rule — the plan says the three
candidates with the highest, median and lowest mean pLDDT, and the code took a fixed stride,
which at six candidates selects ranks 0, 2 and 4 and never the highest. The most reproducible
candidate was therefore missing from the arm whose job is to measure reproducibility. v1 also
folded the 583-residue AChE mature chain, which the construct audit later showed is not a valid
lone-chain construct. v2 fixes both: ipTM SD went **0.095 → 0.149** (+57%) and interface-PAE SD
**3.14 → 4.62 Å** (+47%).

Read against the corrected floor, the two "successes" in study #10 disappear into noise.
`BasalNgf-TrkA-B3` beats its best decoy by **+0.068** and `BasalAChE-Abeta-B4` by **+0.014**,
against a one-SD sampler spread of 0.149. Neither margin is a measurement. Study #9's mean
native-minus-decoy of +0.0012 is likewise well inside it — which is consistent with its verdict,
since that study concluded no separation exists.

**One limit remains on transferring that floor.** It is measured on **three** candidates at
five seeds — the registered design — so it is an estimate with wide uncertainty rather than a
constant. The two limits stated here previously, that arm D deviated from its selection rule and
that it used the superseded AChE mature chain, no longer apply: v2 fixed both, and the floors
above are measured on the same 543-residue construct studies #9 and #10 fold.

**Determinism.** All six candidates returned bit-identical `complex_plddt` across three
same-seed replicates, spread exactly 0.0. The pre-registered caveat that Metal
floating-point reduction order might break this did not materialise at single-chain scale; it
remains untested for larger jobs.

**MSA.** Enabling the ColabFold MSA server shifted mean **single-chain pLDDT** by 0.33 units,
far under seed noise, paired t-test p = 0.489 on the raw p (see the note on why this one is
not multiplicity-adjusted). **Four of six candidates were bit-identical with and without MSA** —
the search returned nothing usable, exactly as expected for manually concatenated motifs with
no natural homologues.

**That finding is about lone peptides, and it does not transfer to complexes.** An MSA cannot
help a sequence with no homologues, but in a peptide–receptor complex it helps the *receptor*,
which has thousands. Study #10 measured exactly that: switching the same pipeline to
`--use_msa_server` raised mean complex ipTM by **+0.167**, up to **+0.59** on one candidate.
That mean rise is **1.12×** the 0.149 ipTM noise floor measured in this study's own arm D —
marginally resolvable, not comfortably so, and the per-candidate +0.59 clearly is. An earlier
version of this paragraph quoted +0.151 from a nine-candidate run and concluded the rise was
*not* resolvable; the base moved and the conclusion inverted with it. So single-sequence mode is
close to free for the isolated designed peptides and is *not* free for the complexes that
studies #6, #7 and #9 scored in that mode. What #10 also showed is that the rise lifts natives
and decoys alike, so it changes the level without changing the ranking.

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
rather than against a static list raised detection from 8 to **23** fabricated residues.
Independently confirmed against the earlier audit: 8/8 fabricated and 17/17 correct calls
reproduce.

A second correction raised the total to **114**. Binding-site strings use `&` to join two
different proteins in some records (`Trem2 Ig domain & Keap1 Kelch domain`) and two sub-sites
of one protein in others (`AChE CAS (Trp84, Phe330, Tyr121) & PAS (Trp286, Tyr72, Tyr341)`).
Splitting on it unconditionally stripped the protein name off the second kind, so those
residues matched no target and were skipped **with nothing written down** — the gate was
under-counting itself and reporting the shortfall as a pass. A clause naming no target now
inherits the last target named in the same record, and where there is none it is reported as
`unresolvable_residue_attribution` instead of dropped: 12 clauses, up from 1. The
inherited residues themselves all resolved correctly, so the fabricated count is unchanged
at 23; what changed is that the gate no longer hides what it could not check.

`PTAFR` deserves separate mention — P25105 has no signal peptide, so the two conventions
coincide and `His14` cannot be excused as a convention artifact.

---

## Slate #11 — can PRODIGY fill the empty affinity field?

`platform/studies/prodigy_falsification.py`, plan `4ffb4b7d2702` (v2; supersedes v1,
both retained). PRODIGY needs only a
structure, and structures now exist, so it is the obvious candidate to fill the ΔG field this
platform leaves empty. Scored on the variance study's arm-D complexes — 3 candidates × 5 seeds =
15 attempts, of which **14 produced a value**. `BasalSuper-AChE-TrkA-B5` at seed 4
returned *No contacts found for selection*: PRODIGY found no interface contacts to score, which is
itself a datum about how unstable these interfaces are across seeds. The registered stopping rule
requires that failure be reported rather than dropped, and n = 14 is what every figure
below rests on.

| Hypothesis | Verdict |
|---|---|
| H1 no better than reseeding | **confirmed** (ratio 1.40) |
| H2 range collapses | **confirmed** (2.61 kcal/mol = 18.2% of the fit range) |
| H3 %NIS drives the variation | **falsified** (-0.4% of the variance) |

Between-candidate SD is **1.34 kcal/mol** against a within-candidate seed noise of
**0.96** — a ratio of **1.40**, below the pre-registered falsification
threshold of 2.0. That is the claim the design tested, and it is the only claim the data support.

This section previously said PRODIGY "does not distinguish different peptides better than
rerunning one peptide with a different seed". The same 14 numbers refute that: a one-way ANOVA on
candidate identity gives **F(2,11) = 9.39, p = 0.0042**, so candidate identity
*is* detectable. The point estimate says so too — 1.40 is greater than 1, not equal to it.
What is true is that the effect is **small** and the study is small: the ratio's bootstrap 95% CI is
**[0.96, 3.84]** (10 000 resamples, seed 0 — both now computed by the study and written to its
artefact, so a reader can regenerate them), which contains the 2.0 threshold, so this design cannot
separate "small" from "large enough to matter". Asserting a null that the data reject is the mirror
image of the overclaiming this repository was rebuilt to remove.

| Candidate | n | mean ΔG (kcal/mol) | seed SD |
|---|---|---|---|
| AstroSuper-CBF-EAAT2-A5 | 5 | -7.95 | 1.44 |
| BasalSuper-AChE-TrkA-B5 | 4 | -6.14 | 0.74 |
| MicroAutophagy-Tag-M4 | 5 | -5.35 | 0.36 |

**H3 refutes the mechanism I proposed, not the conclusion.** I predicted the %NIS terms would
dominate, since they are computed over the whole complex and a 29–39mer barely perturbs a
543-residue receptor's surface. %NIS is indeed nearly constant (43.67–45.82% apolar), and it does
not drive the spread — the variation comes from the interface contacts, which differ genuinely
between candidates.

The *number* attached to that statement was wrong twice, and each correction sharpened the
refutation. The code first summed per-term **standard deviations** and published the ratio under a
key named `nis_variance_fraction`; summing SDs is not a variance decomposition and it assumes away
the covariance between terms. The registered leave-one-term-at-its-grand-mean decomposition is now
what runs. Then the study was found to be scoring the **superseded** arm D — a different candidate
set on the 583-residue AChE mature chain — and was re-scored on the corrected 543-residue construct.
Freezing the two %NIS terms does not remove variance; it **increases** it, giving a share of
**-0.4%**. The %NIS terms are anti-correlated with the interface-contact terms and *damp*
the spread rather than driving it. A negative share is well defined once covariance is kept.

So the operative conclusion is the confound stated in the registered plan **before** any structure
was scored: PRODIGY responds to the interfaces, but those interfaces are seed-unstable —
interface-PAE SD 4.62 Å on these same arm-D folds, and contact counts swinging
33→60 across seeds for `AstroSuper-CBF-EAAT2-A5`, with one seed yielding no scorable interface at all.
**This study cannot separate "PRODIGY cannot discriminate here" from "these interfaces are not
real."** PRODIGY is not wired in.

---

## Slate #6 — pose accuracy, stratified by what the model had seen

`platform/studies/pose_accuracy.py`, plan hash `8457830a2c5e`. 16 protein–ligand X-ray
complexes predicted with Boltz-2; **13 scorable**.

| Hypothesis | Verdict |
|---|---|
| H1 recall stratum > 50% within 2 Å | **falsified** (3/6 = 0.50) |
| H2 interpolation premium ≥ 0.2 | **criterion met** (0.214) — but the test on the same data does not support it (`H2_interpolation_premium_fisher`, **falsified**, Fisher p = 0.59). The analysis emitted that second verdict under a name the registered plan does not contain, so it is reported as unregistered wherever it appears. |
| H3 PoseBusters validity > 0.8 | **not executed** — now a machine-recorded deviation, not just prose |

**A parser bug had been suppressing a benchmark entry, and fixing it flipped a verdict.** The
mmCIF/PDB reader ignored the alternate-location field, so a side chain deposited in two
conformations was read as two atoms 0.5 Å apart. That made `24KK`'s atom counts irreconcilable
and it was reported as a technical failure. Alternate locations are the same atom modelled
twice; the parser now keeps the highest-occupancy copy. `24KK` scores 6.09 Å (a miss), the
congeneric stratum goes from 6 entries to 7, and H2's threshold criterion moves from 0.167 to
**0.214** — over the pre-registered 0.2 line.

That is not a positive result, and this README no longer lets it read as one. The Fisher exact
test on the very same 2×2 gives **p = 0.59**: the criterion is met and the test is not
significant, which is what "underpowered" looks like when both are shown instead of one. Both
now appear side by side, because the criterion and the test were previously collapsed into a
single fabricated p-value.

**The decisive separation.** Median pocket backbone RMSD is **0.348 Å** — the model
reproduces the binding-site fold essentially perfectly — yet it places the ligand wrongly in
8 of 13 cases. `23SI` is the clearest: pocket backbone **0.22 Å**, ligand **8.49 Å** away.
Folding ability and docking ability are distinguishable, and confidence in the first licenses
nothing about the second.

The RMSD distribution is sharply **bimodal**, exactly as the registered metric justification
predicted: hits at 0.31–0.81 Å, misses at 3.3–17.4 Å, nothing between.

**H2 is underpowered, not null.** Premium 0.214 (recall 3/6 = 0.50 vs congeneric 2/7 = 0.286),
Fisher p = 0.59, Wilson intervals [0.19, 0.81] and [0.08, 0.64] overlapping across almost their
whole range. At 6 and 7 per stratum only a very large premium was detectable — stated as a
known confound before any prediction ran, and the reason the criterion crossing 0.2 is reported
as a criterion rather than as evidence.

**The receptor-disjoint stratum does not exist**, and that is a finding about the PDB rather
than a shortfall. Every post-cutoff receptor checked already had pre-cutoff entries — 13 to 1172 (lysozyme). So this
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

**A chain-mapping shortcut had inflated the best post-cutoff score.** The registered plan
specifies an explicit chain mapping; an earlier version abandoned it for DockQ's own chain
search on all 16 entries and described the result as *verified*, when nothing checked it.
Measured entry by entry, the blanket switch was neither necessary nor harmless. 13 of 16 score
identically either way. Only three genuinely need the search: `4XHV` and `4XOE` raise
`KeyError('A')` under the explicit form, and `31EE` finds **no interface** under the curated
`AB:AC` — the curation had named the wrong receptor copy, and peptide C sits on chain B. The
harm was in `10TC`, where DockQ silently substituted native chain H, a **4-residue copy of the
curated 8-residue peptide**; scoring against half the resolved peptide gave DockQ 0.969 where
the curated mapping gives **0.831**. That was the highest score in the post-cutoff stratum.
The curated mapping is now used wherever DockQ accepts it, the three exceptions are recorded
with the reason DockQ gave, and ρ moved from 0.847 to 0.800 as a result. The stratum
fractions did not change.

A 0.50 drop in success rate and a **4.8× drop in median DockQ**. Unlike #6, this effect is
large enough to see at n = 8 per stratum.

**The strata are separated by eleven years, not by the seven months the cutoff requires.** The
registered cutoff is 2023-06-01, but every pre-cutoff entry was deposited in a **five-week
window in January–February 2015**, and the post-cutoff entries run December 2025 – June 2026.
Median gap: **11 years**. So the comparison carries a decade of change in target class,
construct design, crystallisation practice and peptide chemistry alongside the variable it
means to isolate. The registered `known_confounds` list four confounds and this is not among
them; it is stated here because it was found by audit, not because it was anticipated.

What can be checked, has been. The strata are well matched on every structural property
recorded: peptide length (medians 11.0 vs 11.5, Mann-Whitney p = 0.60), receptor length (251
vs 247, p = 0.96) and resolution (1.80 vs 1.84 Å, p = 0.72). None of those predicts DockQ
(|ρ| ≤ 0.41, all p > 0.11). So the measurable covariates do not explain the drop. That
narrows the confound without removing it — era effects this benchmark does not measure remain
unaddressed, and resolving them needs a pre-cutoff set drawn from the months immediately
before the cutoff, which is a new study with its own registration rather than a correction to
this one.

**ipTM ranks interface quality well** — Spearman ρ = **0.800**, p = 2×10⁻⁴. The registered
criterion is a rank correlation, and the section used to report it under the word
*calibrated*. Those are different properties. Spearman is invariant under any strictly
monotone transform, so replacing ipTM by ipTM² leaves ρ and p untouched while moving three
of the ten entries out of the >0.8 band (4Y29, 4Y32, 23AG) — the statistic cannot see the rescaling that the band
thresholds depend on. It measures discrimination, not calibration, and is now named that way.

The absolute bands are a separate, much smaller piece of evidence: 9 confident-and-acceptable,
1 confident-but-wrong, 4 failed-band-and-wrong, **zero failed-band-but-acceptable**, plus 1
grey-and-acceptable and 1 grey-and-wrong. So ipTM < 0.6 produced no false negatives here — on
**4 observations**. That is an interpretation key with an honest denominator, not a calibrated
scale.

**Gate for #9: OPEN, WITH A LIMIT I ORIGINALLY OMITTED AND A CLAIM I HAVE SINCE WITHDRAWN.**
The pipeline recovers 7 of 8 memorisable interfaces, so it has demonstrated sensitivity over
the range #7 measured. This paragraph used to continue: *"and a low score in #9 is evidence
about the candidate rather than about the method. That much stands."* **It does not stand.
Slate #12 falsified it and that clause is retracted.** Five superseded artefacts under
`data/superseded/` still carry the retracted clause verbatim; they are kept unedited
because they record what was believed when they were written, the same reason a registered
plan is never rewritten after the fact. #12 folded these same 16 deposited
complexes — every one of them a binder established by an X-ray structure, 0.91–2.40 Å — against
**ten uniform random permutations of each peptide**, under thresholds registered before the
first permutation was scored. **Only 4 of 16 beat all ten permutations of themselves.** Losing
that comparison is what most demonstrated binders do on this instrument, so a low score is not
evidence about the candidate in the way the retracted clause claimed. What #12 does license is
narrower and is real: natives beat their own permutations **in aggregate** by +0.0895 ipTM
(Holm p = 0.0148, 13 of 16 differences positive), a verdict on a batch of pairs and on no
single pair. **Slate #12 sits further down this document, but it should be read before the #9
table 75 lines below** — #9's own section now carries the same limit, and so does its artefact.

The second omission is one of range. What the original wording of this section did not say is
the range over which sensitivity was demonstrated. The 16 complexes here
have peptides of **7–17 residues** and receptors of **80–304**. The candidates screened in #9
are **31–47 residues** — longer than anything measured here — on receptors of 156–608. No #9
candidate lies inside the calibrated peptide range, and only TREM2 (156 aa) and CHRNA7 (211 aa)
lie inside the calibrated receptor range.

So the aggregate sensitivity argument transfers, but the **numeric bands do not**. Every use of the 0.6
and 0.8 thresholds in #9 and #10 is an extrapolation and is now labelled as one, in the
registered protocol as well as here. #9's primary metric was never one of them: the
native-versus-composition-matched-decoy contrast generates its own reference distribution
inside the study and needs no external calibration. That is why the headline negative survives
the range correction while the band language does not.

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

`platform/studies/candidate_screen.py`, plan `4486520b8863` (v8; supersedes v7 and every
earlier version, all retained), audit **one declared deviation** (below). Every candidate the
screening criterion admits, co-folded with its receptor and with three composition-matched
shuffles that preserve length, charge, pI and GRAVY exactly. **52 folds, zero failures** — 13
candidates, one native and three decoys each — and every one of the 52 was served from a
content-verified cache rather than recomputed (`n_reused` 52, `n_computed` 0).

**The question this screen asks is whether a co-folding confidence score ranks a designed
sequence above shuffles of its own residues. It does not: across the whole set, mean native ipTM
0.462 against mean decoy 0.460, a separation of +0.0012. And that near-zero is not an average
over rows that individually separate — the score puts 0 of the 13 natives above all three
shuffles of themselves.**

**That is a finding about the score. Nothing here was assayed.** No binding measurement, no
cell assay, no animal — every number in this section is `ipTM` read off a structure prediction.
A design that scores below its own shuffle has not been shown to be inactive, any more than one
scoring above it has been shown to bind. The candidates leave this section exactly as untested
as they entered it, which is what the limitations list means by *no wet-lab validation of
anything*.

| Candidate | Target | construct | native ipTM | best decoy | ipTM band |
|---|---|---|---|---|---|
| BasalNgf-TrkA-B3 | NTRK1 | 391 aa ectodomain | 0.817 | **0.872** | confident (> 0.8) |
| PfcDual-nACh-GluN2A-P5 | CHRNA7 | 211 aa ectodomain | 0.757 | **0.894** | grey (0.6–0.8) |
| MicroTlr4-Antagonist-M3 | TLR4 | 608 aa ectodomain | 0.710 | **0.823** | grey (0.6–0.8) |
| MicroDual-Trem2-Nrf2-M5 | TREM2 | 156 aa ectodomain | 0.637 | **0.779** | grey (0.6–0.8) |
| MicroTrem2-Agonist-M1 | TREM2 | 156 aa ectodomain | 0.526 | **0.567** | low (< 0.6) |
| PfcTrk-ErkEnhancer-P2 | NTRK2 | 399 aa ectodomain | 0.442 | **0.486** | low (< 0.6) |
| HippoDual-TrkB-AMPK-X5 | NTRK2 | 399 aa ectodomain | 0.440 | **0.482** | low (< 0.6) |
| PfcACh-PAM-P1 | CHRNA7 | 211 aa ectodomain | 0.403 | **0.830** | low (< 0.6) |
| BasalSuper-AChE-TrkA-B5 | ACHE | 543 aa catalytic core | 0.351 | **0.493** | low (< 0.6) |
| PfcGluN2A-LTP-P3 | GRIN2A | 534 aa ectodomain | 0.328 | **0.389** | low (< 0.6) |
| HippoAChE-AlkaPept-X2 | ACHE | 543 aa catalytic core | 0.248 | **0.382** | low (< 0.6) |
| BasalAChE-Abeta-B4 | ACHE | 543 aa catalytic core | 0.221 | **0.622** | low (< 0.6) |
| HippoTrk-Saponin-X1 | NTRK2 | 399 aa ectodomain | 0.121 | **0.208** | low (< 0.6) |

**What the band column means, and what it does not.** The band is a bin on the native ipTM
alone. It carries no information about the decoy comparison beside it and none about whether
the peptide binds anything. **confident (> 0.8)** is the band in which study #7 found 9 of 10
folds had a CAPRI-acceptable interface; **grey (0.6–0.8)** is the band #7 could not resolve;
**low (< 0.6)** is the band in which #7 found 0 of 4 acceptable, on 4 observations. The
artefact's `band` field and the hypothesis name `H3_candidates_in_failed_band` still spell the
low band `failed` — that is the name of a score bin, not a verdict on a molecule, and this
table no longer repeats the word. Two limits ride on all three bins. #7 measured them on
peptides of 7–17 residues against receptors of 80–304, while these candidates are 31–47
residues against receptors of 156–608, so every band here is an extrapolation and #7 records it
as one. And the bins track the score rather than the design: 9 of the 13 natives sit in the low
band, and for **7 of those 9, all three shuffles of the same residues land in the low band
too**.

**No single row of this table was callable, whatever the folds had returned.** With *m* decoys
a candidate's empirical *p* cannot fall below 1/(*m*+1) — **0.25** at the three decoys used
here, and still **0.0909** at the ten used in #10 and #12, both above α = 0.05. The observed
per-candidate values run 0.5 to 1.0 and could not have run lower than 0.25. So the per-row
reading was unreachable by arithmetic before any sequence was folded, and Slate #12 measured
what it would have been worth: sixteen peptide–receptor complexes whose binding is established
by X-ray structures, each folded against ten permutations of its own peptide, and only **4 of
16** beat all ten. Losing this comparison is what most demonstrated binders do. What the design
supports is the aggregate contrast below; it supports no statement about any one candidate.

**The aggregate contrast is zero to the resolution this design has.** Mean native ipTM
**0.462** against mean decoy **0.460** — a difference of
**+0.0012**, indistinguishable from zero and far inside the 0.149 ipTM sampler noise
measured in study #2. All three hypotheses are decided by pre-specified thresholds, not by tests,
so this study reports **no p-values at all**, and the protocol audit records that as a deviation:
the plan registered `n_comparisons: 3` under Holm and the executed family holds **0**.
Re-classifying a 0/1 indicator out of a Holm family is defensible — it is not a p-value and it
corrupts the correction — but it is a change to the inferential procedure made after the data
were seen, so it belongs on the record rather than in the code alone.

**The three registered verdicts.** Fixed in plan `4486520b8863` before any fold was scored, and
recorded in the artefact under `analysis.verdicts`.

| Hypothesis | Registered threshold | Observed | Verdict |
|---|---|---|---|
| H1 any candidate binds | beats all its decoys **and** ipTM > 0.8 | 0 candidates | **FALSIFIED** |
| H2 natives beat decoys on average | mean native − mean decoy > 0.1 | +0.0012 | **FALSIFIED** |
| H3 candidates in failed band | at least half of the 13 below ipTM 0.6 | 9 | **CONFIRMED** |

The one hypothesis that survived is worth reading literally. What H3 **CONFIRMED** asserts is
that 9 of 13 native ipTM values fell below 0.6 — a fact about where a number landed, in a band
#7 could calibrate on only 4 observations and only outside this size range. It asserts nothing
about what 9 molecules do. H1 and H2 are the same kind of statement in the negative: one score
did not clear a threshold, and two sets of scores did not separate.

**The population is derived, not hand-listed, and the derivation is in the artefact.**
`coverage()` resolves every valid-sequence candidate in the catalogue against the registry and
writes the ground for each inclusion and exclusion into `analysis.coverage`. A candidate is
excluded only when **every** target it declares is unreachable — the registry admits no
soluble-phase construct (a GPCR or transporter, whose ligand site is inside the membrane bundle)
or the target is cytoplasmic. A candidate naming both a reachable and an unreachable target is
screened against the reachable one, with the rest recorded as declared-but-untested.

Getting there took two corrections. The first version of `coverage()` short-circuited on the
hand-written map, so the criterion governed exclusions only while the inclusion half stayed
hand-listed — the defect it was written to remove, surviving in the half that mattered. Applying
the rule uniformly then exposed the rule itself: it excluded CHRNA7 and TLR4 as heteromers when
both are primarily homomers. Narrowed to hetero-only evidence it caught nothing not already
excluded as cytoplasmic, which settles the question — **a keyword scan over a UniProt SUBUNIT
comment cannot establish whether a binding site lies at a subunit interface.** Oligomeric state
is recorded and disclosed but no longer excludes. Two candidates declaring a GluN2A target then became visible and are screened here — one against
GRIN2A and one against CHRNA7, which is the receptor its own construct record names — and on
neither of them does the score separate the designed sequence from shuffles of its own residues.
8 candidates remain excluded, each with its ground in the artefact, and **0** admissible
candidates are left unscreened.

**Why an absolute threshold would have produced a hit.** `BasalNgf-TrkA-B3` reaches ipTM
**0.817**, inside the band study #7 associated with correct interfaces. Its own scrambled sequence
reaches **0.872**. A screen reading absolute confidence would have reported it as the programme's
lead. The same spread between a sequence and a shuffle of its own residues opens at
`PfcACh-PAM-P1`, 0.403 native against **0.830** scrambled, and at `PfcDual-nACh-GluN2A-P5`,
0.757 against **0.894**. In each of those pairs the higher number belongs to the scramble, so
whatever this score is reading, it is not the designed arrangement of the residues. These are
Arg/Trp-rich cationic amphipathic peptides, the class most prone to scoring on composition
alone, which is exactly why the null is composition-matched rather than random.

**The duplicate is now counted once, and it had been inflating the effect size.**
`HippoAChE-AlkaPept-X2` and `BasalAChE-GorgeBlock-B1` carry the identical 36-mer against the
identical AChE construct — one of the duplicate pairs the data gate flags — and both were being
screened. Identical inputs gave byte-identical outputs, which is a real consistency check passed:
it confirms the pipeline is deterministic at fixed seed and that the duplicate finding was
genuine, since the platform listed them as two distinct therapeutics against different targets.

But counting one molecule twice is not harmless. Every statistic here is a mean or a count over
candidates, so the duplicate voted twice in all of them, and it is the most extreme negative
difference in the set. In study #10 it moved the paired mean difference from −0.022 to −0.041
and Cohen's *dz* from −0.117 to −0.220 — roughly doubling the reported effect — and overstated
the t-test's degrees of freedom by one. v4 de-duplicated on (peptide, target), keeping the first
code and recording the other as an alias; that run reported nine distinct designs, and the current
v8 reports **13**. No fold is discarded;
the duplicate's cells remain under custody and are simply not counted twice.

---

## Slate #10 — does the negative survive a full MSA?

`platform/studies/msa_specificity.py`, plan `8511b6cc30ea` (v9; supersedes v8 and every
earlier version, all retained). Study #9 re-run with `--use_msa_server`, the same corrected
constructs, the same RNG seed, **10 decoys each instead of 3**, and all 13 distinct candidates.
143 folds, zero failures. Every stored model was re-parsed and checked against the chains its
own input requested.

| Hypothesis | Verdict |
|---|---|
| H1 natives separate from decoys | **falsified** (paired mean Δ = +0.0009, t-test p = 0.98, dz = +0.01) |
| H2 a candidate is confident *and* specific | **criterion met** (2 candidates) — and see the null below |
| H3 the MSA raises natives by > 0.15 | **criterion met** (+0.167) |

| Candidate | Target | #9 no-MSA | MSA native | Δ | decoy mean | **decoy max** | beats all |
|---|---|---|---|---|---|---|---|
| MicroDual-Trem2-Nrf2-M5 | TREM2 | 0.637 | 0.902 | +0.266 | 0.926 | **0.972** | no |
| HippoDual-TrkB-AMPK-X5 | NTRK2 | 0.440 | 0.831 | +0.392 | 0.778 | **0.875** | no |
| BasalNgf-TrkA-B3 | NTRK1 | 0.817 | 0.818 | +0.001 | 0.495 | 0.750 | **YES** |
| BasalAChE-Abeta-B4 | ACHE | 0.221 | 0.810 | +0.590 | 0.661 | 0.797 | **YES** |
| PfcDual-nACh-GluN2A-P5 | CHRNA7 | 0.757 | 0.746 | -0.011 | 0.594 | **0.866** | no |
| MicroTlr4-Antagonist-M3 | TLR4 | 0.710 | 0.722 | +0.012 | 0.853 | **0.934** | no |
| MicroTrem2-Agonist-M1 | TREM2 | 0.526 | 0.693 | +0.167 | 0.848 | **0.963** | no |
| HippoTrk-Saponin-X1 | NTRK2 | 0.121 | 0.541 | +0.420 | 0.421 | **0.566** | no |
| PfcTrk-ErkEnhancer-P2 | NTRK2 | 0.442 | 0.540 | +0.098 | 0.574 | **0.804** | no |
| PfcGluN2A-LTP-P3 | GRIN2A | 0.328 | 0.495 | +0.168 | 0.468 | **0.770** | no |
| BasalSuper-AChE-TrkA-B5 | ACHE | 0.351 | 0.489 | +0.139 | 0.505 | **0.696** | no |
| PfcACh-PAM-P1 | CHRNA7 | 0.403 | 0.357 | -0.046 | 0.598 | **0.760** | no |
| HippoAChE-AlkaPept-X2 | ACHE | 0.248 | 0.227 | -0.021 | 0.440 | **0.791** | no |

**The paired comparison is now as close to exactly zero as this design can resolve.** Mean native
0.629 against mean decoy 0.628 — a paired difference of **+0.0009**
(p = 0.98, dz = +0.01). With thirteen candidates, ten composition-matched decoys each and a
full MSA, the designed sequences and rearrangements of their own amino acids are
indistinguishable.

**Two candidates beat all ten of their own decoys. That is what chance looks like at this scale.**
A candidate beats all 10 of its decoys with probability 1/11 = 0.091 under the null, so across
13 candidates **1.18 are expected to do it by chance**, and P(X ≥ 2) = **0.334**. Two is the
expected outcome. **The composition-matched null does not protect a *candidate* from being read
as a hit, and this repository's own positive control is what established that.** Slate #12 put
the per-candidate reading to a registered test: the same sixteen X-ray peptide–receptor complexes
the pipeline was calibrated on in #7, each folded against ten permutations of its own peptide,
with every threshold fixed in writing before a fold was scored.

**In aggregate the null works.** The mean paired native-minus-permutation difference is
**+0.0895 ipTM** (95% CI +0.0278 to +0.1512, t(15) = 3.09, p = 0.0074, Holm **0.0148**,
dz = 0.77, 13 of 16 positive). This score is therefore not blind to the order of a peptide's
residues, and the flat result above can no longer be blamed on a score that cannot read residue
order at all.

**Case by case it does not.** Only **4 of 16** complexes beat all ten of their own permutations,
against a threshold of **5 of 16** registered in advance — Bin(16, 1/11) expects 1.45, and
P(X ≥ 4) = 0.0511 against P(X ≥ 5) = 0.0115 — so the per-case hypothesis is recorded as
falsified, at a margin of 0.0011 the plan refused in advance to move the line for.

**And the limit is in the design, not in the budget.** With m permutations a single complex's
empirical p cannot fall below 1/(m+1) — 0.0909 at ten, above α = 0.05 — so no per-candidate call
was licensed at *any* outcome those folds could have returned. Raising m lowers that floor
(1/21 = 0.0476 at twenty) but makes a sweep proportionately harder to achieve, so it buys a
criterion that can be called, not one that is easier to pass.

**The per-candidate reading of this column is therefore withdrawn.** What the column licenses is
a verdict on a *batch* of native–decoy pairs taken together; it licenses none on any single pair.
It does nothing for a *screen* read the same way either, and this is the same error one level up.
The screen-level null is computed in the artefact and flagged by the audit as exploratory, because
it was added after seeing the data.

**One custody gap, stated rather than papered over.** Every number in the four paragraphs above is
in `data/study_interface_null_positive_control.json`, but 160 of that artefact's 176 rows name a
fold output under `runs/interface-null-positive-control/`, and that run tree is **not** in this
repository. Those 160 rows' `model` paths therefore do not resolve in a clone: the statistics
travel, the coordinates they were read from do not.

**The MSA raises the level without changing the ranking**, as #9's registered confound predicted —
it helps the receptor, which has thousands of homologues, not the peptide, which has none. The
mean rise is **+0.167**, which is 1.12× the 0.149 ipTM sampler-noise floor from study #2, so the
average rise is real but only marginally resolvable. It lifts decoys too: 11 of 13 candidates have
a decoy above their native, 6 decoys clear 0.8, and `MicroTrem2-Agonist-M1`'s best scramble reaches
**0.963** against a native of 0.693. Reported without a null, that scramble would have been the
programme's lead compound.

**H3 has been decided five different ways by margins smaller than the study's own resolution.**
Its registered threshold is a rise of 0.15: v1 measured +0.219, v4 +0.134 with a duplicated
candidate still counted, v7 +0.151 on nine candidates, v8 +0.183, and v9 measures +0.167 on thirteen candidates. A
criterion that changes sign when one duplicated row is removed is measuring where the threshold
was drawn, not the MSA. The honest statement is that the MSA raises complex ipTM by roughly
0.13–0.18 on this set.

**What survived every correction, and what did not.** Across three construct corrections, a
de-duplication and two coverage expansions, **H1 was falsified every time** — the designed
sequences never separated from their own composition-matched nulls. What did NOT hold steady is
the size of the gap: across the screen's six retained versions it ran −0.006, −0.015, −0.045,
−0.041, −0.012, +0.001, growing several-fold before coming back through zero, and it has never
left the sampler-noise floor. The verdict is what survived every correction, not the margin. H2's criterion is met, but the screen-level null says two is chance. H3
reversed twice. One verdict is robust and two are artefacts of where thresholds were placed,
which is the more useful thing to know about this study than any individual number in it.

---
## Slate #12 — the composition-matched null discriminates in aggregate, and not case by case

`platform/studies/interface_null_positive_control.py`, plan `69a5009d6f62`, registered
**2026-08-22T06:43:11Z, before any permutation was folded**. The positive control this
repository's central instrument never had: the **same sixteen deposited peptide–receptor
complexes** the interface gate scored in #7, each folded against **ten uniform random
permutations of its own peptide**, under #7's single-sequence settings so that the only thing
differing between the two arms is the order of the peptide's residues. 176 rows — 16 native
folds reused from the gate, 160 permutation folds — **zero failures, zero complexes dropped**.
The protocol audit reports **no deviations**, which makes this the first study in the slate
whose own audit records `confirmatory = true`.

| Hypothesis | Verdict |
|---|---|
| H1 natives separate from permutations of themselves | **confirmed** (+0.0895 ipTM, Holm p = 0.0148, dz = 0.77) |
| H2 the null fires case by case | **falsified** (4 of 16 against a threshold of 5 registered in advance) |
| H3 the natural separation exceeds the designed | **falsified** (Welch p = 0.107, CI −0.021 to +0.197) |

**The falsification is the operative result, and the repository was recommending the thing it
falsifies.** Until this study, `README.md` offered a composition-matched decoy set as a
*per-candidate* control — the form in which a reviewer would actually apply it,
to one design. H2 put exactly that claim to a registered test and it did not reach the
registered strength: only **4 of 16** complexes scored above every one of their own ten
permutations, against a threshold of **5** fixed in writing before the first fold. Under
Bin(16, 1/11) the expectation is **1.45**, P(X ≥ 4) = **0.0511** and P(X ≥ 5) = **0.0115**, so
the observed count misses α by **0.0011** — and the plan stated in the same sentence that four
would not clear α and five would, which is what makes the margin a result rather than a licence
to move the line. **The per-candidate reading of the composition-matched null is withdrawn
throughout this document, and nothing tracked here recommends it any longer.**

**And no per-case call was reachable at any outcome those folds could have returned.** With m
permutations a single complex's empirical p floors at 1/(m + 1) — **0.0909 at ten, above
α = 0.05** — so the per-complex p values in the artefact are descriptive by construction and
H2 had to be decided on a *count* against a binomial reference instead. That floor is the same
arithmetic `platform/cbc/prespec.py` rejects plans for, applied here in advance rather than
discovered afterwards: the plan says so, and says it is why the primary test is paired across
complexes. Raising m lowers the floor (1/21 = 0.0476 at twenty) but makes a sweep
proportionately harder to achieve, so it buys a criterion that **can be called**, not one that
is easier to pass.

**What H1 confirms is real and is narrower than it looks.** The mean paired difference is
**+0.0895 ipTM** (native mean 0.742 against permutation mean 0.652), 95% CI **+0.0278 to
+0.1512**, t(15) = 3.09, p = 0.0074, **Holm p = 0.0148**, dz = 0.77 (CI 0.20–1.33), with **13
of 16 differences positive**. So this score is **not blind to the order of a peptide's
residues**, and #9's and #10's flat results can no longer be attributed to a score that cannot
read residue order at all. What the confirmation licenses is a verdict on a **batch** of
native–permutation pairs taken together. It licenses none on any single pair.

Normality of the sixteen differences is not rejected (Shapiro–Wilk W = 0.939, p = 0.342), and
at n = 16 that check is evidence of no gross violation rather than evidence of normality. Two
distribution-free cross-checks are reported in the artefact and **carry no verdict because they
were not registered**: Wilcoxon signed-rank p = 0.0076 and a sign test at 13/16, p = 0.0213.
Both agree with the registered parametric test, so the H1 verdict does not rest on the
normality assumption — they are shown because a check capable of overturning the primary test
must be shown to have been run.

**H3 is the cell that stayed empty.** It would have decided the screen's negative by a direct
contrast — natural separation against the designed separation of `candidate-screen-v8` under
the same single-sequence settings — instead of by reading two studies side by side. The natural
mean is **75× the designed mean** (0.0895 against 0.0012) and the two sets are still not
separated: Welch t = 1.68 on 21.50 df, **p = 0.1067**, 95% CI on the difference of means
**−0.021 to +0.197, containing zero**. The designed differences scatter from −0.277 to +0.275
about a mean of 0.0012 with 7 of 13 positive; the natural ones sit 13 of 16 positive about
0.0895. **Not detected is not shown absent** — that is confound 7 in the registered plan, and
the verdict is FALSIFIED rather than "no difference". The equivalent comparison against
`msa-specificity-v9`'s designed mean of 0.0009 (6 of 13 positive) is registered as a
*comparison and never as a test*, because that arm differs in alignment mode as well as in
sequence set.

| PDB | split | peptide | receptor | gate DockQ | native ipTM | perm. mean | **perm. max** | Δ | beats all |
|---|---|---|---|---|---|---|---|---|---|
| 4Y29 | pre | 10 | 269 | 0.963 | 0.831 | 0.566 | 0.815 | **+0.265** | **YES** |
| 4XO9 | pre | 14 | 279 | 0.339 | 0.895 | 0.670 | **0.902** | +0.225 | no |
| 23AG | post | 11 | 104 | 0.165 | 0.819 | 0.598 | **0.847** | +0.220 | no |
| 4XT9 | pre | 8 | 243 | 0.978 | 0.923 | 0.712 | 0.832 | **+0.211** | **YES** |
| 10LG | post | 17 | 284 | 0.381 | 0.917 | 0.722 | 0.871 | **+0.195** | **YES** |
| 4XHV | pre | 10 | 94 | 0.899 | 0.897 | 0.745 | **0.961** | +0.152 | no |
| 4XOJ | pre | 13 | 246 | 0.952 | 0.986 | 0.851 | 0.924 | **+0.136** | **YES** |
| 21EE | post | 15 | 80 | 0.167 | 0.340 | 0.254 | **0.391** | +0.086 | no |
| 10TC | post | 8 | 304 | 0.831 | 0.945 | 0.860 | **0.954** | +0.085 | no |
| 29TJ | post | 10 | 289 | 0.483 | 0.934 | 0.914 | **0.962** | +0.020 | no |
| 4S15 | pre | 12 | 256 | 0.031 | 0.300 | 0.282 | **0.458** | +0.018 | no |
| 4Y32 | pre | 7 | 236 | 0.846 | 0.892 | 0.878 | **0.973** | +0.014 | no |
| 4XOE | pre | 14 | 279 | 0.279 | 0.721 | 0.707 | **0.909** | +0.014 | no |
| 31GN | post | 10 | 222 | 0.049 | 0.591 | 0.599 | **0.844** | **−0.008** | no |
| 31EE | post | 12 | 271 | 0.019 | 0.158 | 0.254 | **0.514** | **−0.097** | no |
| 12ZJ | post | 13 | 145 | 0.193 | 0.719 | 0.823 | **0.919** | **−0.104** | no |

**Three complexes ran backwards, and the repository shows the number without the reason.**
31GN, 31EE and 12ZJ scored **below** their own permutations, and all three are among the six
the gate placed incorrectly. The registered descriptive stratification says the same thing
without deciding it: **+0.1316** where the gate reached CAPRI-acceptable (n = 10) against
**+0.0193** where it did not (n = 6). The reading that suggests itself — that the control can
point the wrong way on a case where the pipeline never found the interface — is a hypothesis
this study **cannot** test, because the stratification was registered as descriptive and
carries no verdict. The same applies to the deposition split: **+0.1293** pre-cutoff (n = 8)
against **+0.0497** post-cutoff (n = 8), on the same sixteen complexes where #7 already found
recovery concentrated pre-cutoff (7/8 against 3/8). **Neither study can separate deposition era
from memorisation**, and this one was not designed to.

**160 of this study's 176 rows point at a run tree that is not in this repository.** The 16
native rows reuse the gate's folds and their `model` paths resolve in a clone; the 160
permutation rows name outputs under `runs/interface-null-positive-control/` — 805 files, 28 MB,
161 fold directories including the 4XHV reproduction re-fold — and **that tree is deliberately
not tracked here**. **The custody of this study is therefore incomplete, and stating so is
preferable to a path that dead-ends.** What travels is every number above, in
`data/study_interface_null_positive_control.json`, together with everything needed to make the
folds again: the input set and its `sequence_set_sha256` `14ac1f0f6238…`, the permutation
generator named down to `random.Random(1)` re-seeded per complex, the frozen native ipTM values
the run was checked against, and the settings. What does not travel is the coordinates those
ipTM values were read from. Regenerating them is `--fetch` then `--run` on the module above; at
this study's **measured 45.5 s per computed fold** (7,284 s of compute across two prior
invocations, all 160 folds served from cache on the final one) that is **≈ 2.0 GPU-hours** for
the 160 permutation folds. Until then the confidence values here are reproducible by re-running
and are not verifiable against stored bytes — unlike every other study in this slate.

The one custody check that did travel: **4XHV was re-folded from scratch and reproduced its
reused native ipTM exactly**, Δ = 0.0000 against a 0.01 tolerance registered in advance, so the
sixteen values carried over from #7 are still the values this pipeline produces.

**What this control does and does not validate.** It is measured on **7–17 residue peptides**
bound to **80–304 residue** receptors, in **single-sequence mode**, where a permutation explores
10^3.1–10^11.8 distinct arrangements. #9 and #10 screened **31–47 residue** peptides on
156–608 residue ectodomains, where the same operation explores roughly 10^26–10^43, and #10 ran
with a full MSA. **There is no overlap in peptide length at all, and no result here bounds the
null under an MSA.** The sixteen peptides also reached the PDB by co-crystallising, so the set
is enriched for strong ordered binders and **+0.0895 is an optimistic bound on what the null
can discriminate, not a typical value**. Both are named in the registered confounds rather than
discovered afterwards. Closing the first gap needs a positive control at the candidates' own
length and receptor class — 16 complexes × 10 permutations, ≈ 2.0 GPU-hours of compute, and a
set of 31–47 residue peptide–receptor complexes with X-ray evidence and clean chain mappings
that does not currently exist. Closing the second needs all 176 folds re-run with
`--use_msa_server`, ≈ 17 GPU-hours at #10's measured 345.5 s per fold. Neither is proposed here.

---

## What the page shows, and why the decoys are not in the picker

`platform/build_structures.py` indexes every structure the workbench can open:
**13 candidate–receptor complexes** from study #10, **22 peptide-only folds**, and the
**16 deposited AlphaFold DB receptors**. Each opens its real coordinate file and is drawn
from that file's own B-factor column and PAE array — including the interface PAE across the
two chains, which study #7 measured tracks DockQ, so a reader can see whether the peptide is
*placed* against the receptor rather than only how the complex scored.

**The decoys are deliberately absent from the picker.** Each complex has ten
composition-matched scrambles under custody, and several score above their own native —
`MicroTrem2-Agonist-M1`'s best scramble reaches 0.963 against a native of 0.693. They are
reported in Slate #9 and #10 because they are the finding. They are kept out of a structure
*picker* because letting a reader browse for the best-looking fold is precisely the error the
composition-matched null exists to prevent. Every native is therefore shown with its decoy
mean and decoy maximum beside it, and a native its own scrambles beat says so on the card.

A single-chain fold has no interface, so no ipTM is shown for one. Boltz emits `iptm: 0.0`
there; published beside a peptide that zero reads as the worst possible binding result rather
than as an absence, so the index drops every interface term for monomers and records why.

---

## An independent predictor, and what it can and cannot settle

`platform/studies/alphafold_db_compare.py`, artefact `data/alphafold_db_comparison.json`.
**Exploratory, deliberately.** No hypothesis was registered for it, it has no verdict, and it
is not in the numbered slate.

Every receptor fold in studies #9 and #10 comes from one predictor, so nothing in the slate
distinguishes an ordinary Boltz-2 fold from an arbitrary one. AlphaFold DB is an independent
model with different weights, different training data and a different inference path, and its
deposited per-residue confidence over the same span is a cheap external check. All
16 registry accessions were downloaded (CC BY 4.0);
7 have a Boltz-2 receptor fold and are compared, and the other
9 are listed in the artefact with the reason, so "7 of
16" can never be read as "16".

**AlphaFold Server was not used and could not be.** Its terms prohibit automated use for
protein–ligand and protein–peptide binding prediction, which is exactly what studies #9 and
#10 do. AlphaFold DB is a separately licensed corpus of deposited monomer predictions and
carries no such restriction. Nothing here is submitted to any server.

| Target | Residues | AlphaFold DB pLDDT | Boltz-2 pLDDT (MSA) | r with MSA | r without |
|---|---|---|---|---|---|
| ACHE | 543 | 97.5 | 95.2 | +0.864 | +0.853 |
| CHRNA7 | 211 | 92.0 | 90.2 | +0.674 | +0.597 |
| GRIN2A | 534 | 83.2 | 77.1 | +0.708 | +0.487 |
| NTRK1 | 391 | 81.5 | 85.7 | +0.883 | +0.867 |
| NTRK2 | 399 | 82.1 | 82.0 | +0.956 | +0.715 |
| TLR4 | 608 | 94.8 | 91.5 | +0.775 | +0.523 |
| TREM2 | 156 | 82.9 | 75.7 | +0.913 | +0.933 |

**Giving Boltz-2 an MSA moves it toward AlphaFold on both axes.** Median r rises from
+0.715 to +0.864 and the mean pLDDT gap closes from
5.32 to 2.35 points. That
is the point of running two arms: arm A confounds predictor, MSA and monomer-versus-complex
context all at once, and arm B removes the middle one. The median shift is
+0.0768 over
7 targets.

**What this does not support, stated plainly.** pLDDT is a self-report, not accuracy — two
models agreeing about where they are confident is not agreement about where they are right,
and the residual offset is not evidence that either is better. Both arms still confound
monomer against complex. The correlation runs over residues within one protein, which are not
independent, so no p-value is attached to any r here. And none of it speaks to the peptide,
the interface, or the answer to #9 and #10 — which remains negative.

---

## Applicability domain

A refusal to predict is principled only when **the stated ground is the computed ground**.

The original 1000 Da ADMET rule was **deleted** because it failed that test: the candidate at
4943 Da is *inside* the training molecular-weight bounding box (training max 5299.5 Da), so
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
  cbc/inference.py    a criterion is not a test: Holm over real p-values only
  studies/            pre-registered studies, plus the exploratory AlphaFold DB comparison
  build_dataset.py    the provenance-carrying data layer the page reads
  build_slate.py      the studies index, joined from plans + artefacts + README
  build_structures.py the structure index the 3D viewer picks from
  validate.py         the data-integrity gate
  verify_frontend.py  DOM, data and rendering-rule contract for the page
  check_naming.py     build guard: no pooled score rendered as a free energy
  cbc/report_data.py  the artefacts and derived quantities both report renderers unpack
  build_figures.py    draws docs/figures/ from the artefacts -- the one generator whose
                      output is tracked, six figures including fig6 for study #12
  build_report.py     lays artefact rows out as long-form English, every number read from
                      an artefact and none typed; what it writes is not tracked
  build_report_ko.py  the same rows laid out in Korean from the same dict, so the two
                      cannot drift; what it writes is not tracked
  build_deck.py       lays the same artefact numbers out as slides, figures inlined; what
                      it writes is not tracked
  build_pptx.py       re-lays those slides as PowerPoint by parsing its own HTML rather
                      than re-authoring them; what it writes is not tracked
  check_reports.py    guard: the two renderings must state the same numbers -- skips, and
                      says so, when there is nothing built to compare
  build_paper.py      typesets the author's prose, English and Korean; neither the prose
                      nor the output is in this repository, so a clone has nothing to read
  build_paper_deck.py the same prose laid out as slides, both editions; same absences
  check_paper.py      guard: every numeral a text states must trace to an artefact --
                      skips, and says so, when there is no prose to read
  cbc/paper.py        the format-neutral parser both prose renderers share
  cbc/deck_style.py   the stylesheet and shell every slide renderer shares
runs/                 content-addressed prediction artefacts + manifest
prespec/              registered, hash-locked analysis plans
memory/               append-only provenance ledger (see memory/DESIGN.md)
reviews/              panel findings, adjudications, generated report
research/             database, algorithm and methodology surveys
data/                 validated, provenance-carrying data
data/alphafold_db/    deposited AlphaFold models, downloaded under CC BY 4.0
data/structures.json  51 structures the viewer can open, all under custody
data/slate.json       the pre-registered studies, assembled from plans and artefacts
docs/figures/         six generated figures and five UI captures -- tracked, and the only
                      generator output that is
docs/REFERENCES.json  every citation, with how it was verified
index.html, app.js    the workbench page
```

Every path the `build_*` generators write a document to is ignored, so a clone carries the
generators and none of their output; what is tracked is the code, the artefacts it reads and
the figures it draws.

The page is a static site with no build step. Serve it over HTTP — under `file://` the
browser refuses every `fetch()` as cross-origin, and while the data layer has a `<script>`
shim for that case, the structure viewer genuinely cannot read a coordinate file that way:

```
python3 -m http.server
```

---

## Provenance model

Every scientific value is `{value, units, provenance}`. The UI cannot render a number whose
status is `placeholder` or `not_computed` — those produce a label, never a figure.
`Provenance.__post_init__` rejects a `computed` value with no software recorded and a
`literature` value with no source id, so the constraint holds at construction.

---

## Known limitations

- **Equivalence was never tested, so nothing here demonstrates the absence of a difference.**
  Not one of the 27 plans in `prespec/` pre-specified an equivalence bound or an equivalence
  margin — `grep -rliE "equivalence|margin|TOST" prespec/` returns nothing. Every non-detection
  in this repository is therefore a failure to reject and no more than that: the screen's paired
  native-minus-decoy difference of **+0.0009** (#10), the contrast between the natural and the
  designed arm of the positive control (#12, Welch p = 0.107, 95% CI −0.021 to +0.197), and #2's
  reading that an MSA is immaterial for designed peptides. #2 comes closest, because its H3
  compares the MSA shift against that study's own across-seed noise floor — but a noise floor is
  what the instrument can resolve, not the smallest difference that would matter, and the
  criterion is still settled in part by a p that failed to reject. Read every "no difference" in
  this repository as "not detected at this n".
- **The positive control is an optimistic bound on the screen it validates.** Study #12's
  sixteen complexes are crystallised natural peptides of **7–17 residues**; the designed
  candidates the null is used on are **31–47 residues**. The two sets do not overlap in length
  at all, so the instrument was demonstrated on easier material than it is applied to, and
  "the composition-matched null discriminates" carries from the one to the other by assumption
  rather than by measurement. #12's plan named this before any permutation was folded, and
  naming it is all that has been done about it.
- **The control did not run in the screen's alignment mode either.** #12 folded with
  `msa: empty` — the interface gate's settings, chosen so that the order of a peptide's residues
  was the only thing differing between its two arms — while the headline screen #10 ran with
  `--use_msa_server`. An MSA lifts decoys as well as designs: in #10, **11 of 13** candidates
  have a scramble scoring above their own native, six have one above 0.8, and
  `MicroTrem2-Agonist-M1`'s best scramble reaches **0.963** against a native of 0.693. The arm
  in which the null was shown to work is not the arm in which the negative result was measured.
- Studies #6, #7 and #9 run in single-sequence mode (`msa: empty`); study #10 runs with
  `--use_msa_server`. The variance study measured the MSA to cost the *isolated designed
  peptides* essentially nothing, which is expected for sequences with no homologues — but that
  does not transfer to complexes, where the MSA helps the receptor. Study #10 measured a
  **+0.167** mean rise in complex ipTM, which is 1.12× the 0.149 noise floor —
  above it, though not by much. Single-sequence results
  are therefore a lower bound, and the earlier wording here overstated how little was lost.
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
  **23** residue identities that are wrong in every convention, resolved live against
  `data/target_registry.json`.
- PoseBusters' paper states it uses RDKit `GetBestRMS`; its code has never used that for the
  pass/fail decision, and following the paper literally scores a pose translated 3 Å as
  perfect. Only `CalcRMS` is correct for docking.
- No wet-lab validation of anything.

---

## How to cite

> Jung, S. H. (2026). *CognitionBioChem: A structural pharmacology workbench that reports a
> negative result* (Version 1.0.0) [Computer software]. Zenodo.
> https://doi.org/10.5281/zenodo.22032684

```bibtex
@software{jung_cognitionbiochem_2026,
  author    = {Jung, Seung Ho},
  title     = {CognitionBioChem: A structural pharmacology workbench that reports a negative result},
  year      = {2026},
  version   = {1.0.0},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.22032684},
  url       = {https://doi.org/10.5281/zenodo.22032684}
}
```

Zenodo issues two DOIs and they are not interchangeable. **`10.5281/zenodo.22032684`** is the *concept* DOI
and always resolves to the newest release — cite this one normally. **`10.5281/zenodo.22032685`** is the
*version* DOI, permanently fixed to v1.0.0, and is what you cite when the exact bytes matter —
a reproducibility statement, for instance. The version DOI has to be written into
`CITATION.cff` by hand after each release, because the webhook issues it only once the tag is
already pushed.

If your journal uses Research Resource Identifiers, cite **CognitionBioChem
(RRID:SCR_028851)** inline in the running text; the DOI belongs in the reference list. The
tool is also registered in ELIXIR's software registry as
[biotools:cognitionbiochem](https://bio.tools/cognitionbiochem). The two
are not alternatives — the RRID identifies the tool in a Methods section, the DOI identifies
the archived release.

`docs/REGISTRATION.md` records which registries this project belongs in and which it does not,
with the metadata for each already written: `.zenodo.json`, `CITATION.cff`, `codemeta.json`
and `biotools.json` are all in the repository root. ELN Finder is deliberately excluded there
— it registers electronic lab notebooks, and this is not one.

**What to say about it.** This repository's headline finding is negative: the designed
peptides did not separate from composition-matched shuffles of their own amino acids. If you
cite the software, cite it for what it does — pre-registration, provenance enforcement and
custody of prediction artefacts — and not as evidence that any candidate here binds anything.
`data/slate.json` carries every verdict, including the eleven falsifications.

**Releasing.** `./release.sh 1.1.0` — it verifies the repository, the notes, the tree, the
tag, `VERSION` and the full test suite before it publishes anything, and refuses a placeholder
version. Do not hand-type the git and gh commands; `docs/REGISTRATION.md` records what happened
the two times they were.

**Development note.** This project was built with substantial AI assistance, and the internal
review that found the fabricated values was a multi-agent LLM process, not human peer review.
Both facts are recorded in the status disclosure above and in `NOTICE`.

---

## License and attribution

**Code: Apache-2.0** (see [LICENSE](LICENSE)). SPDX-License-Identifier: `Apache-2.0`.

**Redistributed data keeps its own licence** — see [NOTICE](NOTICE) for the full list. In
short:

| Source | Licence | What is here |
|---|---|---|
| ChEMBL | **CC BY-SA 3.0** | measured activities in `data/corpus_ACHE.json` and the affinity studies |
| UniProt | CC BY 4.0 | sequences in `data/target_registry.json` |
| RCSB PDB | CC0 1.0 | construct sequences, entry identifiers |
| PubChem | public domain | curated structures, InChIKeys, CIDs |
| Boltz-2 outputs | MIT | predicted coordinates in `runs/` |
| `.agents/skills/` (229 files) | Apache-2.0 / CC BY 4.0 | vendored from google-deepmind/science-skills, © Google LLC |

ChEMBL's share-alike term propagates: the ChEMBL-derived data files listed in `NOTICE` are distributed
under **CC BY-SA 3.0**, not Apache-2.0. The code that produced them stays Apache-2.0.

Not affiliated with, endorsed by, or connected to Google DeepMind or the AlphaFold team.
AlphaFold is a trademark of Google DeepMind.

© 2026 Seung H. Jung
