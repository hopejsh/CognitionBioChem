## The instrument was characterised before the screen was read

A screen that reports no separation is informative only if the instrument used to run it was
shown, beforehand and against an external standard, to be capable of resolving the property in
question. A null result from an untested pipeline cannot be distinguished from a pipeline that
was broken, mis-parameterised, or run at a precision below the size of the effect sought. Four
calibrations were therefore executed and reported before the decoy-controlled screen was
unblinded — a peptide-interface gate against X-ray complexes, a seed-variance study, an
affinity benchmark on the one target in the registry with a large public ligand set, and a
stratification of predicted-structure agreement by the evolutionary information the predictor
was given. Each is reported with the number it produced, including where a calibration failed
to establish what it was meant to establish.

### The peptide-interface gate

Throughout, *gate* names a pre-specified pass/fail precondition on the instrument: the pipeline
had to reproduce known peptide–receptor interfaces before the decoy-controlled screen would be
interpreted at all.
Boltz-2 v2.2.1 [@passaro2025; @wohlwend2025] was run over 16 X-ray peptide–receptor complexes
and each predicted complex was scored against its crystallographic reference with DockQ v2
[@mirabello2024], whose continuous score reproduces the CAPRI Incorrect/Acceptable/Medium/High
classification [@basu2016b]. The thresholds applied here are the ones this literature uses: DockQ
0.23 for acceptable quality and DockQ 0.80 for high quality, the two cut-offs at which
AlphaFold-Multimer interface recovery was reported [@evans2021]. Across the 16 complexes, 62%
reached CAPRI-acceptable quality, the median DockQ was 0.36, and the median fraction of native
contacts recovered (fnat) was 0.518.

Those pooled figures average two strata that do not agree. The set was curated in advance in two
date bands relative to the model's training cutoff: 8 complexes deposited before it, which could
have been seen in training, and 8 deposited after it, which could not. On the pre-cutoff half, 7
of 8 reached acceptable quality (0.875, Wilson 95% CI [0.5291, 0.9776]) and the median DockQ was
0.8725 — above the high-quality cutoff. On the post-cutoff half, 3 of 8 reached acceptable
quality (0.375, Wilson 95% CI [0.1368, 0.6943]) and the median DockQ was 0.18, below the
CAPRI acceptable-quality cutoff of 0.23. The pooled 62% and the pooled median of 0.36 are
therefore an upper bound on what this pipeline does on an interface it has not already been shown.

Pooled against pooled, these are ordinary numbers for the regime. AlphaFold-Multimer produced
acceptable-or-better models for 66 of 112 peptide–protein complexes with a median first-ranked
DockQ of 0.47 [@johanssonakhe2022], on a set that was likewise not leakage-excluded; the present
gate is slightly better on hit rate and worse on median pose quality. The pooled median DockQ of
0.36 clears the acceptable-quality cutoff by 0.13 (arithmetic: 0.36 − 0.23) and falls far short of high
quality. The median fnat of 0.518 means that in the typical case a bare majority of the
crystallographic contacts were recovered — enough for the
pose to be scored acceptable, not enough to treat the modelled contact list as a description of
the interface.

The number that makes this a gate rather than a description is the rank correlation between the
model's own interface confidence and the externally scored pose quality. Spearman rho between
ipTM — a quality-of-model estimate restricted to cross-chain residue pairs [@evans2021] — and
DockQ was 0.8 across the 16 complexes, at a raw p of 0.0002. Two bounds belong with that number.
With n = 16 the interval around a rank correlation is wide. And the ordering is not clean at the
level of a decision: scored against the confident (> 0.8) and failed (< 0.6) interpretation
bands, the confidence score misclassifies 5 of the 16 complexes (arithmetic: 1 confident but
wrong, plus 4 in the failed band and wrong). Given the stratification above, the correlation is
also in part a correlation with whether the complex was available to be memorised.

Published assessments of confidence measure different quantities, and neither confirms nor
contradicts this one. MassiveFold generated more than 6000 predictions per CAPRI Round 55
antibody–antigen target and reported that the AlphaFold2 confidence score could not identify the
good models within that single target's pool [@raouraoua2025]; PepPCBench found confidence
metrics correlating poorly with experimental binding affinities across 261 resolved complexes
[@zhai2025]. Neither is a rank correlation of confidence against pose quality across a set of
different targets. The distinction that matters here is preserved: rho = 0.8 says ipTM tracks
*how good a pose is*, not *whether two chains bind*.

[FIGURE: fig5_complex_structure.png — a representative predicted peptide–receptor complex from the interface gate, coloured by per-residue confidence, with the crystallographic reference superposed.]

### How far the gate transfers, and how far it does not

The gate was assembled from PDB entries, and the receptors and peptides in it are not the
constructs the screen was run on. The benchmark peptides are 7 to 17 residues long and their
receptors 80 to 304 residues. The screened candidates are 31 to 47 residues against receptor
constructs of 156 to 608 residues — in silico residue spans supplied to the predictor, not
expression constructs. The shortest candidate is therefore 14 residues longer than the longest
benchmark peptide (arithmetic: 31 − 17), and the largest candidate receptor construct is exactly
twice the size of the largest benchmark receptor (arithmetic: 608 / 304).
PepPCBench, a curated set of 261 experimentally resolved protein–peptide complexes, spans
peptides of 5 to 30 residues [@zhai2025] — the candidate band lies entirely outside it.

Two consequences follow and must be kept separate. The sensitivity argument transfers only as
far as the post-cutoff stratum carries it: the pipeline resolves interfaces on structures it
could have seen (0.875 acceptable, median DockQ 0.8725) and is unreliable on structures it could
not (0.375 acceptable, median DockQ 0.18, at or below the acceptable-quality cutoff at the median). A
negative result is therefore consistent with two readings this gate cannot separate — a real
null, or an instrument that cannot see an interface it has not already been shown. The numeric
bands do not transfer either: no DockQ or fnat figure measured on 7-to-17-residue peptides may be
quoted as the expected accuracy on a 31-to-47-residue manually concatenated chimera. Length is
not the only gap. Accuracy on peptide benchmarks depends on similarity to the training
set [@zhai2025]; on a leakage-excluded benchmark, AlphaFold3-generation methods fall
from 70–80% to 40–56% stringent success [@zhou2025], and the same collapse under
similarity-based rather than date-based splitting is documented for affinity prediction
[@graber2025], on datasets rebuilt to control protein and ligand similarity leakage [@li2024].
CASP15-CAPRI reported that performance remained poor for antibody and nanobody complexes, a class
in which evolutionary relationships between the binding partners are lacking [@lensink2023] —
suggestive of the mechanism at issue here, not a demonstration of it. A motif-and-linker construct
has no co-evolutionary partner signal by
construction, and on Drosophila de novo genes and matched random sequences pLDDT correlates
positively with predicted disorder, the opposite of its behaviour on conserved proteins
[@middendorf2024]. The gate is a floor on competence, and a floor measured largely on structures
the model may already have seen — not a transferable accuracy estimate.

### The sampler's own noise sets the resolution limit on score differences

Six constructs were predicted repeatedly under reseeding, over 87 runs in total. Pooled across
those constructs, the across-seed standard deviation was 0.14943 in ipTM, 2.6615 in complex
pLDDT, and 4.6157 Å in minimum interface PAE. The pooled ipTM figure is not any single
construct's noise: of the three constructs for which a per-construct across-seed ipTM standard
deviation is recorded, the values run from 0.0689 to 0.2344 — more than a threefold spread
(arithmetic: 0.2344 / 0.0689). The floor is coarse, and it is not sharply determined. ipTM is
bounded on [0, 1] and the useful working range of the metric is a fraction of that interval, so
an across-seed SD of 0.14943 means any single-seed difference smaller than roughly that magnitude
is indistinguishable from the sampler. The corresponding statement for the other two channels —
2.6615 pLDDT units, 4.6157 Å of interface PAE — rules out reading small shifts in either as
evidence about a construct.

The variation is across seeds rather than run-to-run non-determinism: at a fixed seed, each of
the six constructs returned exactly one distinct complex pLDDT value over three replicates, with
a spread of 0.0.

Reporting this floor is not decoration. Variance intrinsic to the method, combined with
non-determinism in the benchmark environment, makes reported single-run results hard to
interpret, and reporting across multiple random seeds with significance metrics is among the
guidelines proposed for reproducible deep reinforcement learning benchmarking [@henderson2018]; a
p-value computed from one run is itself a random variable with wide sampling variability
[@halsey2015]. Interface PAE is in any case a descriptive quantity — the predicted aligned
error matrix restricted to inter-chain pairs — not a calibrated probability [@elfmann2023;
@jumper2021]. The seed-variance study fixes, in advance of the screen, the size an effect must
exceed to be readable at all.

### An affinity benchmark the model fails, and the references do not excuse

The Boltz-2 affinity head was benchmarked against public potency data for acetylcholinesterase.
It returned a Spearman correlation of 0.3036, a mean absolute error of 1.3593 log10 units, and
a within-one-log fraction of 0.5333 — that is, 53.33% of predictions landed within a factor of
ten (arithmetic: 0.5333 expressed as a percentage). An MAE of 1.3593 log10 units corresponds to
a 22.9-fold error in potency (arithmetic: 10 raised to 1.3593).

The benchmark was rerun after the reference values were corrected, and the correction made the
correlation worse rather than better: Spearman fell from 0.3036 to 0.1912.

The labels are genuinely soft. Independently measured public IC50 values on identical
protein–ligand systems have a standard deviation about 25% larger than Ki data and greater than
in-house intra-laboratory, inter-day variation, which the authors read as only a moderate amount
of added noise [@kalliokoski2013]. For AChE the reference is soft before any inter-laboratory term
is added — huperzine A preferentially inhibits the
tetrameric G4 form while tacrine and rivastigmine preferentially inhibit the monomeric G1 form
and physostigmine shows no form selectivity at all, and the inhibition constants differ
significantly between cortex, hippocampus and striatum [@zhao2002] — and even the source
species of the enzyme is not interchangeable, since donepezil binds human AChE differently from
the *Torpedo* enzyme [@cheung2012].

Softness of that kind is often invoked to absorb a predictor's error, and the rerun measured it
instead of assuming it. The median dispersion of the corrected reference values was 0.4445 log10
units; the median absolute error of the predictions against them was 1.0471 log10 units. The
error exceeds the labels' own spread by a factor of 1.0471 / 0.4445 (arithmetic), so reference
softness bounds only a minority of it and the residual sits with the predictor. This benchmark is
therefore reported but not used as a sensitivity claim for the screen; the screen reads ipTM and
never renders the affinity head as a thermodynamic quantity, which is appropriate for a regressor
fitted to pooled Ki/Kd/IC50/EC50 labels [@passaro2025] whose sensitivity to the identity of the
target partner has been directly questioned [@bret2026].

### Pose accuracy stratified by what the model could have seen

The last calibration asks how much of the predictor's output is supplied by the evolutionary
record rather than by the construct. In a cross-check against the AlphaFold Protein Structure
Database — whose deposited models carry confidence estimates, not biophysical quantities
[@varadi2022] — the median Pearson correlation between the locally predicted and the deposited
model rose from 0.7154 with single-sequence input to 0.8637 with a full MSA, a gain of 0.1483
(arithmetic: 0.8637 − 0.7154).

[FIGURE: fig4_alphafold_vs_boltz.png — per-target agreement between the local Boltz-2 predictions and AlphaFold DB models, single-sequence input versus full MSA.]

The receptor half of every predicted complex is a well-covered human protein with a deep
alignment; the peptide half has none, and AlphaFold-family models fold peptide partners without
an MSA of their own, which raises the question of what has been memorised rather than learned
[@tsaban2022]. On peptides made non-redundant with the training structures, AlphaFold2-Multimer
identified the correct interface in only 40% of cases from full-length sequences [@bret2024].
The stratification above is consistent with that picture: much of the model's agreement with an
independent predictor is carried by the alignment, and the screened peptides contribute none of
it.

Taken together the four calibrations license a narrow claim. The pipeline recovers peptide
interfaces at published rates on complexes deposited before the training cutoff and at 0.375
acceptable on those deposited after it; its confidence score ranks pose quality at rho = 0.8
across the 16 complexes while misclassifying 5 of them against the interpretation bands; and its
across-seed noise is 0.14943 ipTM units pooled over six constructs. They do not license any
transfer of the benchmark's numeric accuracy to the candidate constructs, nor any use of the
affinity head as evidence, nor the reading that a negative result must mean the candidates do not
bind. The screen that follows was read against exactly these limits.
