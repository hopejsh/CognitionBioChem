# CognitionBioChem — Expert Panel Review and Remediation Report

Produced by a multi-agent review system: 12 PhD-level domain reviewers, 12 independent adversarial verifiers, a panel chair, and 2 completeness critics. Every finding was re-checked by a verifier who was instructed to refute it and to default to skepticism when it could not be independently confirmed.

## 1. Scope and method

| | |
|---|---|
| Disciplines reviewed | 12 |
| Findings raised | 97 |
| Findings independently verified | 76 |
| Confirmed | 75 (50 with a factual correction) |
| Partially refuted | 1 |
| Fully refuted | 0 |

The low refutation rate is not verifier leniency. Most findings are arithmetic or presence/absence claims about source code, so they are checkable rather than arguable, and the largest ones were independently reproduced by a separate local validation pipeline (section 4) that was written without reference to the panel's output.

### Severity

| Severity | Count |
|---|---|
| BLOCKER | 28 |
| CRITICAL | 36 |
| MAJOR | 27 |
| MINOR | 6 |

### Category

| Category | Count |
|---|---|
| scientific error | 23 |
| fabricated data | 18 |
| methodological flaw | 13 |
| unsupported claim | 13 |
| engineering defect | 13 |
| missing capability | 12 |
| legal compliance | 3 |
| integrity risk | 2 |

## 2. Panel verdict

> CognitionBioChem is a competently built, visually polished single-page web front-end (README.md, index.html, app.js, styles.css — the only tracked project files besides .gitignore and skills-lock.json) that presents hand-typed literal values as the output of computational structural biology. It claims to be an "AlphaFold3 De Novo Drug Discovery Platform" with "live AlphaFold Server" integration that "models 25 De Novo Targeted Bio-Conjugate Therapeutics designed via AlphaFold3"; it is in fact a static mockup with no inference code, no model weights, no API client, no network call of any kind (grep for fetch/XMLHttpRequest/axios over all platform files: zero hits), and no AF3 artifact on disk (no .cif, no confidences.json, no ranking_scores.csv; grep for iptm/ranking_score/atom_plddts/msa: zero hits). I re-derived every quantitative claim myself: the "AlphaFold3 pLDDT Score" is `93 + sin(i*0.4)*4 + (charCode % 5)*0.5` (app.js:791), analytically bounded to [89.0, 99.0] — across all 876 residues of the 25 drugs, mean 94.11, and zero residues below 70, so the UI's "Low (50-70)" and "Very Low (<50)" legend bands (index.html:390-391) are mathematically unreachable and the clamps at app.js:792-793 are dead code; the "PAE" is `0.4*|i-j| + f(i)` (app.js:850), asymmetric by construction, with a global maximum of 18.50 Å against an axis captioned "0 - 30 Å" (index.html:397); the "Real Sequence 3D Structure (pLDDT Color Spectrum)" is a parametric helix whose radius is `6 + (charCode % 5) * 0.8` (app.js:715) colored by amino-acid letter, not by any confidence value (app.js:747-749); the 25 ΔG/Kd pairs are irreconcilable, with every one of the 25 stated ΔG values more negative than RT·ln(Kd) by 3.85–5.73 kcal/mol at r = 0.9969, i.e. generated from one another by a wrong constant; the 25 "targeted therapeutics" contain only 21 distinct sequences, four of which appear twice against unrelated receptors (the same 41-mer binds both α7 nAChR ECD and TLR4/MD-2; the same 31-mer binds both the extracellular Frizzled-8 CRD and the cytoplasmic ZO-1 scaffold) with different fabricated affinities each time, plus five further collisions with the leaderboard carrying a third divergent metric set; three entries are not valid sequences at all (two contain the ambiguity code 'B', and app.js:381 is the prose string "His14-Phe174-Linker-Peptide-Conjugate", for which the app nonetheless renders a full pLDDT curve and prints "AF3 pLDDT = 92.4 / 100"); and half the chemistry is unusable — 4 of 8 SMILES fail to parse in RDKit and two more encode the wrong molecule (Ginsenoside Rg1 parses to C38H64O14 against a claimed C42H72O14; Ginkgolide B to C18H22O8 against C20H24O10). The author's own comment at app.js:1048 reads "// --- Chart.js Benchmark Simulation ---". This is not a modeling error that better parameters would fix; it is a provenance failure in which every displayed number is a string literal or a trigonometric expression labelled with the name of a specific published method, compounded by an implied Google DeepMind affiliation (README.md:3 Google-logo badge, index.html:30 subtitle, index.html:410 footer) that does not exist. The right characterization is: a good user-interface prototype for a platform that has not been built, currently mislabelled as the platform itself.

## 3. Root causes

The panel compressed the findings into a small number of underlying causes.

1. PRESENTATION BUILT BEFORE COMPUTATION, THEN LABELLED AS COMPUTATION. The UI was designed first and populated with plausible-looking values so the panels would render. Every 'metric' in the app is either a string literal in an array or a closed-form expression over ASCII character codes; there is no computational substrate underneath any of it. The information architecture is right and the data layer is empty, and the empty layer was given the names of real methods ('AlphaFold3 pLDDT Score' at app.js:802, 'REAL FASTA SEQUENCE PARSING' at app.js:707, 'AlphaFold Server Live Connected' at index.html:42).

2. NO VALIDATION LAYER ANYWHERE, WHICH IS WHY THE FABRICATION IS SELF-EVIDENT. Not one input is checked before use. A prose string ('His14-Phe174-Linker-Peptide-Conjugate', app.js:381) and the non-residue ambiguity code 'B' (app.js:130, 173, 371) flow unchecked into the 3D viewer, the pLDDT chart and the PAE heatmap; 4 of 8 SMILES fail RDKit; 11 of 25 sequences carry an odd cysteine count with no declared disulfide connectivity. A two-line regex and one RDKit call would have caught all of it. Their absence is the cleanest proof that no pipeline ever ran, because a real pipeline fails loudly on these inputs.

3. BORROWED VOCABULARY WITHOUT THE UNDERLYING SEMANTICS — A CATEGORY ERROR, NOT JUST MISSING CODE. AlphaFold3 is a structure predictor with no generative sequence head; nothing can be 'designed via AlphaFold3' (README.md:22) or 'AlphaFold3-optimized' (README.md:45). pLDDT is a local self-consistency estimate, not a binding or ranking metric, yet it is packed into one string with a ΔG and a Kd (app.js:146 and 24 others) as if all three were outputs of one calculation. AF3 emits no free energy and no Kd. And every claimed 'job' is a bare peptide with no receptor chain and no ligand entity, so ipTM, interface PAE, ΔG and Kd are undefined for the stated input even if a genuine run had occurred — which is also why the metrics that actually govern binder design (ipTM, interface PAE, ranking_score, has_clash) appear zero times.

4. SEQUENCES ASSEMBLED BY MOTIF COPY-PASTE WITHOUT CHECKING THE BIOLOGY, PRODUCING DIRECTIONAL INVERSIONS. The peptides are concatenations of verbatim natural motifs joined by GGGGS linkers — GSK3B (P49841) 3-34, BDNF (P23560) 19-39, APP (P05067) 687-706, NFE2L2 (Q16236) 77-84 — not de novo designs. Because provenance was copied but pharmacology was not checked, several are inverted: BasalAChE-Abeta-B4 (app.js:277) grafts Aβ16-35, the aggregation-nucleating core, into a molecule labelled 'Aβ Fibril Disruptor' with 'Fibril Blockade: 100%'; PfcGsk-WntLinker-P4 offers GSK-3β's own N-terminal pseudosubstrate tail as an ATP-pocket ligand; CogBDNF-Mimic-04 uses the BDNF prodomain, which signals with opposite polarity to mature BDNF; AstroZo1-Protect-A3 aims an extracellular peptide at a cytoplasmic scaffold.

5. NO NEGATIVE RESULTS, NO UNCERTAINTY, NO CONTROLS, NO PROVENANCE — SO NOTHING IS FALSIFIABLE FROM INSIDE THE ARTIFACT. All 25 candidates succeed: every Kd < 5 nM, every pLDDT > 92, every row 'hERG IC50 > 50 μM', with 'Off-target Binding: None', 'Fibril Blockade: 100%', 'Cytokine Storm Risk: 0%'. There is no held-out set, no baseline, no reference compound, no scrambled-sequence control, no seed, no model version, no timestamp, no error bar, and no applicability-domain statement anywhere. The leaderboard's ranking key, 'CEI', is undefined in the entire repository. Against the field's own attrition baselines this 25/25 outcome is not a strong result, it is an absent one.

6. MODALITY MISMATCH IN THE SAFETY LAYER: SMALL-MOLECULE LIABILITIES REPORTED FOR PEPTIDES, PEPTIDE LIABILITIES OMITTED. Every candidate is a 3–11 kDa, often strongly polycationic peptide conjugate, yet the panel reports hERG (largely out of applicability domain, and justified at README.md:99 by a claim about 'hydrophobic peptide linkers' when every linker in the repo is the hydrophilic Gly-Ser G4S) and an invented 'Seizure Index', while omitting hemolysis, mammalian cytotoxicity, aggregation propensity, proteolytic stability, MHC-II immunogenicity, BBB permeability and PK entirely. A section titled 'In Silico ADMET' contains no absorption, distribution, metabolism or excretion of any kind — and no exposure estimate, so the hERG safety margin that actually determines cardiac risk cannot be computed at all.

## 4. Independent local verification

These numbers were computed in this repository with RDKit 2026.03.5 and the Python standard library, independently of the panel. Where they overlap, they agree.

| Check | Result |
|---|---|
| Natural-product SMILES that fail to parse | 4 / 8 |
| SMILES encoding a different molecule than their name | 1 |
| Structures with every stereocentre undefined | 3 |
| Sequences containing non-standard residues | 4 / 35 |
| (ΔG, Kd) pairs that are thermodynamically inconsistent | 25 / 25 |
| Largest ΔG/Kd inconsistency | 5.73 kcal/mol |
| Sequences shared by two supposedly distinct candidates | 4 |

### The decisive comparison

The clearest single piece of evidence is what real predictor output looks like beside the formula the platform used. Genuine AlphaFold output for human TrkB (UniProt Q16620) was downloaded from EBI and parsed by `platform/cbc/predictor.py`:

| pLDDT statistic | Real AlphaFold (TrkB, 822 residues) | `app.js:791` formula |
|---|---|---|
| minimum | 23.5 | 89.0 |
| maximum | 98.4 | 99.0 |
| mean | 77.0 | 94.0 |
| standard deviation | 22.9 | 3.0 |
| fraction below 70 | **26.2%** | **0.0%** |

Because the formula is analytically confined to [89.0, 99.0], two of the four confidence bands advertised in the legend were unreachable. The fake also inverts the true signal exactly where it matters: GGGGS linkers, which a real predictor renders at pLDDT 30–60, were painted 'High' green at 89–97.

Backbone geometry gives the same answer. Real coordinates have consecutive Cα atoms at 3.83 ± 0.09 Å. The parametric helix at `app.js:715` produces 0.63–16.6 Å, with 18 of 23 virtual bonds outside ±0.5 Å of the physical value.

## 5. Blocking findings

### B1

NO ALPHAFOLD3, AND NO STRUCTURE PREDICTION OF ANY KIND, EXISTS IN THE PLATFORM. Verified: zero network calls (no fetch/XMLHttpRequest/axios in app.js), zero AF3 output fields (no iptm, ranking_score, confidences.json, summary_confidences, atom_plddts, has_clash, chain_pair_pae_min), zero MSA/inference dependencies (no msa, a3m, jackhmmer, uniref, mgnify), and no .cif/.pdb structure file on disk. The 'AlphaFold Server Live Connected' badge (index.html:42) and the 'Launch AlphaFold Server' button (index.html:363) are ordinary <a href> hyperlinks; the only 'integration' is a clipboard write (app.js:660-671). README.md:22's central claim — 25 therapeutics 'designed via AlphaFold3' — and README.md:24/111's 'direct live integration' are false as statements about this software.

### B2

EVERY DISPLAYED CONFIDENCE AND STRUCTURE IS A CLOSED-FORM FAKE THAT IS PROVABLY DISTINGUISHABLE FROM REAL OUTPUT. pLDDT = 93 + sin(i*0.4)*4 + (charCode%5)*0.5 (app.js:791): I reproduced min 89.0, max 99.0, mean 94.11 over all 876 residues, 0% below 70, making two of the four advertised legend bands unreachable and the clamps at app.js:792-793 dead code. PAE = 0.4|i-j| + f(i) (app.js:850): asymmetric, no domain blocks, global max 18.50 Å against a '0 - 30 Å' caption, and the grid is silently truncated at 45 tokens (app.js:844), dropping residues 46-47 of the 47-mer. The 3D 'backbone' (app.js:711-761) is a helix with radius 6 + (charCode%5)*0.8 whose consecutive point spacing I measured at 0.63–16.6 units against a real, essentially invariant Cα–Cα distance of 3.80 ± 0.04 Å, colored by residue letter rather than by any confidence value. These panels invert the true signal precisely where it matters: GGGGS linkers, which real AF3 renders at pLDDT 30-60, are rendered here at 89-97 and painted 'High' green.

### B3

THE AFFINITY DATA IS THERMODYNAMICALLY IMPOSSIBLE ON ALL 25 ROWS. Applying ΔG = RT·ln(Kd) at 298.15 K (RT = 0.5925 kcal/mol), every stated ΔG is more negative than the value implied by its stated Kd, by 3.85 to 5.73 kcal/mol, with the same sign on all 25 rows and Pearson r(ΔG, log10 Kd) = 0.9969 — the two columns were generated from one another with a wrong constant, not measured or computed. Example: HippoTrk-Saponin-X1 states ΔG = -18.4 kcal/mol with Kd = 0.32 nM, whereas -18.4 implies Kd = 0.033 pM, a factor of ~9,800. No AF3-class model outputs a ΔG or a Kd in any case.

### B4

THE DATASET CONTRADICTS ITSELF: IDENTICAL SEQUENCES CARRY DIFFERENT 'MEASURED' METRICS AND ARE ASSIGNED TO UNRELATED, SOMETIMES INACCESSIBLE, TARGETS. The '25 targeted therapeutics' contain only 21 distinct sequences. The identical 41-mer at app.js:195/319 is declared a binder of both the α7 nAChR extracellular domain and the TLR4/MD-2 complex (ΔG -16.5/1.8 nM/93.2 vs -15.7/3.8 nM/92.8); the identical 31-mer at app.js:173/371 binds both the extracellular Frizzled-8 CRD and the cytoplasmic ZO-1/occludin scaffold, which an extracellular peptide cannot reach; the same 36-mer and 37-mer likewise appear twice. Five further collisions with the AF3_CANDIDATES leaderboard give the same strings a third set of values (the 36-mer carries pLDDT 94.8 / 94.3 / 92.8 and ΔG -16.2 / -17.5 / -12.6). One molecule cannot have three binding free energies, and no target-conditioned method emits one sequence optimized for two unrelated folds.

### B5

SEQUENCE AND CHEMISTRY INPUTS ARE INVALID AND UNVALIDATED, WHICH IS INDEPENDENTLY DISPOSITIVE. Three of the 25 'sequences' are not sequences: two contain the IUPAC ambiguity code 'B' at position 19 (app.js:173, 371; also app.js:130), and app.js:381 is the prose string 'His14-Phe174-Linker-Peptide-Conjugate' — which the app nonetheless feeds to the 3D viewer, the pLDDT chart and the PAE heatmap, generating a 37-'residue' AlphaFold3 confidence profile from the letters of the English word 'Linker' while printing 'AF3 pLDDT = 92.4 / 100'. On the chemistry side, RDKit rejects 4 of the 8 SMILES outright (Huperzine A, Curcumin — 'OCH3' is not valid SMILES — plus two entries that are bare molecular formulas typed into a field the UI labels 'SMILES Formulation'), and two that do parse encode the wrong molecule (Rg1 → C38H64O14 vs claimed C42H72O14; Ginkgolide B → C18H22O8 vs C20H24O10). No real pipeline could have consumed these inputs.

### B6

THE ENTIRE 'IN SILICO ADMET & SAFETY' SECTION IS 25 HAND-TYPED PROSE STRINGS WITH NO MODEL, AND SEVERAL ARE INVERTED. All 25 safety values are string literals read at exactly one place (app.js:640) and interpolated into HTML; 24 of 25 carry the byte-identical 'hERG IC50 > 50 μM' and the 'Seizure Index' takes only three values {0.00, 0.01, 0.02} across 21 rows. README.md:98 states these candidates 'underwent rigorous computational safety screening'; no screening of any kind was performed. '0% Risk' / '0% Cardiotoxicity' / 'Cytokine Storm Risk: 0%' / 'BBB Disruption Risk: 0.0%' are unfalsifiable claims, and the hERG margin that determines actual risk (IC50 / free Cmax) cannot be computed because the repository contains no dose, route, species or exposure estimate. Two entries are affirmatively hazardous as labelled: BasalAChE-Abeta-B4 (app.js:277) and CogAbeta-Clearer-08 (app.js:129) carry Aβ16-35 — the aggregation-nucleating core, the positive control in fibrillization assays — as the payload of an 'Aβ Fibril Disruptor' claiming 'Fibril Blockade: 100%'; and 'Peripheral Side Effects: None' (app.js:251) is attached to a candidate whose own stated mechanism is raising synaptic acetylcholine by +350%.

### B7

IMPLIED GOOGLE DEEPMIND AFFILIATION AND A WORKFLOW THAT THE NAMED ROUTE PROHIBITS. README.md:3 renders a Google-logo shields.io badge reading 'AlphaFold3 | DeepMind_Server'; index.html:30 subtitles the product 'DeepMind Structural Pharmacology & AlphaFold3 De Novo Platform'; index.html:410 footers it 'Generated with AlphaFold3 3D Structural Modeling'. Nothing here is from, endorsed by, or connected to Google DeepMind. Separately, AF3 model parameters are request-only, non-commercial and non-redistributable, and the AlphaFold Server Prohibited Use Policy forbids using the server or its outputs in an automated system that predicts protein binding with ligands or peptides — which is exactly what this platform describes itself as. This is a publication/distribution blocker independent of the scientific ones.

## 6. Full findings register

Sorted by severity, then discipline. Verdict is the independent verifier's.

| ID | Sev | Discipline | Finding | Verdict |
|---|---|---|---|---|
| `AIML-01` | BLOCKER | AI/ML evaluation methodology,… | There is no evaluation of any kind in this project; the "Computational Benchm… | confirmed* |
| `AIML-02` | BLOCKER | AI/ML evaluation methodology,… | The pLDDT curves, PAE heatmap, and 3D "confidence spectrum" are closed-form c… | confirmed* |
| `AIML-03` | BLOCKER | AI/ML evaluation methodology,… | Identical input sequences are assigned different ΔG, Kd, and pLDDT and differ… | confirmed* |
| `AIML-01` | BLOCKER | AI/ML for ADMET and toxicity … | The entire "In Silico ADMET & Safety" layer is 25 hardcoded prose strings — t… | confirmed* |
| `CT-01` | BLOCKER | Computational chemistry / bin… | All 25 (ΔG, Kd) pairs violate ΔG° = RT ln Kd by 3.85–5.73 kcal/mol (2.8–4.2 o… | confirmed |
| `CT-02` | BLOCKER | Computational chemistry / bin… | The ΔG/Kd values are demonstrably not the output of any calculation: identica… | confirmed* |
| `CT-04` | BLOCKER | Computational chemistry / bin… | AlphaFold3 does not compute binding free energy, and the repository contains … | confirmed |
| `DMPK-01` | BLOCKER | DMPK / CNS drug delivery (neu… | No route of administration, dose, dosing frequency, formulation, or PK/PD mod… | confirmed |
| `DMPK-02` | BLOCKER | DMPK / CNS drug delivery (neu… | All 25 candidates are 2.9-5.4 kDa hydrophilic polypeptides with no BBB transp… | confirmed* |
| `GENO-01` | BLOCKER | Human genetics & genomics — t… | No human genetic, transcriptomic, or genomic evidence exists anywhere in the … | confirmed* |
| `GENO-02` | BLOCKER | Human genetics & genomics — t… | The platform never states an indication, a patient population, or a target pr… | confirmed |
| `AIML-01` | BLOCKER | Machine learning for protein … | The 25 "de novo designed" therapeutics are concatenations of copied natural m… | confirmed* |
| `AIML-02` | BLOCKER | Machine learning for protein … | Identical sequences are assigned to structurally unrelated targets: only 21 u… | confirmed* |
| `AIML-03` | BLOCKER | Machine learning for protein … | The pLDDT curves, PAE heatmaps and 3D structures are closed-form functions of… | confirmed* |
| `AIML-01` | BLOCKER | Machine learning for protein … | AlphaFold3 is entirely absent from the codebase; "Live AlphaFold Server Conne… | confirmed* |
| `AIML-02` | BLOCKER | Machine learning for protein … | All pLDDT and PAE values are closed-form fakes that are statistically disting… | confirmed* |
| `MEDCHEM-01` | BLOCKER | Medicinal chemistry / natural… | Half the natural-product SMILES strings are not valid SMILES and do not parse… | confirmed |
| `MEDCHEM-04` | BLOCKER | Medicinal chemistry / natural… | Every structure in the platform is stereochemically flat, so each saponin/ter… | confirmed* |
| `MEDCHEM-07` | BLOCKER | Medicinal chemistry / natural… | Every conjugate is a 3.5-6.1 kDa polycationic peptide that cannot reach the C… | confirmed* |
| `MOLBIO-01` | BLOCKER | Molecular neurobiology / neur… | The "binding-loop peptides" do not occur in the proteins they are attributed … | confirmed* |
| `MOLBIO-02` | BLOCKER | Molecular neurobiology / neur… | Four peptide sequences are byte-identical but assigned to unrelated targets w… | confirmed* |
| `INTEG-01` | BLOCKER | Research integrity, scientifi… | Values generated by hardcoded display formulas are labelled as AlphaFold3 mod… | confirmed* |
| `INTEG-02` | BLOCKER | Research integrity, scientifi… | All 25 ΔG/Kd pairs are thermodynamically impossible; the pair was co-generate… | confirmed* |
| `SWE-01` | BLOCKER | Research software engineering… | AlphaFold3 is never invoked; every "AF3" pLDDT, PAE, and 3D coordinate is a h… | confirmed |
| `SWE-02` | BLOCKER | Research software engineering… | Identical sequences are published as distinct candidates carrying mutually co… | confirmed* |
| `SB-01` | BLOCKER | Structural biology — macromol… | The "3D structure" is a parametric ASCII-driven helix, not a protein backbone… | confirmed* |
| `SB-02` | BLOCKER | Structural biology — macromol… | pLDDT profiles and PAE heatmaps are closed-form functions of ASCII codes and … | confirmed* |
| `SB-03` | BLOCKER | Structural biology — macromol… | AlphaFold 3 cannot model a covalently conjugated natural-product warhead in t… | confirmed |
| `AIML-04` | CRITICAL | AI/ML evaluation methodology,… | Every predicted binding claim is scored with a monomer confidence metric; not… | confirmed* |
| `AIML-05` | CRITICAL | AI/ML evaluation methodology,… | Efficacy and safety are reported as bare point estimates from experiments tha… | confirmed* |
| `AIML-02` | CRITICAL | AI/ML for ADMET and toxicity … | "hERG IC50 > 50 μM (0% Risk)" — a 0% risk statement is never defensible, and … | confirmed* |
| `AIML-03` | CRITICAL | AI/ML for ADMET and toxicity … | The stated hERG mechanism is factually contradicted by the repo's own sequenc… | confirmed* |
| `AIML-04` | CRITICAL | AI/ML for ADMET and toxicity … | "Seizure Index = 0.01-0.02 / 1.0" is a fabricated metric — no such standardiz… | confirmed* |
| `AIML-05` | CRITICAL | AI/ML for ADMET and toxicity … | "Tolerance Downregulation < 4.2% after 30 days" cannot be produced by any in-… | confirmed* |
| `AIML-06` | CRITICAL | AI/ML for ADMET and toxicity … | "Low Immunogenicity" is asserted for 4-11 kDa foreign peptides with zero epit… | confirmed |
| `AIML-07` | CRITICAL | AI/ML for ADMET and toxicity … | The liabilities that actually govern this modality — membrane lysis/hemolysis… | confirmed |
| `AIML-08` | CRITICAL | AI/ML for ADMET and toxicity … | Two candidates use Aβ16-35 / Aβ16-23 verbatim as the therapeutic payload and … | confirmed* |
| `CT-03` | CRITICAL | Computational chemistry / bin… | The stated ΔG magnitudes are at or beyond the empirical ceiling for non-coval… | partial |
| `DMPK-03` | CRITICAL | DMPK / CNS drug delivery (neu… | Four candidates are cationic amphipathic alpha-helices with hydrophobic momen… | confirmed* |
| `DMPK-04` | CRITICAL | DMPK / CNS drug delivery (neu… | Two candidates contain the amyloid-beta(16-35) core sequence verbatim and are… | confirmed |
| `DMPK-05` | CRITICAL | DMPK / CNS drug delivery (neu… | Brain-region-specific targeting is asserted for all 25 candidates with no tar… | confirmed* |
| `GENO-03` | CRITICAL | Human genetics & genomics — t… | Human genetics points the wrong way for four target programmes: the platform … | confirmed* |
| `AIML-04` | CRITICAL | Machine learning for protein … | Three sequences contain the invalid residue letter B, one "sequence" is a pla… | confirmed* |
| `AIML-05` | CRITICAL | Machine learning for protein … | Copy-pasting motifs without understanding them produced four mechanistically … | confirmed* |
| `AIML-03` | CRITICAL | Machine learning for protein … | pLDDT is misused as a binder-quality and affinity metric; the interface metri… | confirmed* |
| `AIML-04` | CRITICAL | Machine learning for protein … | The "REAL FASTA SEQUENCE PARSING & 3D BACKBONE TOPOLOGY" viewer renders a phy… | confirmed* |
| `AIML-05` | CRITICAL | Machine learning for protein … | The claimed AlphaFold3 jobs are under-specified: no receptor chain and no lig… | confirmed* |
| `MEDCHEM-02` | CRITICAL | Medicinal chemistry / natural… | The compound labelled 'Baicalein' is a different flavone — 6,7,8-trihydroxyfl… | confirmed* |
| `MEDCHEM-03` | CRITICAL | Medicinal chemistry / natural… | Ginsenoside Rg1 and Ginkgolide B SMILES encode constitutionally wrong molecul… | confirmed* |
| `MEDCHEM-05` | CRITICAL | Medicinal chemistry / natural… | Two candidates are the amyloidogenic core of Abeta, Abeta(16-35) verbatim, pr… | confirmed |
| `MEDCHEM-06` | CRITICAL | Medicinal chemistry / natural… | The central 'natural-product warhead fused to a peptide' design premise is st… | confirmed* |
| `MOLBIO-03` | CRITICAL | Molecular neurobiology / neur… | AChE binding sites mix Torpedo californica and human residue numbering inside… | confirmed |
| `MOLBIO-04` | CRITICAL | Molecular neurobiology / neur… | A 36-mer polycationic peptide cannot clamp both the AChE CAS and PAS, and the… | confirmed* |
| `MOLBIO-05` | CRITICAL | Molecular neurobiology / neur… | TrkB d5 domain is correctly identified but four of six named binding residues… | confirmed* |
| `MOLBIO-06` | CRITICAL | Molecular neurobiology / neur… | Two candidates are labelled positive allosteric modulators while the residues… | confirmed |
| `MOLBIO-07` | CRITICAL | Molecular neurobiology / neur… | Efficacy magnitudes (+280% LTP, +310% spine density, +350% ACh, +420% phagocy… | confirmed* |
| `INTEG-03` | CRITICAL | Research integrity, scientifi… | Absolute safety claims ('0% Risk', 'Peripheral Side Effects: None', 'Cytokine… | confirmed* |
| `INTEG-04` | CRITICAL | Research integrity, scientifi… | In-vivo efficacy and chronic-dosing outcomes (LTP +280%, ACh +350%, CBF +45%,… | confirmed |
| `INTEG-05` | CRITICAL | Research integrity, scientifi… | 'AlphaFold Server Live Connected' and 'Generated with AlphaFold3' assert a co… | confirmed* |
| `SWE-03` | CRITICAL | Research software engineering… | No schema, type, unit, or range validation exists anywhere; scientific values… | confirmed |
| `SWE-04` | CRITICAL | Research software engineering… | Not reproducible or installable by anyone: no manifest, no environment, no te… | confirmed* |
| `SWE-07` | CRITICAL | Research software engineering… | No LICENSE file, no AlphaFold3 citation, and DeepMind/Google branding plus a … | confirmed* |
| `SB-04` | CRITICAL | Structural biology — macromol… | Four pairs of candidates share byte-identical sequences yet report different … | confirmed* |
| `SB-05` | CRITICAL | Structural biology — macromol… | 103 cysteines across 25 designs, 11 with an odd count, with no disulfide conn… | confirmed* |
| `AIML-06` | MAJOR | AI/ML evaluation methodology,… | No result in the platform is reproducible: no AF3 job records, no seeds, no m… | confirmed |
| `AIML-07` | MAJOR | AI/ML evaluation methodology,… | "Live AlphaFold Server Connection" and "AlphaFold Server Live Connected" desc… | confirmed |
| `AIML-09` | MAJOR | AI/ML for ADMET and toxicity … | No safety value in the platform carries uncertainty, an applicability-domain … | confirmed |
| `CT-05` | MAJOR | Computational chemistry / bin… | One-decimal ΔG values are reported with no uncertainty, no method, no tempera… | confirmed* |
| `CT-06` | MAJOR | Computational chemistry / bin… | 'Cognitive Enhancement Index (CEI)' is an invented score with no definition, … | confirmed* |
| `DMPK-06` | MAJOR | DMPK / CNS drug delivery (neu… | No proteolytic stability or plasma-half-life consideration; all 25 are unmodi… | confirmed |
| `DMPK-07` | MAJOR | DMPK / CNS drug delivery (neu… | Efficacy is ranked on binding free energy and Kd alone; Kp,uu,brain, fu,plasm… | confirmed |
| `DMPK-08` | MAJOR | DMPK / CNS drug delivery (neu… | Developability and CMC are unassessed and the advertised "Copy FASTA -> Launc… | confirmed* |
| `GENO-04` | MAJOR | Human genetics & genomics — t… | The '5 brain regions / cell-type targeted' organising claim rests on no expre… | confirmed* |
| `GENO-05` | MAJOR | Human genetics & genomics — t… | TREM2 is the one genetically validated target and the agonist direction is ri… | confirmed* |
| `AIML-06` | MAJOR | Machine learning for protein … | "Designed via AlphaFold3" is category-incoherent (AF3 is a structure predicto… | confirmed |
| `AIML-06` | MAJOR | Machine learning for protein … | Two sequences contain the non-residue character 'B' and one field is not a se… | confirmed |
| `AIML-07` | MAJOR | Machine learning for protein … | AlphaFold3 availability is misrepresented, the described workflow is prohibit… | confirmed |
| `MEDCHEM-08` | MAJOR | Medicinal chemistry / natural… | No assay-interference assessment anywhere, though four of eight compounds are… | confirmed* |
| `MEDCHEM-09` | MAJOR | Medicinal chemistry / natural… | AChE binding-site residue lists are chimeras of Torpedo and human numbering; … | confirmed |
| `MEDCHEM-10` | MAJOR | Medicinal chemistry / natural… | No chemistry layer exists: no structure validation, canonicalization, InChIKe… | confirmed* |
| `MOLBIO-08` | MAJOR | Molecular neurobiology / neur… | The M1/M2 microglial polarization dichotomy organising an entire brain-region… | confirmed |
| `MOLBIO-09` | MAJOR | Molecular neurobiology / neur… | TREM2 agonism by a linear monovalent 12-mer is not a plausible mechanism, and… | confirmed* |
| `MOLBIO-10` | MAJOR | Molecular neurobiology / neur… | The Keap1 module conflates two mechanistically distinct interventions in diff… | confirmed |
| `INTEG-06` | MAJOR | Research integrity, scientifi… | Google DeepMind branding, an AlphaFold3 shield badge with the Google logo, an… | confirmed* |
| `INTEG-07` | MAJOR | Research integrity, scientifi… | The candidate dataset is internally contradictory and partly not chemistry: i… | confirmed* |
| `INTEG-08` | MAJOR | Research integrity, scientifi… | Reference natural-product SMILES are wrong or unparseable, showing the curate… | confirmed* |
| `SWE-05` | MAJOR | Research software engineering… | Every drug-modal open leaks a WebGL context and installs a permanent, uncance… | confirmed* |
| `SWE-06` | MAJOR | Research software engineering… | Unpinned Chart.js CDN dependency, a five-year-stale Three.js, and zero Subres… | confirmed |
| `SWE-08` | MAJOR | Research software engineering… | No architectural layering: 36% of the application script is scientific data l… | confirmed* |
| `SB-06` | MAJOR | Structural biology — macromol… | No structure validation of any kind exists — no MolProbity/Ramachandran, no c… | confirmed |
| `SB-07` | MAJOR | Structural biology — macromol… | Renderer accepts and silently visualises non-sequence input; residue markers … | confirmed* |
| `AIML-10` | MINOR | AI/ML for ADMET and toxicity … | Safety profiles are generated for inputs that are not sequences and for seque… | confirmed* |
| `AIML-08` | MINOR | Machine learning for protein … | Modal WebGL contexts and animation loops leak on every drug-card open, multip… | confirmed* |
| `MEDCHEM-11` | MINOR | Medicinal chemistry / natural… | Onjisaponin V is conflated with DISS, a structurally unrelated compound, and … | confirmed |
| `MOLBIO-11` | MINOR | Molecular neurobiology / neur… | Two sequences contain a non-standard amino acid letter and one "sequence" fie… | confirmed* |
| `INTEG-09` | MINOR | Research integrity, scientifi… | 'Cognitive Enhancement Index (CEI)' is plotted as a computational benchmark a… | confirmed* |
| `SWE-09` | MINOR | Research software engineering… | The synthetic confidence visualizations contradict their own legends and cont… | confirmed |

\* confirmed with a factual correction from the verifier.

## 7. What was genuinely good

- THE INFORMATION ARCHITECTURE IS THE RIGHT ONE, AND IT SURVIVES A REBUILD UNCHANGED. Five brain regions × five candidates, a leaderboard tab, and a per-candidate modal placing 3D structure, a per-residue confidence profile and a PAE matrix side by side is exactly the layout a real structure-prediction platform needs. A genuine Boltz-2 / Chai-1 / OpenFold3 backend can be dropped behind these same components without redesigning a single screen. This is real, reusable work — the scaffolding is sound and only the data layer is hollow.

- THE FRONT-END ENGINEERING IS COMPETENT AND IDIOMATIC. Clean tab routing with proper active-state management (app.js:425-450), correct separation of data arrays from render functions, a working window-resize handler with camera aspect recomputation (app.js:1036-1046), and — the detail most people miss — explicit Chart.js instance teardown before re-creation (app.js:779-781) to avoid canvas leaks. This is someone who can build and maintain a real interface. (The one real defect in the same class is the WebGL side: initModal3DCanvas constructs a fresh THREE.WebGLRenderer on every modal open (app.js:688) with no dispose(), and the stale animation loop's guard `if (!modalThreeRenderer) return` (app.js:764) tests a module-scope variable that the new open has already reassigned, so loops accumulate and rotation speed multiplies — worth fixing as part of the viewer rewrite, not after.)

- THE DOMAIN VOCABULARY IS DRAWN FROM PRIMARY LITERATURE AND, AT THE LEVEL OF NAMING, USED CORRECTLY. Huperzine A does engage the AChE catalytic anionic site through cation-π; Cys151 genuinely is the Keap1 electrophile sensor; the ETGE motif genuinely is the high-affinity Nrf2 Kelch-binding element; KLVFF genuinely is the Aβ16-20 self-recognition element used in aggregation-inhibitor design; GGGGS genuinely is the standard flexible fusion linker. Somebody read the source literature to find these. The failure is that the motifs were copied without checking directionality and provenance, not that they were invented — which means the curation effort is salvageable as a properly cited motif-provenance table.

- THE BISPECIFIC BIO-CONJUGATE ARCHITECTURE IS, IN THE ABSTRACT, A LEGITIMATE DESIGN CONCEPT. Natural-product warhead + targeting peptide + flexible linker + second targeting module is a real modality with real precedent, and organizing a CNS portfolio by brain region and cell type is a defensible way to structure a discovery program. The 25-candidate concept sketch is worth preserving as a hypothesis catalogue once it is relabelled as such and the four mechanistically inverted entries are removed or corrected.

- ONE PART OF THE UI IS ALREADY HONEST, AND IT IS THE SEED OF THE CORRECT VERSION. index.html:359 tells the user to 'Submit this candidate's FASTA sequence directly to AlphaFold Server for live 3D prediction and PDB/CIF download,' and the Copy-FASTA button plus the launch link implement exactly that. This correctly concedes that prediction has not been run and must be done externally. Keeping that control, deleting the 'Live Connected' badge beside it, and adding a parser for the mmCIF/confidences.json the user brings back is the shortest path from the current state to a truthful, genuinely useful tool.

- THE REPOSITORY ALREADY CONTAINS GENUINE STRUCTURE-ANALYSIS CODE THAT IS SIMPLY NOT WIRED UP. The vendored .agents/skills/ tree includes working AlphaFold-database fetch and analysis scripts (fetch_structure.py, analyze_plddt.py, analyze_pae.py) that parse real pLDDT and real PAE and detect domain boundaries, alongside ChEMBL, PDB, UniProt and Open Targets skills. Real parsers for the exact quantities the app fabricates are sitting unused in the same checkout. Phase 1 of any remediation is largely a matter of connecting what is already here rather than writing it from scratch.

## 8. Data-integrity gate

`platform/validate.py` encodes the contract and exits non-zero when any record violates it. On the legacy dataset:

| Violation category | Count |
|---|---|
| thermodynamic inconsistency | 25 |
| cysteine parity | 12 |
| fabricated residue | 11 |
| disulfide undeclared | 10 |
| duplicate sequence | 7 |
| affinity implausible | 5 |
| compartment mismatch | 5 |
| smiles unparseable | 4 |
| sequence invalid | 4 |
| stereochemistry undefined | 3 |
| mixed numbering convention | 3 |
| smiles wrong molecule | 1 |
| prose in sequence field | 1 |
| **total** | **91** |

## 9. Remediation roadmap

### Phase 0 — Stop the misrepresentation (laptop, no GPU, no license, no network; ~4 hours)

**Goal.** Make every claim in the artifact true as of today, before any new capability is built. Nothing downstream is worth doing while the current labels stand, and this phase is pure deletion and relabelling — it cannot fail for technical reasons.

**Workstreams.**

- Delete or relabel every fabricated renderer: remove renderModalPlddtChart (app.js:775-832), renderModalPaeHeatmap (app.js:834-866) and the synthetic helix generators (app.js:674-773, app.js:959-1022) as data sources, or wrap all three behind a visible 'ILLUSTRATIVE PLACEHOLDER — NOT MODEL OUTPUT' banner. Remove the words 'AlphaFold3' and 'Real' from app.js:707, app.js:802, index.html:371, 377, 383, 397 and README.md:108-110.
- Remove the false-integration claims: delete the 'AlphaFold Server Live Connected' badge (index.html:42), the 'Live AlphaFold Integration' stat card (index.html:67-71), the 'live AlphaFold Server integration' phrase (index.html:54), README.md:24 'direct live integration' and README.md:111. Keep the Copy-FASTA control and the Launch button — they are honest — and reword the surrounding copy to 'Prediction is run externally; paste results back in.'
- Remove the implied affiliation: delete the Google-logo badge at README.md:3, remove 'DeepMind' from index.html:30, delete the 'Generated with AlphaFold3 3D Structural Modeling' footer at index.html:410, and rename the working directory away from DeepMind_Bio.
- Delete every unverifiable number rather than softening it: all 25 ΔG/Kd/pLDDT strings in the affinity fields (app.js:146-394), all 25 safety strings (app.js:147-395), README.md:96-102 in full, and the undefined CEI column and chart series (index.html:306, 316; app.js:1063) — or publish CEI's formula and inputs. Replace 'de novo' with 'motif-concatenation concept sketch' at README.md:1, 13, 22, index.html:6, 30, 39, 53-54, 65, 106, 262, 265-266, 323, 326 and app.js:525.
- Add a prominent status banner to index.html and the top of README.md: what has been computed (nothing yet), what the sequences are (hand-assembled motif concatenations), and what the visuals represent (placeholders).

**Success criteria.**

- `grep -rniE 'alphafold3|AF3|de novo|live connected|pLDDT|ΔG|Kd|hERG|Seizure Index|CEI' README.md index.html app.js` returns only occurrences that are inside an explicit placeholder/disclaimer block or a correctly-scoped external-tool reference — a reviewer can enumerate every remaining hit and agree with each one.
- No numeric ΔG, Kd, pLDDT, IC50, percentage-risk or index value remains anywhere in the repository without an adjacent provenance record naming its source.
- No Google/DeepMind branding, logo, or name appears in README.md, index.html, app.js or the directory path.
- A first-time reader who opens only index.html can state correctly, without reading source, that no structure prediction has been performed.

### Phase 1 — Build the real validation and provenance layer (laptop, no GPU, no license; ~1 week)

**Goal.** Ship genuinely working, verifiable code that computes real things about the existing data. This is the largest amount of honest capability obtainable with no GPU and no model weights, and it is a hard prerequisite for every later phase because it defines the data contract everything else writes into.

**Workstreams.**

- Sequence validator (real code, runs offline): reject any sequence not matching /^[ACDEFGHIKLMNPQRSTVWY]{5,}$/ at data-load time; refuse to render a modal, chart or Copy-FASTA control for a failing entry and show an explicit error instead. This immediately quarantines app.js:130, 173, 371 (the 'B' entries) and app.js:381 (the prose string). Add cysteine-parity and disulfide-connectivity checks that flag the 11 odd-cysteine entries and require an explicit connectivity declaration for the 8-cysteine constructs (105 possible pairings each).
- Chemistry validator with RDKit (already installed in the repo's .venv, version 2026.03.5): MolFromSmiles round-trip on every warhead, formula cross-check against the stated formula, canonical SMILES and InChIKey emission, and stereocentre count. This flags the 4 unparseable entries (app.js:10, 50, 60, 70) and the 2 wrong-molecule entries (Rg1, Ginkgolide B) automatically. Repair each structure against PubChem/ChEMBL and store the verified SMILES plus InChIKey.
- Thermodynamic consistency checker (real code): assert |ΔG − RT·ln(Kd)| < 0.3 kcal/mol at a stated temperature for any row that reports both; fail the build otherwise. Applied today this rejects all 25 rows, which is the correct behaviour.
- Duplicate and contradiction detector: hash every sequence, report collisions across FULL_BRAIN_DRUGS_DATA and AF3_CANDIDATES, and fail if two records sharing a sequence carry different metrics or biologically incompatible targets (extracellular peptide vs cytoplasmic target). This catches all 4 intra-set duplicates and all 5 leaderboard collisions.
- Provenance schema, enforced at render time: every displayed value carries {value, units, source_type ∈ {literature, computed, measured, placeholder}, source_id (DOI/PMID/UniProt/PDB/file path), method, model+version, run_date, git_sha, uncertainty, applicability_domain}. Make the UI structurally incapable of rendering a value with source_type absent, and render 'not computed' as a first-class state. This is the single change that prevents the whole class of defect from recurring.
- Motif provenance table: for every borrowed segment, the UniProt accession and residue range (GSK3B P49841 3-34; BDNF P23560 19-39; APP P05067 687-706; NFE2L2 Q16236 77-84; the WNT3A P56704 ~203-223 signature; GGGGS linkers), with a note where the copy is imperfect.

**Success criteria.**

- `python validate.py` exits non-zero on the current data and prints exactly: 3 invalid sequences, 11 odd-cysteine entries, 4 unparseable SMILES, 2 formula mismatches, 25 thermodynamic violations, 4 intra-set duplicate pairs, 5 leaderboard collisions. Every count is independently reproducible by a third party from a clean checkout.
- After repair, the same script exits zero, and every SMILES round-trips through RDKit to its stated molecular formula with a recorded InChIKey.
- Every value rendered in the UI has a non-null source_type; a deliberately provenance-stripped test record causes a visible 'not computed' state rather than a rendered number.
- A provenance table in README.md gives a UniProt accession and residue range for ≥95% of the residues in every retained sequence.

### Phase 2 — Real target evidence and real predictor-output parsing (laptop, no GPU; ~2 weeks)

**Goal.** Replace free-text target strings with structured, citable target records, and make the app able to display genuine model output the moment any is produced — including output the user obtains manually from AlphaFold Server. This decouples 'can display real results' from 'can generate real results', so the platform becomes honest and useful before any GPU is available.

**Workstreams.**

- Structured target records via public APIs (all free, all CPU): UniProt accession plus exact domain boundaries and sequence for every named receptor; PDB entries with resolution and method for every target that has experimental structure (TrkB D5, Keap1 Kelch, AChE, α7 nAChR ECD, TLR4/MD-2, GSK-3β, FZD8 CRD); ChEMBL bioactivities for each warhead; Open Targets association evidence for each target-indication pair. Replace strings like 'TrkB Ig-like D5 Domain (Asp298, Glu319, ...)' with a record carrying the accession, the numbering convention used, and the PDB entry the residue numbers were read from. Note that the existing binding-site strings mix numbering conventions across organisms (Torpedo AChE Trp84/Phe330 alongside human Trp286/Tyr341 in the same parenthesis at app.js:154) — every residue annotation must be re-derived against one declared reference.
- Real predictor-output parser: read a genuine <job>_model.cif plus <job>_confidences.json / <job>_summary_confidences.json and surface atom_plddts (aggregated to per-residue), the full-resolution token×token PAE, pTM, ipTM, ranking_score, has_clash, fraction_disordered and chain_pair_pae_min. The repository already contains working analyze_plddt.py and analyze_pae.py under .agents/skills/ — wire them in rather than rewriting. Validate the parser end-to-end against AlphaFold DB entries downloaded by UniProt accession, which requires no GPU and no weights.
- Real molecular viewer: replace the hand-rolled Catmull-Rom helix with Mol*, NGL or 3Dmol.js reading actual coordinates; color by parsed atom_plddts against the four standard AlphaFold bands; derive binding-site highlighting from residues in contact with the partner chain rather than a fixed sphere at the origin. Fix the WebGL lifecycle at the same time: store the requestAnimationFrame id and cancel it in both initModal3DCanvas and closeDrugModal, dispose geometries/materials/renderer, or construct one renderer and reuse it.
- Correct PAE and pLDDT visualisation: square canvas at full token resolution with no 45-token cap, a monotonic sequential colormap with a labelled colourbar in Ångström, chain-boundary rules, and axis ticks; pLDDT y-axis derived from the data or fixed at 0-100 with band shading rather than pinned to 50-100.
- Upload/paste path: let a user drop the mmCIF and confidence JSON returned by AlphaFold Server (or any AF3-class tool) into the modal and see genuinely parsed results, tagged with source_type='computed' and the originating file hash.

**Success criteria.**

- Given a real AlphaFold DB entry fetched by UniProt accession, the app renders its structure, its per-residue pLDDT curve and its PAE matrix, and the displayed values match an independent parse of the same files to within floating-point tolerance.
- A deliberately low-confidence region (a disordered terminus or a Gly-Ser linker in a real prediction) renders in the 'Low' or 'Very Low' band — proving the display can express failure, which the current one provably cannot.
- Every target record carries a UniProt accession, a numbering convention, and either a PDB ID or an explicit 'no experimental structure' flag; no free-text-only residue annotation remains.
- Opening all 25 modals in sequence leaves exactly one live WebGL context and one animation loop (verifiable in devtools), with no rotation-speed drift.

### Phase 3 — Real structure prediction on properly specified complexes (GPU required; no AF3 license needed; ~3-4 weeks)

**Goal.** Generate genuine predictions for the quantities that actually bear on binding — which requires re-specifying every job as a complex rather than a bare peptide, and using a model that can legally be run locally in an automated pipeline.

**Workstreams.**

- Choose a permissively licensed AF3-class backend and state it explicitly in the README with version and license. Boltz-1/Boltz-2 (MIT, code and weights, academic and commercial use) is the closest fit because Boltz-2 additionally emits an affinity estimate; Chai-1 (Apache 2.0, code and weights, explicitly usable for drug discovery), Protenix (Apache 2.0) and OpenFold3 (Apache 2.0) are equally viable. Do NOT plan on AF3 weights (request-only, non-commercial, non-redistributable) or on AlphaFold Server (no API, daily quota, and its Prohibited Use Policy forbids automated protein-ligand/peptide binding prediction — precisely this use case).
- Re-specify every job as a complete complex: a receptor chain (UniProt accession + exact domain sequence), the designed peptide chain, and the natural-product warhead as an explicit ligand entity. Note the implementation constraint: for a covalently conjugated warhead the ligand must be given as a CCD code or a user-provided CCD block with explicit bondedAtomPairs — bare SMILES cannot carry a covalent bond because it defines no unique atom names. SMILES is acceptable only for a non-covalently docked warhead.
- Run with multiple seeds and diffusion samples; persist model.cif, confidences.json, summary_confidences.json and ranking_scores.csv per run, and record seed, sample index, model version, run date, wall-clock and git SHA against every value surfaced.
- Rank on ipTM plus interface PAE with ranking_score as tiebreak and has_clash as a hard filter — never on monomer pLDDT, which measures local self-consistency and is the regime in which idealized designed sequences are most confidently wrong. Report the seed-to-seed spread, not a single point estimate.
- Replace ΔG/Kd entirely: either drop them, or report Boltz-2's affinity head in its native units (log10 IC50 in µM) with its binder/non-binder probability, or compute free energies by a named method (FEP/TI, MM-GBSA with a stated protocol) with force field, protocol and error bars committed. Never present a model confidence and a thermodynamic quantity in the same field.
- Establish calibration and controls: run known binder/non-binder pairs and scrambled-sequence negatives through the identical pipeline so the reported metrics have a scale.

**Success criteria.**

- For every retained candidate, the repository contains a real model.cif and confidences.json produced locally, and the UI reads its values from those files with the file hash recorded — no literal survives.
- A published leaderboard is sorted by a metric that is defined in the README, and the displayed ordering is reproduced exactly by re-sorting on that metric (today's ordering is reproduced by no published column).
- Scrambled-sequence negative controls score measurably worse than the designed candidates on ipTM and interface PAE; if they do not, that result is published rather than suppressed.
- Every surfaced number carries seed, sample count, model version, run date and across-seed spread.
- No ΔG or Kd appears anywhere unless produced by a named free-energy method with a committed protocol and error bars.

### Phase 4 — An honest design campaign with reported attrition (GPU required; ~6-10 weeks)

**Goal.** Produce candidates that are actually designed against targets, rather than motifs concatenated by hand, and report the failures — which is what makes a design result interpretable.

**Workstreams.**

- Fix the mechanistic inversions first, because they carry physical hazard and would otherwise propagate into synthesis: withdraw or relabel the Aβ16-35 constructs (app.js:277, app.js:129) — a wild-type copy of the central hydrophobic cluster extended through GAIIGLM is an aggregation seed, and the legitimate KLVFF-derived inhibitor class works only with register-disrupting modification (proline, N-methylation, D-residues); correct or remove the GSK-3β pseudosubstrate-as-ATP-ligand entry (app.js:225); correct CogBDNF-Mimic-04 to mature BDNF (P23560 129-247) rather than the prodomain; reassign or delete the extracellular-peptide-targets-cytoplasmic-ZO-1 entry (app.js:371).
- Pick two targets with good experimental structures (TrkB D5 and Keap1 Kelch are both well served in the PDB) rather than attempting 25 at once.
- Run a real generative stack conditioned on target coordinates and hotspot residues: RFdiffusion or BindCraft for backbones, ProteinMPNN/LigandMPNN for sequence with cysteine omitted unless a disulfide is deliberately scaffolded. For the 26-49-residue constrained-peptide regime this project actually occupies, RFpeptides is the more appropriate tool and designs the cyclization chemistry explicitly. Where the intent is to reuse a known motif, use RFdiffusion motif scaffolding and call it that — motif scaffolding is a respected technique; hand concatenation with GGGGS is not.
- Filter with published, numeric thresholds and publish them: BindCraft's shipped defaults are interface pAE ≤ 0.35 (normalized), i_pTM ≥ 0.5, pLDDT ≥ 0.8, shape complementarity ≥ 0.6, Rosetta ΔG < 0, surface hydrophobicity ≤ 0.35, interface unsatisfied H-bonds ≤ 4. Add self-consistency RMSD between the re-prediction and the design model.
- Commit the full audit trail: design PDBs, per-design score table, random seeds, filter thresholds, the count generated, the count surviving each filter, and the targets where nothing survived. State an expected hit rate with a citation so readers can calibrate — the field's benchmark campaign screened on the order of 10^4 designs per target to obtain a handful of binders, and even 2025-era one-shot pipelines report 10-100% across targets on tens of purified designs, with explicit failures.

**Success criteria.**

- For each of the two targets: a committed table of N designs generated, N surviving each named filter with its numeric threshold, and the seeds — with N_generated ≫ N_surviving, and at least one target or filter stage where the answer is 'nothing passed' if that is what happened.
- Zero retained sequences contain a non-standard residue, an odd cysteine count, or an undeclared disulfide topology.
- Every retained sequence's nearest natural homolog is reported with an identity percentage from an explicit homology search; anything ≥95% identical over ≥20 residues to a natural protein is labelled a graft, not a design.
- No entry claims an aggregation-nucleating sequence as an aggregation inhibitor; any amyloidogenic segment carries an explicit register-disrupting modification and an aggregation-propensity prediction.

### Phase 5 — Modality-appropriate developability and safety, with calibrated uncertainty (mostly laptop/CPU; wet lab for confirmation; ~3-4 weeks of compute work)

**Goal.** Replace the fabricated safety panel with a real assessment matched to the modality — peptide conjugates, not small molecules — and make abstention on out-of-domain inputs the default behaviour rather than a silent clean bill of health.

**Workstreams.**

- Small-molecule warheads only (CPU, laptop): run ADMET-AI or Chemprop v2 over the RDKit-validated warhead SMILES from Phase 1, emitting per-endpoint predictions with calibrated uncertainty. Note upfront that curcumin is a documented PAINS/IMPS frequent hitter and that baicalein and salvianolic acid B are polyphenol redox-cyclers and colloidal aggregators — assay-interference flags belong in the record.
- Peptide panel, computed where possible and marked 'not assessed' where not: MHC-II immunogenicity via NetMHCIIpan-4.3 across a representative HLA-DR/DQ/DP allele panel with committed per-frame scores (CPU, hours); aggregation propensity via sequence predictors; sequence-derived descriptors that already flag risk today — length, MW, net charge at pH 7.4, GRAVY and Eisenberg hydrophobic moment, displayed against melittin and LL-37 reference values. Several of these peptides are strongly cationic amphipathic (the most-reused 36-mer is ~4.9 kDa, net charge ~+9, GRAVY -1.09, hydrophobic moment 0.615 — more amphipathic than melittin), which is the chemotype for which hemolysis must be measured rather than assumed in either direction.
- Wrap every predictor in inductive conformal prediction at a stated confidence level and enforce an explicit applicability-domain check that forces abstention rather than a value. Small-molecule hERG models are trained on 150-600 Da compounds; a 4.9 kDa polycation is categorically out of domain and the correct output is 'not assessed — out of applicability domain', not 'safe'.
- Correct the endpoint set: one fixed schema applied identically to all candidates so cross-candidate comparison is possible (today 22 distinct third-slot labels make it impossible); move efficacy-flavoured fields (lysosomal clearance, cytokine suppression, vasodilation rate, fibril blockade) out of the safety panel; add the missing A, D, M and E (permeability, plasma protein binding, BBB permeability, CYP inhibition/induction, metabolic stability, clearance, half-life) and DILI/genotoxicity as explicit endpoints, populated or marked unassessed. Add reference and control compounds (donepezil, memantine, galantamine, a known hERG blocker, a known seizurogen) run through the identical pipeline so the numbers have a scale.
- State the honest ceiling on any seizure claim: the best integrated in vitro ion-channel panel reported in the literature reaches roughly 65% accuracy for predicting convulsion, so no per-compound scalar at 0.01 resolution is supportable. For a portfolio built on AChE inhibition, α7 nAChR potentiation, M1 PAM activity and NMDAR modulation, the honest default is 'elevated seizure concern pending assay', not 'negligible'.
- Wet-lab items, explicitly labelled as not obtainable in silico: hemolysis HC50 on human erythrocytes; mammalian cytotoxicity (hepatic, renal, primary neuron/astrocyte); plasma and CSF proteolytic stability; extracellular-application hERG electrophysiology (the outer-vestibule route is the one open to a polycationic peptide, not the Tyr652/Phe656 inner-cavity site the README invokes); MEA seizure-liability screening; and any chronic tolerance/receptor-downregulation endpoint, which requires repeat in vivo dosing and receptor quantification and cannot be predicted at all.

**Success criteria.**

- Every safety value renders as {point estimate, interval with stated coverage, model+version, training set, applicability-domain verdict, date, git SHA} or as an explicit 'not assessed' — with no bare numbers and no 0%/100% claims anywhere.
- All 25 candidates report the identical endpoint set, so a cross-candidate safety ranking is computable; an out-of-domain input provably triggers abstention in a unit test.
- Reference compounds run through the same pipeline land in the expected rank order relative to the candidates; if they do not, the pipeline is not shipped.
- The wet-lab-required endpoints appear in the UI as named open liabilities with the specific assay listed, not as omissions.

### Phase 6 — Experimental validation and honest reporting (wet lab; 6-12 months, external dependency)

**Goal.** Close the loop that turns a computational platform into evidence. Nothing before this point licenses any claim about what these molecules do in a biological system, and the platform's copy should say so until this phase produces data.

**Workstreams.**

- Synthesize a small number of the surviving designs — order of 10-20 per target, which is what current macrocycle and binder campaigns actually test — with disulfide connectivity resolved and characterized (LC-MS, analytical HPLC) so a single species is being assayed.
- Measure binding directly (SPR or BLI against the purified target domain) and report Kd with fitted error, alongside the predicted ipTM/interface PAE, so the platform accumulates a real prediction-vs-measurement calibration set.
- Run the wet-lab safety panel from Phase 5 (hemolysis, cytotoxicity, plasma/CSF stability, extracellular hERG electrophysiology, MEA seizure liability) before any in vivo work.
- Publish the calibration curve — predicted metric vs measured affinity, including the designs that failed — and use it to set the platform's own filter thresholds rather than borrowing published ones.
- Update the README's expected-hit-rate statement with this project's own measured attrition.

**Success criteria.**

- A committed table of every synthesized design with measured Kd (or 'no binding detected') and the fitted uncertainty, including all failures.
- A published calibration plot of predicted ipTM / interface PAE against measured affinity, with the correlation and sample size stated.
- Project-specific filter thresholds derived from that calibration replace the borrowed literature defaults in the pipeline configuration.
- The platform's headline claims are restated in terms of measured outcomes with n and error bars, and the README's expected hit rate is this project's own number.

