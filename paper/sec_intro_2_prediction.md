## Structure prediction, co-folding, and what a confidence score is

### Self-assessment arrived with AlphaFold2, and it was calibrated against crystallography

AlphaFold2 was validated on CASP14 monomers and reports two confidence metrics alongside its
coordinates [@jumper2021]. The predicted local-distance-difference test (pLDDT) estimates,
per residue, how well the model's local environment will agree with the experimental structure
of that same chain; the predicted aligned error (PAE) estimates, per residue pair, the
positional error of residue *i* when the model is superposed on residue *j*. Both are
regressions onto geometric agreement with a crystal structure. Neither is a probability that the
chain occupies the modelled state in solution, and neither is an energy. The AlphaFold Protein
Structure Database, exposing both metrics across more than 360,000 predicted structures,
describes them as model-confidence estimates rather than biophysical quantities [@varadi2022].

The distance between "confidently modelled" and "biophysically real" is easiest to see where the
training distribution runs out. For *Drosophila* de novo genes and matched random sequences,
pLDDT correlates *positively* with predicted disorder — the reverse of the negative correlation
seen for conserved proteins — and performance degrades where there is no sequence identity to
anything in the database [@middendorf2024]. A chimeric peptide of published motifs joined
by flexible linkers sits in exactly that regime: no evolutionary record exists for the fused
sequence, and the confidence head is being asked to extrapolate.

PAE is a directed matrix, and that structure is what makes it useful for complexes: the diagonal
blocks report the internal rigidity of each chain or domain, while the off-diagonal blocks
report the error in the *relative placement* of one chain when the model is aligned on the
other. Restricting the matrix to inter-chain pairs gives interface PAE — a descriptive readout
that permits an estimate of prediction quality, and whose interpretation the authors of the
standard viewer describe as difficult for non-specialists [@elfmann2023]. It is not a calibrated
probability of binding.

### pTM and ipTM: one scalar for a two-chain question

AlphaFold-Multimer added interface-aware confidence: pTM, a global TM-score estimate, and ipTM,
the same estimate restricted to cross-chain residue pairs. On 4,446 recent complexes it
recovered heteromeric interfaces at DockQ ≥ 0.23 in about 70% of cases and reached DockQ ≥ 0.8
in about 26% [@evans2021]. DockQ is the yardstick throughout this literature: a continuous [0,1]
score combining the fraction of native contacts, ligand RMSD and interface RMSD, calibrated so
that it almost exactly reproduces the CAPRI incorrect/acceptable/medium/high classification,
with "acceptable" at DockQ ≥ 0.23 [@basu2016b]. DockQ v2 broadens scope and automates chain
mapping without recalibrating the score, so its numbers remain comparable to the 2016 literature
[@mirabello2024].

Two properties of ipTM matter for any screen that ranks candidates by it. First, pTM and ipTM
are predicted TM-score estimates of the accuracy of a model built from the chains supplied,
benchmarked against interface quality (DockQ) rather than against whether the chains associate
at all [@evans2021]; the model therefore emits no output that reports non-association. Second,
its use as a ranking signal is empirically weak. Separating correct from incorrect association
modes and ranking within the correct set are different problems, and CAPRI found early that
predictors could do the first and not the second [@lensink2007]. The modern version is the same
result at much larger scale: MassiveFold generated more than 6,000 predictions per
antibody–antigen target in CAPRI Round 55 and produced acceptable-to-high-quality models for all
of them, yet the AlphaFold2 confidence score could not be used to find the good models inside
the pool [@raouraoua2025], and its CASP16-CAPRI successor, at up to 8,040 models per target,
closes on the same difficulty [@raouraoua2026]. A screen that reads one ipTM per candidate from
a few seeds is comparing single draws from these distributions — the same single-run comparison
problem documented for deep reinforcement-learning benchmarks, where non-determinism combined
with variance intrinsic to the method makes results from one run uninterpretable
[@henderson2018].

### The co-folding generation

AlphaFold3 replaced the structure module with a diffusion decoder operating directly on atom
coordinates, predicting proteins, nucleic acids, small molecules, ions and modified residues in
one framework, with reported gains over specialised docking tools for protein–ligand and over
AlphaFold-Multimer v2.3 for antibody–antigen [@abramson2024]. Boltz-1 is an open, MIT-licensed
reimplementation claiming AlphaFold3-level accuracy, and it introduces "Boltz-steering" as an
inference-time correction *because*, in its authors' own words, the base models produce
"hallucinations and non-physical predictions" [@wohlwend2025] — physically implausible predicted
structures, a failure mode of the predictor, and not the deliberate hallucination procedure used
in de novo protein design. Boltz-2 adds an affinity module, presented as the first such model
approaching free-energy-perturbation accuracy on small-molecule affinity at least 1000-fold more
cheaply [@passaro2025]; Chai-1 belongs to the same generation [@zhai2025; @kim2025]. What
changed is scope and availability, not the epistemic status of the confidence metrics, which
remain regressions onto geometric agreement. The predictor used here is Boltz-2 v2.2.1 under its
MIT licence; its affinity head is a regressor fitted to pooled potency labels and is never
rendered here as a thermodynamic quantity.

### A high confidence score is not evidence of a real interaction

The largest systematic protein–protein statement points the same way. From an all-by-
all matrix over nearly 300 human genome-maintenance proteins — roughly 40,000 AlphaFold-Multimer
predictions — Schmid and Walter report that standard AF-M confidence metrics do not reliably
separate relevant interactions from an abundance of false positives, and had to train a separate
classifier on structural and omics features to obtain usable discrimination [@schmid2025].
Confidence-derived scores are not empty: pDockQ recovered 51% of interacting pairs at a 1%
false-positive rate on curated heterodimers, for which AlphaFold2 produced acceptable models in
63% of cases [@bryant2022] — but that is a different claim from "this designed sequence binds
this receptor". For designed binders the enrichment is sobering: combining an AlphaFold3-derived
score-only model with AlphaFold2-derived methods raised the rate of experimentally validated
binders from 15.2% to 31.6%, leaving roughly two of three top-ranked designs failing [@liu2025].

For protein–**peptide** complexes the numbers are consistently worse, and specificity is the
weak axis. AlphaFold-Multimer produced acceptable-or-better models for 66 of 112 peptide–protein
complexes, 25 of them high quality; forced sampling raised this to 75 of 112 and the median
first-ranked DockQ from 0.47 to 0.55 while best-possible DockQ rose to 0.72, making model
*selection*, not sampling, the bottleneck — and at a 1% false-positive rate the same work
recovered only 26% of true peptide–protein interactions, at 85% precision [@johanssonakhe2022].
On peptides from intrinsically disordered regions made non-redundant with the training
structures, AlphaFold2-Multimer found the correct interface site and structure in only 40% of
cases from full-length sequences, rising to about 90% only after the interaction region had been
delineated by hand; that study also found discrimination between alternative binding partners
particularly challenging for small interaction motifs [@bret2024]. And on 261 experimentally
resolved complexes with peptides of 5–30 residues, PepPCBench reports that confidence metrics
correlate poorly with measured binding affinities [@zhai2025]: a high confidence score is weak
evidence of tight binding.

### The antibody–antigen evidence, which is the closest published analogue

Antibodies and nanobodies are where co-folding is weakest, for a reason that transfers directly
to designed peptides. CASP15-CAPRI reported high-quality models for about 40% of 37 targets, up
from 8% two years earlier, yet performance remained poor for complexes with antibodies and
nanobodies, where evolutionary relationships between the binding partners are lacking
[@lensink2023]. A manually concatenated peptide has no co-evolutionary partner signal by construction,
so the same deficit should apply here — an expectation this study tests rather than assumes. Systematic evaluation over 427 non-redundant antibody–antigen
complexes put near-native success at about 30%, rising to about 50% with increased sampling
[@yin2024], and Round 55 of CAPRI showed that even when good models are present in a very large
pool, confidence does not find them [@raouraoua2025]. Confidence scoring for these complexes is
now a problem in its own right: AntiConf benchmarked nine co-folding methods, Boltz-2 among
them, on 200 antibody–antigen complexes, analysing their confidence scores for precision and
recall [@unsal2026].

The decisive experiment is the one that supplies negatives. Smorodina paired 106
nanobody–antigen complexes against 11,342 shuffled, non-cognate pairings across AlphaFold3,
Boltz-2 and Chai-1, and found that these methods return geometrically plausible complexes for
pairings that do not exist — structural plausibility without binding specificity
[@smorodina2026]. That is the present experiment transposed one system down: rather than
shuffling which antigen a nanobody is shown, the study reported here shuffles residue order
within a peptide while holding target, composition and length fixed. A peptide analogue already
exists in immunopeptidomics: on 72 pMHC-II complexes supplemented with shuffled negative
peptides and curated non-binders, AlphaFold3 achieved the highest positive recall, 0.86, and a
fine-tuned AlphaFold2 0.81, but both frequently misclassified unbound peptides as binders,
whereas the sequence-based NetMHCIIpan-4.3 reached 0.93 negative recall at only 0.44 positive
recall [@ko2026]. On that benchmark, both structure-based methods frequently placed a
non-binding peptide in the groove and scored it as a binder.

[FIGURE: fig5_complex_structure.png — A predicted receptor–peptide complex from this study, illustrating the three quantities a confidence-based screen reads: complex pLDDT, the off-diagonal interface block of the PAE matrix, and the scalar ipTM.]

### Memorisation, data leakage, and physical validity

Reported co-folding performance is inflated by training-set overlap between benchmark and
training data — data leakage — and the size of the inflation has been measured for
protein–peptide prediction specifically. On a benchmark that did not exclude structures
present in the models' training data, AlphaFold3-generation methods
reached 70–80% stringent success (fnat ≥ 0.8; Protenix highest at 80.8%) against 53% for
AlphaFold2-Multimer; on the leakage-excluded set the new methods fell to 40–56% while AlphaFold-
Multimer stayed flat [@zhou2025]. PepPCBench independently reports that peptide accuracy depends
on training-set similarity [@zhai2025], and the memorisation question was raised early, when
AlphaFold2 was found to model peptide–protein complexes with no MSA at all for the peptide
partner [@tsaban2022]. The same pathology is quantified for affinity: leakage between PDBbind
and the CASF benchmarks severely inflated deep-learning metrics, and retraining on a leakage-
filtered split caused benchmark performance to drop substantially [@graber2025]. Deposition date
alone is not a sufficient control, since a structure deposited after a cutoff may be a close
homologue of one deposited long before; leakage is properly defined by sequence and structural
similarity on both partners [@li2024], and it has been catalogued across 17 fields of machine-
learning-based science [@kapoor2023].

Physical validity is a separate failure. PoseBusters showed that deep-learning docking methods
frequently emit stereochemically and sterically invalid poses, and that on physical plausibility
and generalisation to novel sequences no deep-learning method outperformed classical docking
[@buttenschoen2024] — the same observation the Boltz-1 authors made from inside the model when
they shipped inference-time steering [@wohlwend2025]. Two protein–ligand evaluations bracket
what the newest affinity machinery does. Prospectively, on 557 Mac1–ligand complexes determined
after the training cutoffs, AlphaFold3 and Chai-1 pose confidence tracked measured potency
weakly but significantly, while Boltz-2 affinity correlated most strongly and, after
calibration, beat a baseline predictor on mean absolute error [@kim2025].
Against this, probing Boltz-2 affinity with binding-site mutation and with outright target
shuffling left the active/inactive classification insensitive to key mutations and, in some
cases, to target exchange altogether [@bret2026]. The honest reading is that these models carry
real ranking signal on chemistry they have seen, while their sensitivity to partner identity is
unresolved: the classification was unchanged by key binding-site mutations and, in some cases,
by target exchange, which is weaker than a demonstration that partner identity is ignored
outright.

What none of this supplies is a within-candidate, composition-matched effect size for designed
peptides — a number that says whether the predictor is reading the motif or merely the amino-acid
composition. Negative controls in the co-folding literature are usually non-cognate pairings
[@smorodina2026], or shuffled peptides evaluated for classification rather than as a
within-candidate effect size [@ko2026]; neither yields a paired, composition-matched effect
size for a designed peptide against its own target. That is the gap
the present study addresses.
