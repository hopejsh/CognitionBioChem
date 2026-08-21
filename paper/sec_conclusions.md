## Conclusions

The question asked here was narrow, and it is prior to every other question a designed peptide
raises. Thirteen chimeric peptides, concatenated by hand from motif
segments with no generative model, no sequence optimisation and no structure-based design
software involved, directed at domains of targets drawn from a sixteen-target cognition
registry, were co-folded against those domains with Boltz-2 v2.2.1, and
each was scored against ten composition-matched shuffles of its own residues under a protocol
fixed by SHA-256 hash before its data was seen. Not efficacy, not selectivity, not brain
entry: only whether the interface confidence this predictor emits is attributable to the
arrangement of a candidate's residues rather than to the residues themselves.

It is not. Across the thirteen candidates the mean designed ipTM was 0.6287 and the mean decoy ipTM
0.6278 — a paired difference of 0.0009, Cohen's dz 0.0057, paired t-test p = 0.98.
Two candidates beat all ten of their own decoys, against 1.182 expected under the per-candidate
null, with P(X >= 2) = 0.3338; two apparent winners is an unremarkable outcome for a screen with
no effect, not two hits. The paired difference is smaller, by more than two orders of magnitude, than
the predictor's own seed-to-seed ipTM standard deviation of 0.14943. The same hypothesis was
falsified in all eleven retained versions of the analysis.

### What this licenses, and what it does not

It licenses one claim: ipTM from this predictor, on this construct class, does not rank
manually concatenated motif chimeras above permutations of their own residues — so a screen
ordering such constructs by that quantity cannot be shown to be ordering anything above its own
seed-to-seed noise.

It does not license more. Absence of evidence is not evidence of absence [@altman1995]. No peptide
was assayed by any experimental method, and nothing here bears on whether any of the thirteen
binds its intended domain. Neither is this a verdict on the instrument as such: the same pipeline
recovered CAPRI-acceptable interfaces for 62% of sixteen X-ray peptide–receptor complexes, with a
median DockQ of 0.36 and Spearman rho(ipTM, DockQ) of 0.8, when a reference structure existed to
score against. Placing a peptide on a receptor that is known to bind it, and deciding whether a
peptide belongs there at all, are different tasks. The first succeeded only partially — 62%
acceptable, median DockQ 0.36. The second failed outright.

### The recommendation

One methodological recommendation follows more strongly than any other. A per-candidate null built
from the candidate's own residues, and the sampler's seed-to-seed spread on the same metric,
should be reported alongside confidence-based rankings of this kind; composition- and
property-matched nulls of this kind are established practice in sequence analysis and in
virtual-screening benchmarks [@workman1999; @rivas2000; @mysinger2012]. Both are cheap: at ten
decoys per candidate the null costs eleven predictions per candidate instead of one (10 + 1, by
arithmetic on the decoy count), and the noise floor costs a handful of reseeded repeats. Without
the first, this screen could not have separated a designed interface from an amino-acid
composition — the failure mode composition-matched nulls were introduced to catch [@workman1999;
@rivas2000] — and measured discrimination is in any case a property of the decoy set at least as
much as of the method [@chaput2016; @imrie2021]. Without the second, it could not have told
whether the separation it reported exceeded what re-running the identical input would produce.

### The instrument, not the peptides

The result is negative, and the reason to report it is that the experiment could have come out the
other way and been believed. The decoy construction, the test statistic and the decision rule were
registered under a SHA-256 hash before the study's data was seen; the noise floor was measured rather than
assumed; the two winners were counted against a binomial expectation rather than read off a table.
Under that arrangement, a designed-minus-decoy difference large relative to the measured 0.14943
would have been a finding, and a reader would have had the means to check it. The difference was
0.0009.

That is what the work is for. Thirteen peptides that fail to separate from their own shuffles are
of no consequence to anyone; a screening protocol whose positive answer would have been worth
something, run to the point where it returned a negative one, is the part that could be reused.
