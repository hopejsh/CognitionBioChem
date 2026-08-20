# CognitionBioChem v1.0.0

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

- **8 pre-registered studies**, 25 hypotheses,
  13 confirmed and 11 falsified. Every plan is hash-locked in
  `prespec/` and was registered before its data was seen. Not one study is confirmatory:
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
- **313 automated checks** across six suites, each verified to fail on the defect it names.

## What it does not do

It runs no AlphaFold 3, computes no binding free energy for display, and predicts no ADMET for
a molecule outside the model's applicability domain. Values asserted by an earlier version that
no calculation supports are preserved under `retracted_claims` rather than deleted.

## Development note

Built with substantial AI assistance. The internal review that found the fabricated values was
a multi-agent LLM process, not human peer review. Both facts are in the README and `NOTICE`.
