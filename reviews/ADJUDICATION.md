# ADJUDICATION

Three verifiers returned UPHOLD_WITH_CORRECTIONS. I checked the load-bearing corrections against the repository myself before ruling. Two of them overturn specialists on points of fact, and I follow the verifiers in both cases.

**Confirmed at the filesystem this session:**

- `data/corpus_ACHE.json` → HUPERZINE A (CHEMBL395280): `"activity_type": "IC50"`, `"value_nm": 5.0`, `"assay_confidence": null`. **The thermodynamics and n=1 specialists both asserted `standard_type = null`. That is false.** The null field is `assay_confidence`. Verifier 3 is right; this is fatal to every argument built on it.
- `grep -rn "1.364" platform/` → **zero matches.** `kd_to_dg`/`dg_to_kd` are called only inside `thermo.py` and its tests. `affinity_pred_value` appears only in `platform/studies/ache_affinity_benchmark.py`, converted as `6 - y` to a dimensionless pIC50 (lines 78, 163), never to kcal/mol, never into `thermo`. **The sign/units contradiction is real but lives entirely in ledger prose. No executable path commits it.**
- `verify_all.py` is 74 lines with five suites. **There is no naming check of any kind.** The thermodynamics ruling's instruction to "keep the existing verify_all.py build-failing rule" refers to a rule that does not exist. It must be written, not preserved.
- `platform/studies/ache_affinity_benchmark.py` exists — a pre-registered n=17 study written expressly to settle this dispute, with Spearman ρ primary, Holm across three tests, and H3 = "the disputed Huperzine A error is representative." `data/study_ache_affinity.json` **does not exist.** The study is written and unrun.

---

## 1. THE AFFINITY-HEAD NAMING RULING

### What the output is

**`affinity_pred_value` is a single scalar on a learned log₁₀(µM) potency axis, fitted jointly to pooled Ki/Kd/IC50/AC50/EC50/XC50 labels under a loss weighted toward within-assay pairwise differences; its ordering is the quantity the training objective optimised, and its absolute level is an uncalibrated corpus-average offset.**

That is the sentence a scientist will accept, and it is the sentence the Boltz-2 authors themselves come closest to writing: *"the predicted value should be viewed as a general measure of binding strength that supports ranking and can be approximately interpreted as an IC50-like value."*

I take that authorial sentence — surfaced by Verifier 1, missed by the specialist — as decisive on one sub-point and on one only. It defeats the specialist's claim that calling the output an IC50 estimate is a *category mismatch* established *deductively*. The authors explicitly license approximate IC50-like reading. **The correct claim is weaker and still sufficient: the absolute level is uncalibrated across assays, and the authors say "ranking" and "approximately."** Downgrade that inference from `deductive` to `strong`. Nothing else changes.

### Is the dG prohibition upheld?

**UPHELD, and EXTENDED.** No carve-out. Three independent grounds, re-ranked as the specialist correctly urged:

1. **Pooled referent (fatal, irreparable).** Six endpoint types on one axis. The information needed to recover ΔG° — endpoint type, [S], Km, mechanism — was destroyed at label-construction time. This is an identifiability failure, not a calibration deficit. No constant inverts a many-to-one map.
2. **IC50 ≠ Kd (systematic, quantified).** At the most benign condition, [S] = Km competitive, IC50/Ki = 2 exactly → 0.4107 kcal/mol of one-signed bias, which already consumes over half the 0.77 kcal/mol public-data reproducibility floor.
3. **Sign (real, one-character, and the trap).** (6−y)·1.364 = **+8.0406**; `thermo.kd_to_dg(1.2740e-6)` = **−8.0420**. Same magnitude, opposite sign. The residual is **0.00146 kcal/mol**, not the 0.001 the specialist stated (Verifier 1 correct), and is entirely the docs' rounding of RT·ln10 = 1.364247 to 1.364.

### "Apparent" / "effective" ΔG — REFUSED

The docking-literature carve-out presumes a **single-referent** Kd/Ki regression target. This head has six referents. "Apparent ΔG" widens an error bar; the defect here is identity, and it is sign-inverted besides. A caveated "apparent ΔG = +8.04" is not a hedged claim, it is a wrong claim about the direction of a thermodynamic driving force. **There is no permissible qualified form. Do not ship one.**

### On kcal/mol as a unit — I rule against both the specialist and the paper

Verifier 1 correctly flags that the Boltz-2 appendix states *"All predictions are converted to kcal/mol prior to computing the metrics."* The authors do express this head's output in kcal/mol. The specialist's claim that the paper never calls it a binding free energy survives (19 occurrences of "free energy", all referring to FEP/ABFE/MM-PBSA or to the external ΔG reference).

But Verifier 3 caught the specialists in a self-contradiction that decides the matter: the n=1 ruling condemns "3.3 kcal/mol" for dressing a pooled-endpoint score in thermodynamic units, then renders the ensemble spread as "0.99 kcal/mol" in the replacement ledger claim it wants written. A *difference* of pooled log-potencies is no more a ΔΔG than an absolute value is a ΔG.

**Ruling: this platform renders nothing from this head in kcal/mol — not the value, not the difference, not the ensemble spread.** log₁₀ units only. The unit costs nothing to drop and is the single thing that invites the mislabel. Record in the ledger that the authors do use kcal/mol, and that the platform declines to, so that nobody later "discovers" the appendix line and concludes the panel was uninformed.

### EXACT FIELD NAMES AND STRINGS

```json
"boltz2_affinity_pred_value": 0.10515692830085754,
"boltz2_affinity_pred_value_units": "dimensionless; log10 of a potency expressed in uM, on Boltz-2's pooled-endpoint scale",
"boltz2_affinity_probability_binary": 0.44469520449638367,
"boltz2_ensemble_members": [-0.2593143582344055, 0.4696282148361206],
"boltz2_ensemble_disagreement_log10": 0.7289425730705261,
"boltz2_binary_members": [0.5521826148033142, 0.33720779418945312],
"boltz2_log_potency_backtransform_um": 1.2739633,
"boltz2_log_potency_delta_log10": null
```

Mandatory caveat, emitted verbatim wherever any of the above is displayed:

> Boltz-2's affinity head was trained on pooled Ki, Kd, IC50, AC50, EC50 and XC50 labels with a loss weighted toward within-assay differences. Its output is a log-potency score whose ordering is meaningful and whose absolute level is not calibrated to any single measurable quantity. It is not a binding free energy, not a dissociation constant, and not an IC50 under stated assay conditions. This platform reports no free energy from this head.

For a back-transformed value, the arithmetic must be shown inline:

> Back-transforming the documented relation gives 10^0.1052 µM = 1.27 µM. This is the model's log-potency scale exponentiated; it is not a measured IC50 and not a dissociation constant.

### FORBIDDEN FIELD NAMES (build-failing)

Adopt the specialist's extension (a) in full — the defect is identical one level down and currently passes nothing, because nothing currently checks:

`binding_free_energy`, `dg`, `dg_kcal`, `delta_g`, `ddg`, `free_energy`, `kd`, `kd_molar`, `kd_nm`, `ka`, `ki`, `ic50`, `ec50`, `pkd`, `pki`, `pic50`

— any of these appearing in the same object as a Boltz-affinity-derived value is a build failure. Also forbidden: passing the value to `thermo.check()`, `kd_to_dg()`, `dg_to_kd()`, or `REFERENCE_AFFINITIES`. Unflipped it is sign-inverted and `check()`'s `if dg < tightest` guard against −18.3 can never fire; flipped it is still not a ΔG.

---

## 2. THE REFUSAL CRITERION

### Does the 1000 Da rule survive?

**No. Delete it.** It fails on its own terms, and the specialist's measurement is what kills it: MW 4910 Da is **inside** the training MW bounding box (training max 5299.5 Da). Molecular weight is not what places the query outside the domain — TPSA, HBD, RotB, NumN, AmideBonds, NHOHCount and NOCount are. The rule is simultaneously over-inclusive (it would refuse the 224 training molecules the model was actually fitted on) and under-motivated (a round number is a policy, not a domain). This is criterion C4 failing: the stated ground is not the actual ground.

### The charge-axis argument — STRUCK

Verifier 2 overturns the specialist here and is right. The "zero molecules at charge ≥ +9" count uses RDKit **as-drawn formal charges** for training molecules against a **physiological net charge** for the candidate. The specialist's own proxy peptide returns `Chem.GetFormalCharge = 0` — on the training set's own scale the query is neutral, which is exactly why FormalCharge is absent from the seven descriptors that fired. Measured protonation-independently (basic-centre SMARTS), 216 unique training molecules carry ≥4 basic centres and 5 carry ≥9. **The charge axis is sparse, not empty.** By the specialist's own dichotomy that mandates a binned error curve, not composition alone.

The refusal survives anyway, on ground that is unassailable: **the heaviest single covalent species in 53,525 molecules is 2285.7 Da, counted; the query is 2.16× that.** Rest it there.

### Reference-set hygiene — mandatory before any threshold is fixed

Verifier 2's finding that **11,182 of 53,525 rows (20.9%) are duplicate canonical SMILES** is the most consequential correction in this section. It deflates the kNN threshold (39.3% of training molecules have a zero-distance neighbour), inflates the leverage denominator, and **breaks the exchangeability premise on which every conformal guarantee in the specialist's document rests.** Deduplicate to 42,343 unique molecules first. Post-dedup: kNN p95 rises 1.623 → 1.880, query margin 60.3× → 52.1×; h* = 0.001488, margin 120× → 95×. Report `n_total` and `n_unique` side by side, always.

Also disclose that the 20-descriptor matrix is **rank 19, not 20** — `pinv` was silently invoked on the interpretable panel, not only on the 200-descriptor set as the implementation notes claimed.

### THE DECISION PROCEDURE

Given molecule *x* and endpoint model *m*:

```
0. PRECONDITION. A pinned, deduplicated reference set R_m for endpoint m exists,
   with SHA256 and n_unique recorded. If not → REFUSE with reason
   "no applicability domain defined for this endpoint"  (this is an honest
   refusal about the platform, not about the molecule; say so).

1. COMPUTE, always, all four, and emit all four:
   BB(x)   = descriptors outside [min_j, max_j] of R_m, with margins
   h(x)    = x^T (X^T X)^+ x   vs  h* = 3(p+1)/n_unique
   kNN(x)  = mean standardised-Euclidean distance to 5 nearest in R_m
   T(x)    = max Morgan(r=2, 2048) Tanimoto to R_m

2. REFUSE  iff  ANY of:
   (a) kNN(x) > q_hat(alpha=0.01), the conformal-outlier quantile of the
       leave-one-out kNN distribution of R_m ;  OR
   (b) |BB(x)| >= 1  (any descriptor outside the training envelope) ;  OR
   (c) counted zero training support in x's region on a
       protonation-independent, as-drawn-consistent axis.

3. PREDICT WITH WIDENED INTERVAL  iff not refused AND ANY of:
   (d) h(x) > h*  ;  OR
   (e) kNN(x) > p95 of the LOO kNN distribution.
   Interval by Mondrian split conformal, taxonomy = AD-score decile,
   heteroscedastic score alpha_i = |y_i - yhat_i| / sigma(x_i) with
   sigma from the existing 5-model ensemble SD, quantile
   ceil((n(g)+1)(1-alpha))/n(g).
   REQUIRES n(g) >= 100 calibration molecules in the bin. If n(g) < 100,
   the case is REFUSE, not widen.

4. PREDICT otherwise, with the four AD numbers attached.
```

### Threshold provenance — every one labelled

| Threshold | Value | Source |
|---|---|---|
| `h* = 3p/n`, p = descriptors+1 | 0.001488 (dedup) | **OECD ENV/JM/MONO(2007)2 para 112**, verbatim |
| Bounding box = training min/max | — | **OECD paras 108–109**, verbatim |
| k = 5, Euclidean, standardised | — | **Khurshid et al. arXiv:2411.00920 §2.0.2** |
| Conformal outlier quantile | `ceil((n+1)(1−α))/n` | **Angelopoulos & Bates arXiv:2107.07511 §4.4, eq (14)** |
| Mondrian per-group quantile | `ceil((n(g)+1)(1−α))/n(g)` | **Angelopoulos & Bates eqs (8)–(9)** |
| Heteroscedastic score `\|y−ŷ\|/σ(x)` | — | **Xu et al. arXiv:2304.00970 eq (1)** |
| **α = 0.01 for refusal** | 0.01 | **PROJECT CONVENTION** |
| **p95 for the widen tier** | 95th pct | **PROJECT CONVENTION** |
| **n(g) ≥ 100 for a Mondrian bin** | 100 | **PROJECT CONVENTION** |
| **Refuse-if-ANY aggregation** | — | **PROJECT CONVENTION** — this is the rule the specialist never declared, and the verdict for the disputed molecule flips without it (Tanimoto 0.595 does not flag it) |

Every project convention must be written into the AD definition file **before** any query is scored, with a git commit hash. Pre-registered means pre-registered.

### What must be COMPUTED for a refusal to be principled

1. All four AD numbers, **including the one that does not flag the query.** Suppressing Tanimoto = 0.595 (with 23.6% of training molecules more isolated from their own nearest neighbour) is selective evidence. Publish it.
2. The numeric margin: `h/h*`, `kNN/q_hat`, per-descriptor BB excess.
3. The training-support count in the query's region, from a named, hashed, **deduplicated** dataset — a counted zero, never an assumed one, and counted on the same measurement scale as the query.
4. **The acceptance rate on a genuinely disjoint held-out set.** Verifier 2 measured 56.2% exact-canonical-SMILES overlap between the shipped `drugbank.csv` (2,845 molecules) and pooled TDC — it is not held out. Strip the overlap, then publish the rate on the remainder. On the un-stripped set the specialist's own rules accept **81.02%**, not the ~96% floated, with leverage alone refusing 13.29% of approved drugs. If the retuned rule still refuses one in eight marketed drugs, the domain is drawn too tight and must be widened before it is shipped.
5. C4: the stated ground must be the computed ground.

### On the conformal theorem — DEMOTED

Verifier 2 overturns the specialist and is right. Eq (14) holds for **any** score function, including a constant or a random one, because `q_hat` is defined as a quantile of the training scores. It is satisfied by construction, says nothing about power, and constrains only refusal on the *training* distribution — a platform that refuses 100% of real user queries satisfies it exactly. The source itself says the score function "is very important for the method to perform well."

**Eq (14) is a calibration device, not a proof of non-vacuity.** The empirical held-out acceptance rate is the only answer to "a platform that can only ever refuse has not been distinguished from a platform that cannot compute." Do not cite the theorem for that purpose.

### On the feature space

Every advertised number comes from a 20-descriptor linear hat matrix pooled over 16 endpoints, applied to a Chemprop message-passing GNN with 200 RDKit features plus learned graph embeddings. OECD para 98 — quoted by the specialist — requires the AD be derived on "the descriptors and (statistical) approach used to develop the model," and that "every model should be associated with its own AD." **As advertised, the numbers fail the specialist's own C1.** Production must compute per-endpoint ADs in ADMET-AI's own 200-feature space, with rank and pseudo-inverse disclosed. Ship the 20-descriptor panel alongside as the interpretable view, explicitly labelled a proxy.

---

## 3. THE n=1 RULING

### What the observation licenses

**Deductively, needing no reference value at all:**
- The repository contains a sign/units contradiction: (6−y)·1.364 = +8.0406 vs `kd_to_dg` = −8.0420. Real, and worse than the ledger states — `clm_a47c9774148de980` presents "dG = (6 − y) * 1.364 kcal/mol" as *"Verbatim from its docs,"* and the docs say **pIC50** in kcal/mol, never dG. The ledger misquotes its own source.
- **No code path commits the error.** Verified: zero matches for `1.364` under `platform/`. The contradiction is in prose. Fix the prose; add the guard so it stays fixed.
- The ensemble's two binary heads (0.5522, 0.3372) straddle 0.5 and give opposite binder/non-binder calls. This prediction is not decision-grade.
- The pipeline runs end to end: chain A = 583 residues, chain B = 18 heavy atoms, C15 N2 O1, the correct formula for huperzine A.

**As a measurement (one, and it is the good one):**
- `affinity_pred_value` is bit-identically the arithmetic mean of −0.2593143582344055 and 0.4696282148361206. The two members disagree by **0.7289 log₁₀ units** — 30.3% of the headline gap — on one input, reference-free.

### What it does not license

- **"Boltz-2 has a 2.41 log-unit error."** The gap is a composite of at least four unidentified addends. This is Duhem, not sample size: more *n* would not identify them, because three auxiliaries were never independently checked.
- **"The method's error is 3.3 kcal/mol."** Same defect plus an illegitimate unit.
- **"Validation against measured ground truth," confidence 0.95.** It is a smoke test.
- Any error bar, calibration, bias/variance split, or cross-compound ranking.
- Reading affinity from ptm/pLDDT/ipTM — `thermo.py`'s own METHOD_ACCURACY already names this a category error.
- Directional language about the model "underpredicting potency." The prediction landed 0.105 log from y = 0.

### Three specialist claims I strike

**(i) "standard_type = null" — FALSE, and it must not reach the ledger.** The record carries `activity_type: "IC50"`. The null field is `assay_confidence`. The specialist asserted this four times, built 4:1 odds on it, and drafted it into replacement ledger text. Executing that draft would insert a fabricated field value into the artifact whose entire purpose is eliminating unsourced numbers. Strike it everywhere.

**(ii) The 4:1 odds — struck.** A Kalliokoski pair is two *literature* measurements; 8/10 bounds P(the pair contains an error), which distributes across both members. It cannot be handed wholesale to one designated side, still less when the other side is a model output with its own large unconstrained error scale. Keep only the qualitative statement: at Δ ≈ 2.4, record error is a common and unexcluded explanation, and **assay CHEMBL643374 has never been inspected.**

**(iii) "y = 0 is the model's prior mean" — NOT RETRIEVED.** The docs' three examples (−3, 0, +2) are a calibration illustration with midpoint −0.5, not a distribution. Nothing in the docs or the paper states the centre of the affinity training-label distribution. Regression to the mean is a live hazard here; its magnitude and direction are unestimated. Drop the "no-information point" argument and everything resting on it.

**One further correction:** the ensemble spread is **not** an "assumption-free n=2 replicate." The docs describe value1/value2 as two fixed trained models — deterministic given the input, not i.i.d. draws. The d₂ = √2 range estimator does not apply. And the docs' own example JSON shows `affinity_pred_value` 0.8367 with value1 = value2 = 0.8225, so the mean identity is an **empirical property of this file, not a documented one.** Report the disagreement; drop "sd estimator," drop "assumption-free," drop the kcal/mol.

### EXACT WORDING TO PUBLISH

> A single end-to-end run of Boltz-2 v2.2.1 (single-sequence mode, `msa: empty`) on huperzine A + human AChE produced `affinity_pred_value` = 0.1052 on the model's pooled log-potency scale. One ChEMBL record for this pair (CHEMBL395280, assay CHEMBL643374, activity type IC50) gives 5.0 nM; the record's assay-confidence field is unpopulated and the assay has not been inspected. Back-transformed, the two differ by 2.41 log₁₀ units.
>
> **This is a smoke test, not a validation.** With one non-randomly-selected compound the discrepancy cannot be apportioned between the model, the reference record, and the run configuration, and the published inter-laboratory reproducibility floor for public IC50 data is itself 0.68 log₁₀ units (Kalliokoski et al. 2013). The model's two ensemble members disagreed by 0.73 log₁₀ units on this input and gave opposite binder/non-binder calls (0.55 vs 0.34). The interface was produced without an MSA at ipTM 0.714. **No accuracy claim is made.** The pre-registered n = 17 study at `platform/studies/ache_affinity_benchmark.py` exists to replace this observation and has not yet been run.

### Where it lives and what type it is

**`platform/tests/test_smoke_affinity.py`** — a **regression fixture**, not a validation. It asserts the archived bytes reproduce: `affinity_pred_value == 0.10515692830085754`; the bit-exact mean-of-members identity for both heads; `ptm == 0.9490268230438232`; chain A length 583; chain B formula C15 N2 O1, 18 heavy atoms. Its job is detecting pipeline drift and it does that job well. **It must assert nothing about agreement with ChEMBL.**

Ledger, in `memory/ledger/affinity-compute.jsonl`:

- `clm_2b6c59b70cb31f95` → kind `measurement` → **`smoke_test`**; confidence 0.95 → **0.6**; title → "END-TO-END SMOKE TEST (n=1, non-randomly selected, reference assay uninspected)". Use the published wording above verbatim. **Do not write "standard_type = null."**
- `clm_006980da2af0131d` → replace "a real method with a measured 2.4 log-unit error" with "a real method whose absolute accuracy is **unmeasured**, reported alongside an explicit statement of what is not known."
- `clm_a47c9774148de980` → correct the sign; add that its own "verbatim from its docs" is a misquote (docs say *pIC50* in kcal/mol, not dG); record that **no code path currently commits the error**.
- **New** `clm_ensemble_disagreement`, kind `measurement`, confidence 0.85: "`affinity_pred_value` is bit-identically the mean of members −0.25931 and 0.46963. Disagreement 0.7289 log₁₀ on one input; binary heads 0.5522 / 0.3372 straddle the 0.5 boundary and give opposite calls. Reference-free. Accounts for 30.3% of the 2.41-log gap. Reported in log₁₀ units only; this is ensemble disagreement between two fixed models, not a replicate standard deviation."

### Three compounds, three records — do not conflate them

The n=1 specialist claimed `validation_gate.json` flags this compound's SMILES as unparseable, manufacturing a doubt the existence claim then resolves. Verifier 3 is right that this conflates:
- `data/dataset.json` — legacy display record "Huperzine A (Lycopodium serratum)", SMILES unparseable, **never foldable, never a live candidate**;
- `data/curated.json` — PubChem CID 854026, InChIKey ZRJBHWIHUMBLCN-YQEJDHNASA-N, stereochemistry resolved;
- `data/corpus_ACHE.json` — CHEMBL395280, `stereocenters_undefined: 0`, `quality_flags: []`, the record the affinity study actually uses.

The archival gap is real; the manufactured doubt is not.

---

## 4. IMPLEMENTATION ORDER

**Ordered by error removed per keystroke.**

**1 — Strike the false fact (30 min).** Remove every occurrence of `standard_type = null` from rulings, panel records and draft ledger text. Replace with the accurate description: one record, activity type IC50, `assay_confidence` unpopulated, assay CHEMBL643374 uninspected. *Largest error per keystroke in the entire dispute: it is a fabricated field value about the project's own data, sitting inside the project's own audit trail, in three separate specialist documents, drafted for insertion into the ledger.*

**2 — Retype the three ledger claims and add the fourth (1 h).** Exactly as specified in §3. This removes a confidence-0.95 "ground truth" claim that the data cannot support.

**3 — Write the naming gate that was claimed to exist (1–2 h).** New suite in `verify_all.py`, expected exit 0: fail the build if any file under `platform/`, `data/` or `runs/` associates a Boltz-affinity-derived value with any name in the forbidden list of §1, or passes it to `thermo.check`/`kd_to_dg`/`dg_to_kd`/`REFERENCE_AFFINITIES`. Include a positive test that the gate catches a deliberately planted violation — a gate never shown to fire is the same defect as an AD never shown to accept.

**4 — Make the sign trap unrepresentable (1 h).** In `thermo.py`, add:

```python
def boltz_log_potency(affinity_pred_value: float) -> float:
    """Boltz-2 affinity_pred_value -> dimensionless pIC50-scale log potency (6 - y).

    NOT a free energy. NOT a Kd. The head is trained on pooled
    Ki/Kd/IC50/AC50/EC50/XC50 with a loss weighted toward within-assay
    differences; its absolute level is uncalibrated. This module deliberately
    provides NO kcal/mol conversion for this quantity.
    """
```

Add a `METHOD_ACCURACY` entry `"Boltz-2 affinity head"` with `rmse_kcal: None` and a note that no absolute-accuracy figure has been established, citing 0.729 log₁₀ ensemble disagreement as the only measured dispersion. Have any call site raise, not warn, when `affinity_probability_binary < 0.5` — the documented usage precondition fails there, which is this run's situation. (Flag: 0.5 as the decision threshold is a **project convention**; the docs state only that the field is a probability in [0,1].)

**5 — Close the provenance hole (2 h).** `runs/919fef2194e3` has no archived `input.yaml`; so does `runs/9704aa8b5dda`. Make `runs/manifest.json` schema-require an input record, backfill both with an explicit "input not preserved; ligand identity reconstructed post hoc from mmCIF by heavy-atom formula only, stereochemistry unverified," and add `unarchived_input` as a `validation_gate.json` category. Add `affinity_offlabel_usage` for any future record comparing `affinity_pred_value` to a measured value while `affinity_probability_binary < 0.5`.

**6 — Run the study you already registered (1 day).** `platform/studies/ache_affinity_benchmark.py --register --run --analyse`. Neither specialist noticed it exists. Do not design a new one until H1/H2/H3 have returned. Only then decide whether n = 17 needs extending toward the 30–65 range — and if it does, extend it as a pre-registered amendment, planning on an **upper confidence limit** for σ, never on the 2.41 pilot gap (which would give n = 267 and waste the effort on a number with no standing).

**7 — Rebuild the AD (1 week).** Deduplicate to 42,343; recompute per endpoint in the 200-feature space with rank and pinv disclosed; declare the aggregation rule and the three project conventions in a version-pinned file; strip the 56.2% TDC overlap from the DrugBank set and publish the acceptance rate on the remainder; retune if it still refuses >5% of marketed drugs. **Delete the 1000 Da rule in the same commit that lands the replacement, not before** — an undefended refusal is still better than an undefended prediction.

---

## 5. WHAT REMAINS UNRESOLVED

**1. The absolute accuracy of the affinity head.** Nothing in this dispute measures it. *Settled by:* running the registered n = 17 study, then extending to n ≈ 30–65 sampled **randomly** from the applicability domain, requiring populated activity types, preferring multiple independent records per pair, restricting to `affinity_probability_binary > 0.5`, and running **paired** MSA / single-sequence conditions so the configuration auxiliary is tested rather than assumed. Report against the 0.68 log₁₀ floor and state plainly that no method can be shown to beat it on heterogeneous public data.

**2. Whether the 5.0 nM reference is sound.** Unknown, and nobody has looked. *Settled by:* fetching assay CHEMBL643374 and document CHEMBL1129143, and pulling all 23 ChEMBL IC50 records for this pair (reported elsewhere in this repository as spanning 3.99 log units — a 5.4 log spread in the reference data that is itself larger than the disputed gap). Two hours of work that would have prevented most of this dispute.

**3. Whether the disputed peptide is actually outside the domain.** Every AD number in the record is for a **constructed 43-residue proxy**, not the real 4943 Da candidate, and the proxy's as-drawn formal charge is 0. *Settled by:* obtaining the actual structure and re-running the panel. Until then the refusal rests on the MW axis alone — which is sufficient, but say so rather than implying a four-axis case.

**4. The charge axis.** Broken as measured. *Settled by:* a pH 7.4 protonation model (Dimorphite-DL or equivalent) applied uniformly to both the training set and the query, or a protonation-independent basic-centre count. Report the non-zero counts honestly (216 unique training molecules with ≥4 basic centres, 5 with ≥9). If the axis turns out sparse-but-nonzero — which it appears to be — it demands a binned error curve, not a refusal.

**5. Whether the two ensemble members are independent.** Assumed, not shown; the docs' example JSON has value1 = value2, contradicting the mean identity observed here. *Settled by:* inspecting the two checkpoints, and re-running with several seeds to separate model-to-model disagreement from sampling variance. This matters because the 0.729 figure is the only dispersion estimate the project owns.

**6. Whether ensemble SD is usable as the heteroscedastic σ(x) in the widened-interval tier.** Sheridan 2015 recommends exactly that signal for diverse training sets; Ovadia and Hirschfeld measured that it degrades under shift, and Hirschfeld is co-authored by an ADMET-AI author. The specialist cited the positive literature and then discarded the metric it recommends. *Settled by:* computing the mean pairwise Carhart/Dice similarity of the pinned corpus to establish which regime applies, then measuring error-ranking performance of ensemble SD per endpoint on held-out TDC data. Do not resolve this by argument; it is an empirical question with a cheap experiment.