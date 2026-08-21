## What a negative result means, and what independent evidence says

### The claim the data support, and its boundaries

Across the thirteen designed peptides the mean designed ipTM was 0.6287 and the mean decoy ipTM
0.6278: a paired difference of 0.0009, Cohen's dz of 0.0057, paired t-test p = 0.98.
The comparator for that difference is the predictor's own reproducibility. Re-running the same
construct across seeds gave an ipTM standard deviation of 0.14943, so the paired difference is
smaller than the single-seed spread by more than two orders of magnitude (dividing 0.14943 by
0.0009 gives 166). Counting from the per-candidate table, six of the thirteen designed values
exceeded the mean of their own decoys — the count a fair coin would produce.

Stated narrowly: Boltz-2 v2.2.1, run on these thirteen constructs against seven of the sixteen
registered target definitions, assigned interface confidence to a designed sequence and to
composition-matched permutations of its own residues in a way that does not separate them. A
random permutation of the candidate's own residues holds length, net charge, hydrophobic fraction
and glycine/serine content fixed and destroys only order, so the comparison isolates one question:
is the model responding to the arrangement of residues or only to their amino acid composition?
Composition correction has been central to sequence analysis since composition-based statistics
were added to PSI-BLAST as part of a set of refinements that raised ROC from 0.758 to 0.895
[@schaffer2001]; here it removes essentially all of the apparent signal.

Three things do not follow. It is not a demonstration that the peptides fail to bind: no binding
assay, cell assay or animal experiment was performed, and a non-significant comparison is not
evidence of absence [@altman1995]. It is not a demonstration of equivalence: thirteen paired
observations give little power against small effects [@button2013], a single p-value is itself a
draw from a wide sampling distribution [@halsey2015], and a positive claim of no difference would
require equivalence bounds fixed in advance from a smallest effect size of interest [@lakens2017].
Nor is it a demonstration that the predictor is unfit for purpose: on sixteen X-ray peptide–receptor
complexes the same pipeline produced CAPRI-acceptable models for 62% of cases, with median DockQ
0.36 and median fnat 0.518, and ipTM tracked DockQ at Spearman rho 0.8. Where a reference structure
exists, the model's confidence score carries real information about pose quality. Structural
plausibility and partner discrimination are separable axes: geometrically plausible complexes are
produced routinely while ipTM frequently fails to discriminate cognate from non-cognate pairings
[@smorodina2026]; the second axis is the one on which this screen returned nothing.

[FIGURE: fig1_native_vs_decoy.png — Designed ipTM against the ten composition-matched shuffles
per candidate, with the seed-to-seed standard deviation of 0.14943 drawn for scale.]

### Convergence with independent work

The closest independent evidence reaches the same conclusion in a different molecular class using
the same metric. A controlled benchmark of 106 nanobody–antigen complexes against 11,342 shuffled
non-cognate pairings, across AlphaFold3, Boltz-2 and Chai-1, reports that geometrically plausible
complexes are produced routinely while ipTM frequently fails to discriminate cognate from
non-cognate pairings, and that increased sampling improves structural refinement without improving
pairing discrimination; the recommendation is independent seeds plus explicit negative controls
[@smorodina2026]. Three points coincide: the metric is ipTM, one evaluated model is Boltz-2, and
structural plausibility is generated independently of binding specificity. The differences matter
too. That null shuffles the *pairing*, substituting a non-cognate antigen for a fixed binder; the
present null shuffles the *residues within the candidate* with the target held constant, so target
identity is a control rather than the manipulated variable. Their binders are folded
immunoglobulin domains with a defined paratope; these constructs are short concatenations with no
scaffold to conserve. And that work is a preprint, not peer reviewed. Two experiments with
different nulls in different molecular classes agreeing about the same metric is stronger than
either alone, but neither has been replicated.

The second line concerns Boltz-2's affinity module. Probed with target mutation and target
shuffling, its binary active/inactive classification remains insensitive to key binding-site
mutations and in some cases to target exchange, raising concerns about the hidden features governing
the predictions [@bret2026]. That is the same failure in kind — a score that does not depend on the
identity of the partner being scored — but not the same experiment: it concerns small-molecule
ligands and the affinity head, whereas this screen used ipTM and never rendered the affinity head as
a thermodynamic quantity. The literature is contested and should not be flattened: in a prospective
evaluation on 557 Mac1–ligand complexes solved after the training cut-offs, Boltz-2 was among the
methods that reproduced more than 50% of poses to better than 2 Å RMSD, alongside AlphaFold3 and
Chai-1 [@kim2025]. The reconciliation is that the model performs on chemistry resembling its
training data while showing no demonstrated sensitivity to partner identity — and even pose-level
results carry a leakage caveat, since co-folding benchmarks and training corpora are both
PDB-derived [@leng2026]; the same PDBbind-to-benchmark leakage was shown to inflate binding-affinity
predictors, whose measured performance collapses once the split is cleaned [@graber2025]. This
study's own energetic check is uninformative in the same direction: a contact-based binding-affinity
prediction gave a between-candidate-to-seed discrimination ratio of 1.4 with a bootstrap interval of
[0.9629, 3.844] that contains 1, over predicted energies that cover only 18% of PRODIGY's
calibration range, so it neither supports nor contradicts the ipTM result.

The third line is confidence calibration for antibody–antigen complexes, reported before this work
began. Nine co-folding methods including Boltz-2, benchmarked on 200 antibody–antigen complexes,
required a purpose-built precision-driven metric because the native confidence scores did not
deliver the needed precision and recall [@unsal2026]. In CAPRI Round 55, MassiveFold generated
more than 6,000 predictions per antibody–antigen target and obtained acceptable-to-high-quality
models for all of them, yet the confidence score could not identify the good models within the
pool [@raouraoua2025]. CASP15–CAPRI is consistent with that mechanism: high-quality models for
about 40% of 37 targets overall, but performance poor specifically for antibodies and nanobodies,
where evolutionary relationships between the binding partners are absent [@lensink2023]. A
manually concatenated chimeric peptide likewise has no co-evolutionary partner signal, though
whether short designed peptides behave like antibody–antigen targets in this respect is untested
here. The same failure appears in a large all-by-all screen of nearly 300 human genome-maintenance
proteins, where standard AlphaFold-Multimer confidence did not separate real interactions from
abundant false positives and a separate classifier was required [@schmid2025]; and for peptides a
pMHC-II benchmark supplemented with shuffled negatives found AlphaFold3 reaching the highest
positive recall at 0.86 while both it and a fine-tuned AlphaFold2 frequently misclassified unbound
peptides as binders [@ko2026].

The control differs from the ones the co-folding papers cited here rely on, which pair a fixed
binder with non-cognate partners: nanobodies against 11,342 shuffled pairings [@smorodina2026],
GPCR peptide ligands against decoy ligands [@hoegen2025]. Cross-partner pairings vary composition,
length and alignment depth along with sequence order. Matched nulls are not new in themselves —
property-matched decoys are standard in ligand screening [@mysinger2012], tightening the match
lowers measured performance [@imrie2021], bias-matched decoys address the same shortcut on
nucleic-acid targets [@wen2026], and the pMHC-II benchmark above used shuffled negative peptides
[@ko2026] — but a within-candidate permutation scored against a fixed target holds composition,
length and target identity constant and varies only residue order.

### Why a confident geometry is not evidence of an interaction

pLDDT and PAE are regressions onto geometric agreement with an experimental structure of the same
chain — not probabilities that the modelled state is populated in solution, and not energies
[@jumper2021]; the database distributing them calls them model-confidence estimates rather than
biophysical quantities [@varadi2022]. Interface PAE inherits this: it is defined as the expected
positional error at one residue when the predicted and actual structures are aligned at another, so
interpreting it for a complex leans on independent evidence such as crosslinking restraints rather
than on the score alone [@elfmann2023]. ipTM adds an interface-aware confidence score for the
predicted interface [@evans2021], but it estimates the quality of a modelled complex rather than
testing whether the two chains associate, which is why standard confidence metrics did not separate
genuine interactions from abundant false positives in a large all-by-all screen [@schmid2025]. Asked
to co-fold a peptide with a receptor domain it places the chain somewhere definite, because placing
chains is what it was trained to do — and Boltz-1 introduced inference-time steering specifically to
correct hallucinations and non-physical predictions [@wohlwend2025]. Confidence also misbehaves
where evolutionary support is absent: for de novo and random sequences pLDDT correlates positively
with predicted disorder, the opposite of its behaviour on conserved proteins [@middendorf2024] — the
regime a chimera of published motifs joined by GGGGS linkers occupies. The present data show it at
the item level: MicroTrem2-Agonist-M1 scored 0.6929 while the best of its ten shuffles scored
0.9625, and MicroTlr4-Antagonist-M3 scored 0.7223 against a best shuffle of 0.9341. The scrambled
sequence got the more confident interface.

### The two apparent successes

Two of thirteen candidates beat all ten of their own decoys. Under the null the probability that the
designed sequence is the maximum of eleven exchangeable values is 1/11 = 0.0909, so the expected
number of winners is 1.182 and the probability of two or more is 0.3338. Two winners is not two
hits; it is close to the modal outcome of a screen with no effect. The margins say the same:
BasalNgf-TrkA-B3 scored 0.818 against a best decoy of 0.7498, a margin of 0.0682 by subtraction,
and BasalAChE-Abeta-B4 scored 0.8105 against 0.7969, a margin of 0.0136. Both are smaller than the
seed-to-seed ipTM standard deviation of 0.14943, so neither survives the sampler's own noise.

Calling them hits would have been the specific error this design was built to prevent. A
composition-matched decoy set answers a per-item question; a screen asks whether *any* item beat
what the best item would do under the null, and conflating the two is the multiple-comparison
mistake that false-discovery-rate methods automate [@storey2003] and that proteomics solved
structurally, by letting decoy hit frequency estimate the error rate of the whole identification
set [@elias2007]. The decoy distribution here is the empirical null for the screen, not a
per-candidate sanity check. Thresholds need the same discipline, performing poorly unless the
admissible range is fixed a priori [@mcleay2010] — hence registration of every criterion under a
SHA-256 hash before its data were seen, and hence 11 of the 25 hypotheses falsified.

[FIGURE: fig2_screen_level_null.png — Observed count of candidates beating all ten of their own
decoys against the binomial null with per-candidate probability 0.0909 over thirteen candidates:
expected 1.182, observed 2, P(X >= 2) = 0.3338.]

### What remains open

Three explanations survive, and the study ranks them only partially.

The designs may be genuinely inert. This is not remote: they are chimeric peptides, manually
concatenated from published motifs, motif-like segments and one de novo helix joined by GGGGS
linkers, with no generative model or optimisation loop involved; only 7 of the 16 motif entries
carry a UniProt accession, and 31 of 35 candidates carry at least one of 22 fragments the
provenance record marks unattributed. Nothing in the screen tests this, because nothing in it is
an assay.

They may bind while the predictor cannot see it, and the published performance envelope makes this
live. On leakage-controlled peptide sets AlphaFold3-generation methods drop to 40–56% stringent
success [@zhou2025]; for peptides from disordered regions made non-redundant with the training
structures, AlphaFold2-Multimer found the correct interface in only 40% of cases from full-length
sequences, with discrimination between alternative partners particularly challenging for small
motifs [@bret2024]; and AlphaFold-Multimer produced acceptable-or-better models for 66 of 112
peptide–protein complexes [@johanssonakhe2022]. A method that misses a substantial fraction of
true complexes returns a null on true binders often enough that the null cannot exclude them, and
confidence correlates poorly with measured affinity in any case [@zhai2025].

The receptor construct definitions, meaning the in silico residue spans supplied to the predictor
rather than expression constructs, may be wrong — a mis-drawn domain boundary, or a receptor
modelled without an obligate partner: the TLR4 ectodomain presents its ligand surface only in
complex with MD-2. The paired design does not
protect against this: each decoy is scored against exactly the same target construct as its
design, so a wrong target degrades both identically and yields the same null difference an
uninformative predictor would.

The screen separates one thing cleanly: whether the confidence assigned to a candidate depends on
the order of its residues or only on their composition. It found no evidence that the confidence
depends on residue order; with thirteen pairs it cannot establish that composition is all that
matters. It cannot separate inert designs from invisible binding from mis-specified targets,
because all three predict the result obtained, and deeper alignments do not resolve them — a full
MSA lifted agreement with the AlphaFold Protein Structure Database from a median Pearson r of
0.7154 under single-sequence input to 0.8637, while the primary hypothesis was falsified in all 11
retained versions. Better constructs, a better-founded model and a wet-lab assay each address one
of the three, and only the last is decisive.
