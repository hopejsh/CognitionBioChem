#!/usr/bin/env python3
"""Study #12: the positive control the composition-matched null has never had.

The screen (candidate-screen-v8, and its MSA re-run msa-specificity-v9) found that not one
designed candidate separated from permutations of its own residues on interface confidence.
That negative admits two opposite readings and the screen cannot separate them:

  (a) the confidence score does not read the designs' content — in which case the permutation
      null is doing its job as a control and the manuscript's proposal stands; or
  (b) these particular sequences carry no order-dependent binding content, so a score that
      ranks them level with their own permutations is behaving CORRECTLY, and the null has
      demonstrated nothing about the score.

Reading (b) is not a straw man. Eleven of the thirteen candidates contain no attributed
natural motif of six residues or more, and attributed motif residues are 5.3% of the 487
designed residues; the manuscript's own Supporting Information judges (b) the more likely
reading. What is missing is the other cell of the table: NOWHERE in this work has a sequence
with DEMONSTRATED binding been scored against permutations of its own residues. Results §1.4
concedes exactly that — "the null is demonstrated to reject and is not demonstrated to
discriminate".

This study folds each of the interface gate's sixteen experimentally determined peptide-
receptor complexes against ten uniform random permutations of its own peptide, under the
GATE's settings rather than the screen's, because these are the gate's complexes and the
comparison must not confound the null with an alignment change. The sixteen native folds
already exist in the gate artefact and are REUSED, not recomputed; which ones, and at what
value, is frozen in REUSED_NATIVES below and checked against the artefact before the run.

The plan is registered BEFORE any prediction. A paper that criticises reading a confidence
score without a registered control cannot choose its own analysis after seeing this result.

    ./.venv/bin/python platform/studies/interface_null_positive_control.py --register
    ./.venv/bin/python platform/studies/interface_null_positive_control.py --fetch
    ./.venv/bin/python platform/studies/interface_null_positive_control.py --run
    ./.venv/bin/python platform/studies/interface_null_positive_control.py --analyse
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import inference as inf, prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402
from studies.candidate_screen import _scrambles  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "interface-null-positive-control-v1"
GATE = REPO / "data" / "study_peptide_interface.json"
SCREEN = REPO / "data" / "study_candidate_screen.json"
MSA_SCREEN = REPO / "data" / "study_msa_specificity.json"
RESULT = REPO / "data" / "study_interface_null_positive_control.json"

#: Fold outputs are written straight into the repository rather than into /tmp. Every earlier
#: study wrote to a /tmp root and relied on platform/rescue_runs.py to take custody
#: afterwards -- a step that has been forgotten before, which is how runs/ came to hold 24
#: directories while the published artefacts cited 148 absolute /tmp paths that resolve to
#: nothing in a fresh clone. Writing here in the first place means the bytes behind every
#: ipTM in this artefact are under custody from the moment they exist, and there is no window
#: in which a reboot can remove them.
WORK = REPO / "runs" / "interface-null-positive-control"

#: The permutations, frozen to disk by --fetch BEFORE any prediction runs, so that the input
#: to the run is a file that can be checked rather than a function call that has to be
#: trusted. --run regenerates them and aborts if they differ.
INPUTS = REPO / "data" / "study_inputs" / "interface_null_positive_control.json"

#: Permutations per complex. Fixes the per-complex empirical p floor at 1/(10+1) = 0.0909.
N_PERM = 10
SEED = 1
#: Complexes that must score above ALL ten of their own permutations for H2. Under the
#: per-complex null that happens with probability 1/11, so the expected count over 16
#: complexes is 1.45 and P(X >= 5) = 0.0115, while P(X >= 4) = 0.0511 would not clear alpha.
H2_MIN_SWEEPS = 5
#: CAPRI acceptable, used only for a registered stratification — never as an inclusion filter.
DOCKQ_ACCEPTABLE = 0.23
#: Tolerance for the reused-native reproduction check. Study #2 measured same-seed folds to
#: be bit-identical (spread 0.0), so anything above this is an environment change, not noise.
REPRO_TOLERANCE = 0.01
#: The native fold re-computed once to prove the reused values are still the values this
#: pipeline produces. Chosen before the run as the cheapest complex (94-residue receptor).
REPRO_PDB = "4XHV"

#: Frozen snapshot of the gate folds this study REUSES instead of recomputing: pdb_id, the
#: native ipTM, the gate's DockQ, and the memorisation stratum. Recorded at registration so
#: the reused arm cannot be re-picked afterwards, and verified against the gate artefact at
#: run time. This is a freeze of published values, not a hand-typed statistic.
REUSED_NATIVES = (
    ('4S15', 0.3004900813102722, 0.031, 'pre_cutoff'),
    ('4XHV', 0.8967278003692627, 0.899, 'pre_cutoff'),
    ('4XO9', 0.8946818709373474, 0.339, 'pre_cutoff'),
    ('4XOE', 0.7209686636924744, 0.279, 'pre_cutoff'),
    ('4XOJ', 0.9862698316574097, 0.952, 'pre_cutoff'),
    ('4XT9', 0.9231666326522827, 0.978, 'pre_cutoff'),
    ('4Y29', 0.8305281400680542, 0.963, 'pre_cutoff'),
    ('4Y32', 0.8925052285194397, 0.846, 'pre_cutoff'),
    ('10LG', 0.9165648818016052, 0.381, 'post_cutoff'),
    ('10TC', 0.9450889825820923, 0.831, 'post_cutoff'),
    ('12ZJ', 0.7191354632377625, 0.193, 'post_cutoff'),
    ('21EE', 0.33958902955055237, 0.167, 'post_cutoff'),
    ('23AG', 0.8186440467834473, 0.165, 'post_cutoff'),
    ('29TJ', 0.9341909885406494, 0.483, 'post_cutoff'),
    ('31EE', 0.15750667452812195, 0.019, 'post_cutoff'),
    ('31GN', 0.5908287167549133, 0.049, 'post_cutoff'),
)

#: The same sixteen, as the plan text names them, so the registered list and the code cannot
#: drift apart.
REUSED_TEXT = " ".join(f"{p} {v:.4f}" for p, v, _, _ in REUSED_NATIVES)


def _gate_rows() -> list[dict]:
    return [r for r in json.loads(GATE.read_text())["rows"] if r.get("ok")]


def prespec_args() -> tuple:
    """The arguments --register builds the plan with.

    Named once so the registration path and the hash-stability test cannot disagree about
    them. The only free quantity is how many gate complexes there are; everything else in
    the plan is fixed text or a frozen constant of this module.
    """
    return (len(REUSED_NATIVES),)


def build_prespec(n_complexes: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "Do peptides with experimentally demonstrated binding — the sixteen deposited "
            "peptide-receptor complexes of the interface gate — separate from uniform random "
            "permutations of their own residues on Boltz-2 interface confidence, under the "
            "same single-sequence settings the gate used? This is the cell the "
            "composition-matched null has never had filled: no sequence with a demonstrated "
            "interaction has been scored against permutations of itself anywhere in this "
            "work, which is why the null is demonstrated to reject and is not demonstrated "
            "to discriminate."),
        primary_metric="paired_native_minus_permutation_mean",
        primary_metric_justification=(
            "The score is ipTM, and the test is paired ACROSS complexes: each complex "
            "contributes one native ipTM and the mean ipTM of its own ten permutations, and "
            "the sixteen differences are tested against zero. ipTM rather than DockQ because "
            "a permuted sequence has no deposited structure, so DockQ cannot be computed for "
            "the null arm at all, and because the claim under test is about the CONFIDENCE "
            "SCORE the screen read, not about pose accuracy — the gate already measured "
            "Spearman rho(ipTM, DockQ) = 0.80 on these same sixteen, which is what makes ipTM "
            "worth interrogating rather than discarding. Paired rather than a per-complex "
            "permutation p because with m = 10 permutations the empirical p has a hard floor "
            "of 1/(m+1) = 0.0909, above alpha = 0.05, so a per-complex test could never fire "
            "and would be the unreachable verdict this project's registration module rejects; "
            "per-complex empirical p values are reported as descriptive only, and the "
            "per-complex question is decided instead by H2's count against a binomial "
            "reference. Pairing also removes between-complex variation, which is large here "
            "because the receptors run 80-304 residues and the peptides 7-17, and ipTM "
            "depends on both. The metric deliberately mirrors the screen's "
            "paired_native_minus_decoy_mean so the positive control and the screen are read "
            "on one scale."),
        decision_threshold=(
            "H1 (PRIMARY) confirmed if the mean paired difference — native ipTM minus the "
            "mean ipTM of its own ten permutations — is positive with a Holm-adjusted paired "
            "t-test p < 0.05 over a registered family of two tests. H2 confirmed if at least "
            f"{H2_MIN_SWEEPS} of the {n_complexes} complexes score above EVERY one of their "
            "own ten permutations; that threshold is fixed now because under the per-complex "
            "null a complex sweeps its ten with probability 1/11, giving an expected count of "
            "1.45, P(X >= 5) = 0.0115 and P(X >= 4) = 0.0511 — four sweeps would not clear "
            "alpha and five will. H2 is a threshold criterion on a count, decided by looking "
            "at the number, and is registered HERE, in advance, as excluded from the Holm "
            "family: a 0/1 indicator is not a p-value and would steal a multiplier from the "
            "genuine tests. The executed family is therefore two, matching n_comparisons. H3 "
            "confirmed if the sixteen natural paired differences exceed the thirteen designed "
            "paired differences of candidate-screen-v8 with a Holm-adjusted Welch t-test "
            "p < 0.05 in that direction."),
        n_planned=n_complexes * (1 + N_PERM),
        n_comparisons=2,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        n_permutations=N_PERM,
        stopping_rule=(
            f"Fixed and absolute. The complexes are exactly the {n_complexes} scored rows of "
            "data/study_peptide_interface.json, frozen at registration by the PDB list in the "
            "analysis plan. Each is folded once against each of ten permutations of its own "
            "peptide, generated by random.Random(1) through the screen's own _scrambles(), in "
            "a fixed order; the sixteen native folds are reused from the gate. Nothing is "
            "added or removed after the first prediction: not a complex, not a permutation, "
            "not a seed, and no permutation set is re-drawn. No interim analysis is performed "
            "and no ipTM is inspected until all 160 new folds have completed or failed. "
            "Technical failures are recorded with their reason and excluded; a complex "
            "retaining fewer than 5 usable permutations is dropped from the paired test with "
            "that stated. If H1 is falsified, that is the result: no MSA arm, no second seed, "
            "no alternative confidence score and no re-stratified subset may be substituted "
            "for it afterwards, and any such analysis run later is exploratory and must be "
            "labelled so."),
        analysis_plan=(
            "REUSED NATIVES. The sixteen native folds are taken from the gate artefact "
            "(data/study_peptide_interface.json, rows[].iptm) and are NOT recomputed: "
            f"{REUSED_TEXT}. Those values are frozen in the study module and are compared "
            "against the artefact before the run; a mismatch aborts. Because the native arm "
            "was computed earlier than the permutation arm, one native — "
            f"{REPRO_PDB} — is re-folded once with identical settings as a reproduction "
            "check; if its ipTM moves by more than "
            f"{REPRO_TOLERANCE} the reused values are discarded and all sixteen natives are "
            "recomputed before any analysis. That verification fold is a control and is "
            "recorded separately from the 176 scored folds. "
            "NEW FOLDS. For each complex, ten uniform random permutations of its own peptide "
            "are drawn with random.Random(1) via studies.candidate_screen._scrambles, which "
            "rejects the identity permutation and duplicates. Each is folded with Boltz-2 "
            "2.2.1 as chain A = the deposited receptor construct, chain B = the permuted "
            "peptide, msa=empty (single-sequence), accelerator gpu, seed 1, "
            "diffusion_samples 1, recycling_steps 3 — the GATE's settings, not the screen's, "
            "so that the only thing that differs between the two arms of this study is the "
            "order of the peptide's residues. "
            "TESTS. Per complex, native ipTM minus the mean of its ten permutations; the "
            "sixteen differences are tested against zero with a paired (one-sample) t-test "
            "and reported with Cohen's dz (H1). The number of complexes scoring above all ten "
            "of their permutations is compared against the binomial reference with p0 = 1/11 "
            "(H2). The sixteen differences are compared against the thirteen per-candidate "
            "differences of candidate-screen-v8 with a Welch t-test (H3); candidate-screen-v8 "
            "is the comparator because it is the single-sequence arm and alignment mode is "
            "the variable that moves ipTM most, and msa-specificity-v9's thirteen differences "
            "(m = 10 permutations, MSA server) are reported alongside as a registered "
            "sensitivity comparison, not as a second test. Holm across the two tests; both "
            "are two-sided, so direction is checked separately from significance and a "
            "significant effect in the wrong direction falsifies rather than confirms. "
            "REGISTERED DESCRIPTIVE STRATIFICATIONS, fixed now so they cannot be chosen after "
            "the result: the paired difference split by whether the gate's DockQ reached "
            "CAPRI acceptable (>= 0.23; 10 of 16 did), and split by the gate's pre/post "
            "training-cutoff stratum. Neither carries a verdict. "
            "WHAT THE OUTCOMES LICENSE, stated before the data. If H1 is confirmed, the "
            "composition-matched null is demonstrated to discriminate on sequences that "
            "demonstrably bind, the screen's flat result can no longer be attributed to a "
            "score blind to residue order, and the manuscript's proposal of the null as a "
            "standard control has its positive control. It does NOT by itself decide between "
            "readings (a) and (b) for the designed set: discrimination shown on 7-17 residue "
            "crystallised natural peptides transfers to 31-47 residue designed chimeras only "
            "by assumption, and that assumption is named in the confounds rather than "
            "absorbed. If H1 is falsified, the null is not demonstrated to discriminate even "
            "here, neither reading of the screen's negative is licensed, and the manuscript's "
            "central proposal cannot be offered as a standard control for this pipeline in "
            "single-sequence mode — a change of subject, and the result to be reported."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_natural_peptides_separate_from_their_permutations",
                statement=(
                    "Peptides with experimentally demonstrated binding score higher on "
                    "interface confidence than uniform random permutations of their own "
                    "residues, so the composition-matched null discriminates when there is "
                    "order-dependent binding content for it to find."),
                predicted_by=(
                    "the manuscript's central proposal — the permutation null offered as a "
                    "standard control — which stands only if the null can discriminate a "
                    "sequence with demonstrated binding from permutations of itself; i.e. "
                    "reading (a) of the screen's negative, that the score did not read the "
                    "designs' content"),
                confirmed_if=("mean paired difference > 0 with Holm-adjusted paired t-test "
                              "p < 0.05"),
                falsified_if=("mean paired difference <= 0, or Holm-adjusted paired t-test "
                              "p >= 0.05")),
            ps.Hypothesis(
                name="H2_the_null_discriminates_case_by_case",
                statement=(
                    "The null fires on individual complexes and not only on a mean over "
                    "sixteen — the form in which a control offered for routine use on a "
                    "single design would actually be applied."),
                predicted_by=(
                    "the proposal that a permutation null can be run as a per-case control on "
                    "one candidate, which requires per-case and not merely aggregate "
                    "discrimination"),
                confirmed_if=(f"at least {H2_MIN_SWEEPS} of {n_complexes} complexes score "
                              "above all ten of their own permutations (P = 0.0115 under the "
                              "per-complex null)"),
                falsified_if=f"fewer than {H2_MIN_SWEEPS} complexes do"),
            ps.Hypothesis(
                name="H3_natural_separation_exceeds_designed",
                statement=(
                    "The natural peptides' separation from their own permutations is larger "
                    "than the designed candidates' separation measured under the same "
                    "single-sequence settings in candidate-screen-v8, so the missing cell is "
                    "filled by a contrast rather than by two studies read side by side."),
                predicted_by=(
                    "reading (b) of the screen's negative — that the flat result is a "
                    "property of the thirteen designed sequences, eleven of which carry no "
                    "attributed natural motif of six residues or more and whose attributed "
                    "motif residues are 5.3% of 487 designed residues — rather than of the "
                    "score. The strong form of reading (a), a score blind to residue order "
                    "everywhere, predicts no contrast in either direction"),
                confirmed_if=("mean natural difference > mean designed difference with "
                              "Holm-adjusted Welch t-test p < 0.05"),
                falsified_if=("the natural mean does not exceed the designed mean, or "
                              "Holm-adjusted Welch p >= 0.05")),
        ),
        secondary_metrics=(
            "mean_native_iptm", "mean_permutation_iptm", "cohens_dz",
            "per_complex_empirical_p", "n_complexes_beating_all_permutations",
            "beats_all_permutations_null", "paired_difference_by_dockq_stratum",
            "paired_difference_by_split", "log10_distinct_permutations",
            "natural_minus_designed_contrast", "contrast_vs_msa_specificity_v9",
            "per_complex", "native_fold_reproduction_check",
            "wall_clock_seconds_per_fold",
        ),
        exclusions=(
            f"Decided now, before any prediction. All {n_complexes} scored rows of the gate "
            "artefact enter, with NO filter on ipTM, DockQ, split, peptide length or receptor "
            "size. The inclusion criterion is demonstrated binding — a deposited two-entity "
            "X-ray complex — not whether the predictor already placed the peptide correctly, "
            "so the six complexes whose gate DockQ is below CAPRI acceptable (4S15 0.031, "
            "12ZJ 0.193, 21EE 0.167, 23AG 0.165, 31EE 0.019, 31GN 0.049) are kept. Dropping "
            "them would select for cases where the model already succeeds and would inflate "
            "the null's apparent discrimination; the split is reported as a registered "
            "descriptive stratification instead. No complex is excluded for having a small "
            "permutation space: the smallest, 4Y32 at 7 residues, admits 1,260 distinct "
            "arrangements, far more than the ten drawn, and the size is reported per complex. "
            "The identity permutation and duplicates within a complex's set are rejected by "
            "the generator, which is its fixed behaviour and not a post-hoc filter. Folds "
            "that fail technically are recorded with their reason and excluded; a complex "
            "retaining fewer than 5 usable permutations is dropped from the paired test with "
            "that stated."),
        known_confounds=(
            "1. LENGTH. These peptides are 7-17 residues; the screened candidates are 31-47, "
            "with no overlap at all. Whatever this study shows about the null holds at 7-17 "
            "residues and is transferred to 31-47 only by assumption. "
            "2. CRYSTALLISATION BIAS. A peptide-receptor complex reaches the PDB only if the "
            "peptide binds well enough to co-crystallise, so this set is enriched for strong, "
            "structurally ordered binders. It gives an OPTIMISTIC bound on what the null can "
            "discriminate — the same bias the gate's own plan records about its recovery "
            "rate — and a null that discriminates here is not thereby shown to discriminate "
            "on weak or transient binders. "
            "3. THE NULL IS NOT EQUALLY STRONG ACROSS THE TWO SETS. A permutation of a short "
            "peptide explores a far smaller space than a permutation of a long one: 4Y32's "
            "7-mer has 1,260 distinct arrangements (log10 3.1) and 4XT9's and 10TC's 8-mers "
            "6,720, against roughly 10^26 to 10^43 for the 31-47 residue candidates. A short "
            "permuted peptide also retains more of the native's local order by chance and its "
            "composition constrains the achievable interface more tightly, so the two studies' "
            "nulls are not the same instrument at the same strength, and the screen's flat "
            "result and any separation here cannot be subtracted from one another cleanly. "
            "H3's contrast is confounded with exactly this, and with receptor class (80-304 "
            "residue soluble functional modules here, 156-608 residue cysteine-rich "
            "glycosylated ectodomains there) and with permutation count (m = 10 here, m = 3 "
            "in candidate-screen-v8); a confirmed H3 is therefore attributable to the SETS, "
            "not to design content alone, and is reported that way. "
            "4. REUSED NATIVE ARM. The sixteen natives were folded earlier than the "
            "permutations, so any change of Boltz version, driver or hardware between the two "
            "would appear as a difference between arms rather than between sequences. "
            f"Mitigated by re-folding {REPRO_PDB} at identical settings and requiring its ipTM "
            f"to reproduce within {REPRO_TOLERANCE}; if it does not, all sixteen natives are "
            "recomputed. "
            "5. PER-COMPLEX RESOLUTION. With m = 10 the per-complex empirical p floors at "
            "1/11 = 0.0909, which exceeds alpha = 0.05, so NO per-complex call is made at the "
            "registered alpha and no single complex can be declared a hit on its own p. Those "
            "values are descriptive; the per-complex question is answered only in aggregate, "
            "through H2's count against the binomial reference. "
            "6. SINGLE-SEQUENCE MODE. All folds run with an empty alignment, which Boltz "
            "documents as degrading accuracy, and both arms are depressed together. A "
            "falsified H1 bounds the null in single-sequence mode only; it does not establish "
            "that the null fails to discriminate with a full MSA, where a pilot moved one "
            "native from 0.3402 to 0.7588 while moving its decoy from 0.3478 to 0.2986. "
            "7. POWER. n = 16 paired differences, and 16 versus 13 for the Welch contrast; "
            "only a large and consistent effect will register, and a falsified H1 with a "
            "small positive mean is 'not detected', not 'shown absent'. "
            "8. ipTM IS THE MODEL'S SELF-ASSESSMENT. It agrees with DockQ on these sixteen "
            "(Spearman rho = 0.80) but it is not an affinity, and separation on ipTM is "
            "evidence about what this pipeline distinguishes, not about what the molecules do."),
    )



# ---------------------------------------------------------------------------- #
# fetch
# ---------------------------------------------------------------------------- #

def _distinct_permutations(seq: str) -> int:
    n = math.factorial(len(seq))
    for v in Counter(seq).values():
        n //= math.factorial(v)
    return n


def _verify_reused() -> list[dict]:
    """Check the frozen native snapshot still matches the gate artefact."""
    rows = {r["pdb_id"]: r for r in _gate_rows()}
    out, bad = [], []
    for pid, iptm, dockq, split in REUSED_NATIVES:
        r = rows.get(pid)
        if r is None or abs(r["iptm"] - iptm) > 1e-12 or r["split"] != split:
            bad.append(pid)
            continue
        out.append({**r, "frozen_iptm": iptm, "frozen_dockq": dockq})
    if bad:
        raise SystemExit(
            f"frozen native snapshot no longer matches {GATE.name} for {bad}. The reused arm "
            "is part of the registered plan; resolve the discrepancy explicitly rather than "
            "re-freezing it.")
    return out



def _fold_plan() -> list[dict]:
    """The complete input to the run: the sixteen complexes, each with its ten permutations.

    Deterministic, and that is the point. _scrambles re-seeds random.Random(SEED) on every
    call, so the ten permutations a complex receives depend only on its own peptide and on
    SEED -- not on the order the complexes are visited, not on how many complexes there are,
    and not on anything that has happened earlier in the process. Regenerating this list a
    year from now reproduces it exactly, which is what makes the permuted sequences recorded
    in the artefact checkable rather than merely present.
    """
    out = []
    for nat in _verify_reused():
        pep = nat["peptide_seq"]
        perms = _scrambles(pep, N_PERM, SEED)
        # _scrambles is documented to reject the identity and duplicates; assert it here
        # rather than assume it, because a null built from a set containing the native
        # sequence would quietly weaken the very comparison this study exists to make.
        assert len(set(perms)) == N_PERM and pep not in perms, pep
        assert all(sorted(x) == sorted(pep) for x in perms), pep
        out.append({
            "pdb_id": nat["pdb_id"], "split": nat["split"],
            "receptor_seq": nat["receptor_seq"], "receptor_len": len(nat["receptor_seq"]),
            "peptide_seq": pep, "peptide_len": len(pep),
            "gate_dockq": nat["dockq"], "gate_iptm": nat["iptm"],
            "gate_ptm": nat.get("ptm"), "gate_complex_plddt": nat.get("complex_plddt"),
            "gate_model": nat.get("model"),
            "distinct_permutations": _distinct_permutations(pep),
            "permutations": perms,
        })
    return out


def _inputs_payload(plan: list[dict]) -> dict:
    return {
        "study_id": STUDY_ID,
        "source": ("data/study_peptide_interface.json (peptide-interface-v1), the sixteen "
                   "scored rows: deposited two-entity X-ray peptide-receptor complexes"),
        "permutation_seed": SEED,
        "permutation_generator": (
            "studies.candidate_screen._scrambles(peptide, 10, 1): random.Random(1) re-seeded "
            "per complex, uniform Fisher-Yates shuffle of the peptide's residues, rejecting "
            "the identity permutation and any duplicate within the complex's own set"),
        "n_complexes": len(plan),
        "n_permutations_per_complex": N_PERM,
        "n_new_folds": len(plan) * N_PERM,
        "complexes": plan,
    }


def _inputs_digest(plan: list[dict]) -> str:
    """A hash over the sequences alone, so the artefact can name the exact input set."""
    body = "\n".join(
        f"{c['pdb_id']}\t{c['receptor_seq']}\t{c['peptide_seq']}\t" + ",".join(c["permutations"])
        for c in plan)
    return hashlib.sha256(body.encode()).hexdigest()


def fetch() -> None:
    """Freeze the run's inputs on disk before any prediction exists to look at."""
    plan = _fold_plan()
    payload = _inputs_payload(plan)
    payload["sequence_set_sha256"] = _inputs_digest(plan)
    INPUTS.parent.mkdir(parents=True, exist_ok=True)
    INPUTS.write_text(json.dumps(payload, indent=1))
    print(f"{len(plan)} complexes from {GATE.relative_to(REPO)}; frozen natives verified")
    print(f"{'pdb':6s} {'split':11s} {'rec':>5s} {'pep':>4s} {'log10 perms':>11s}  peptide")
    for c in plan:
        print(f"{c['pdb_id']:6s} {c['split']:11s} {c['receptor_len']:5d} "
              f"{c['peptide_len']:4d} {math.log10(c['distinct_permutations']):11.2f}  "
              f"{c['peptide_seq']}")
        for k, s_ in enumerate(c["permutations"]):
            print(f"{'':6s} {'perm' + str(k):11s} {'':5s} {'':4s} {'':11s}  {s_}")
    print(f"\nseed {SEED}, {N_PERM} permutations each, {len(plan) * N_PERM} new folds")
    print(f"sequence set sha256 {payload['sequence_set_sha256'][:16]}")
    print(f"wrote {INPUTS.relative_to(REPO)}")


def _load_plan() -> tuple[list[dict], str]:
    """Regenerate the plan and hold it against whatever --fetch wrote.

    The regenerated list is the one used. The file is a check, not a source: if the two ever
    disagree, the seeded generator has stopped being reproducible and the run stops rather
    than silently folding a different null.
    """
    plan = _fold_plan()
    digest = _inputs_digest(plan)
    if INPUTS.exists():
        prior = json.loads(INPUTS.read_text())
        if prior.get("sequence_set_sha256") != digest:
            raise SystemExit(
                f"the permutations regenerate differently from {INPUTS.name}: frozen "
                f"{prior.get('sequence_set_sha256')}, regenerated {digest}. The permutation "
                "set is part of the registered plan and may not change; resolve this rather "
                "than overwriting the file.")
    else:
        fetch()
    return plan, digest


def _prune(out: Path) -> None:
    """Apply runs/manifest.json's retention policy as each fold lands, not in a later sweep.

    Coordinates, the confidence summary and the exact input.yaml are kept -- every number
    this study publishes derives from those. The tokenised input cache, the fetched
    alignments and the trainer logs are not. pae_/pde_ matrices are dropped because no
    quantity in this study derives from either; keeping them for 160 folds would add roughly
    a gigabyte of arrays to the repository that no code path here opens. Nothing removed is
    read by the reuse path, which needs only the model, the confidence file and the manifest.
    """
    for d in sorted(out.rglob("*"), key=lambda x: -len(x.parts)):
        if d.is_dir() and d.name in ("processed", "msa", "lightning_logs"):
            shutil.rmtree(d, ignore_errors=True)
    for f in out.rglob("*.npz"):
        if f.name.startswith(("pae_", "pde_")):
            f.unlink(missing_ok=True)


def _rel(path: str | None) -> str | None:
    """Repository-relative provenance. An absolute path is not custody."""
    if not path:
        return None
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        return None


# ---------------------------------------------------------------------------- #
# run
# ---------------------------------------------------------------------------- #

def _prior_invocations() -> list[dict]:
    """What earlier invocations of --run measured, carried forward.

    A run that is interrupted and resumed computes some folds now and takes the rest from
    the content-addressed cache, so no single invocation's numbers describe what the study
    cost. Dropping the earlier invocation would understate it; counting the cached folds as
    though this process had run them would overstate it. Both are recorded instead, and the
    cumulative figure is the sum of the measured seconds of the folds each invocation
    actually ran -- every fold counted once, in the invocation that computed it.
    """
    if not RESULT.exists():
        return []
    try:
        prior = json.loads(RESULT.read_text()).get("reuse_accounting") or {}
    except json.JSONDecodeError:
        return []
    out = list(prior.get("prior_invocations") or [])
    if prior.get("n_permutation_folds_computed_this_invocation"):
        out.append({
            "n_folds_computed": prior["n_permutation_folds_computed_this_invocation"],
            "n_folds_served_from_cache": prior.get(
                "n_permutation_folds_served_from_cache"),
            "compute_seconds": prior.get("compute_seconds_this_invocation"),
            "wall_clock_seconds": prior.get("wall_clock_seconds_this_invocation"),
            "ended": prior.get("completed_all_planned_folds"),
        })
    return out


def _accounting(rows: list[dict], planned: int, t0: float,
                prior: list[dict] | None = None) -> dict:
    """What this invocation actually computed, kept separate from what it reports.

    The manuscript was caught once overstating its compute by 6.5x, by multiplying a
    per-fold rate by a fold count that included folds served from cache. So compute here is
    the SUM of the measured wall clock of the folds this process really ran, and the
    per-fold mean divides that sum by the number of folds in it -- never by the number of
    rows in the artefact. A reused fold contributes to neither.
    """
    prior = prior or []
    perms = [r for r in rows if r["kind"] != "native"]
    computed = [r for r in perms if r.get("ok") and not r.get("reused")]
    cached = [r for r in perms if r.get("ok") and r.get("reused")]
    failed = [r for r in perms if not r.get("ok")]
    secs = sum(r.get("seconds") or 0.0 for r in computed)
    cum_folds = len(computed) + sum(x["n_folds_computed"] for x in prior)
    cum_secs = secs + sum(x.get("compute_seconds") or 0.0 for x in prior)
    return {
        "n_rows_in_artefact": len(rows),
        "n_native_rows_reused_from_the_gate": sum(1 for r in rows if r["kind"] == "native"),
        "n_permutation_folds_planned": planned,
        "n_permutation_folds_computed_this_invocation": len(computed),
        "n_permutation_folds_served_from_cache": len(cached),
        "n_permutation_folds_failed": len(failed),
        "compute_seconds_this_invocation": round(secs, 1),
        "mean_seconds_per_computed_fold": round(secs / len(computed), 1) if computed else None,
        "wall_clock_seconds_this_invocation": round(time.time() - t0, 1),
        "completed_all_planned_folds": len(computed) + len(cached) + len(failed) == planned,
        "prior_invocations": prior,
        "cumulative_folds_computed_across_invocations": cum_folds,
        "cumulative_compute_seconds": round(cum_secs, 1),
        "cumulative_mean_seconds_per_computed_fold": (round(cum_secs / cum_folds, 1)
                                                      if cum_folds else None),
        "cumulative_wall_clock_seconds": round(
            (time.time() - t0) + sum(x.get("wall_clock_seconds") or 0.0 for x in prior), 1),
        "note": (
            "compute_seconds_this_invocation is the summed measured wall clock of the folds "
            "this process ran. It is NOT a per-fold rate multiplied by a fold count: folds "
            "served from the content-addressed cache and the sixteen native rows reused from "
            "the gate are excluded from both the numerator and the denominator of "
            "mean_seconds_per_computed_fold. Multiplying a rate by folds that were never "
            "computed is how this project once overstated its compute by 6.5x. The first "
            "invocation of this study was killed by the harness at fold 85 of 176; the "
            "cumulative_* figures sum the measured seconds of the folds each invocation "
            "actually ran, so every fold is counted exactly once, in the invocation that "
            "computed it, and a fold served from the cache on resumption is counted in "
            "neither invocation twice nor in this one at all."),
    }


def run() -> None:
    t_start = time.time()
    prior_invocations = _prior_invocations()
    plan = ps.load(STUDY_ID)
    complexes, digest = _load_plan()
    rows: list[dict] = []
    WORK.mkdir(parents=True, exist_ok=True)

    # Reproduction check on one native, so the reused arm is not taken on trust. Registered
    # in advance: if 4XHV moves by more than 0.01 the reused values are discarded and all
    # sixteen natives must be recomputed before any analysis.
    ref = next(c for c in complexes if c["pdb_id"] == REPRO_PDB)
    print(f"reproduction check on {REPRO_PDB} ... ", end="", flush=True)
    t0 = time.time()
    repro = st.run_boltz(
        [st.Chain("A", ref["receptor_seq"], "protein", msa="empty"),
         st.Chain("B", ref["peptide_seq"], "protein", msa="empty")],
        WORK / f"{REPRO_PDB}_native_repro", accelerator="gpu", seed=SEED,
        diffusion_samples=1, recycling_steps=3, timeout=3600, reuse=True)
    _prune(WORK / f"{REPRO_PDB}_native_repro")
    repro_iptm = (repro.get("confidence") or {}).get("iptm")
    delta = None if repro_iptm is None else abs(repro_iptm - ref["gate_iptm"])
    ok_repro = delta is not None and delta <= REPRO_TOLERANCE
    print(f"{time.time() - t0:.1f}s  ipTM={repro_iptm} vs frozen {ref['gate_iptm']:.6f} "
          f"delta={delta} -> {'REPRODUCES' if ok_repro else 'DOES NOT REPRODUCE'}")
    check = {"pdb_id": REPRO_PDB, "frozen_iptm": ref["gate_iptm"],
             "recomputed_iptm": repro_iptm, "delta": delta,
             "tolerance": REPRO_TOLERANCE, "reproduces": ok_repro,
             "reused_from_cache": bool(repro.get("reused")),
             "seconds": round(time.time() - t0, 1),
             "model": _rel((repro.get("files") or {}).get("model")),
             "counted_as_a_scored_fold": False,
             "consequence": ("reused native folds are used as registered" if ok_repro else
                             "registered consequence: the reused values are discarded and all "
                             "natives must be recomputed before analysis")}

    planned_perms = len(complexes) * N_PERM

    def _write() -> None:
        RESULT.write_text(json.dumps({
            "study_id": STUDY_ID,
            "prespec_hash": plan["hash"],
            "boltz_settings": {
                "model": "boltz-2", "version": st.boltz_info().version,
                "msa": "empty (single-sequence)", "accelerator": "gpu",
                "seed": SEED, "diffusion_samples": 1, "recycling_steps": 3,
                "note": ("the gate's settings, so the only thing differing between the two "
                         "arms of this study is the order of the peptide's residues")},
            "permutation_seed": SEED,
            "permutation_generator": _inputs_payload(complexes)["permutation_generator"],
            "sequence_set_sha256": digest,
            "inputs": str(INPUTS.relative_to(REPO)),
            "reproduction_check": check,
            "reuse_accounting": _accounting(rows, planned_perms, t_start, prior_invocations),
            "n_observed": sum(1 for x in rows if x.get("ok")),
            "rows": rows,
        }, indent=1))

    total = len(complexes) * (1 + N_PERM)
    i = 0
    for c in complexes:
        pid, pep = c["pdb_id"], c["peptide_seq"]
        i += 1
        print(f"[{i}/{total}] {pid} native   REUSED   ipTM={c['gate_iptm']:.4f}")
        rows.append({"pdb_id": pid, "split": c["split"], "kind": "native",
                     "sequence": pep, "peptide_len": c["peptide_len"],
                     "receptor_len": c["receptor_len"], "gate_dockq": c["gate_dockq"],
                     "distinct_permutations": c["distinct_permutations"],
                     "ok": True, "reused": True, "seconds": 0.0,
                     "iptm": c["gate_iptm"], "ptm": c["gate_ptm"],
                     "complex_plddt": c["gate_complex_plddt"],
                     # The gate's own coordinate file, carried across so that every row in
                     # this artefact -- reused or computed here -- names the bytes behind its
                     # ipTM directly, rather than deferring to another artefact to do it.
                     "model": c["gate_model"],
                     "source": ("peptide-interface-v1, data/study_peptide_interface.json — "
                                "reused as registered, not recomputed here")})
        for k, perm in enumerate(c["permutations"]):
            i += 1
            kind = f"perm{k}"
            print(f"[{i}/{total}] {pid} {kind:<8s}", end="", flush=True)
            out = WORK / f"{pid}_{kind}"
            t0 = time.time()
            try:
                r = st.run_boltz(
                    [st.Chain("A", c["receptor_seq"], "protein", msa="empty"),
                     st.Chain("B", perm, "protein", msa="empty")],
                    out, accelerator="gpu", seed=SEED,
                    diffusion_samples=1, recycling_steps=3, timeout=3600, reuse=True)
            except Exception as exc:  # noqa: BLE001
                print(f"raised: {str(exc)[:60]}")
                rows.append({"pdb_id": pid, "split": c["split"], "kind": kind,
                             "sequence": perm, "peptide_len": len(perm),
                             "receptor_len": c["receptor_len"],
                             "gate_dockq": c["gate_dockq"], "ok": False,
                             "reused": False, "seconds": round(time.time() - t0, 1),
                             "error": str(exc)[:200]})
                _write()
                continue
            dt = time.time() - t0
            _prune(out)
            conf = r.get("confidence") or {}
            ok = r.get("returncode") == 0 and conf.get("iptm") is not None
            reused = bool(r.get("reused"))
            rec = {"pdb_id": pid, "split": c["split"], "kind": kind,
                   "sequence": perm, "peptide_len": len(perm),
                   "receptor_len": c["receptor_len"], "gate_dockq": c["gate_dockq"],
                   "distinct_permutations": c["distinct_permutations"],
                   "ok": ok, "reused": reused, "seconds": round(dt, 1),
                   "iptm": conf.get("iptm"), "ptm": conf.get("ptm"),
                   "complex_plddt": conf.get("complex_plddt"),
                   "model": _rel((r.get("files") or {}).get("model"))}
            if ok:
                print(f"{dt:6.1f}s  ipTM={rec['iptm']:.4f}"
                      f"{'   (cache)' if reused else ''}")
            else:
                rec["error"] = (r.get("error") or "") + " " + (r.get("stderr_tail") or "")[-150:]
                print(f"{dt:6.1f}s  FAILED")
            rows.append(rec)
            _write()
    _write()
    acct = _accounting(rows, planned_perms, t_start, prior_invocations)
    print(f"\nwrote {RESULT.relative_to(REPO)}")
    print(f"folds computed this invocation: {acct['n_permutation_folds_computed_this_invocation']}"
          f"   served from cache: {acct['n_permutation_folds_served_from_cache']}"
          f"   failed: {acct['n_permutation_folds_failed']}"
          f"   natives reused from the gate: {acct['n_native_rows_reused_from_the_gate']}")
    _mean = acct["mean_seconds_per_computed_fold"]
    print(f"compute {acct['compute_seconds_this_invocation']}s over the folds actually run "
          f"({f'{_mean}s each' if _mean is not None else 'nothing was recomputed'}); "
          f"wall clock {acct['wall_clock_seconds_this_invocation']}s")
    if acct["prior_invocations"]:
        print(f"across {len(acct['prior_invocations']) + 1} invocations: "
              f"{acct['cumulative_folds_computed_across_invocations']} folds computed, "
              f"{acct['cumulative_compute_seconds']}s of compute "
              f"({acct['cumulative_mean_seconds_per_computed_fold']}s each), "
              f"{acct['cumulative_wall_clock_seconds']}s of wall clock")



# ---------------------------------------------------------------------------- #
# analyse
# ---------------------------------------------------------------------------- #

def _sweep_null(observed: int, n_complexes: int, m: int) -> dict:
    from math import comb
    p0 = 1.0 / (m + 1)
    tail = sum(comb(n_complexes, x) * p0 ** x * (1 - p0) ** (n_complexes - x)
               for x in range(observed, n_complexes + 1))
    return {"per_complex_null_probability": round(p0, 4),
            "expected_under_null": round(n_complexes * p0, 3),
            "observed": observed, "p_at_least_observed": round(tail, 5),
            "threshold_registered": H2_MIN_SWEEPS,
            "interpretation": (
                f"with {m} permutations each, a complex sweeps all of them with probability "
                f"{p0:.4f} under the null, so {n_complexes * p0:.2f} of {n_complexes} are "
                f"expected to by chance; observing {observed} has probability {tail:.4f}.")}


def _designed_differences(path: Path) -> list[float]:
    """Per-candidate native-minus-permutation-mean differences from a screen artefact."""
    rows = [r for r in json.loads(path.read_text())["rows"] if r.get("ok")]
    by: dict[str, dict] = {}
    for r in rows:
        d = by.setdefault(r["code"], {"native": None, "decoys": []})
        if r["kind"] == "native":
            d["native"] = r["iptm"]
        else:
            d["decoys"].append(r["iptm"])
    return [d["native"] - statistics.fmean(d["decoys"])
            for d in by.values() if d["native"] is not None and d["decoys"]]


def analyse() -> int:
    from scipy import stats
    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("ok")]
    by: dict[str, dict] = {}
    for r in ok:
        d = by.setdefault(r["pdb_id"], {"native": None, "perms": [], "meta": r})
        if r["kind"] == "native":
            d["native"] = r["iptm"]
            d["meta"] = r
        else:
            d["perms"].append(r["iptm"])

    per, diffs, dropped = [], [], []
    for pid, d in by.items():
        if d["native"] is None or len(d["perms"]) < 5:
            dropped.append({"pdb_id": pid, "n_permutations": len(d["perms"]),
                            "reason": "fewer than 5 usable permutations, dropped as registered"})
            continue
        m = d["meta"]
        pm = statistics.fmean(d["perms"])
        n_ge = sum(1 for x in d["perms"] if x >= d["native"])
        per.append({
            "pdb_id": pid, "split": m.get("split"), "peptide_len": m.get("peptide_len"),
            "receptor_len": m.get("receptor_len"), "gate_dockq": m.get("gate_dockq"),
            "native_iptm": round(d["native"], 4), "n_permutations": len(d["perms"]),
            "permutation_mean": round(pm, 4), "permutation_max": round(max(d["perms"]), 4),
            "difference": round(d["native"] - pm, 4),
            "beats_all_permutations": all(d["native"] > x for x in d["perms"]),
            "empirical_p": round((1 + n_ge) / (len(d["perms"]) + 1), 4),
            "log10_distinct_permutations": round(
                math.log10(m["distinct_permutations"]), 2) if m.get(
                    "distinct_permutations") else None,
        })
        diffs.append(d["native"] - pm)
    per.sort(key=lambda x: -x["difference"])

    t_p, dz = None, None
    if len(diffs) >= 3 and statistics.pstdev(diffs) > 0:
        t_p = float(stats.ttest_1samp(diffs, 0.0).pvalue)
        dz = statistics.fmean(diffs) / statistics.stdev(diffs)

    designed = _designed_differences(SCREEN)
    w = stats.ttest_ind(diffs, designed, equal_var=False)
    w_p = float(w.pvalue)
    designed_msa = _designed_differences(MSA_SCREEN)

    def _stratum(pred) -> dict:
        sel = [p["difference"] for p in per if pred(p)]
        return {"n": len(sel), "mean_difference": round(statistics.fmean(sel), 4) if sel else None}

    n_sweeps = sum(1 for p in per if p["beats_all_permutations"])
    mean_diff = statistics.fmean(diffs) if diffs else 0.0
    contrast = mean_diff - (statistics.fmean(designed) if designed else 0.0)

    ruling = inf.decide(
        criteria={"H2_the_null_discriminates_case_by_case": inf.Criterion(
            n_sweeps >= H2_MIN_SWEEPS, n_sweeps,
            f"at least {H2_MIN_SWEEPS} of {len(per)} complexes beat all "
            f"{N_PERM} of their own permutations")},
        tests={k: v for k, v in (
            ("H1_natural_peptides_separate_from_their_permutations", t_p),
            ("H3_natural_separation_exceeds_designed", w_p)) if v is not None and 0.0 < v <= 1.0})
    # Two-sided tests: a significant effect in the wrong direction must not confirm a
    # directional hypothesis, and a test that could not be computed is FALSIFIED, not absent.
    if mean_diff <= 0 or "H1_natural_peptides_separate_from_their_permutations" not in ruling["verdicts"]:
        ruling["verdicts"]["H1_natural_peptides_separate_from_their_permutations"] = "FALSIFIED"
    if contrast <= 0 or "H3_natural_separation_exceeds_designed" not in ruling["verdicts"]:
        ruling["verdicts"]["H3_natural_separation_exceeds_designed"] = "FALSIFIED"

    report = {
        "study_id": STUDY_ID, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(ok), "primary_metric": "paired_native_minus_permutation_mean",
        "metrics": {
            "paired_native_minus_permutation_mean": round(mean_diff, 4),
            "mean_native_iptm": round(statistics.fmean(
                [p["native_iptm"] for p in per]), 4) if per else None,
            "mean_permutation_iptm": round(statistics.fmean(
                [p["permutation_mean"] for p in per]), 4) if per else None,
            "cohens_dz": round(dz, 4) if dz is not None else None,
            "per_complex_empirical_p": {p["pdb_id"]: p["empirical_p"] for p in per},
            "n_complexes_beating_all_permutations": n_sweeps,
            "beats_all_permutations_null": _sweep_null(n_sweeps, len(per), N_PERM),
            "paired_difference_by_dockq_stratum": {
                "gate_dockq_acceptable": _stratum(
                    lambda p: (p["gate_dockq"] or 0) >= DOCKQ_ACCEPTABLE),
                "gate_dockq_incorrect": _stratum(
                    lambda p: (p["gate_dockq"] or 0) < DOCKQ_ACCEPTABLE),
                "note": "registered descriptive stratification; carries no verdict",
            },
            "paired_difference_by_split": {
                "pre_cutoff": _stratum(lambda p: p["split"] == "pre_cutoff"),
                "post_cutoff": _stratum(lambda p: p["split"] == "post_cutoff"),
                "note": "registered descriptive stratification; carries no verdict",
            },
            "log10_distinct_permutations": {
                p["pdb_id"]: p["log10_distinct_permutations"] for p in per},
            "natural_minus_designed_contrast": {
                "natural_mean": round(mean_diff, 4),
                "designed_mean_candidate_screen_v8": round(statistics.fmean(designed), 4),
                "contrast": round(contrast, 4),
                "n_natural": len(diffs), "n_designed": len(designed),
                "welch_p": round(w_p, 5)},
            "contrast_vs_msa_specificity_v9": {
                "designed_mean_msa_arm": round(statistics.fmean(designed_msa), 4),
                "n_designed": len(designed_msa),
                "contrast": round(mean_diff - statistics.fmean(designed_msa), 4),
                "note": ("registered sensitivity comparison, not a test: that arm used the "
                         "MSA server, so it differs from this study in alignment mode as "
                         "well as in sequence set")},
            "per_complex": per,
            "native_fold_reproduction_check": payload.get("reproduction_check"),
            "wall_clock_seconds_per_fold": inf.wall_clock(ok),
        },
        "paired_t_p": round(t_p, 5) if t_p is not None else None,
        "welch_p": round(w_p, 5),
        **ruling,
        "permutation_seed": payload.get("permutation_seed"),
        "permutation_generator": payload.get("permutation_generator"),
        "sequence_set_sha256": payload.get("sequence_set_sha256"),
        "boltz_settings": payload.get("boltz_settings"),
        "reuse_accounting": payload.get("reuse_accounting"),
        "dropped_complexes": dropped,
        "failures": [{"pdb_id": r.get("pdb_id"), "kind": r.get("kind"),
                      "error": str(r.get("error"))[:150]}
                     for r in payload["rows"] if not r.get("ok")],
    }
    report["prespec_audit"] = ps.verify_result(STUDY_ID, report)
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 100)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   "
          f"{len(per)} complexes, {len(ok)} folds")
    print("=" * 100)
    print(f"\nPRIMARY  mean paired (native - own permutation mean) = "
          f"{m['paired_native_minus_permutation_mean']}   paired t p = {report['paired_t_p']}"
          f"   Cohen's dz = {m['cohens_dz']}")
    print(f"\n{'pdb':6s} {'split':11s} {'len':>4s} {'native':>8s} {'perm mn':>8s} "
          f"{'perm mx':>8s} {'diff':>8s} {'emp p':>6s} {'DockQ':>6s} sweeps")
    for p in per:
        print(f"{p['pdb_id']:6s} {str(p['split']):11s} {p['peptide_len']:4d} "
              f"{p['native_iptm']:8.4f} {p['permutation_mean']:8.4f} "
              f"{p['permutation_max']:8.4f} {p['difference']:+8.4f} "
              f"{p['empirical_p']:6.3f} {p['gate_dockq']:6.3f} "
              f"{'YES' if p['beats_all_permutations'] else 'no'}")
    print("\n  " + m["beats_all_permutations_null"]["interpretation"])
    c = m["natural_minus_designed_contrast"]
    print(f"\nCONTRAST  natural {c['natural_mean']} (n={c['n_natural']}) vs designed "
          f"{c['designed_mean_candidate_screen_v8']} (n={c['n_designed']})  = "
          f"{c['contrast']}   Welch p = {c['welch_p']}")
    # The COST of the study is the cumulative figure, not the last invocation's: a rerun
    # served entirely from cache computes nothing, and printing that as the study's compute
    # would understate it exactly as badly as multiplying a rate by cached folds overstates
    # it. Both the cumulative total and what this invocation did are shown.
    acct = report.get("reuse_accounting") or {}
    if acct:
        print(f"\nFOLDS  {acct['cumulative_folds_computed_across_invocations']} of "
              f"{acct['n_permutation_folds_planned']} permutation folds computed across "
              f"{len(acct.get('prior_invocations') or []) + 1} invocation(s), "
              f"{acct['n_permutation_folds_failed']} failed; "
              f"{acct['n_native_rows_reused_from_the_gate']} natives reused from the gate "
              "and not recomputed.")
        print(f"       compute {acct['cumulative_compute_seconds']}s "
              f"({acct['cumulative_mean_seconds_per_computed_fold']}s per computed fold), "
              f"wall clock {acct['cumulative_wall_clock_seconds']}s. This invocation "
              f"computed {acct['n_permutation_folds_computed_this_invocation']} and took "
              f"{acct['n_permutation_folds_served_from_cache']} from the cache.")
    print("\nPRE-SPECIFIED VERDICTS")
    print(inf.format_verdicts(report))
    if report["dropped_complexes"]:
        print(f"\nDROPPED: {report['dropped_complexes']}")
    if report["failures"]:
        print(f"\nFAILURES: {len(report['failures'])}")
    a = report["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 100)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    for f in ("register", "fetch", "run", "analyse"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    if a.register:
        spec = build_prespec(*prespec_args())
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        print(f"registered {spec.register().relative_to(REPO)}")
        print(f"  hash {spec.hash()}")
        print(f"  {len(REUSED_NATIVES)} complexes x {1 + N_PERM} = {spec.n_planned} folds "
              f"({len(REUSED_NATIVES) * N_PERM} new, {len(REUSED_NATIVES)} reused)")
        print(f"  min attainable adjusted p = {spec.min_attainable_p():.4g} "
              f"(primary test is parametric; the per-complex empirical p floors at "
              f"{1 / (N_PERM + 1):.4f})")
        return 0
    if a.fetch:
        fetch()
        return 0
    if a.run:
        run()
        return 0
    if a.analyse:
        return analyse()
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
