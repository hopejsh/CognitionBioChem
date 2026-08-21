## Where the confidence came from

The screen-level null established that the thirteen candidates did not separate from
composition-matched shuffles of their own residues. It did not explain why several of
them nevertheless returned confidence values that, reported without a control, would
have read as successes. This section takes apart one such case, then reports two further
checks: a comparison of the receptor-chain confidence against the corresponding entries
in the AlphaFold Protein Structure Database, and the one method in the pipeline that
reports a number in units of energy.

### The anatomy of a confident-looking complex

BasalAChE-Abeta-B4, a chimeric peptide directed at the acetylcholinesterase catalytic
gorge (P22303) and manually concatenated with no generative model, no sequence
optimisation and no structure-based design software involved, returned a complex ipTM of
0.8105 — the fourth-highest designed ipTM of the thirteen candidates, and one of two
candidates whose designed value exceeded all ten of its own shuffles. That count is
fully consistent with chance: 1.182 such candidates are expected under the null, the
per-candidate probability is 0.0909, and P(X >= 2) = 0.3338.

It is not the strongest case the screen produced. BasalNgf-TrkA-B3 returned a higher
designed ipTM, 0.818, also beat all ten of its own shuffles, and separated further from
them on both margins. B4 is dissected here for a different reason: its receptor is the
target in this registry with the deepest experimental precedent, which makes it the
clearest case in which to ask what a high complex-level confidence value is made of.

Complex-level confidence in this pipeline is reported over both chains at once. A
complex pLDDT is a mean over every modelled residue, so when a receptor domain is
co-folded with a short peptide the pooled value is a length-weighted average dominated
by the receptor, and the peptide — the only chain whose confidence bears on the design
question — enters in proportion to its length. A pooled complex pLDDT for a construct of
this shape is substantially the receptor's number wearing the complex's name.

That the receptor scores as it does is unsurprising rather than informative.
Acetylcholinesterase has been solved crystallographically since 1991 — a 537-residue
alpha/beta monomer, determined at 2.8 A, with the catalytic triad at the base of a deep
gorge lined by fourteen aromatic residues [@sussman1991] — and high-resolution human
structures have been available for over a decade [@cheung2012]. pLDDT was defined as a
per-residue estimate of agreement with an experimental structure of that same chain
[@jumper2021]; on a chain with this much experimental precedent it is being asked to
interpolate, and it does so well.

The peptide chain is where the information about the actual question sits, and it is the
chain the predictor is least equipped to score. Confidence for sequences without an
evolutionary record is difficult to read at all: for de novo and matched random sequences,
pLDDT correlates positively with predicted disorder, inverting the relationship seen for
conserved proteins, and predictor behaviour degrades specifically where identity to
anything in the database is absent [@middendorf2024]. A chain built by concatenating
published motifs through GGGGS linkers occupies that regime by construction — a flexible
Gly/Ser linker of the family introduced for single-chain Fv constructs [@huston1988]
leaves the fused segments mobile rather than fixing a defined relative geometry, which is
the property that distinguishes flexible from rigid linkers [@chen2013], and bioactive
motifs are known to lose their bound-state conformation when excised from a parent protein
[@lee2014]. The Abeta-derived component of this candidate inherits a further uncertainty:
the acetylcholinesterase–amyloid link on which it rests is a peripheral-site-dependent
in-vitro fibril-assembly effect [@inestrosa1996], not a characterised binding geometry
([FIG: fig5_complex_structure.png]).

[FIGURE: fig5_complex_structure.png — BasalAChE-Abeta-B4 modelled against the ACHE catalytic gorge, receptor and peptide chains coloured by per-residue pLDDT on a common scale.]

The interface metric behaves the same way. This candidate's ipTM margin over the best of
its ten shuffles is 0.8105 − 0.7969 = 0.0136 (arithmetic), which is 0.0910 of the
seed-to-seed ipTM standard deviation of 0.14943 measured on this pipeline (arithmetic).
Its margin over the mean of its ten shuffles, 0.1493, is 0.9991 of that same standard
deviation (arithmetic) — this candidate's separation amounts to about one draw from the
sampler's own spread. The largest margin in the screen is not qualitatively different:
BasalNgf-TrkA-B3 exceeds its decoy mean by 0.818 − 0.4952 = 0.3228 (arithmetic), which
is 2.1602 of the same standard deviation (arithmetic), and therefore still sits inside
the range of a two-seed difference. A single-seed confidence value is a draw from a
distribution, and comparing candidates by one number each is comparing draws
[@raouraoua2026].

This is the behaviour the peptide co-folding literature reports. On a curated set of
experimentally resolved peptide complexes, prediction accuracy tracks similarity to the
training set [@zhai2025]; discriminating between alternative partners is described as
particularly challenging for small interaction motifs [@bret2024]; standard confidence
metrics do not reliably separate real interactions from an abundance of false positives
at scale [@schmid2025]; and in the nearest published analogue to the present design,
structurally plausible complexes are produced routinely while ipTM frequently fails to
distinguish cognate from non-cognate pairings [@smorodina2026]. ipTM is a
quality-of-model estimate conditioned on the assumption that the chains form a complex
[@evans2021]; the model is never offered the option of reporting that they do not.

### An external check against the AlphaFold Protein Structure Database

To ask whether the receptor-side confidence was peculiar to this predictor, per-residue
pLDDT for the target chains was compared against the corresponding entries in the
AlphaFold Protein Structure Database, used here under CC BY 4.0. The median Pearson
correlation across compared chains was 0.7154 when Boltz-2 was run from single sequence
and 0.8637 with a full MSA, a difference of medians of 0.1483 (arithmetic on those two
values). That is a difference between two summary medians rather than a paired effect
estimate, no test statistic is attached to it, and the direction is not robust to the
choice of reference structure. It is a direction worth reporting, not a result worth
asserting. The mean pLDDT offset between the two sources narrowed in the same direction,
though its magnitude is not reported here.

This comparison is exploratory and is bounded accordingly. It confounds four variables
the design cannot separate. The first is the predictor: Boltz-2 against the AlphaFold2
models deposited in the database [@varadi2022]. The second is the depth of evolutionary
input. The third is monomer-versus-complex context, since the database entries are
single-chain predictions and the study's models are two-chain. The fourth is shared
supervision: Boltz-2's training corpus is PDB-derived [@leng2026], the database entries
are AlphaFold2 predictions [@varadi2022], and the confidence score on both sides is the
same kind of quantity — a per-residue regression onto agreement with an experimental
structure of that chain [@jumper2021]. Part of any agreement between them is therefore
common training signal rather than independent corroboration. Agreement about where two
models are confident is in any case not agreement about where they are right.

No p-value is attached to any of these correlations. Per-residue values within a chain
were not treated as independent observations; effective sample sizes were estimated and
are substantially smaller than the residue counts. Notably, the largest correlation
observed in the single-sequence arm rests on the fewest effective observations of any
chain in the comparison, which is the configuration in which a high correlation
coefficient carries the least evidence.

The check therefore supports one modest statement — the receptor-side confidence profile
is reproduced by a second model reporting the same kind of confidence quantity, which
makes it unlikely to be a quirk of this run, and is not evidence that either profile is
accurate — and no statement about the peptides, whose chains have no counterpart in the
database at all ([FIG: fig4_alphafold_vs_boltz.png]).

[FIGURE: fig4_alphafold_vs_boltz.png — Per-residue pLDDT for the target chains, Boltz-2 against AlphaFold DB, single-sequence and full-MSA arms, with per-chain Pearson correlations and effective sample sizes.]

### PRODIGY: a contact-count regression, not a free energy

No free energy is calculated anywhere in this pipeline. No free-energy perturbation,
MM-GBSA, molecular dynamics or docking calculation was performed, and the Boltz-2
affinity head is a regressor fitted to pooled potency labels that is never rendered here
as a thermodynamic quantity [@passaro2025]. PRODIGY, a contact-based predictor applied
post hoc to the modelled interfaces, is the only method in the pipeline that reports a
number in units of energy, and that number is a regression on interfacial contact counts,
not a computed binding free energy.

What PRODIGY was used to compute is a ratio of spreads: the between-candidate spread in
the predicted values divided by the seed-to-seed spread of the same quantity, over the
interfaces of a small set of candidates. It is not a design-versus-shuffle contrast, and
it does not compare the screen's candidates against their own decoys. The study's
pre-specification audit records the result as non-confirmatory: fewer interfaces were
analysed than the plan called for, the hypothesis family was reclassified after the fact,
and the bootstrap interval quoted below was not among the pre-specified metrics. It is
reported here as exploratory.

This quotient is registered as the study's discrimination ratio; the name denotes a
between-to-within spread ratio here — a signal-to-noise quantity — and not the
novel-object-recognition index that carries the same name in the behavioural literature.
The discrimination ratio it returned was 1.4. The bootstrap confidence interval on that
ratio is [0.9629, 3.844], whose lower bound lies below 1 — the value at which the method
does not discriminate at all — and whose upper bound is more than double the point
estimate. The predicted values occupy 18% of PRODIGY's calibration range, so the entire
comparison plays out within under a fifth of the span the method was fitted on.

The correct reading is that the design cannot resolve the question. An interval that
contains the no-discrimination value is not evidence that the method fails, and a point
estimate above 1 is not evidence that it works; absence of evidence is not evidence of
absence [@altman1995], and licensing a claim of no difference would require a
pre-specified smallest effect of interest and an equivalence test, neither of which this
study registered for PRODIGY [@lakens2017]. The width of the interval relative to the
occupied range is the informative quantity, and it is what a low-powered comparison looks
like [@button2013; @greenland2016]. Two independent considerations argue against
attempting a stronger claim on more data alone: contact counting is a coarse proxy for a
binding energy that is concentrated in a small number of hot-spot residues
[@clackson1995], and the input to PRODIGY here is a modelled interface rather than an
experimental structure, produced by the same pipeline whose peptide-side confidence is
the subject of this section.
