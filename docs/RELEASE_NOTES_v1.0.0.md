<!-- RELEASE-NOTE-FROZEN: this is the body of the published v1.0.0 GitHub release and the
     description behind version DOI 10.5281/zenodo.22032685. It is a record of what that
     release contained on 2026-08-20, not a description of the repository. Its counts are
     deliberately not maintained; the lines that state one carry the SLATE-COUNT-HISTORICAL
     marker that platform/check_metadata_counts.py documents for exactly this case.
     platform/build_release_notes.py refuses to regenerate a file carrying this marker.
     For the current state, read docs/RELEASE_NOTES_v1.1.0.md. -->

# CognitionBioChem v1.0.0

> **Frozen. This describes the v1.0.0 release of 2026-08-20, not the repository today.**
> Study #12, `interface-null-positive-control-v1`, was registered on 2026-08-22 — two days
> after this release — and it changed both of the claims below that a reader is most likely
> to carry away. It added a ninth study to the slate, and it is the **first study in the
> slate whose protocol audit records no deviation from its registered plan**, which the
> sentence "Not one study is confirmatory" was written before and does not survive. Its <!-- SLATE-COUNT-HISTORICAL: quotes the superseded sentence in order to retract it -->
> registered positive control also withdrew the per-candidate reading of the
> composition-matched null throughout the repository. None of that is below, because none of
> it existed yet. **The current state is `docs/RELEASE_NOTES_v1.1.0.md`.**

The first release. It exists to make a negative result citable.

## The finding

Across a 13-candidate screen and a 143-fold
full-MSA rerun, the designed peptides did not separate from composition-matched shuffles of
their own amino acids: **mean native ipTM 0.6287 against a mean decoy of
0.6278**. The hypothesis has been falsified in all
**11 retained versions** of the two screening
studies, across candidate sets from 6 to 13 designs. Two candidates beat all ten of their own
decoys, which is what chance looks like at this scale:
1.182 are expected to, and
P(X ≥ 2) = 0.3338.

## What is in the release

- **8 pre-registered studies**, 25 hypotheses, <!-- SLATE-COUNT-HISTORICAL: v1.0.0's slate; #12 registered 2026-08-22 -->
  13 confirmed and 11 falsified. Every plan is hash-locked in <!-- SLATE-COUNT-HISTORICAL: v1.0.0's verdict totals -->
  `prespec/` and was registered before its data was seen. Not one study is confirmatory: <!-- SLATE-COUNT-HISTORICAL: true of all eight studies then; #12's audit records confirmatory = true -->
  each deviated from its plan in at least one respect, and each says so.
- **51 structures** under custody — 13 candidate-receptor
  complexes, 22 peptide-only folds and
  16 deposited AlphaFold DB receptors — each opening its real
  coordinate file with per-residue pLDDT, PAE and, for complexes, interface PAE.
- **An exploratory AlphaFold DB comparison** in two arms. Median Pearson r between the two
  models' per-residue confidence rises from
  0.7154 to
  0.8637 when Boltz-2 is given an MSA. It ships an
  effective sample size and a mis-registration null, because 156 residues on TREM2 are worth
  about five independent observations.
- **313 automated checks** across six suites, each verified to fail on the defect it names. <!-- SLATE-COUNT-HISTORICAL: v1.0.0 ran six suites -->

## What it does not do

It runs no AlphaFold 3, computes no binding free energy for display, and predicts no ADMET for
a molecule outside the model's applicability domain. Values asserted by an earlier version that
no calculation supports are preserved under `retracted_claims` rather than deleted.

## Development note

Built with substantial AI assistance. The internal review that found the fabricated values was
a multi-agent LLM process, not human peer review. Both facts are in the README and `NOTICE`.
