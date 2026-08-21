## Methodological implications for confidence-based computational screening

The finding itself is narrow: thirteen manually concatenated chimeric peptides, no separation
from composition-matched shuffles of their own residues. The design decisions that produced it
are not, and in each case the literature already contained the warning.

### Composition-matched controls should be the default, not a robustness check

Composition is available to a sequence model before any motif is, and the literature repeatedly
shows composition alone reproducing effects attributed to structure. A package of modifications
to PSI-BLAST raised retrieval accuracy across 103 expert-curated queries from ROC 0.758 ± 0.005
to 0.895 ± 0.003, and the single modification accounting for the majority of that gain was a
position-specific scoring system tuned to each database sequence's amino-acid composition
[@schaffer2001] — much of what had looked like homology was composition. Intrinsic disorder is
likewise largely compositional [@romero2001], and the blind CAID assessment marks where that
tractability stops — across 43 methods on 646 DisProt proteins the best predictor reached F =
0.792 on structured-region-filtered data but only F = 0.231 on *disordered binding regions*, the
residues that actually contact a partner [@necci2021]. A peptide screen cannot borrow the
credibility of sequence-property prediction for a claim about binding specificity.

Chemistry has run the argument to its conclusion. DUD-E built 102 targets with 22,886 clustered
ligands and 50 property-matched decoys per ligand, explicitly to defeat artificial enrichment,
analogue bias and false-negative decoys [@mysinger2012]; convolutional networks then achieved
superior enrichment on it, performance the authors attribute to hidden analogue and decoy bias
in the dataset rather than to learned protein–ligand recognition [@chen2019]; an AVE redundancy
measure correlates with measured performance across seven widely used benchmarks, implying that
much reported ligand-based performance may reflect benchmark overfitting rather than
prospective accuracy [@wallach2018]. On full DUD-E, Glide reached BEDROC(alpha = 80.5) > 0.5 on
30 of 102 targets; after removal of targets with significant residual bias, 47 targets remained
and Glide cleared the same bar on 5 [@chaput2016]. Tightening the null lowers the score —
docking AUC ROC fell from 0.70 to 0.63 against better-matched decoys [@imrie2021] — and the
same shortcut is documented for deep models on RNA–small molecule data, whose negatives
differed systematically from the positives in bulk physicochemical properties [@wen2026].
Measured discrimination is a property of the control set at least as much as of the method.

For sequences the mechanics are settled: mono-residue permutation destroys order and every motif
while holding the residue multiset fixed, and k-let-preserving permutation is available when a
stronger null is wanted [@jiang2008]. Such a null is capable of killing a broad claim while
leaving a narrow one standing — mRNAs did not fold more stably than dinucleotide-matched randoms
[@workman1999] and genome-scan signal came mostly from local base-composition bias [@rivas2000],
yet under that same null hammerhead ribozymes, SRP RNAs and several riboswitches did separate
[@clote2005] — which is why the present result should be read as no detectable class-level
effect on this construct set rather than as a proof of impossibility.

For co-folding confidence the direct evidence agrees. AlphaFold-Multimer confidence does not
reliably separate relevant interactions from an abundance of false positives, forcing an
external classifier to make an all-by-all screen interpretable [@schmid2025], and in a GPCR
peptide benchmark the best structure-aware model reached AUC 0.86 on 124 ligands against 1,240
decoys, with rescoring of predicted structures on local interactions further improving recovery
of the principal ligand among the decoys [@hoegen2025]. The nearest analogue to this experiment
— 106 nanobody–antigen complexes against 11,342 shuffled non-cognate pairings — reports
plausible geometry alongside ipTM that frequently fails to discriminate cognate from
non-cognate; it is not peer reviewed [@smorodina2026].

### A per-item null does not license a screen-level reading

A composition-matched decoy set answers a per-item question: is this candidate better than
permutations of itself? A screen asks a different one: did *any* candidate beat what the best of
a null set of that size would return? With 10 decoys per candidate, "beats all its own decoys"
has an exact per-candidate null probability of 0.0909; over 13 candidates the expected number of
winners is 1.182 and the probability of two or more is 0.3338. Two were observed — an excess of
0.818 winners by subtraction, and close to the modal outcome of a screen with no effect at all.
Calling them hits would commit the standard multiple-comparison error one level up. Genomics
automates the arithmetic with per-feature q-values [@storey2003]; proteomics solved it
structurally, searching a concatenated target–decoy database so that decoy hit frequency
estimates the error rate of the whole identification set [@elias2007]. The decoy distribution is
the empirical null for the screen, not a per-candidate sanity check.

[FIGURE: fig2_screen_level_null.png — Observed winners against the binomial null for 13 candidates at a per-candidate probability of 0.0909, with two winners falling inside the bulk of the null distribution.]

### Measure the sampler's noise before interpreting any difference

The screen's paired difference was 0.0009 in mean ipTM (designed 0.6287, decoy 0.6278), with
Cohen's dz = 0.0057 and p = 0.98. Re-running the same pipeline across seeds — 87 runs over 6
constructs — gives a pooled ipTM standard deviation of 0.14943, with per-construct values of
0.2344, 0.0854 and 0.0689 for the three constructs recorded individually; a pooled complex pLDDT
standard deviation of 2.6615, ranging 0.131 to 3.46 per construct; and a pooled
minimum-interface-PAE standard deviation of 4.6157. The variation is seed-to-seed and not
run-to-run: at a fixed seed, three replicates returned one distinct complex pLDDT value for each
of the 6 constructs, spread 0.0. Dividing the pooled ipTM standard deviation by the mean paired
difference gives 166.03, so the across-seed spread of a single prediction is 166.03 times the
mean difference the screen was asked to resolve, and a per-candidate difference of that size
could not be separated from seed noise. The mean is taken over 13 pairs and is estimated more
precisely than any single prediction, so the ratio bounds the per-candidate scale rather than
the precision of the mean. Reporting across multiple seeds with variance estimates is the
guideline that emerged from deep reinforcement-learning benchmarking, where non-determinism plus
variance intrinsic to the methods makes reported single-run comparisons hard to interpret
[@henderson2018]. The p-value cannot substitute: it is itself a random variable with wide
sampling variability [@halsey2015], a design with as little power as this one sits where
effect-size estimates are inflated and a significant result is unlikely to reflect a true effect
[@button2013], and it carries neither precision nor magnitude [@greenland2016]. Increased
sampling reportedly improves structural refinement without improving discrimination
[@smorodina2026]. Whether additional sampling would narrow the seed-level spread reported here
was not tested.

### Most decisions were threshold comparisons that yield no p-value, and correction runs the wrong way for a null

The protocol comprised 8 pre-registered studies and 25 hypotheses, of which 13 were confirmed,
11 falsified and 1 not tested; 5 were decided by a test statistic and 19 by a threshold, the
two counts summing to the 24 that were tested. Most of the protocol was therefore settled by a
pass/fail comparison against a fixed cutoff rather than by a test statistic, so registering
those cutoffs in advance was not a courtesy: data-driven threshold selection performs poorly
unless the admissible range is limited a priori [@mcleay2010]. What pre-registration guards
against is flexibility exercised after the data are visible: it drives the actual
false-positive rate far above nominal [@simmons2011], degrades positive predictive value most
where many weakly pre-selected relationships are tested cheaply [@ioannidis2005], and leaves an
analytic space wide enough to span contradictory conclusions [@tierney2021].

Two errors follow from treating a threshold comparison as though it produced a p-value. Encoding
a threshold as a p-value fabricates a quantity the comparison cannot produce and inflates the
correction family, so every genuine test pooled with it is judged against a larger multiplier;
adjustment already trades type I error for type II [@rothman1990] and makes one comparison's
interpretation depend on how many others share the paper [@perneger1998]. Here only the 5 test
statistics entered the Holm family. The second error is subtler: applying a step-down correction
to a hypothesis whose claim is *failure to reject* is backwards. Holm maps every p-value to a
value greater than or equal to itself [@aickin1996], so adjustment converts rejections into
non-rejections and nothing else — it cannot protect a null claim and only lends it the
appearance of rigour. The correct instrument is equivalence testing: absence of evidence is not
evidence of absence [@altman1995], and two one-sided tests against bounds set from a smallest
effect size of interest are what license the claim that effects large enough to matter are
absent [@lakens2017], as was required to establish similarity of higher-order protein structure
where significance testing proved unsuitable [@hageman2021]. Absent a pre-specified smallest
effect of interest, the present result supports only the weaker statement that no difference was
detected at the achieved precision — and the seed-level spread reported above is what a later
study needs to set an equivalence bound at all.

Pre-registration binds only insofar as it is specific: an audit of 300 psychology studies found
registrations routinely lacking the detail needed to run the study as written [@van2024], and of
27 articles carrying the Preregistered badge between 2015 and 2017 only two contained no
deviation from plan [@claesen2021]. Fixing candidates, decoy construction, test statistic and
decision rule under a SHA-256 hash is a design claim a reader can check against the artefacts.

[FIGURE: fig3_falsified_every_version.png — The primary hypothesis falsified in all 11 retained versions of the analysis, showing the conclusion does not rest on a single pipeline state.]

### The negative is the part the literature is missing

The record is filtered in the direction that makes this result scarce. Of 74 FDA-registered
antidepressant studies covering 12,564 patients, 31% went unpublished, and the literature
implied 94% of trials were positive where the FDA data showed 51%, inflating meta-analytic
effect sizes by 32% overall [@turner2008]; and across 102 randomised trials, outcomes were far
more likely to be fully reported when significant, at pooled odds ratios of 2.4 for efficacy
and 4.7 for harm [@chan2004]. Registration before enrolment was the institutional answer
[@de2004]. Computational screening is not covered by that requirement, and is exposed to
data leakage documented across 17 fields and 294 papers, in some cases producing wildly
overoptimistic conclusions [@kapoor2023] — on a weak floor of re-execution: of 27,271 Jupyter
notebooks from biomedical publications, 879 reproduced the reported results [@samuel2024].
Pinned environments and workflow orchestration [@gruning2018] make a result checkable, not
true.

A pre-registered screen against a composition-matched null, reporting a mean paired difference
of 0.0009 against a pooled seed-level ipTM standard deviation of 0.14943, is the kind of
observation publication filtering removes from the record. That mean arises from per-candidate
differences that, by subtracting each candidate's decoy mean from its designed ipTM, span -0.2411
(PfcACh-PAM-P1) to +0.3228 (BasalNgf-TrkA-B3) — signal that cancels rather than signal
uniformly absent — and it is that distribution, not the mean alone, that a better-powered study
would need as the empirical basis for an equivalence bound. The seed-level spread measured
here, pooled ipTM SD 0.14943 across 87 runs on 6 constructs and itself ranging 0.0689 to 0.2344
across the three constructs recorded individually, indicates the order of magnitude a
comparable screen on comparable constructs would have to clear.