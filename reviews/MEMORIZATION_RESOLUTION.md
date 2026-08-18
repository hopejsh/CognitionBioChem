# ADJUDICATION — Boltz-2 affinity head, Huperzine A × human AChE

**Chair's note on scope.** The previous panel's ruling was procedural. This one is not. I have re-verified the load-bearing numbers against the artefacts on this machine rather than inheriting them, and where the three new disciplines disagreed with each other I have ruled rather than averaged. Two of the four factual questions that were open at the start of this session are now closed by measurement, not by argument.

---

## 1. THE RULING

**Position A loses the dispute. Position B wins the disposition, and every argument B gave for it is struck.**

That is not a split. A and B were arguing about *what the observation licenses about this project's chemistry*. On that question A is wrong, and A is wrong for reasons that its own strongest premise generates. B reached the correct disposition, but not one of B's four stated grounds survives contact with the evidence, and the standard B proposed ("a single non-random observation licenses nothing") is a rule the project must not adopt.

### What is now settled, and on what evidence

**(a) The 2.41 figure is a statistic of the retrieval procedure, not of the model. Decisive, and arithmetic.** The reference was not given; it was found, by scanning 23 IC50 records for this pair whose own dispersion is SD 0.980 log, and selecting the joint-3rd-most-potent tier. I simulated the selection directly (200,000 replicates, N(µ = 1.201, σ = 0.980), n = 23 draws, actual predicted pIC50 5.895):

| order statistic of the discrepancy | E[value] | SD |
|---|---|---|
| largest | 3.09 | 0.50 |
| 2nd largest | 2.65 | 0.38 |
| **3rd largest** | **2.39** | **0.33** |
| random record | 1.20 | 0.98 |

P(3rd largest ≥ 2.406) = **0.467**. The observed 2.406 sits at the median of what the selection procedure produces. Decomposition: **2.41 = 1.20 (the model's real offset against the pooled reference mean) + 1.19 (pure selection) + 0.02 (residual).** Half the disputed quantity is the retrieval path. A read a property of its own search as a property of the model; B sensed this and never computed it, and so could not distinguish "somewhat selected" from "half constituted by selection."

**(b) B's misconfiguration plank is refuted with the sign reversed. Measured, and I re-verified it from the raw JSON.** Nine runs of the identical input exist in this session's artefacts:

- single-sequence, n = 6 (incl. the disputed run): y = 0.1052, 0.1924, 0.1194, 0.0250, 0.1798, 0.2055 → **mean 0.1379, SD 0.0685**
- real ColabFold MSA (depth ~11k), n = 3: y = 1.0216, 0.9696, 0.8543 → **mean 0.9485, SD 0.0856**
- **configuration effect = +0.811 log10, SE 0.057 (t ≈ 14)**

Running it the way the vendor intends moves predicted IC50 from 1.4 µM to **8.9 µM** — 0.81 log *further* from every candidate reference. The "misconfigured run" excuse is not unproven; it is false, and inverted. It may not be raised again for this receptor.

**(c) The instrument's repeatability is excellent and was never the problem.** `--seed` defaults to `None`; every number in this dispute came from one unseeded draw. Six replicates give SD 0.068 log. The panel was accidentally safe on precision and unsafe on everything else.

**(d) The forensic ipTM finding is void.** "This run sits below the 0.75 training-admission bar (ipTM 0.7136)" is an artifact of one unseeded draw. Across the six single-sequence replicates ipTM ran 0.714–0.841, **four of six above 0.75**; and one MSA run returned 0.550, so MSA does not reliably raise it either. Struck. By contrast `affinity_probability_binary` is genuinely stable (0.422–0.463 SS; 0.344–0.380 MSA) — the low binder probability is real.

**(e) B's NULL-metadata claim is false, and the error is this project's.** All three 5.0 nM records carry `standard_type = "IC50"`, units nM, relation "=", pchembl 8.30. The project's own ledger already contains the correction (`clm_cfc50f17bdec6f4b`): the code read the key `type` where the field is `activity_type`, and the actually-null field is `assay_confidence`. B asserted a property of ChEMBL that is a property of our retrieval code.

**(f) A's premise is right and A's inference is self-refuting.** Training-set membership is PROBABLY_IN — five assays clear every reproducible clause of Boltz-2's published extraction predicate. But the memorization hypothesis is what fixes the target label, and the labels it admits are 21, 33, 47, 47, 5280 nM (mean pIC50 **7.02**). All three 5.0 nM records *fail* that predicate (4, 7, 4 eligible datapoints against a ≥10 threshold); one, CHEMBL1771986, is an amyloid-β-aggregation readout — a peripheral-anionic-site phenotype, not catalytic inhibition. **A scored the memorization hypothesis against a reference the memorization hypothesis excludes.** Independently, the provenance-clean stratum (12 records whose assay description names the enzyme source) gives mean pIC50 **7.036 ± 0.156**. Two entirely different routes converge to within 0.02 log. That is the reference.

**(g) The "noisy pair" premise is an annotation artifact, and it inverts.** Stratified by whether the assay names its enzyme source: source-stated n = 12, SD **0.539**; unspecified n = 11, SD **1.336**; means statistically identical (Δ = 0.13, t = 0.29); variances not (F = 6.14, p = 0.006). Provenance controls dispersion, not location. Filtered properly this pair is **quieter** than Kalliokoski's generic σ_pIC50 = 0.68, not 1.4× noisier. The whole 3.99-log range lives in the unannotated half — and the four most potent records in the set are the four with the worst provenance. The reference population was never the problem. The referent *selection* was.

**(h) A's inference is a category error about direction of inference.** A's conclusion is a population claim ("this project's chemistry"). The standard uncertainty of a mean error estimated from one compound is σ_between-compound ≈ 1.53 log, so the generalization estimate is **2.16 ± 3.06 (k = 2) = [−0.90, +5.22]** — it contains zero. A computed a pair-level uncertainty (±0.74) and used it to license a population-level claim carrying ±3.06. Aggravated by the fact that the instance was selected for being the *most*-assayed possible case, i.e. the least representative sample of a project whose chemistry is largely novel.

**(i) A's "strong prior" is a one-observation posterior wearing a prior's clothes.** Labelling it a prior installs it upstream of future evidence, where it will never be updated. That is the mechanism by which n = 1 becomes unfalsifiable, and it is why this must be refused explicitly rather than merely discounted.

### Where B is wrong even though B wins

B's stated standard — "a single non-random observation licenses nothing" — is false and, worse, is a ratchet. Evidential relevance is not a function of sample size: E is inert with respect to H only when P(E|H) = P(E|¬H), and n does not enter that condition. n = 1 bounds *precision*, not *relevance*. Applied consistently the rule retires every future single-pair success the platform obtains; applied as such rules usually are — against unwelcome results, forgotten for welcome ones — it is a bias with a methodological costume.

**The correct rule, which the project adopts: post-hoc selection of the comparison, not the count of comparisons, is the defeater.** A pre-registered single prediction against a pre-specified reference protocol can be strong evidence. A post-hoc single prediction against a post-hoc-selected reference is weak regardless of sign. That reformulation lands B's conclusion, is not self-defeating, and binds the project's future successes on identical terms.

And B's "it licenses nothing" is too strong. Something real survives (§3).

### What remains undecidable, and whether it is obtainable here

**Undecidable now: whether the affinity head's skill on AChE is memorization-dependent.** Not because the huperzine observation is imprecise, but because the estimand is a *contrast* — a difference between two conditional performances stratified on training-set membership — and a contrast is **undefined** at n = 1, since one observation occupies one stratum. No amount of further care about huperzine A could ever have broken this deadlock. That is the exact sense in which both camps were arguing past the question.

**Obtainable here: yes.** The stratified rank-recovery design in §4, on this MacBook, in two 10-hour nights, using ChEMBL v34-vs-v37 bulk dumps to convert membership from a prior into a lookup. No cluster, no cloud.

**Not obtainable here, and stop claiming otherwise:** confirmation of membership. The affinity split is unreleased, no processing script ships in the repo, and the assay-level ipTM ≥ 0.75 gate is not reproducible. `PROBABLY_IN` is the ceiling from outside. Anyone asserting CONFIRMED_IN or CONFIRMED_OUT is overclaiming; one email to Boltz/MIT would close it and is worth sending.

**Closed as a non-issue:** the receptor. Both the disputed run (`/private/tmp/aff/in.yaml`) and the study construct (`/tmp/ache_mature.txt`) contain the identical 583-residue P22303 mature chain, SHA-256 `b5db97836a739e0eee92ef5e185431d900a1a16f9170041d2d5a55aba8b80475`. The "543-residue" figure recurs ~20 times in `reviews/idea_panel.json` and is simply wrong. The two camps were not arguing about different receptors.

---

## 2. THE UNCERTAINTY BUDGET

**Measurand.** D = pIC50(reference) − pIC50(prediction), log10 units, where predicted pIC50 = 6 − `affinity_pred_value`. Note at the outset that the instrument and the reference measure different quantities: the head's target is a pooled log10(µM) potency over Ki/Kd/IC50/XC50/EC50/AC50 with **no inter-endpoint offset**, while the reference is a pure IC50. That is a traceability failure, not a performance finding, and it is why an absolute-error claim against this head carries an irreducible unknown bias.

### Budget A — the 2.41 figure exactly as the panel constructed it

| term | source | u (log10) | % variance |
|---|---|---|---|
| u₁ run-to-run repeatability | Type A, n = 6, SD 0.0685 | 0.068 | 0.4% |
| u₂ ensemble model-form split | half of mean \|y₁−y₂\| = 0.637 | 0.319 | 7.8% |
| u₃ endpoint pooling, no offset | rectangular on [0, 0.355], 0.355/√12 | 0.102 | 0.8% |
| u₄ single ChEMBL record as referent | SD of the 23-record population | 0.980 | 74.1% |
| u₅ configuration left undecided | rectangular on the 0.811 effect, /√3 | 0.468 | 16.9% |

u_c = √(0.068² + 0.319² + 0.102² + 0.980² + 0.468²)
= √(0.004624 + 0.101761 + 0.010404 + 0.960400 + 0.219024) = √1.296213 = **1.139**

U(k = 2) = **2.28**.  **D = 2.41 ± 2.28 (95%)**, z = 2.11, lower bound **+0.13**.

**Is 2.41 distinguishable from zero? Two answers, and the distinction is the whole ruling.**

*As a raw difference:* barely — by 0.13 log, one coverage factor's worth of honesty from evaporating. The dispute was fought over a quantity whose expanded uncertainty is 95% of its own value.

*As evidence of anomalous model error: no, and not marginally.* Budget A's u₄ models the referent as a **random draw**. It was not: it was the 3rd-most-extreme of 23. Under the correct sampling model the selection procedure alone contributes **+1.19 log**, and the observed 2.406 sits at the **47th percentile** of what that procedure produces (E = 2.391, SD 0.333). There is no excess over the selection expectation to attribute to the model. **2.41 is not distinguishable from zero excess error.** It is the expected output of the search.

### Budget B — bias-corrected, the estimate that should have been reported

Corrections applied to D: referent selection (5.0 nM cherry → provenance-clean 7.036) **−1.265**; endpoint pooling **+0.177**; configuration, if moving to vendor-intended MSA mode **+0.811**.

| | as-run (single-sequence, 6-run mean) | vendor-intended (MSA, 3-run mean) |
|---|---|---|
| predicted pIC50 | 5.862 | 5.052 |
| reference pIC50 | 7.036 ± 0.156 | 7.036 ± 0.156 |
| raw D | 1.174 | 1.985 |
| + pooling bias | +0.177 | +0.177 |
| **D_corr** | **1.351** | **2.162** |

u_c (as-run) = √(0.028² + 0.319² + 0.102² + 0.156²) = √0.137285 = 0.371 → U(k=2) = **0.74**
u_c (MSA) = √(0.049² + 0.319² + 0.102² + 0.156²) = √0.138900 = 0.373 → U(k=2) = **0.75**

> **D_corr(as-run) = 1.35 ± 0.74 (k = 2), z = 3.6**
> **D_corr(MSA) = 2.16 ± 0.75 (k = 2), z = 5.8**

Both exclude zero. u₂, the reproducible disagreement between the two affinity checkpoints, now carries **70% of the variance** — and it is not noise: the split was sign-stable across all six single-sequence runs (y₁ < y₂ every time) and **reversed sign** in all three MSA runs (y₁ > y₂). That is model-form uncertainty with a configuration dependence, and neither disputant mentioned it.

**The single most instructive arithmetic fact in this file:** referent-selection bias (−1.27) very nearly cancels configuration + pooling bias (+0.99). **2.41 was approximately numerically right for two large, opposite, entirely unrecognised reasons.** It is not a measurement; it is a coincidence — and the most dangerous possible outcome, because it would have validated the method that produced it.

### The two comparisons that decide what the corrected figure means

**Acceptance band.** Boltz-2's own published held-out accuracy implies σ_instrument ≈ **1.5 log10** — and this is robust to the one unresolved reading in the file. The metrologist read Table 15's MAE 1.7001 as kcal/mol (÷1.364 → 1.246 log → σ = 1.562); the philosopher used the 8 blinded assays' 1.660 kcal/mol (→ 1.217 log → σ = 1.525). The two routes agree to 2%. If instead Table 15 is already in log units, σ = 2.13 and the finding becomes *more* unremarkable. The ambiguity therefore cannot flip the conclusion, only its margin. **D_corr/σ_instrument = 2.162/1.53 = 1.41σ (MSA) or 0.88σ (as-run). In spec. Unremarkable.**

**Likelihood ratio** (folded-normal densities, σ_works = 1.525 vs σ_uninformative = 2.30):

| \|e\| | LR(head is broken : head works as published) |
|---|---|
| 1.35 (as-run, corrected) | **0.83** |
| 2.16 (MSA, corrected) | **1.16** |
| 2.41 (as quoted) | **1.33** |

At the honest error the LR is **below one** — correctly referenced, the observation points very slightly *toward* the head working as advertised, because a ~1.3-log miss is the modal outcome of a head with a ~1.2-log published MAE. Even the inflated figure is worth about a fifth of a bit. A single observation on this target would have to miss by ~3.5 log to reach LR = 3.

---

## 3. WHAT THE OBSERVATION LICENSES

Two statements are licensed. The first requires no reference value at all and is therefore the stronger. **This is the exact permitted wording; nothing beyond it may be published, displayed, or entered in the ledger.**

> **Reference-free (fully licensed).** On a single Huperzine A + human AChE (UniProt P22303 mature chain, 583 aa, SHA-256 `b5db978…`) complex, Boltz-2 v2.2.1 on Apple MPS is highly repeatable across seeds (`affinity_pred_value` SD 0.068 log10, n = 6) but its two affinity ensemble members disagree by 0.64 log10 on average (range 0.36–1.10, n = 9), and their sign relationship reverses between single-sequence and MSA configurations. `affinity_probability_binary` was 0.34–0.46 across all nine runs, i.e. the model did not assert that the ligand binds. This prediction is not decision-grade, and that conclusion follows from the model's own output without reference to any measured value.

> **Against a measured reference (licensed, with the stated scope).** Against a provenance-controlled reference of pIC50 7.04 ± 0.16 (92 nM; mean of 12 independent ChEMBL IC50 records whose assay description names a human enzyme source; SD of that stratum 0.54 log, below the 0.68-log generic inter-laboratory floor), Boltz-2 v2.2.1 under-predicted Huperzine A's human-AChE potency by **1.35 ± 0.74 log10 units (k = 2)** as run in single-sequence mode, and by **2.16 ± 0.75 log10 units (k = 2)** in the vendor-intended MSA configuration. Both figures include a +0.18-log correction for the head's endpoint-pooling bias. This is a real discrepancy on this one compound–target pair, and it is 0.9–1.4 σ within Boltz-2's own published held-out error distribution (σ ≈ 1.5 log10) — i.e. within specification. It is a measurement of one pair. It supports **no** statement about the affinity head's performance on this project's chemistry: the standard uncertainty of a mean error estimated from a single compound is ±1.53 log, giving a generalization interval of [−0.90, +5.22] which contains zero. Training-set membership for this pair is PROBABLY_IN, not confirmed, and cannot be confirmed from outside.

**Three prohibitions, binding.**

1. **The figure 2.41 is retired.** It is half retrieval artifact, its expanded uncertainty is ±2.28, and it is the median output of a max-selection procedure. It may not be quoted again, with or without caveats.
2. **The single-sequence run may not be described as a "lower bound on achievable performance."** Measured: the MSA configuration is 0.81 log *worse*.
3. **`affinity_pred_value` may never be rendered as an absolute IC50 or ΔG.** Its k = 2 expanded uncertainty from the vendor's own held-out data is ±3.1 log10 — a factor of ~1,300. Its ordering is what the objective optimised; its level is an uncalibrated corpus-average offset.

**One permission, deliberately granted against Position B.** The huperzine anomaly is **kept as motivation**. Motivations do not require evidential warrant; justifications do. B's prescription to "retire it as motivation" inverts the contexts of discovery and justification — and the anomaly has already earned its keep by generating a good experimental design. It may appear in a Motivation section and nowhere else, and never with a decimal point attached to a claim about model quality.

---

## 4. THE EXPERIMENT TO RUN

**Title.** *A provenance-controlled, mechanism-balanced, membership-stratified rank-recovery test of the Boltz-2 affinity head on human AChE.* Study id `ache-affinity-ranking-v2`.

This **supersedes** `prespec/ache-affinity-ranking-v1.cd955b3977b5.json`, which must not be run as written. Its cohort file (`/tmp/ache_bench.json`) records HUPERZINE A at **nm = 5.0, n_records = 1** — the disputed cherry-pick, frozen into the registered reference. Its H2 regresses error against a record count that is capped at 5 by a 300-activity retrieval slice, so it tests a retrieval artifact. v1 would have reproduced the exact error this panel exists to correct, at n = 17, under a hash. Register v2; do not edit v1.

### Design

**Membership is a lookup, not a prior.** Download and diff `chembl_34_sqlite.tar.gz` (4,859,330,198 B, 2024-04-15 — the exact release Boltz-2 names) and `chembl_37_sqlite.tar.gz` (5,764,252,857 B). Apply Boltz-2's published predicate (App. A.2.1: confidence_score == 9, SINGLE PROTEIN, biochemical/functional, standard_type ∈ {Ki,Kd,IC50,XC50,EC50,AC50}, PAINS removed, ≤50 heavy atoms) to v34.

**Arms** (target CHEMBL220, *Homo sapiens*):
- **S1 SEEN-DENSE** — pair present in chembl_34 under that predicate, compound carries ≥20 qualifying records across all targets in v34.
- **S3 UNSEEN** — compound absent from chembl_34 entirely, with a qualifying human-AChE potency in chembl_37.
- *(S2 SEEN-SPARSE, 1–2 records: run only if the clock allows; separates "in training" from "in training a lot".)*

**Matching — draw S3 first, then match S1 to it.** Four axes, and the last two are the amendment this panel adds:
1. measured pIC50, 0.5-log bins, 1:1 greedy nearest-neighbour (kills range restriction, the precondition for comparing two correlations at all);
2. heavy-atom count ±6;
3. **binding-site class — CAS / PAS / dual-binding, balanced within ±10% between arms**;
4. **rapid- vs slow-binding, balanced.**

Axes 3–4 exist because Cheng–Prusoff makes the IC50↔Ki offset *mechanism-dependent*: competitive gives IC50 = Ki(1+[S]/Km), i.e. +0.27 to +0.98 log at the [S] people actually use (Km = 117 µM acetylthiocholine, typical [S] 0.1–1 mM); noncompetitive gives no offset; uncompetitive gives the opposite sign. S1 would otherwise draw from classic CAS medicinal chemistry and S3 from 2024–2026 literature that is heavily PAS-directed and multitarget. **Unbalanced, Δρ would measure a generational shift in inhibitor mechanism and report it as a memorization gradient** — inheriting precisely the defect that produced the original dispute.

**Analogue leakage, measured not assumed.** For every S3 compound compute max ECFP4 (r = 2, 2048 bit) Tanimoto to the v34 AChE training compounds. **Hard-exclude ≥0.7.** Retain as covariate, pre-bin <0.4 / 0.4–0.7 for a pre-registered sensitivity analysis. Require S3 to span ≥6 distinct source documents with ≤8 compounds each (kills congeneric compression).

**Reference protocol, fixed before any prediction — the amendment that matters most.** Per compound, aggregate chembl_37 activities with: target CHEMBL220, organism *Homo sapiens*, `standard_type == 'IC50'` only, relation '=', units nM, pchembl present, assay `confidence_score == 9`, description **not** matching the non-catalytic blocklist (amyloid / aggregation / A-beta / propidium / peripheral anionic), **and — new — the assay description must name the enzyme source (human / recombinant / erythrocyte / RBC).** Take the median pIC50; retain spread and record count; flag single-record compounds. Extract preincubation time and [S] where stated and retain as covariates.

The provenance clause is not fastidiousness. ChEMBL `confidence_score = 9` encodes *target-mapping* confidence, not assay-reporting completeness: CHEMBL5117328 (5280 nM), CHEMBL4481753 (4300 nM) and CHEMBL3385584 (0.54 nM) are all described "AChE (unknown origin)", all carry confidence 9 and `assay_organism = Homo sapiens`, and those three alone span the full 3.99 log. Boltz-2's headline filter and the v1 protocol are both structurally blind to the one variable that dominates variance on this target. Cross-species HupA IC50 medians span 2.6 log (Electrophorus 5.29 → Torpedo 7.94), so "unknown origin" is not a cosmetic gap.

**Receptor, frozen by hash.** The 583-aa P22303 mature chain, SHA-256 `b5db97836a739e0eee92ef5e185431d900a1a16f9170041d2d5a55aba8b80475`, identical to the disputed run. Recorded in the manifest. The 543-aa figure in `reviews/idea_panel.json` is an error and is corrected, not carried forward.

**Execution.** Boltz-2 v2.2.1, MPS, `affinity_binder` on the ligand chain, one YAML per complex, **`seed = 1` explicitly** (the default is `None`), run list generated in advance and interleaved S1,S3,S1,S3 in matched pairs so truncation stays balanced and potency-matched. Predicted pIC50 = 6 − `affinity_pred_value`.

**Main arm runs single-sequence.** Justified, not conceded: the configuration effect on this receptor is measured at +0.811 ± 0.057, i.e. close to a constant offset, and the primary metric is offset-invariant by construction. It is 12% faster and it matches the configuration in which the disputed observation was made. **This is contingent on the offset-constancy rider below** — the one measurement that could invalidate it.

### Primary metric

**Δρ_S = ρ_S(S1) − ρ_S(S3)**, the difference in within-target Spearman rank correlation between predicted and curated measured pIC50, computed separately in each potency-matched arm. One-sided α = 0.05. **Governing inference: 10,000-permutation within-bin label shuffle.** BCa bootstrap CI over compounds (10,000 resamples; resampling over compounds, never over individual measurements). If permutation and Fisher-z disagree, permutation governs — fixed in advance.

Why rank, not absolute error: it is the axis the objective optimises (Huber loss on absolute values and, *with stronger weight*, on pairwise intra-assay differences, introduced expressly because "this difference-based formulation implicitly cancels out assay-specific confounding factors"); it is offset-invariant and the offset is enormous (Table 15: 1.7001 uncentered vs 0.8569 centered — 0.843 of pure per-assay constant); it survives the reference noise floor, which absolute error does not; it is robust to the 7-log outliers this corpus contains (huprine X 0.026 nM, pralidoxime 340,000 nM); and — decisively — **it is a per-arm quantity, so it can be differenced across strata.** A pooled metric cannot express a memorization gradient at all, which is the entire dispute. Absolute error is the *first secondary*, never the headline. Early enrichment is deferred and named here so nobody proposes it later: at n = 75 per arm EF@1% is decided by a single molecule.

### Pre-specified hypotheses

| | statement | predicted by | confirmed if | falsified if |
|---|---|---|---|---|
| **H1** *primary* | Δρ_S > 0: rank skill is memorization-dependent | A | permutation p < 0.05 one-sided **and** Δρ_S ≥ 0.20 (both required) | 90% one-sided upper bound on Δρ_S < 0.20, i.e. observed Δρ_S ≤ −0.017. Equivalence-style; a non-significant positive point estimate falsifies nothing and is reported **indeterminate** |
| **H2** | ρ_S(S3) > 0: the head ranks chemistry it provably never trained on | B | lower bound of one-sided 95% BCa CI > 0 | upper bound of 95% CI < 0.20, i.e. observed ρ_S(S3) ≤ 0.003 |
| **H3** *neither camp* | memorization did not occur: ρ_S(S1) is itself materially below published held-out level | neither | upper bound of 95% CI on ρ_S(S1) < 0.42 (observed ≤ 0.243). **This dissolves A at the root:** if the pairs were not effectively memorised, "the model has probably seen this pair" cannot license "therefore this error is damning" — while simultaneously denying B, since the head would be underperforming its own published numbers | 95% CI contains or exceeds 0.42 |
| **H4** | absolute error is offset-dominated: MAE(uncentered) − MAE(centered) ≥ 0.5 log | B | ≥ 0.5 log, 95% bootstrap CI excludes zero (anchor: 0.843) | < 0.20 log or CI includes zero — A's use of raw absolute error would then be legitimate |
| **H5** *revised* | **offset constancy:** across 10 compounds run in both configurations, the paired MSA−SS difference has SD < 0.30 log about a constant mean | chair | SD < 0.30 → the SS main arm is validated and the config effect is a nuisance offset | SD ≥ 0.30 → the offset is compound-dependent, the SS main arm is configuration-contaminated, and this is reported as a limitation on the primary. *Note: the mean effect is no longer in question — it is +0.811 ± 0.057, measured. Only its constancy is.* |
| **H6** *deterministic, zero cost* | the disputed 5.0 nM records fail the reference protocol | B | excluded by any clause. Expected: CHEMBL643374 has confidence_score 8 and null assay_organism (fails confidence-9 **and** the new provenance clause); CHEMBL1771986 is "Inhibition of AChE-induced amyloid beta aggregation" (fails the blocklist); all three fail Boltz-2's own ≥10-datapoint filter | passes every clause — the discrepancy then stands against an admissible reference |
| **H7** *negative control, adjudicates nothing* | fewer than 60% of predictions land within 1 log of reference, in **both** arms | both | n/a | n/a. **Listed so that no one mistakes a large MAE for a finding.** Anchors: Table 15 gives 30.7% within 1 log uncentered; blinded assays average 1.217 log MAE. Any analysis headlined "Boltz-2 was off by more than a log" is predicted identically by both camps and settles nothing — that is the original defect, stated in advance to prevent its recurrence |

### Sample size

Anchors converted from the published tables via ρ_S = (6/π)arcsin(r/2): Table 15 hit-to-lead τ = 0.2855 → ρ_S = **0.417**; 8 blinded private assays mean τ = 0.2191 → ρ_S = **0.324**. Honest prospective band [0.32, 0.42]. Power on ρ_S(S1) = 0.42 vs ρ_S(S3) = 0.00.

Var(z_s) = 1.06/(n−3); SE(z₁−z₂) = √(2.12/(n−3)). z(0.42) = ½ln(1.42/0.58) = 0.4478.
One-sided α = 0.05, power 0.80: 1.6449 + 0.8416 = 2.4865.
√(2.12/(n−3)) = 0.4478/2.4865 = 0.1801 → 2.12/(n−3) = 0.03243 → n−3 = 65.4 → **n = 69/arm**.
Monte-Carlo on ranks (20,000 reps/cell) shows the analytic form optimistic by 0.02–0.03 (n = 70: 0.782 vs 0.808 analytic; type-I correctly calibrated at 0.047). **Pre-registered target n = 75/arm, 150 complexes, simulation-corrected power ≈ 0.81.** SE(Δz) = 0.1716; minimum detectable ρ_S(S1) against a null arm = 0.403.

**Stated limitation, on the record before launch:** power for partial memorization (0.42 vs 0.10) is only 0.62, and (0.42 vs 0.15) ≈ 0.50. Detecting 0.42 vs 0.10 needs 112/arm. **A partial gradient will not be resolved by this study.** And H1 is falsified only by an observed Δρ ≤ −0.017 — a real, reachable condition, deliberately not dressed up as "we can exclude any gradient."

Degraded-budget table (simulation-corrected power, 0.42 vs 0.00): 55/arm → 0.69; 58 → 0.71; 65 → 0.75; 75 → 0.81. **Floor 55/arm.** Below that no p-value is reported.

**Cohort-feasibility gate, pre-registered.** The reference protocol now requires source-stated assays, which will thin the yield. Build the cohort *first*. If the UNSEEN arm yields < 55 compounds after all filters, the study is re-scoped and its achieved n and power reported — **the filters are not relaxed after seeing predictions.**

### Cost — corrected against measured runtime

The 184 s/complex figure in the brief is wrong by 2.3×, and the "few hours" figure by ~4×. Measured this session, wall clock, same machine:

- single-sequence: 446, 442, 437, 394, 379 s → **mean 420 s**
- with ColabFold MSA: 455, 483, 489 s → **mean 476 s**

150 SS complexes = 17.5 h. **This is a two-night study, not an overnight one, and the previous plan was ~2.4× over its own estimate.**

- Phase 0, daytime CPU: 10.62 GB of ChEMBL dumps (57/28/14/7 min at 25/50/100/200 Mbit/s; 6.9 TiB free), extract, index, apply the v34 predicate, build and match arms, ECFP4 Tanimoto in RDKit, one cached AChE MSA. **1.5–2.0 h before the night starts.**
- Night 1 (10 h): 3-complex timing pilot (0.35 h) + **87 SS complexes** (10.2 h → truncate at the clock).
- Night 2 (10 h): **63 SS complexes** (7.4 h) + 10 paired MSA runs for H5 (1.3 h) + 8 second-seed replicates (0.9 h) = 9.6 h.
- Total: 150 main + 18 riders + 3 pilot = **171 invocations, ≈20 h across two nights.** Analysis afterwards is seconds.

### Stopping rule

1. **Frozen artefacts.** Before a single invocation: cohort file (compound ids, arm labels, matched-pair indices, curated reference pIC50s, provenance tier, record counts, Tanimoto, binding-site class), run order, receptor sequence, analysis script, and this hypothesis list are written **into the repository** — not `/tmp` — and their SHA-256 hashes recorded in the run manifest. Any later change is a protocol deviation and is reported as one.
2. **Wall-clock stop, never data-dependent.** Halt at T = 10.0 h per night or on list completion. No observed value may extend, shorten, or redirect the run.
3. **Truncation is balanced by construction** via S1/S3 interleaving; analyse at whatever n completed, stating achieved n and its simulation-corrected power in the headline.
4. **Nuisance-parameter sizing permitted, outcome-dependent sizing forbidden.** The timing pilot measures machine speed only; n is set once, before the main arm, as n = min(150, 2·⌊(T − t_elapsed − t_reserve)/(2·r_measured)⌋). It never touches an affinity value.
5. **Floor and the discipline of declining to answer.** Below 55/arm the primary is **DECLARED NOT ADJUDICATED**; no p-value on Δρ is computed; the panel reconvenes. H4–H7 are still reported.
6. **One analysis, one time**, after the deadline. No secondary may be promoted to headline regardless of what it shows.
7. **Failed runs** are recorded with reason and excluded **together with their matched partner**, preserving the matching. Never silently retried — a retry loop is an outcome-dependent stopping rule in disguise.
8. **No early-success or early-futility boundary.** At this n any sequential boundary would be crossed by noise often enough to reopen the argument this study exists to close.

**The one hour that should precede all of this:** nobody has read the primary paper behind CHEMBL643374 or CHEMBL3635481. For a slow-binding, mixed-competitive inhibitor (Ki 26 nM on recombinant human AChE; SPR k_off = 3.082×10⁻³ s⁻¹ → residence time 324 s; ChEMBL's own k_on for this pair has its units wrong by 10⁵ — a curation error inside the database being used as ground truth), preincubation time, [S], enzyme source and temperature exist **only** in the methods section. Three agents have argued about that record and none has opened it. Do that first; it is the highest-value hour available.

---

## 5. WHAT EACH DISPUTANT GOT WRONG

### Position A (computational chemist)

**Right, and should be conceded plainly:** the base-rate-to-instance step is a legitimate defeasible inference, not a fallacy — and it has since been corroborated by replication of Boltz-2's published extraction predicate (five qualifying assays; PROBABLY_IN). A was also right that a real discrepancy exists on this pair, which B denied. That is more than B conceded and it should be on the record.

**Wrong:**

1. **Scored the memorization hypothesis against a reference that hypothesis excludes.** The admitted labels average pIC50 7.02; the 5.0 nM records fail Boltz-2's own ≥10-datapoint filter and one is not a catalytic endpoint. A's strongest premise destroys A's headline number. This is not a base-rate error — it is an internal inconsistency between the hypothesis under test and its operationalisation.
2. **Reported a property of the retrieval procedure as a property of the model.** 1.19 of the 2.41 log is the expected contribution of selecting the 3rd-most-extreme of 23 records; the observed value sits at the 47th percentile of that distribution.
3. **Compared a human-AChE prediction against records that never state their enzyme, at unstated [S], with unstated preincubation** — for a compound whose Ki varies ~10-fold across enzyme sources and whose apparent IC50 varies ~3-fold with read window. Not a target-matched comparison.
4. **Used pair-level uncertainty (±0.74) to license a population-level claim carrying ±3.06.** The classic error, and the one that actually decides the dispute.
5. **Generalised from the least representative available instance** — selected for being the most-assayed possible case, in a project whose chemistry is largely novel.
6. **Called a one-observation posterior a "prior,"** installing it upstream of future evidence where it can never be updated.
7. **Never named the alternative hypothesis.** "The head is bad" is not a hypothesis until you say *compared to what*. Against "performs at its own published blinded level," LR = 0.83 at the honest error — it points the wrong way for A.

### Position B (ML-evaluation specialist)

**Right:** the bottom line — the datum licenses no generalisation — and the observation that the metric is off-task. The vendor's own docs say `affinity_pred_value` "should only be used when comparing different active molecules, not inactives" and belongs in hit-to-lead/lead-optimisation; quoting it as an absolute IC50 for one compound is off-label use.

**Wrong, on all four stated grounds:**

1. **"Assay type was not even recorded" is factually false.** All three 5.0 nM records carry `standard_type = "IC50"`, pchembl 8.30. The NULL was our own retrieval bug — B asserted a property of ChEMBL that is a property of our code, the mirror image of the mistake B accused A of.
2. **"Misconfigured single-sequence run" is refuted with the sign reversed.** Measured: +0.811 ± 0.057 log. Fixing the configuration makes the prediction 0.81 log *worse*. B asserted this plank; it was never measured until this session; it is now dead. Also worth generalising: structural confidence (ptm 0.949, plddt 0.930) did not predict the affinity behaviour at all.
3. **"It licenses nothing" is too strong.** 1.35 ± 0.74 as-run (2.16 ± 0.75 in MSA mode) is a real, reportable pair-level measurement, and the head's ±1.5-log absolute accuracy is a real, reportable specification.
4. **The stated standard is false and dangerous.** "A single non-random observation licenses nothing" confuses an estimator's variance with an observation's likelihood ratio; n does not enter the relevance condition. Applied consistently it is sterile; applied selectively it is a ratchet. B was reaching for the right instrument and grabbed the wrong one: the defeater is post-hoc selection of the comparison, and — for *this* dispute specifically — that the estimand is a **contrast**, which is undefined at n = 1, not merely imprecise.
5. **Attacked the reference's metadata rather than its variance,** and got the metadata wrong. The right objection was available and stronger: ChEMBL disagrees with itself about this pair by more than 2.41 log in 8% of its own internal pairwise comparisons — and once stratified by provenance, that dispersion collapses to SD 0.54, *below* the generic floor, proving the reference population was never the problem.
6. **Aimed the remedy at the wrong context.** Retiring the anomaly *as motivation* conflates discovery with justification. Keep the hunch; kill the decimal point.

### Both

- **Nobody ran the instrument twice.** `--seed` defaults to `None`. Every number in the dispute was one unseeded draw of a stochastic process, treated as a reading. The panel was accidentally safe (SD 0.068) and would not have known if it hadn't been.
- **Nobody read the uncertainty the model shipped in the same file.** `affinity_probability_binary` 0.44 — the model declined to assert binding. The two ensemble members disagreed by 0.729 log, straddling the binder/non-binder boundary in opposite directions (0.552 vs 0.337). The model announced its own incompetence on this prediction, in the JSON both sides were quoting from. Using a self-flagged low-confidence prediction as a test of a model is selection on the *predictor* side, mirroring the selection on the reference side: **the datum was chosen twice for extremity, once at each end.**
- **Nobody measured the two largest budget terms.** The configuration effect (asserted by B, expected near zero by the experiment designer) is +0.81 and points the wrong way. The 0.64-log ensemble split — visible in the very JSON under dispute, sign-stable within each configuration and reversing between them — is the largest single contributor to the corrected budget and was filed as "noise" by the forensic report. It is model-form uncertainty, and it means the reported value is the midpoint of two instruments that persistently disagree by more than a factor of four.
- **Nobody priced endpoint pooling.** Six physically distinct endpoint types mapped onto one log10(µM) axis with no offset, while pKi sits ~0.355 log above pIC50 — and Boltz-2's own authors restricted their *validation* set to Ki only "to ensure a higher degree of experimental consistency." A signed structural bias, magnitude unquantifiable because the paper reports no endpoint proportions. That unquantifiability is itself the finding, and it is a permanent argument for ranking metrics over absolute ones.
- **Nobody defined the measurand.** An IC50 is a property of an assay, not of a compound–target pair — and for a slow-binding mixed-competitive inhibitor this is not pedantry. ChEMBL shows the fingerprint plainly for this very compound: "pre-incubated for 10 mins" → 12 nM; "measured for 1 min" → 33 nM; "after 30 mins" → 0.54 nM. ChEMBL has no structured field for preincubation. Boltz-2 has no input for it. Neither side asked what quantity either was estimating.
- **Nobody read the primary paper** behind the record three agents have now argued over.

---

## 6. WHAT THIS CHANGES IN THE CODEBASE

Ordered by severity. Items 1–4 are defects that would have produced a wrong published result.

**1. `platform/cbc/corpus.py:206` — the assay-confidence filter is a silent no-op.**
```python
if conf is not None and conf < protocol.min_assay_confidence:
```
A null confidence **passes**. And the ChEMBL `/activity` payload does not carry `confidence_score` (it lives on `/assay`), so `conf` is *always* None: all **27/27** activity records in `data/corpus_ACHE.json` have `"assay_confidence": null`, while the protocol advertises `min_assay_confidence: 8` and the summary string claims "assay confidence >= 8". The corpus's headline quality claim is unenforced.
*Fix:* join `/assay` (or the bulk dump) to obtain `confidence_score`; invert the guard so **null rejects**; and add the provenance clause from §4 — the assay description must name the enzyme source. Regenerate `data/corpus_ACHE.json`. Add a unit test asserting no admitted activity has a null confidence.

**2. The reference values are single cherry-picked records, and the study that would use them is already registered.**
`/tmp/ache_bench.json` holds HUPERZINE A at **nm = 5.0, n_records = 1**; 14 of 18 compounds have exactly one record; the retrieval examined only 300 activities. `platform/studies/ache_affinity_benchmark.py:168` computes `meas_pic50` from that single value while the analysis plan says "median ChEMBL value." H2 (`:199–204`) regresses error against a record count capped at 5 by the retrieval slice — it cannot detect what it claims.
*Fix:* exhaustive per-compound retrieval; provenance-stratified median under the §4 protocol; record count from a corpus census, not a retrieval slice; report the per-compound spread and tier alongside every reference value.

**3. The cohort and receptor are not content-addressed.** `platform/studies/ache_affinity_benchmark.py:31,36` point `BENCH` and `ACHE_MATURE` at `/tmp`. The prespec hash `cd955b3977b5` covers the *specification* and neither the cohort nor the receptor — so the frozen artefact is the one thing that is not frozen.
*Fix:* move both into the repo, hash them, record the hashes in `runs/manifest.json`, and have `cbc/prespec.py` refuse to register a study whose cohort file is outside the repo or unhashed. Record the receptor as verified: 583 aa, SHA-256 `b5db97836a739e0eee92ef5e185431d900a1a16f9170041d2d5a55aba8b80475`, **identical** in `/private/tmp/aff/in.yaml` and `/tmp/ache_mature.txt`.

**4. Supersede, do not edit, `prespec/ache-affinity-ranking-v1.cd955b3977b5.json`.** Register `ache-affinity-ranking-v2` per §4: two membership-stratified arms, potency + heavy-atom + binding-site-class + kinetic-class matching, the provenance-controlled reference protocol, Δρ_S as primary with a permutation-governed p-value, H1–H7, and the two-night stopping rule. v1 stays on disk as history — deleting it would hide the error; running it would repeat it.

**5. Memory ledger corrections.**
- `clm_2b6c59b70cb31f95` — **retract and supersede.** It records "predicted IC50 1274 nM vs ChEMBL measured 5.0 nM — an error of 2.41 log10 units (about 3.3 kcal/mol)", quotes ipTM 0.714 from an unseeded run, and calls the single-sequence result "a lower bound on achievable performance." All three are now wrong: the reference is a cherry-pick, ipTM ranges 0.71–0.84 across seeds, and MSA mode is 0.81 log *worse*. Replace with the §3 wording.
- `clm_006980da2af0131d` — amend "a measured 2.4 log-unit error" to **1.35 ± 0.74 (k = 2) as run; 2.16 ± 0.75 in vendor-intended MSA mode**, against a provenance-clean reference of 92 nM.
- `clm_47899508e28660fb` — **uphold and strengthen.** The reference-free ensemble-split claim is the strongest thing in the ledger. Update to n = 9 runs: mean split 0.64 log, range 0.36–1.10, sign-stable within configuration and reversing between configurations.
- `clm_371e8c335f9b1722` — **keep struck, append evidence.** Directional language is now supported at pair level by 9 replicates against a provenance-clean reference, but the regression-to-the-mean hazard is still unestimated (the MSA runs land at y ≈ 0.95, so the head is demonstrably not pinned at y = 0 — partial, not sufficient). Directional claims still await the n = 150 study.
- `clm_cfc50f17bdec6f4b` — **uphold.** The `type` vs `activity_type` key bug is the origin of B's central evidentiary claim, and the ledger caught it before this panel did. Confirm the fix is in the retrieval path, not only in the ledger.

**6. New enforced rules in `verify_all.py`, alongside the existing `platform/check_naming.py` ΔG gate.**
- **Seeded-runs rule:** no `affinity_pred_value`, ipTM, pLDDT or pTM may be quoted in any claim, report or display unless the producing run recorded an explicit seed **and** a replicate count. `platform/cbc/compute/structure.py:201` already threads `--seed`; make it non-optional for any run whose output can be cited.
- **Reference-provenance rule:** no measured reference value may be displayed or entered in the ledger without its provenance tier (source-stated / unspecified), its record count, and its within-compound spread.
- **Absolute-potency rule:** extend `check_naming.py` from ΔG to IC50/Kd/Ki. `affinity_pred_value` may be rendered as a **rank or score only**. Its k = 2 expanded uncertainty from the vendor's own held-out data is ±3.1 log10 — a factor of ~1,300 — and its ordering is the only part the objective optimised.
- **Retired-figure rule:** a literal check that the string `2.41` does not reappear in any claim, report, or page in connection with the affinity head.

**7. `reviews/idea_panel.json` — the "543-residue hAChE" figure recurs ~20 times and is wrong; the construct is 583 aa.** Every compute estimate anchored on it is anchored on the right *run* with the wrong *label*, so the timings survive but the reasoning must be corrected. While there: replace the 184 s/complex unit cost with the measured **420 s single-sequence / 476 s MSA**. Every plan in that file built on 184 s is 2.3× under-budget, including the "200 complexes is a ~10 h overnight batch" claim (it is ~23 h).

**8. One email, not a code change.** Ask Boltz/MIT two questions: (i) is the affinity split releasable, or can they confirm membership for CHEMBL395280 × CHEMBL220 in the v34-derived corpus; (ii) is the reported ensemble mean calibrated end-to-end, or is one of the two heads the calibrated one? Answer (ii) collapses u₂ from 0.319 to ~0 and tightens the corrected figure to ±0.40. Both are cheaper than any experiment in this document.

---

### Closing

Two hours of compute answered questions two panels of argument could not, and the answer changed both the number and its meaning. The general rule the project adopts from this: **before anyone argues about a discrepancy, write down the measurand, run the instrument more than once, state how the reference was chosen, and attach a coverage factor.** The huperzine A dispute was not hard. It was under-instrumented — and it was nearly resolved in the wrong direction by a number that happened, through the cancellation of two large opposite errors, to land close to the right answer.