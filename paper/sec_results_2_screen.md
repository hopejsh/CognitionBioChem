## The designed peptides did not separate from composition-matched shuffles of their own residues

### Design of the screen and the effect of the multiple sequence alignment

Each candidate was co-folded against its assigned receptor domain and compared with shuffles of its
own residues. The shuffle is a random permutation of the candidate's own residues, so it holds
length, net charge, hydrophobic content and glycine/serine fraction fixed and destroys only the
arrangement — the weakest null with respect to motif content and the strongest with respect to the
bulk properties a predictor can exploit without recognising anything [@jiang2008; @schaffer2001].
If a candidate cannot beat permutations of itself, its motif content is contributing nothing the
model resolves.

The screen was run in two configurations. The first used three shuffles per candidate and no
multiple sequence alignment; the second re-ran the same comparison with a full alignment and ten
shuffles per candidate. The paired statistics reported below are those of the full-alignment rerun,
which is the better-powered of the two and the one with the deeper input the model was designed to
use. That the alignment did materially change what the network produced on one independent
comparison is visible in the cross-check against the AlphaFold Protein Structure Database
[@varadi2022]: the median Pearson correlation between predicted and deposited per-residue confidence
rose from 0.7154 with single-sequence input to 0.8637 with a full alignment. That cross-check is a
per-residue confidence comparison against deposited AlphaFold DB models, not a measurement on the
peptide-receptor complexes screened here, so it licenses only the statement that the alignment
changed what the network produced on that comparison. The alignment raised the level of agreement
there. It did not create separation here.

Across the thirteen candidates, mean designed ipTM was 0.6287 and mean decoy ipTM 0.6278. The paired
difference was 0.0009, Cohen's dz was 0.0057, and the paired t-test returned p = 0.98.
Dividing the paired difference by dz gives an implied standard deviation of the paired differences
of roughly 0.15 to 0.17 — the two input values are themselves rounded, so this is an
order-of-magnitude statement rather than a precise one — a spread roughly two orders of magnitude
larger than the mean difference it surrounds, and comparable to the sampler's own seed-to-seed
standard deviation on ipTM of 0.14943.

This is a null result at the achieved precision and is reported as one. A large p-value is not
evidence of absence [@altman1995], and no smallest effect of interest was pre-specified, so no
equivalence test was run and none is claimed [@lakens2017]. Thirteen pairs is a low-power design in
which the magnitude of any recovered effect would be inflated and unreliable [@button2013], and a
single p-value is a draw from a wide sampling distribution [@halsey2015; @greenland2016]. The
defensible statement is the narrow one: on this construct set, under this predictor, no separation
between designed peptides and composition-matched shuffles of their own residues was detected
([FIG: fig1_native_vs_decoy.png]).

[FIGURE: fig1_native_vs_decoy.png — Designed ipTM against the distribution of composition-matched decoy ipTM for each of the thirteen candidates; the paired difference is 0.0009.]

### Per-candidate values

| Candidate | Target | Designed ipTM | Best of 10 decoys | Decoy mean | Beats all decoys |
| --- | --- | --- | --- | --- | --- |
| MicroDual-Trem2-Nrf2-M5 | TREM2 | 0.9025 | 0.9724 | 0.9258 | no |
| HippoDual-TrkB-AMPK-X5 | NTRK2 | 0.8314 | 0.8754 | 0.7776 | no |
| BasalNgf-TrkA-B3 | NTRK1 | 0.818 | 0.7498 | 0.4952 | yes |
| BasalAChE-Abeta-B4 | ACHE | 0.8105 | 0.7969 | 0.6612 | yes |
| PfcDual-nACh-GluN2A-P5 | CHRNA7 | 0.7461 | 0.8658 | 0.5935 | no |
| MicroTlr4-Antagonist-M3 | TLR4 | 0.7223 | 0.9341 | 0.8528 | no |
| MicroTrem2-Agonist-M1 | TREM2 | 0.6929 | 0.9625 | 0.8483 | no |
| HippoTrk-Saponin-X1 | NTRK2 | 0.5408 | 0.566 | 0.4211 | no |
| PfcTrk-ErkEnhancer-P2 | NTRK2 | 0.5405 | 0.8037 | 0.5744 | no |
| PfcGluN2A-LTP-P3 | GRIN2A | 0.4953 | 0.7704 | 0.468 | no |
| BasalSuper-AChE-TrkA-B5 | ACHE | 0.4895 | 0.6963 | 0.5053 | no |
| PfcACh-PAM-P1 | CHRNA7 | 0.3567 | 0.7603 | 0.5978 | no |
| HippoAChE-AlkaPept-X2 | ACHE | 0.2265 | 0.7911 | 0.4401 | no |

Counting from the table, four of the thirteen designs reached 0.8 or above, three fell between 0.6
and 0.8, and six fell below 0.6. The bands in routine use — high values read as a confident
interface, intermediate values as uncertain, low values as a probable failure — are conventions
inherited from AlphaFold-Multimer's introduction of interface-aware confidence [@evans2021]; they
are not calibrated probabilities of binding, and the companion interface PAE channel is likewise a
descriptive quantity rather than a calibrated probability, with an interpretation that is not
standardised [@elfmann2023]. Read by that convention, the highest value in the set, 0.9025 for
MicroDual-Trem2-Nrf2-M5 against TREM2, would be reported as a good interface and taken forward.

The decoy column is what makes that reading untenable. Six of the thirteen candidates — again
counted from the table — had at least one shuffle of their own residues reaching 0.8 or above, two
more than the number of designs that did. The single highest ipTM anywhere in the screen, 0.9724,
belongs to a shuffle of MicroDual-Trem2-Nrf2-M5, not to the design. The second TREM2 candidate,
MicroTrem2-Agonist-M1, scored 0.6929 against a decoy mean of 0.8483 and a best decoy of 0.9625: it
scored below the mean of its own shuffles, by 0.8483 − 0.6929 = 0.1554, or about 1.04 of one seed
standard deviation once that difference is divided by 0.14943. Counting designs that merely exceeded
their own decoy mean gives six of thirteen, which is one of the two most likely outcomes under a
no-effect binomial with p = 0.5 — an arithmetic observation, like the screen-level calculation
below, and not a pre-registered test.

This behaviour is what the surrounding literature predicts. Standard co-folding confidence metrics
do not reliably separate genuine interactions from an abundance of false positives at scale, which
is why an external classifier was required to make an all-by-all AlphaFold-Multimer screen over
nearly 300 human genome-maintenance proteins interpretable [@schmid2025]; for peptides specifically,
the correct interface was identified in only 40% of cases from full-length sequences, recovering
only after fragment decomposition [@bret2024]; prediction accuracy depends on training-set
similarity across 261 experimentally resolved peptide complexes [@zhai2025]; and structure
predictors given shuffled negative peptides in a pMHC-II setting achieved high positive recall while
frequently misclassifying unbound peptides as binders [@ko2026]. The nearest published analogue —
106 nanobody-antigen complexes scored against 11,342 shuffled non-cognate pairings across three
co-folding engines including the one used here — reports geometrically plausible complexes produced
throughout while ipTM frequently fails to discriminate cognate from non-cognate [@smorodina2026].
Pose placement and the discrimination of binders from decoys are decoupled quantities [@hoegen2025],
and the present result sits on the unfavourable side of that split.

### Two candidates beat all of their own decoys; the expected number is 1.182

Two of the thirteen candidates, BasalNgf-TrkA-B3 and BasalAChE-Abeta-B4, exceeded all ten of their
own decoys. Under exchangeability of a design and its ten shuffles, the per-candidate probability
of that outcome is 1/11 = 0.0909. Over thirteen candidates the expected number of such winners is
13 × 0.0909 = 1.182, and the probability of observing two or more is P(X ≥ 2) = 0.3338. Two winners
is not two hits; it is close to the modal outcome of a screen containing no effect at all.

The point generalises beyond this screen. A composition-matched decoy set answers a per-candidate
question — is this sequence better than permutations of itself? A screen asks a different question:
did any member of the set do better than the best member would have done under the null? Applying
the per-candidate decision rule to the screen commits, one level up, exactly the multiple-comparison
error the decoy set was built to prevent one level down. Genomics made this arithmetic automatic
with the false-discovery-rate framework [@storey2003]; proteomics solved it structurally by letting
decoy hit frequency estimate the error rate of the whole identification set [@elias2007]. A
candidate screen scored by co-folding confidence needs the same discipline, and the decoy
distribution is the empirical null for the screen rather than a per-candidate sanity check.

One caveat belongs here rather than in the discussion. The screen-level binomial calculation was
performed after the per-candidate results were seen. It was not part of the pre-registered protocol,
which fixed the candidates, the decoy construction and the paired test statistic under a SHA-256
hash before any prediction was run. It is therefore exploratory, and is reported as an arithmetic
observation about what the pre-registered design implies, not as a test that carries pre-specified
error control ([FIG: fig2_screen_level_null.png]) [@simmons2011; @ioannidis2005].

[FIGURE: fig2_screen_level_null.png — Observed count of candidates beating all of their own decoys against the binomial null with per-candidate probability 0.0909 over thirteen candidates.]

### Both margins over the best decoy lie inside the instrument's own noise

The margins are small relative to the measured reproducibility of the score. Reseeding the sampler
gave a standard deviation of 0.14943 on ipTM, 2.6615 on complex pLDDT and 4.6157 on minimum
interface PAE. BasalNgf-TrkA-B3 beat its best decoy by 0.818 − 0.7498 = 0.0682, which is 0.4564 of
one such standard deviation. BasalAChE-Abeta-B4 beat its best decoy by 0.8105 − 0.7969 = 0.0136,
or 0.09101 of one standard deviation. Neither margin survives contact with the noise floor; both
are differences a rerun with different seeds could plausibly erase or reverse.

Measured against the decoy mean rather than the best decoy the picture is slightly better and still
not decisive: BasalNgf-TrkA-B3 exceeds its decoy mean by 0.3228, or 2.1602 seed standard
deviations, and BasalAChE-Abeta-B4 by 0.1493, which is 0.999 of one standard deviation. All four
ratios in this paragraph are the stated differences divided by 0.14943. A single-seed confidence
value is a draw from a distribution, and comparing candidates by one number each is comparing draws
[@raouraoua2025; @henderson2018]; this is why the noise floor was measured before the screen was
read rather than after.

### The result did not change across versions of the candidate set

The screen was rebuilt repeatedly as candidates were added, corrected and retired. The primary
hypothesis — that designed peptides separate from composition-matched shuffles of their own residues
— was falsified in all 11 retained versions of the record, over candidate sets of differing size
ending at the thirteen reported here. No retained version of the candidate list produced a
separation; across the 11 retained versions the conclusion did not track which peptides were in the
set at the time.

That stability is worth stating precisely because it is weak evidence of a strong thing. It does
not show that the peptides cannot bind, and it does not show that the predictor is without skill:
on sixteen X-ray peptide-receptor complexes the same pipeline returned 62% CAPRI-acceptable models
with a median DockQ [@basu2016b; @mirabello2024] of 0.36 and a Spearman correlation of 0.8 between
ipTM and DockQ. The model places peptides at interfaces with measurable accuracy. It
did not, on this construct set, distinguish a designed sequence from a permutation of the same
residues, and did not in any retained version of the analysis
([FIG: fig3_falsified_every_version.png]).

[FIGURE: fig3_falsified_every_version.png — The primary hypothesis was falsified in all 11 retained versions of the record, across successive revisions of the candidate set.]
