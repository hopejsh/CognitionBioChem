## Limitations, and what would be required to answer the binding question

### The candidates are not optimised designs

The thirteen candidates are chimeric peptides: manual concatenations of published motifs, motif-like
segments and one de novo helix joined by GGGGS linkers. No generative model produced them and no
optimisation, learned or physics-based, refined them. The attribution audit is worse than that
implies: of 16 motif entries only 7 carry a UniProt accession, leaving 9 of 16 with no sequence
record behind them (arithmetic on those counts), and 31 of the 35 candidates carry at least one of
22 fragments the record itself marks unattributed. An excised motif usually loses its bound-state
conformation [@lee2014; @van2014], and a Gly/Ser linker adds conformational freedom rather than
defined geometry — it selects oligomeric state, not productive orientation, and costs affinity where
it has been measured [@huston1988; @holliger1993; @chen2013].

Nor was the in-silico refold-and-redock filter applied that raises de novo binder success roughly
ten-fold [@bennett2023]. RFpeptides, on diffusion-generated backbones and learned sequence design
[@watson2023; @dauparas2022], tested twenty or fewer macrocycles per target across four targets and
obtained binders against all four, at 1–10 µM for MCL1 and MDM2, 6 nM for the best anti-GABARAP
macrocycle and below 10 nM for RbtA [@rettie2025; @rettie2024]; even when AlphaFold3-derived
rescoring is combined with AlphaFold2-based filters, validated-binder rates rise only from 15.2% to
31.6% [@liu2025]. A screen of unoptimised chimeras that fails against its own shuffles has said
nothing about peptide design as a discipline, only about these thirteen molecules and this scoring
channel.

### One predictor, one sampler

All predictions came from Boltz-2 v2.2.1. AlphaFold 3 was not used because access is request-only,
non-commercial and Linux/CUDA-bound and the AlphaFold Server's terms prohibit automated
protein–peptide binding prediction — a licensing constraint, not a judgement, but the consequence
stands: nothing here separates an idiosyncrasy of one model from a property of co-folding models.
Boltz-2 affinity classification has been reported insensitive to binding-site mutation and in some
cases to target exchange [@bret2026]; on 557 Mac1–ligand complexes determined after the training
cut-offs, Boltz-2, AlphaFold 3 and Chai-1 each reproduced more than half of poses to under 2 Å RMSD,
and none of the three recapitulated the common conformational rearrangements [@kim2025]. A two- or
three-model design, now standard in peptide and antibody benchmarking [@zhai2025; @unsal2026;
@ko2026; @smorodina2026], would have made model agreement a readout and separated MSA depth from
architecture.

Stochasticity compounds this. The seed-to-seed standard deviation of ipTM was 0.14943 against a
designed-minus-decoy paired difference of 0.0009 — a ratio of 166.03, computed from those two
values. Reporting across seeds is the minimum standard [@henderson2018], and massive-sampling work
shows that confidence cannot select the good models from a pool [@raouraoua2025; @raouraoua2026].

### No wet-lab validation, and the experiment that would settle it

Nothing here could have detected binding had it occurred. The pipeline emits ipTM, complex pLDDT,
interface PAE and an affinity-head value fitted to pooled Ki/Kd/IC50/EC50 labels that is never
rendered as a thermodynamic quantity; no docking, MM-GBSA, FEP or molecular dynamics was run. The
confidence quantities among these — ipTM, complex pLDDT and interface PAE — are regressions onto
geometric agreement with a reference structure, not probabilities that a complex exists in solution
[@jumper2021; @varadi2022; @elfmann2023]; the affinity-head value is a separate regression, onto
pooled potency labels. And across 261 experimentally resolved protein–peptide complexes their
confidence metrics correlated poorly with experimental binding affinities [@zhai2025]. The one
empirical, contacts-based energy estimate in the pipeline, PRODIGY, gave a between-candidate-to-seed
discrimination ratio of 1.4 with a bootstrap interval of [0.9629, 3.844] that contains 1.

The decisive experiment is a direct binding measurement: surface plasmon resonance or biolayer
interferometry against the purified receptor construct, using the boundaries folded in silico, with
each designed peptide and its own shuffles on the same surface in the same session over a full
concentration series. A positive is saturable, concentration-dependent binding of the design with a
fitted K_D and no saturable response from its shuffles; a negative is no saturable response from
either up to the highest concentration achieved, which for 31- to 47-residue chimeras may be set by
solubility and must therefore be reported. The assay class is feasible for these targets:
recombinant TrkAd5 binds NGF with picomolar affinity [@dawbarn2006], and biolayer interferometry has
dissected TREM2–apoE engagement [@kober2020]. Binding would then need an orthogonal functional
assay, because this field carries widely propagated CNS pharmacology that purpose-built quantitative
panels could not reproduce [@boltaev2017; @pankiewicz2021].

### Receptor construct definition as a source of error

A screen against a named domain is only as good as the claim that the site exists in the chain that
was folded, and several targets fail that test. The phenylethanolamine site lies at the GluN1–GluN2B
amino-terminal-domain interface [@karakas2011], not within the GluN2B cleft to which it was
originally assigned [@perindureau2002], so an isolated GluN2B ATD chain cannot present it; the
best-validated positive allosteric site is at the GluN1–GluN2A ligand-binding-domain dimer interface
[@hackos2016], on a receptor that is an obligate heterotetramer [@hansen2018]. The α7 nicotinic
receptor is a homopentamer with interfacial agonist sites [@noviello2021], TLR4 recognition requires
MD-2 in a 2:2:2 assembly [@park2009], and AChE is not species-interchangeable: donepezil binds human
AChE differently than it binds the Torpedo enzyme [@cheung2012] whose E2020 complex originally
defined the pharmacophore [@kryger1999].

Construct definition was corrected over the slate's history. Each correction changed the precision
of the numbers; none changed the direction of the answer, and H1 was falsified in all 11 retained
versions. The affinity arm carries the same softness in its references, and correcting them made the
arm weaker rather than stronger: the Spearman correlation fell from 0.3036 in the uncorrected
benchmark, measured over 15 observed compounds, to 0.1912 over the 14 that have a corrected
reference. The registered comparison records that fall as a delta of -0.1128, taken against the
three-decimal 0.304 the plan carried rather than against 0.3036, with a bootstrap 95% confidence
interval of [-0.4622, 0.7303] spanning zero at p 0.51258 and a median absolute error of 1.0471
log10 units. The corrected references are themselves dispersed — median
log10 standard deviation 0.4445, maximum spread across records for a single compound 4.996 log10
units, median 4.5 records per compound and 2 compounds resting on a single record — which is what
the literature on mixed public affinity labels would predict [@kalliokoski2013], and which the
enzyme-form and brain-region dependence of reported AChE inhibitor Ki values illustrates directly
[@zhao2002]. That study falsified both its ranking hypothesis and its hypothesis that fixing the
references would matter, and confirmed the third: the model, not the labels, dominates the error.

### Nothing here speaks to developability

No blood–brain-barrier permeability was measured or predicted, and the ADMET model refused these
constructs as outside its applicability domain. That refusal was correct, and it leaves the question
open. The barrier excludes essentially all large-molecule neurotherapeutics [@pardridge2005], and
peptide classifiers trained on curated blood–brain-barrier-penetrating peptide sets [@kumar2021]
have had their generalisation questioned by their own successors [@charoenkwan2022]. The
best-evidenced shuttle is sobering: an 86-fold gain in brain influx for ANG1005 [@thomas2009]
converted to a 15% investigator-assessed and 8% independently reviewed intracranial response rate
that missed its preset rule [@kumthekar2020]. Stabilisation itself is achievable — truncation plus
D-amino acid substitution raises somatostatin's few-minute plasma half-life to about 1.5 h in
octreotide [@werle2006] — but the modification frequently costs binding, and the cost tracks where
it sits: site-specific PEGylation of gp41 HR2 fusion inhibitors bought up to a 3.4-fold longer
proteolytic degradation half-life while every conjugate lost fusion-inhibitory activity, a loss that
could be minimised by moving the PEG to a non-interacting helix face [@danial2012], and hydrocarbon
stapling of the BimBH3 helix reduced affinity rather than raising it [@okamoto2013]. Nerinetide,
built by this idiom [@aarts2002], failed phase 3 twice [@hill2020; @hill2025].

[FIGURE: fig4_alphafold_vs_boltz.png — Agreement between AlphaFold DB and Boltz-2 rises with MSA depth, but the two arms share evolutionary input and overlapping training corpora.]

### Confounds in the AlphaFold DB arm

The AlphaFold Protein Structure Database was used under CC BY 4.0 as an independent comparison, and
the median Pearson correlation rose from 0.7154 with single-sequence input to 0.8637 with a full
MSA, a difference of 0.1483 (arithmetic). "Independent" does not survive scrutiny. The entries are
monomer predictions of full-length canonical sequences, distributed explicitly as model-confidence
estimates rather than biophysical quantities [@varadi2022; @jumper2021], so the arm compares
confidence profiles for a chain, not assessments of a complex. Both arms are fitted to overlapping
PDB-derived corpora, where similarity-based leakage inflates performance substantially [@graber2025;
@li2024], and co-folding benchmarks built from PDB-resolved complexes report their own scores as
leakage-contaminated upper bounds for this reason [@leng2026], and MSA depth is an input they share,
so the rise measures convergence of two models on shared evidence rather than on an experimental
structure. In the regime a chimera occupies, with no evolutionary record, pLDDT behaves
qualitatively differently than on conserved proteins [@middendorf2024]. This is a correlated second
opinion.

[FIGURE: fig3_falsified_every_version.png — Successive corrections moved the precision of the estimate, not its sign: H1 was falsified in all 11 retained versions.]

### The slate is exploratory, not confirmatory

The slate comprises 8 pre-registered studies and 25 hypotheses: 13 confirmed, 11 falsified, 1 not
tested; 5 decided by a test statistic and 19 by a threshold. Pre-registration here means an
in-repository hash-locked pre-specification, not deposition with an external registry: the SHA-256
hash fixed each plan before its data was seen, so any departure between plan and executed study is
recoverable by diffing the two, though a reader who does not trust the archive has no independent
timestamp to check it against; no ledger of such departures is compiled here, and none is claimed.
The meta-research argues against assuming there are none: only two of 27 Preregistered-badge
articles contained no deviation from plan [@claesen2021], and registered plans are routinely too
underspecified to conduct as written [@van2024]. A slate decided predominantly by thresholds rather
than by test statistics is exploratory throughout.

Two statistical caveats follow. Holm correction was applied only to genuine test statistics, which
is defensible, but family-wise correction can only map a p-value upward and so offers no protection
to a claim whose content is failure to reject [@aickin1996; @rothman1990; @perneger1998]. And no
equivalence test was pre-specified: with 13 paired candidates, a paired difference of 0.0009 and
Cohen's dz of 0.0057, the supportable claim is that no difference was detected at the achieved
precision, not that none exists [@altman1995; @lakens2017; @hageman2021; @button2013].

### Recommendations for anyone running a similar screen

1. Measure the sampler noise floor first, and refuse to read a difference below it: here the
   seed-to-seed ipTM SD of 0.14943 exceeded the effect of interest by a factor of 166.03
   [@henderson2018; @raouraoua2026].
2. Pre-register the null and the decoy count. With d decoys the per-candidate probability of
   beating all of them is 1/(d+1) — 0.0909 at ten — so the screen-level expectation of 1.182
   winners over 13 candidates is fixed before anything runs [@mysinger2012; @elias2007].
3. Run at least two architecturally distinct predictors, and report disagreement as a result
   [@zhai2025; @ko2026; @unsal2026].
4. Calibrate on experimental complexes first, using peptide-specific CAPRI criteria [@basu2016b;
   @marcu2017], stratify that calibration by the training cutoff, and read the post-cutoff stratum.
   The interface benchmark here was 62% CAPRI-acceptable pooled over 16 X-ray peptide–receptor
   complexes, with median DockQ 0.36, median fnat 0.518 and Spearman rho of 0.8 between ipTM and
   DockQ; split by deposition date it was 7 of 8 acceptable with median DockQ 0.8725 on complexes
   that could have been in training, against 3 of 8 acceptable with median DockQ 0.18 — below the
   CAPRI acceptable-quality cutoff of 0.23 — on complexes that could not. Only that stratum licenses
   a claim about resolution [@li2024]. Match the calibration set to the regime as well as the date:
   these benchmark complexes carry peptides of 7 to 17 residues against receptors of 80 to 304,
   whereas the screened candidates are 31 to 47 residues against receptor constructs of 156 to 608,
   so the calibration was measured outside the regime it is being asked to license.
5. Fix construct boundaries and assembly state against experimental structures before folding
   anything, recording which sites are interfacial and so absent from a single chain
   [@karakas2011; @park2009]; and require a sequence accession for every motif, treating an
   unattributed fragment as disqualifying rather than as a footnote.
6. Pre-specify the smallest effect size of interest and an equivalence bound, so that a null is
   interpretable when it arrives [@lakens2017; @altman1995] — and then publish it [@turner2008;
   @chan2004; @ioannidis2005].
