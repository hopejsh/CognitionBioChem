#!/usr/bin/env python3
"""Study #9: the candidate screen, against composition-matched decoys.

This is the study the whole platform was built to make possible, and it could not be run
honestly until study #7 measured whether the pipeline has any sensitivity. That gate is now
OPEN: #7 recovered 7 of 8 memorisable peptide interfaces (DockQ >= 0.23) and established that
ipTM tracks interface correctness at Spearman rho = 0.800, with ZERO false negatives below
ipTM 0.6.

RETRACTION. This docstring used to continue: "So a low score here is evidence about the
candidate rather than about the method." Study #12 (interface-null-positive-control-v1)
falsified that: the same 16 deposited X-ray complexes, all established binders, were folded
against ten uniform random permutations of each peptide, and only 4 of 16 beat all ten of
their own permutations against a threshold of 5 registered in advance. Losing this comparison
is what most demonstrated binders do here, so a low score is NOT evidence about the candidate
in that sense. #12 confirmed the aggregate form only (+0.0895 ipTM, Holm p = 0.0148, 13 of 16
positive), so the per-candidate columns this study emits are descriptive and carry no verdict
on any candidate.

The design point is that a raw ipTM has no reference distribution. These candidates are
Arg/Trp-rich cationic amphipathic peptides, the sequence class most prone to promiscuous
scoring, so the only construct that separates "this design binds" from "peptides of this
composition score this way against this receptor" is a per-candidate null built from
composition-matched shuffles. A pilot during the idea panel found a random shuffle scoring
ipTM 0.735 — higher than any native replicate — which in isolation would have read as a hit.

Each shuffle preserves the exact residue multiset, so length, net charge, isoelectric point
and GRAVY are identical to the native by construction; only the order changes.

    ./.venv/bin/python platform/studies/candidate_screen.py --register
    ./.venv/bin/python platform/studies/candidate_screen.py --run
    ./.venv/bin/python platform/studies/candidate_screen.py --analyse
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import inference as inf, prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "candidate-screen-v8"
REGISTRY = REPO / "data" / "target_registry.json"
RAW = REPO / "data" / "extracted_raw.json"
WORK = Path("/tmp/cbc_screen")
RESULT = REPO / "data" / "study_candidate_screen.json"

N_DECOYS = 3
SEED = 1

#: Calibration from study #7, measured on 16 peptide-receptor complexes.
IPTM_FAILED_BAND = 0.6      # 0 of 4 complexes below this were correct
IPTM_CONFIDENT = 0.8        # 9 of 10 above this were correct

#: Which registry target each candidate names. Only candidates whose receptor is in the
#: registry and is extracellular are screened: an intracellular target cannot be reached by
#: a peptide with no penetrating mechanism, and predicting that complex would answer a
#: question the biology has already settled.
CANDIDATE_TARGETS = {
    "HippoAChE-AlkaPept-X2": "ACHE",
    "BasalAChE-GorgeBlock-B1": "ACHE",
    "BasalAChE-Abeta-B4": "ACHE",
    "BasalSuper-AChE-TrkA-B5": "ACHE",
    "HippoTrk-Saponin-X1": "NTRK2",
    "PfcTrk-ErkEnhancer-P2": "NTRK2",
    "BasalNgf-TrkA-B3": "NTRK1",
    "MicroTrem2-Agonist-M1": "TREM2",
    "MicroTlr4-Antagonist-M3": "TLR4",
    "PfcACh-PAM-P1": "CHRNA7",
    # Added after coverage() showed the stated criterion admits them while the
    # hand-written map did not. MicroDual-Trem2-Nrf2-M5 also names Keap1, which is
    # cytoplasmic and unreachable; it is screened against the reachable half.
    "HippoDual-TrkB-AMPK-X5": "NTRK2",
    "MicroDual-Trem2-Nrf2-M5": "TREM2",
    # Added after the short-circuit was removed and the criterion applied uniformly.
    # A candidate naming several admissible targets is screened against the
    # alphabetically first, deterministically, and coverage() records the others as
    # declared-but-untested rather than letting the choice go unstated.
    "PfcGluN2A-LTP-P3": "GRIN2A",
    "PfcDual-nACh-GluN2A-P5": "CHRNA7",
}


#: Aliases the raw catalogue uses for each registry target, for deriving coverage.
_TARGET_ALIASES = {
    "ACHE": ("AChE", "acetylcholinesterase"), "NTRK1": ("TrkA",), "NTRK2": ("TrkB",),
    "TREM2": ("Trem2", "TREM2"), "TLR4": ("TLR4",), "CHRNA7": ("nAChR", "α7", "alpha-7"),
    "GRIN2A": ("GluN2A",), "GRIN2B": ("GluN2B",), "FZD8": ("Frizzled", "FZD8", "Fzd"),
    "KEAP1": ("Keap1",), "NFE2L2": ("Nrf2",), "GSK3B": ("GSK-3", "GSK3"),
    "SLC1A2": ("EAAT2",), "NOS3": ("eNOS",), "PTAFR": ("PAFR",), "CHRM1": ("M1",),
}


def coverage() -> dict:
    """Which valid-sequence candidates the stated criterion admits, and why the rest are out.

    CANDIDATE_TARGETS is hand-written, so a headline like "nine out of nine" was certified by
    the map rather than by the criterion it claims to apply, and could not be false by
    construction. This re-derives the population from the catalogue and the registry, so the
    exclusions are visible and each carries its reason.
    """
    reg = json.loads(REGISTRY.read_text())["targets"]
    raw = json.loads(RAW.read_text())
    screened, excluded = [], []
    for d in raw["FULL_BRAIN_DRUGS_DATA"]:
        code, seq = d["code"], d.get("sequence", "")
        if not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]{5,}", seq):
            continue
        # NO SHORT-CIRCUIT ON THE MAP. An earlier version admitted anything already in
        # CANDIDATE_TARGETS without testing it, so the criterion only ever governed
        # exclusions and the inclusion half stayed hand-listed -- which is the defect this
        # function was written to remove, surviving in the half that matters.
        blob = " ".join(str(d.get(k, "")) for k in ("targets", "bindingSites", "mechanism"))
        named = sorted({sym for sym, al in _TARGET_ALIASES.items()
                        if any(a.lower() in blob.lower() for a in al)})
        if not named:
            excluded.append({"code": code, "reason": "names no target in the registry"})
            continue
        reasons, admissible = [], []
        for sym in named:
            t = reg.get(sym, {})
            if t.get("construct_basis") is None:
                reasons.append(f"{sym}: ligand site is inside the membrane bundle; no "
                               "soluble-phase construct exists")
            elif sym in _INTRACELLULAR:
                reasons.append(f"{sym}: cytoplasmic; a peptide with no penetrating mechanism "
                               "cannot reach it")
            else:
                admissible.append(sym)
                reasons.append(f"{sym}: admissible ({t['construct_basis']}, "
                               f"{t['ligand_accessible_span'][1] - t['ligand_accessible_span'][0] + 1} aa)")
        rec = {"code": code, "named": named, "reasons": reasons,
               "admissible_targets": admissible,
               "mapped_to": CANDIDATE_TARGETS.get(code),
               "declared_but_untested": [a for a in admissible
                                         if a != CANDIDATE_TARGETS.get(code)]}
        if admissible and code in CANDIDATE_TARGETS:
            screened.append(code)
        else:
            excluded.append(rec)

    unscreened = [e for e in excluded if e.get("admissible_targets")]
    return {"screened": sorted(screened), "excluded": excluded,
            "admissible_but_unscreened": [e["code"] for e in unscreened],
            "n_admissible_but_unscreened": len(unscreened),
            "note": ("Oligomeric state is RECORDED in the registry and disclosed in the README, "
                     "but is not used to exclude: a keyword scan over a SUBUNIT comment cannot "
                     "establish whether a given binding site lies at a subunit interface, and "
                     "using it that way excluded CHRNA7 and TLR4 -- both primarily homomers -- "
                     "while the map screened them anyway. Exclusion rests only on grounds the "
                     "code can establish: no soluble-phase construct, or a cytoplasmic "
                     "compartment.")}


#: Registry targets that live in the cytosol or nucleus.
_INTRACELLULAR = {"KEAP1", "NFE2L2", "GSK3B", "NOS3"}


def _receptor_seq(symbol: str) -> str | None:
    """The receptor surface a soluble peptide can physically reach, or None to refuse.

    This used to return the mature chain, which was wrong for every membrane receptor in the
    registry. The mature chain of a single-pass receptor also contains its transmembrane
    helix and cytoplasmic tail — for TREM2 that is 56 of 212 residues (26%), for CHRNA7 269
    of 480 (56%). Folded in isolation those segments are solvent-exposed hydrophobic surface,
    which is exactly what a structure predictor will dock a hydrophobic peptide onto; in the
    cell they are inside the bilayer or on the far side of it, so the contact cannot form.
    The construct therefore scored an interface that does not exist, and it did so in the
    direction that inflates the score for the least specific candidates.

    The span comes from the UniProt Topological-domain and Transmembrane features, recorded
    per target in the registry. A target whose ligand site lies inside the membrane bundle
    (GPCR, transporter) returns None: no soluble-phase construct of it is valid, and refusing
    is the correct answer rather than folding a loop.
    """
    reg = json.loads(REGISTRY.read_text())
    t = reg["targets"].get(symbol)
    if not t or t.get("construct_basis") is None:
        return None
    span = t["ligand_accessible_span"]
    return t["sequence"][span[0] - 1:span[1]]


def _construct_note(symbol: str) -> dict:
    """Provenance for the construct, so a reader can see which residues were folded."""
    t = json.loads(REGISTRY.read_text())["targets"][symbol]
    span = t["ligand_accessible_span"]
    return {"uniprot": t["uniprot"], "basis": t["construct_basis"],
            "canonical_span": span, "length": span[1] - span[0] + 1,
            "convention": "canonical (counts from the initiator methionine)"}


def _candidates(limit: int | None = None) -> list[dict]:
    raw = json.loads(RAW.read_text())
    out = []
    for d in raw["FULL_BRAIN_DRUGS_DATA"]:
        code, seq = d["code"], d.get("sequence", "")
        if code not in CANDIDATE_TARGETS:
            continue
        if not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]{5,}", seq):
            continue
        sym = CANDIDATE_TARGETS[code]
        rseq = _receptor_seq(sym)
        if not rseq:
            continue
        out.append({"code": code, "peptide": seq, "target": sym,
                    "receptor_len": len(rseq), "construct": _construct_note(sym)})
    out.sort(key=lambda c: c["receptor_len"])   # cheapest first

    # One (peptide, target) pair appears under two codes: HippoAChE-AlkaPept-X2 and
    # BasalAChE-GorgeBlock-B1 carry the identical 36-mer against the identical AChE construct,
    # which is one of the duplicate pairs the data gate flags. Screening both counts one
    # molecule twice, and because every downstream statistic is an average or a count over
    # candidates, the duplicate votes twice in all of them: in study #10 it moved the paired
    # mean difference from -0.0221 to -0.0412 and Cohen's dz from -0.117 to -0.220, roughly
    # doubling the reported effect, while overstating the t-test's df by one. It is also the
    # most extreme negative difference in the set, so it does not merely add noise.
    #
    # De-duplicating on (peptide, target) keeps the first code and records the alias, so the
    # design is still visible in the output but is counted once.
    deduped: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    for c in out:
        key = (c["peptide"], c["target"])
        first = by_key.get(key)
        if first is None:
            by_key[key] = c
            deduped.append(c)
        else:
            first.setdefault("identical_to", []).append(c["code"])
    out = deduped
    return out if limit is None else out[:limit]


def _scrambles(seq: str, n: int, seed: int) -> list[str]:
    """Composition-matched shuffles: identical residue multiset, different order."""
    rng = random.Random(seed)
    out, seen = [], {seq}
    while len(out) < n:
        chars = list(seq)
        rng.shuffle(chars)
        s = "".join(chars)
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out



def peptide_multiplicity(rows: list[dict], codes=None) -> dict:
    """How many DISTINCT PEPTIDES the screened constructs cover.

    De-duplication in `_candidates()` is applied on `(peptide, target)`. That is the right
    key for the question "is this fold already computed", and the wrong one for the question
    "how many molecules is this a screen of": a single peptide aimed at two receptors
    survives as two constructs, and every mean and count downstream is taken over
    constructs. `PfcACh-PAM-P1` (CHRNA7) and `MicroTlr4-Antagonist-M3` (TLR4) carry the
    identical 41-mer, so thirteen screened constructs cover twelve distinct peptides. The
    two rows do not merely share a native: their whole decoy arm is the same eleven
    sequences at the same seed, folded against two different receptors — which is what
    `decoy_arms_identical` records, from the rows rather than from this sentence.

    This is the same harm the screen already documents for the AChE pair
    (`HippoAChE-AlkaPept-X2` / `BasalAChE-GorgeBlock-B1`), where the duplicate "voted twice
    in all of them ... roughly doubling the reported effect". That pair collapses under the
    `(peptide, target)` key because both name ACHE. This one does not, and it went uncounted
    for exactly that reason.

    Nothing here changes a registered statistic. It records the population as it is, so
    prose has an artefact to source "13 constructs, 12 distinct peptides" to, and so
    `shared_peptide_sensitivity()` has the groups to recompute over.
    """
    want = set(codes) if codes is not None else None
    seq: dict[str, str] = {}
    target: dict[str, str] = {}
    arms: dict[str, dict[str, str]] = {}
    for r in rows:
        if not r.get("ok"):
            continue
        if want is not None and r["code"] not in want:
            continue
        arms.setdefault(r["code"], {})[r["kind"]] = r.get("peptide_used")
        if r["kind"] != "native":
            continue
        seq[r["code"]] = r["peptide"]
        target[r["code"]] = r["target"]

    by_seq: dict[str, list[str]] = {}
    for code in sorted(seq):
        by_seq.setdefault(seq[code], []).append(code)

    groups = []
    for s, g in sorted(by_seq.items(), key=lambda kv: kv[1][0]):
        if len(g) < 2:
            continue
        groups.append({
            "peptide_length": len(s),
            "peptide_sha256_12": hashlib.sha256(s.encode()).hexdigest()[:12],
            "codes": [{"code": c, "target": target[c]} for c in g],
            # Whether the two constructs also share every decoy. They do: the shuffles are
            # generated from the sequence at a fixed seed, so an identical sequence gives an
            # identical decoy set. The arms are therefore the same peptides against
            # different receptors, not two independent draws of a design.
            "decoy_arms_identical": all(arms[g[0]] == arms[c] for c in g[1:]),
        })

    n_constructs, n_distinct = len(seq), len(by_seq)
    return {
        "n_constructs": n_constructs,
        "n_distinct_peptides": n_distinct,
        "deduplication_key": "(peptide, target)",
        "shared_sequence_groups": groups,
        "note": (
            f"{n_constructs} candidate-receptor constructs cover {n_distinct} distinct "
            f"peptides. De-duplication is applied on (peptide, target), so one peptide "
            f"declared against two receptors is screened, and counted, twice. Every mean "
            f"and count in this study is taken over constructs, so a shared peptide votes "
            f"once per construct; see metrics.shared_peptide_sensitivity for what each "
            f"headline becomes when it votes once."
            if groups else
            f"{n_constructs} constructs, {n_distinct} distinct peptides: no sequence is "
            f"screened against more than one receptor."),
    }


def counted_once_variants(multiplicity: dict, codes) -> list[dict]:
    """Every way of keeping one construct per distinct peptide.

    With one shared pair there are two: keep the CHRNA7 fold or keep the TLR4 fold. Which
    one to keep is not a question the data answers — the two differ by which receptor the
    same peptide was folded against — so both are reported rather than one being chosen.
    """
    groups = multiplicity.get("shared_sequence_groups") or []
    if not groups:
        return []
    members = [[c["code"] for c in g["codes"]] for g in groups]
    out = []
    for keep in itertools.product(*members):
        dropped = sorted(set(c for g in members for c in g) - set(keep))
        out.append({
            "keeps": sorted(keep),
            "drops": dropped,
            "codes": [c for c in codes if c not in dropped],
        })
    return out


def _shared_peptide_sensitivity(per: list[dict], mult: dict) -> dict | None:
    """This study's headlines, recomputed with each shared peptide counted once.

    Registered nothing, replaces nothing. The three verdicts are decided by pre-specified
    thresholds on the values reported in `metrics`, and those stay exactly as computed; this
    records how far each of them sits from the line once a molecule that holds two
    constructs stops voting twice.
    """
    variants = counted_once_variants(mult, [p["code"] for p in per])
    if not variants:
        return None
    by = {p["code"]: p for p in per}

    def stat(codes: list[str]) -> dict:
        rows = [by[c] for c in codes]
        nat = [r["native_iptm"] for r in rows]
        dec = [x for r in rows for x in r["decoy_iptm"]]
        beat = sum(1 for r in rows if r["beats_all_decoys"])
        below = sum(1 for v in nat if v < IPTM_FAILED_BAND)
        return {
            "n_constructs": len(rows),
            "fraction_candidates_beating_null": round(beat / len(rows), 4),
            "mean_native_iptm": round(statistics.fmean(nat), 4),
            "mean_decoy_iptm": round(statistics.fmean(dec), 4),
            "native_minus_decoy_mean": round(
                statistics.fmean(nat) - statistics.fmean(dec), 4),
            "n_candidates_above_0.8": sum(1 for v in nat if v > IPTM_CONFIDENT),
            "n_candidates_below_0.6": below,
            "H1_any_candidate_binds": (
                "FALSIFIED" if not any(r["beats_all_decoys"]
                                       and r["native_iptm"] > IPTM_CONFIDENT
                                       for r in rows) else "CONFIRMED"),
            "H2_natives_beat_decoys_on_average": (
                "CONFIRMED" if statistics.fmean(nat) - statistics.fmean(dec) > 0.1
                else "FALSIFIED"),
            "H3_candidates_in_failed_band": (
                "CONFIRMED" if below >= len(rows) / 2 else "FALSIFIED"),
        }

    counted_once = {("drop " + ", ".join(v["drops"])): stat(v["codes"]) for v in variants}
    as_reported = stat([p["code"] for p in per])
    moved = sorted({k for k in ("H1_any_candidate_binds",
                                "H2_natives_beat_decoys_on_average",
                                "H3_candidates_in_failed_band")
                    if any(v[k] != as_reported[k] for v in counted_once.values())})
    spread = [v["native_minus_decoy_mean"] for v in counted_once.values()]
    return {
        "as_reported": as_reported,
        "counted_once": counted_once,
        "verdicts_that_move": moved,
        "interpretation": (
            f"{as_reported['n_constructs']} screened constructs cover "
            f"{mult['n_distinct_peptides']} distinct peptides, so every mean and count "
            f"above is taken over a set in which one peptide appears twice. Counting it "
            f"once moves the mean native-minus-decoy difference from "
            f"{as_reported['native_minus_decoy_mean']:+.4f} to "
            f"{min(spread):+.4f}/{max(spread):+.4f} depending on which receptor's fold is "
            f"kept. "
            + ("No registered verdict changes at any of those choices."
               if not moved else
               f"These verdicts change: {', '.join(moved)}.")),
    }


def prespec_args() -> tuple:
    """The arguments --register builds the plan with.

    Named once so the registration path and the hash-stability test cannot disagree
    about them: the test previously guessed, guessed wrong for the two-argument
    studies, and reported drift that did not exist.
    """
    c = _candidates()
    return (len(c) * (1 + N_DECOYS), len(c))

def build_prespec(n_folds: int, n_cand: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "For each platform candidate predicted together with its declared receptor, is "
            "the interface distinguishable from what the same model at the same settings "
            "assigns to a sequence of identical amino-acid composition in random order?"),
        primary_metric="fraction_candidates_beating_null",
        primary_metric_justification=(
            "The fraction of candidates whose native ipTM exceeds every one of its own "
            "composition-matched decoys is the right primary metric because it is the only "
            "quantity here with a reference distribution. A raw ipTM has none, and these "
            "candidates are Arg/Trp-rich cationic amphipathic peptides — the class most "
            "prone to scoring well against anything — so an absolute threshold would measure "
            "composition rather than design. Using a per-candidate null also makes the "
            "verdict robust to the receptor: each candidate is compared only against "
            "sequences of its own composition against its own target. A pilot found a random "
            "shuffle scoring ipTM 0.735, above every native replicate, which in isolation "
            "would have read as a hit."),
        decision_threshold=(
            "H1 confirmed if any candidate's native ipTM exceeds all of its decoys AND "
            "reaches the confident band ipTM > 0.8; H2 confirmed if the mean native ipTM "
            "exceeds the mean decoy ipTM by more than 0.1; H3 confirmed if at least half the "
            "candidates fall below ipTM 0.6, the band in which study #7 found 0 of 4 "
            "interfaces correct."),
        n_planned=n_folds,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed: each candidate is predicted once with its receptor and once with each of "
            "3 composition-matched decoys, all at seed 1, in a fixed order. No candidate, "
            "decoy or receptor is added or removed after the first prediction. Technical "
            "failures are recorded and excluded with the reason stated."),
        analysis_plan=(
            "For each candidate, build 3 composition-matched shuffles with a fixed RNG seed. "
            "Predict the receptor LIGAND-ACCESSIBLE CONSTRUCT plus each peptide with Boltz-2 "
            "2.2.1 — the extracellular topological domain for a membrane receptor, the "
            "mature chain for a soluble one, in both cases with obligate-assembly "
            "segments excluded (an isoform-variable terminal span carrying an "
            "interchain disulfide), refusing targets whose ligand site lies inside "
            "the membrane bundle — "
            "msa=empty, gpu, seed 1, diffusion_samples 1, recycling_steps 3. Record ipTM, "
            "pTM and complex_plddt. For each candidate report whether the native ipTM "
            "exceeds all its decoys, the native-minus-decoy-mean difference, and the "
            "empirical p = (1 + #{decoy >= native}) / (N + 1). Interpret levels against "
            "study #7's calibration bands. Holm across the three hypotheses."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_any_candidate_binds",
                statement=("At least one candidate produces an interface both better than "
                           "its composition-matched null and confident in absolute terms."),
                predicted_by="the platform's original claim that these are targeted binders",
                confirmed_if=("some candidate has native ipTM above all its decoys AND "
                              "native ipTM > 0.8"),
                falsified_if="no candidate satisfies both conditions"),
            ps.Hypothesis(
                name="H2_natives_beat_decoys_on_average",
                statement=("Even without any individual candidate succeeding, the designed "
                           "sequences score better on average than their shuffles, which "
                           "would indicate the design contains some real information."),
                predicted_by="a weaker version of the platform's claim",
                confirmed_if="mean native ipTM exceeds mean decoy ipTM by more than 0.1",
                falsified_if="the difference is 0.1 or less"),
            ps.Hypothesis(
                name="H3_candidates_in_failed_band",
                statement=("Most candidates fall in the ipTM band where study #7 measured "
                           "no correct interfaces, so the screen returns a negative."),
                predicted_by=("the pilot, where the flagship AChE candidate scored ipTM "
                              "0.21-0.47 across replicates"),
                confirmed_if="at least half the candidates have native ipTM < 0.6",
                falsified_if="fewer than half fall below 0.6"),
        ),
        secondary_metrics=(
            "mean_native_iptm", "mean_decoy_iptm", "per_candidate_empirical_p",
            "n_candidates_above_0.8", "n_candidates_below_0.6", "native_minus_decoy_mean",
            "wall_clock_seconds_per_fold",
        ),
        exclusions=(
            f"All {n_cand} candidates admitted by coverage(), which resolves every "
            "valid-sequence candidate in the catalogue against the target registry and "
            "records the ground for each inclusion and exclusion in the artefact. A "
            "candidate is excluded when EVERY target it declares is unreachable: either the "
            "registry admits no soluble-phase construct for it (a GPCR or transporter, whose "
            "ligand site lies inside the membrane bundle) or the target is cytoplasmic and a "
            "peptide with no cell-penetrating mechanism cannot reach it. A candidate naming "
            "BOTH a reachable and an unreachable target is screened against the reachable "
            "one, with the others recorded as declared-but-untested -- not excluded. "
            "Oligomeric state is recorded but does not exclude: a keyword scan over a UniProt "
            "SUBUNIT comment cannot establish whether a binding site lies at a subunit "
            "interface. Sequences containing non-standard residues are excluded."),
        supersedes="candidate-screen-v7",
        supersedes_reason=(
            "v7 registered an exclusions clause that did not describe what the code does. It read as if a candidate naming several targets were excluded, whereas coverage() screens such a candidate against its reachable target and records the unreachable ones as declared-but-untested; it also still implied the oligomeric flag was an exclusion ground after that had been withdrawn. The text was corrected AFTER v7 had already been executed, which would have meant editing a hash-locked plan in place -- the registry rejected it by refusing to resolve a study with two plans, which is the guard working. v8 carries the corrected wording. No candidate, arm, threshold or decision rule changes; the 52 folds are reused after each stored model is re-parsed and checked against the chains its own input requested."),
        known_confounds=(
            "1. Single-sequence mode depresses all arms equally; the native-versus-decoy "
            "CONTRAST is the interpretable quantity, not the absolute level. 2. Three decoys "
            "give a minimum empirical p of 0.25, so no individual candidate can reach "
            "significance — the design tests the SET, and per-candidate p values are "
            "descriptive only. This is stated in advance rather than discovered afterwards. "
            "4. STUDY #7'S BANDS ARE AN EXTRAPOLATION HERE, AND ARE LABELLED AS ONE. #7 calibrated ipTM against DockQ on 16 complexes whose peptides were 7-17 residues and whose receptors were 80-304. These candidates are 31-47 residues, longer than anything #7 measured, on receptors of 156-608. No candidate lies inside the calibrated peptide range, and only TREM2 (156 aa) and CHRNA7 (211 aa) lie inside the calibrated receptor range. The absolute thresholds in H1 and H3 are therefore extrapolated, and every verdict that rests on them is reported as extrapolated rather than calibrated. The primary metric does not depend on them: the native-versus-decoy contrast is a within-candidate comparison whose reference distribution is generated inside this study. "
            "3. Composition-matched shuffling preserves charge and hydrophobicity but not "
            "secondary-structure propensity, so a helical native competes against shuffles "
            "that may not be helical; this makes the test conservative in the native's "
            "favour. 4. A negative result bounds what THIS pipeline detects at THIS "
            "configuration, not what the molecules do in a cell."),
    )


def run() -> None:
    plan = ps.load(STUDY_ID)
    cands = _candidates(limit=None)
    rows: list[dict] = []
    total = len(cands) * (1 + N_DECOYS)
    i = 0
    for c in cands:
        rseq = _receptor_seq(c["target"])
        variants = [("native", c["peptide"])] + [
            (f"decoy{k}", s) for k, s in enumerate(_scrambles(c["peptide"], N_DECOYS, SEED))]
        for kind, pep in variants:
            i += 1
            print(f"[{i}/{total}] {c['code'][:26]:28s} {kind:7s} vs {c['target']:7s} ",
                  end="", flush=True)
            t0 = time.time()
            try:
                r = st.run_boltz(
                    [st.Chain("A", rseq, "protein", msa="empty"),
                     st.Chain("B", pep, "protein", msa="empty")],
                    WORK / f"{c['code']}_{kind}", accelerator="gpu", seed=SEED,
                    diffusion_samples=1, recycling_steps=3, timeout=5400, reuse=True)
            except Exception as exc:  # noqa: BLE001
                print(f"raised: {str(exc)[:50]}")
                rows.append({**c, "kind": kind, "peptide_used": pep, "ok": False,
                             "error": str(exc)[:200]})
                continue
            dt = time.time() - t0
            conf = r.get("confidence") or {}
            reused = bool(r.get("reused"))
            ok = r.get("returncode") == 0 and conf.get("iptm") is not None
            rec = {**c, "kind": kind, "peptide_used": pep, "ok": ok,
                   "seconds": round(dt, 1), "reused": reused, "iptm": conf.get("iptm"),
                   "ptm": conf.get("ptm"), "complex_plddt": conf.get("complex_plddt")}
            if ok:
                print(f"{dt:6.1f}s  ipTM={rec['iptm']:.4f}  plddt={rec['complex_plddt']:.3f}")
            else:
                rec["error"] = (r.get("stderr_tail") or "")[-150:]
                print(f"{dt:6.1f}s  FAILED")
            rows.append(rec)

    RESULT.write_text(json.dumps(
        {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
         "n_observed": sum(1 for r in rows if r.get("ok")), "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")


def analyse() -> int:
    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("ok")]
    by: dict[str, dict] = {}
    for r in ok:
        by.setdefault(r["code"], {"target": r["target"], "native": None, "decoys": []})
        if r["kind"] == "native":
            by[r["code"]]["native"] = r["iptm"]
        else:
            by[r["code"]]["decoys"].append(r["iptm"])

    per = []
    for code, d in by.items():
        if d["native"] is None or not d["decoys"]:
            continue
        n_ge = sum(1 for x in d["decoys"] if x >= d["native"])
        per.append({
            "code": code, "target": d["target"], "native_iptm": round(d["native"], 4),
            "decoy_iptm": [round(x, 4) for x in d["decoys"]],
            "decoy_mean": round(statistics.fmean(d["decoys"]), 4),
            "decoy_max": round(max(d["decoys"]), 4),
            "beats_all_decoys": all(d["native"] > x for x in d["decoys"]),
            "empirical_p": round((1 + n_ge) / (len(d["decoys"]) + 1), 4),
            "band": ("confident" if d["native"] > IPTM_CONFIDENT
                     else "failed" if d["native"] < IPTM_FAILED_BAND else "grey"),
        })
    per.sort(key=lambda x: -x["native_iptm"])

    natives = [p["native_iptm"] for p in per]
    decoys = [x for p in per for x in p["decoy_iptm"]]
    n_beat_and_confident = sum(1 for p in per
                               if p["beats_all_decoys"] and p["native_iptm"] > IPTM_CONFIDENT)

    mult = peptide_multiplicity(payload["rows"], [p["code"] for p in per])
    sensitivity = _shared_peptide_sensitivity(per, mult)
    diff = (statistics.fmean(natives) - statistics.fmean(decoys)) if per else 0.0
    n_below = sum(1 for p in per if p["native_iptm"] < IPTM_FAILED_BAND)

    # All three registered hypotheses are threshold criteria on descriptive statistics; none
    # produces a test statistic. They were previously encoded as p = 0.0/1.0 and published
    # under the key `p_holm`, which asserted an inference that was never computed. This study
    # therefore emits no p-values at all — which is the honest description of its design, and
    # is stated rather than hidden. See cbc/inference.py.
    ruling = inf.decide(criteria={
        "H1_any_candidate_binds": inf.Criterion(
            n_beat_and_confident > 0, n_beat_and_confident,
            f"at least one candidate beats all decoys AND ipTM > {IPTM_CONFIDENT}"),
        "H2_natives_beat_decoys_on_average": inf.Criterion(
            diff > 0.1, round(diff, 4), "mean native minus mean decoy > 0.1"),
        "H3_candidates_in_failed_band": inf.Criterion(
            bool(per) and n_below >= len(per) / 2, n_below,
            f"at least half of {len(per)} candidates below ipTM {IPTM_FAILED_BAND}"),
    }, tests={})

    report = {
        "study_id": STUDY_ID, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(ok), "primary_metric": "fraction_candidates_beating_null",
        "metrics": {
            "fraction_candidates_beating_null": round(
                sum(1 for p in per if p["beats_all_decoys"]) / len(per), 4) if per else None,
            "mean_native_iptm": round(statistics.fmean(natives), 4) if natives else None,
            "mean_decoy_iptm": round(statistics.fmean(decoys), 4) if decoys else None,
            "native_minus_decoy_mean": round(diff, 4),
            "n_candidates_above_0.8": sum(1 for p in per if p["native_iptm"] > IPTM_CONFIDENT),
            "n_candidates_below_0.6": n_below,
            "per_candidate_empirical_p": {p["code"]: p["empirical_p"] for p in per},
            "wall_clock_seconds_per_fold": inf.wall_clock(ok),
            # Exploratory, and the prespec audit says so: every metric above is a mean or a
            # count over CONSTRUCTS, and one peptide holds two of them. This block is what
            # each headline becomes when that peptide is counted once. It does not replace
            # the registered value -- changing the de-duplication key is a change to the
            # analysis and would need a new plan -- it states what the registered value is
            # sensitive to. Emitted only when there is a shared sequence to be sensitive to.
            **({"shared_peptide_sensitivity": sensitivity} if sensitivity else {}),
        },
        "per_candidate": per,
        # The screened population by MOLECULE rather than by construct. The README's own
        # de-duplication paragraph explains at length why counting one molecule twice is not
        # harmless, and then counts thirteen; this is the field that sentence must source to.
        "peptide_multiplicity": mult,
        # The README says coverage() "records why each candidate is in or out". It did
        # not: nothing wrote it anywhere, so the claim pointed at a function a reader
        # would have to run themselves. It is part of the artefact now.
        "coverage": coverage(),
        **ruling,
        "interpretation_key": (
            "Study #7 measured, on 16 peptide-receptor complexes with known answers: ipTM > "
            "0.8 was correct in 9 of 10 cases; ipTM < 0.6 was correct in 0 of 4, with no "
            "false negatives. The gate for this study was OPEN because #7 recovered 7 of 8 "
            "memorisable interfaces, so the pipeline has demonstrated sensitivity over the "
            "range #7 measured (peptides 7-17 aa, receptors 80-304 aa; the candidates here "
            "are 31-47 aa on receptors of 156-608, so every band above is an extrapolation). "
            "RETRACTION. This key previously ended: 'and a low score here is evidence about "
            "the candidate rather than about the method.' Study #12, "
            "interface-null-positive-control-v1 (prespec 69a5009d6f62, registered before any "
            "permutation was folded; data/study_interface_null_positive_control.json), "
            "falsified that clause and it is withdrawn. #12 folded the same 16 deposited "
            "X-ray complexes -- every one an established binder -- against ten uniform "
            "random permutations of each peptide, and only 4 of 16 scored above all ten "
            "permutations of themselves, against a threshold of 5 registered in advance "
            "(H2 FALSIFIED). Losing this comparison is therefore what most demonstrated "
            "binders do on this instrument, and a low score here is NOT evidence about the "
            "candidate in the way the retracted clause claimed. What #12 confirmed is "
            "narrower and holds: natives beat their own permutations in aggregate by "
            "+0.0895 ipTM (Holm p = 0.0148, 13 of 16 differences positive), which licenses "
            "a verdict on a batch of native-versus-shuffle pairs and none on any single "
            "pair. The per-candidate readings below -- beats_all_decoys and empirical_p -- "
            "are descriptive for that reason and carry no verdict on any candidate."),
        "failures": [{"code": r["code"], "kind": r.get("kind"),
                      "error": str(r.get("error"))[:120]}
                     for r in payload["rows"] if not r.get("ok")],
    }
    report["prespec_audit"] = ps.verify_result(STUDY_ID, report)
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 96)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   "
          f"{len(per)} candidates, {len(ok)} folds")
    print("=" * 96)
    print(f"\nPRIMARY  candidates beating their own composition-matched null: "
          f"{m['fraction_candidates_beating_null']}")
    print(f"         mean native ipTM {m['mean_native_iptm']}  vs  mean decoy "
          f"{m['mean_decoy_iptm']}   difference {m['native_minus_decoy_mean']:+.4f}")
    print(f"\n{'candidate':28s} {'target':8s} {'native':>7s} {'decoy max':>10s} "
          f"{'decoy mean':>11s} {'p':>6s}  band      beats null")
    for p in per:
        print(f"{p['code'][:27]:28s} {p['target']:8s} {p['native_iptm']:7.4f} "
              f"{p['decoy_max']:10.4f} {p['decoy_mean']:11.4f} {p['empirical_p']:6.2f}  "
              f"{p['band']:9s} {'YES' if p['beats_all_decoys'] else 'no'}")
    print(f"\ncandidates in the confident band (>0.8): {m['n_candidates_above_0.8']}")
    print(f"candidates in the failed band (<0.6):    {m['n_candidates_below_0.6']}")
    print("\nPRE-SPECIFIED VERDICTS")
    print(inf.format_verdicts(report))
    if report["failures"]:
        print(f"\nFAILURES: {len(report['failures'])}")
        for f in report["failures"][:5]:
            print(f"  {f['code'][:26]:28s} {str(f['kind']):8s} {f['error'][:60]}")
    a = report["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 96)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    for f in ("register", "run", "analyse"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    if a.register:
        c = _candidates(limit=None)
        spec = build_prespec(*prespec_args())
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        print(f"registered {spec.register().relative_to(REPO)}")
        print(f"  hash {spec.hash()}   {len(c)} candidates x {1 + N_DECOYS} = "
              f"{spec.n_planned} folds")
        for x in c:
            print(f"    {x['code'][:30]:32s} -> {x['target']:8s} "
                  f"receptor {x['receptor_len']} aa")
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
