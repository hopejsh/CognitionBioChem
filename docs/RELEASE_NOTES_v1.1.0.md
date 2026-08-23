<!-- RELEASE-NOTE-GENERATED: written by platform/build_release_notes.py from data/,
     prespec/ and verify_all.SUITES. Do not hand-edit -- rebuild it:
       ./.venv/bin/python platform/build_release_notes.py
     Once this version is tagged and published, replace this marker with RELEASE-NOTE-FROZEN
     so a later rebuild cannot rewrite the record of a published release. -->

# CognitionBioChem v1.1.0

The release that adds the registered positive control, and narrows how the negative result may
be read. Every count below is generated from the artefacts, not typed.

## The finding

Across a screen of 13 candidate–receptor constructs covering **12 distinct peptides** — one
41-mer is screened against two receptors and so is counted twice in every mean and count — and a
143-fold full-MSA rerun, the designed peptides did not separate from composition-matched
shuffles of their own amino acids: **mean native ipTM 0.6287 against a mean decoy of 0.6278**.
The hypothesis has been falsified in all **11 retained versions** of the two screening studies,
across candidate sets from 6 to 13 constructs.

## What changed since v1.0.0

Study #12, `interface-null-positive-control-v1`, was registered on **2026-08-22** — after v1.0.0
was published — and measured the null itself. Sixteen deposited X-ray peptide–receptor complexes
were folded against ten uniform random permutations of each peptide.

- The natives beat their own permutations **in aggregate** by **+0.0895 ipTM** (Holm p = 0.0148,
  13 of 16 differences positive). The score is not blind to residue order on sequences that
  demonstrably bind.
- Only **4 of 16** beat all ten permutations of themselves, against a threshold of 5 registered
  in advance: P(X ≥ 4) = 0.05114 under Bin(16, 1/11). **The per-case reading of the
  composition-matched null is withdrawn** as a result, throughout the repository: the comparison
  licenses a verdict on a batch of native–decoy pairs taken together and none on any single
  pair. The empirical-p floor is 1/11 = 0.0909, above α, so no per-case verdict was reachable at
  any outcome — a statement about the design, not a count of failures.
- The natural separation could not be shown to exceed the designed one (Welch p = 0.1067).
- Its protocol audit records **0 deviations** from its registered plan and `confirmatory = true`
  — the first study in this slate to do so. v1.0.0's note said no study was confirmatory. That
  was true when it was written and is not true now; the old note is kept, frozen, and says so at
  the top.
- **Custody.** 160 of #12's 176 rows point at `runs/interface-null-positive-control/`; the other
  16 are native folds reused from #7 under content-addressed run directories. README records
  that this run tree is not in the repository, so #12's confidence values are reproducible by
  re-running and are **not** verifiable against stored bytes — unlike every other study in this
  slate.

## What is in the release

- **9 pre-registered studies**, 28 hypotheses, 14 confirmed and 13 falsified, 1 not tested.
  Every plan is hash-locked in `prespec/` and was registered before its data was seen, under 27
  registered analysis plans counting every superseded version. **1 confirmatory study**: #12's
  audit records no deviation. The other 8 deviated from their plans in at least one respect, and
  each says so.
- **51 structures** under custody — 13 candidate–receptor complexes, 22 peptide-only folds and
  16 deposited AlphaFold DB receptors — each opening its real coordinate file with per-residue
  pLDDT, PAE and, for complexes, interface PAE.
- **An exploratory AlphaFold DB comparison** in two arms. Median Pearson r between the two
  models' per-residue confidence rises from 0.7154 to 0.8637 when Boltz-2 is given an MSA. It
  ships an effective sample size and a mis-registration null, because 156 residues on TREM2 are
  worth about five independent observations.
- **12 verification suites**, in which every check is itself verified to fail on the defect it
  names.

## What it does not do

It runs no AlphaFold 3, computes no binding free energy for display, and predicts no ADMET for a
molecule outside the model's applicability domain. Values asserted by an earlier version that no
calculation supports are preserved under `retracted_claims` rather than deleted.

## Development note

Built with substantial AI assistance. The internal review that found the fabricated values was a
multi-agent LLM process, not human peer review. Both facts are in the README and `NOTICE`.
