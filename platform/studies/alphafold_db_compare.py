"""AlphaFold DB against Boltz-2: do two independent predictors agree about WHERE a
receptor construct is confidently folded?

This is EXPLORATORY. It is not pre-registered, it has no hypothesis and no verdict, and it
is deliberately kept out of the numbered slate. It exists for one narrow purpose: every
receptor fold in studies #9 and #10 comes from a single predictor, so a reader has no way to
tell an ordinary fold from an arbitrary one. AlphaFold DB is an independent model -- different
weights, different training data, different inference path -- and its per-residue confidence
over the same span is a cheap external check.

WHY ALPHAFOLD DB AND NOT ALPHAFOLD SERVER. AlphaFold Server's terms prohibit automated use
for protein-ligand and protein-peptide binding prediction, which is exactly what studies #9
and #10 do. AlphaFold DB is a separately licensed corpus of deposited monomer predictions
(CC BY 4.0) and carries no such restriction. Nothing here is submitted to any server; the
deposited files are downloaded and read.

WHAT THIS CANNOT SUPPORT. pLDDT is a model's self-report, not accuracy. Two models agreeing
about where they are confident is not evidence that either is right, and a difference in mean
pLDDT is not evidence that one is better. The confounds are enumerated in the artefact and
are not incidental -- arm A confounds three things at once. Arm B exists to remove one of them.

  arm A   AlphaFold DB (monomer, full MSA)  vs  Boltz-2 study #9  (complex, single sequence)
  arm B   AlphaFold DB (monomer, full MSA)  vs  Boltz-2 study #10 (complex, full MSA)

Arm B holds the MSA constant, so the residual difference is predictor plus monomer-versus-
complex context rather than predictor plus MSA plus context.

COVERAGE IS REPORTED, NOT IMPLIED. Every registry accession is downloaded. A target is
compared only if a Boltz-2 receptor fold exists for it, and each uncompared target is listed
with the reason, so that "7 of 16" can never be read as "16".

    python platform/studies/alphafold_db_compare.py --fetch
    python platform/studies/alphafold_db_compare.py --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc.predictor import fetch_alphafold_db, parse_mmcif  # noqa: E402
from cbc.provenance import git_sha                         # noqa: E402

REPO = Path(__file__).resolve().parents[2]
AFDB_DIR = REPO / "data" / "alphafold_db"
OUT = REPO / "data" / "alphafold_db_comparison.json"
REGISTRY = REPO / "data" / "target_registry.json"
MANIFEST = REPO / "runs" / "manifest.json"

ARMS = [
    ("boltz_single_sequence", "data/study_candidate_screen.json", "candidate-screen",
     "study #9 -- receptor folded inside a two-chain complex with msa=empty"),
    ("boltz_full_msa", "data/study_msa_specificity.json", "msa-specificity",
     "study #10 -- same complex, --use_msa_server, so the MSA confound is removed"),
]


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r, or None when either vector is constant (r is undefined, not zero)."""
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def lag1(v: list[float]) -> float:
    """Lag-1 autocorrelation. Confidence runs in contiguous stretches along a chain, so
    residues are nowhere near independent and the residue count is not the sample size."""
    n = len(v)
    if n < 3:
        return 0.0
    m = statistics.fmean(v)
    den = sum((x - m) ** 2 for x in v)
    if den <= 0:
        return 0.0
    return sum((v[i] - m) * (v[i + 1] - m) for i in range(n - 1)) / den


def effective_n(xs: list[float], ys: list[float]) -> int:
    """Bartlett's first-order effective sample size, n(1-rx*ry)/(1+rx*ry).

    Published beside r, `n_residues_compared` reads as the sample size and is not one. On
    TREM2 the 156 residues carry an effective n below 4, which makes the LARGEST correlation
    in the table the least supported number in it. Reporting the residue count without this
    is the same overclaim as reporting a p-value the design cannot license.
    """
    rho = lag1(xs) * lag1(ys)
    if rho >= 1.0:
        return 1
    return max(1, int(round(len(xs) * (1 - rho) / (1 + rho))))


def shift_null(xs: list[float], ys: list[float], min_lag: int = 10) -> dict | None:
    """How large is r between these profiles when they are deliberately mis-registered?

    `what_this_does_support` claimed the two models "agree substantially" -- a comparative
    claim with nothing to compare against, in a repository whose central study turns on
    composition-matched nulls. Circularly shifting one profile destroys the residue-by-residue
    correspondence while preserving both profiles' shape and autocorrelation exactly.

    WHAT IT RULES OUT, AND WHAT IT DOES NOT. It rules out r being an artefact of the two
    marginal distributions -- of one model simply having a similar spread of confidences to
    the other. It does NOT separate residue-specific agreement from generic-profile agreement:
    two models that agree only because both put low pLDDT at the termini and high in the
    middle would still beat this null in every target, because the shift moves those shared
    features out of register. An earlier version of this docstring claimed the opposite and
    `what_this_does_support` drew the inference the null does not license.

    The fraction is also reported as a fraction of HEAVILY OVERLAPPING shifts, not as a
    p-value: the shifts share nearly all their data, so the effective number of independent
    comparisons is far below n_shifts and a fraction of 0 means "below 1/n_shifts", not zero.
    """
    n = len(xs)
    if n < 3 * min_lag:
        return None
    obs = pearson(xs, ys)
    if obs is None:
        return None
    null = []
    for lag in range(min_lag, n - min_lag):
        r = pearson(xs, ys[lag:] + ys[:lag])
        if r is not None:
            null.append(abs(r))
    if not null:
        return None
    null.sort()
    beat = sum(1 for v in null if v >= abs(obs))
    frac = beat / len(null)
    return {"n_shifts": len(null),
            "fraction_of_shifts_reaching_observed_r": (
                round(frac, 4) if beat else f"<{1 / len(null):.2g}"),
            "null_abs_r_p95": round(null[int(0.95 * (len(null) - 1))], 4),
            "note": "circular shift of the Boltz profile against the AlphaFold one. It "
                    "preserves both profiles and destroys only the residue correspondence, so "
                    "it rules out r being an artefact of the two marginal distributions. It "
                    "does NOT separate residue-specific agreement from the generic fact that "
                    "both models are unconfident at termini. The shifts overlap heavily, so "
                    "this fraction is not a p-value and a zero count is reported as an upper "
                    "bound rather than as 0."}


def registry() -> dict:
    return json.loads(REGISTRY.read_text())["targets"]


def fetch_all() -> None:
    reg = registry()
    for symbol in sorted(reg):
        acc = reg[symbol]["uniprot"]
        out = AFDB_DIR / symbol
        if list(out.glob("*.cif")):
            print(f"  {symbol:8s} {acc}  already present")
            continue
        out.mkdir(parents=True, exist_ok=True)
        try:
            fetch_alphafold_db(acc, out)
            print(f"  {symbol:8s} {acc}  downloaded")
        except Exception as exc:                                    # noqa: BLE001
            print(f"  {symbol:8s} {acc}  FAILED: {exc}")


def afdb_plddt(symbol: str) -> tuple[dict[int, float], list[str]] | None:
    """Per-canonical-residue pLDDT from the deposited model, keyed by label_seq_id."""
    d = AFDB_DIR / symbol
    cifs = sorted(d.glob("*.cif"))
    if not cifs:
        return None
    residues, _chains, _lig = parse_mmcif(cifs[0])
    by_pos = {r.seq_id: r.plddt for r in residues if r.plddt is not None}
    # The AlphaFold side was never scale-checked, while the `method` field claimed both were.
    # A fractional deposited file would leave every r unchanged and every mean off by ~90.
    if by_pos and max(by_pos.values()) <= 1.0:
        return None
    return by_pos, sorted(f.name for f in d.iterdir() if f.is_file())


def boltz_chain_a_plddt(run_dir: Path) -> list[float] | None:
    """Chain A per-residue pLDDT from the stored model, checked to be on AlphaFold's 0-100.

    An earlier version of this docstring stated that Boltz writes the value as a fraction and
    that this function rescales it. Both halves were false and the artefact repeated them in
    its published `method`. Every one of the 497 Boltz models under custody carries 0-100 in
    the mmCIF B-factor column, so the branch below has never executed; the fraction lives in
    the confidence JSON, which is a different file. The guard stays because a mixed-scale file
    would otherwise put a 0.96 beside a 97.5 and make two agreeing models look like two
    disagreeing ones -- but a reader must not be told a transform happens that does not.
    """
    cifs = sorted(run_dir.glob("*.cif"))
    if not cifs:
        return None
    residues, _chains, _lig = parse_mmcif(cifs[0])
    a = [r.plddt for r in residues if r.chain == "A" and r.plddt is not None]
    if not a:
        return None
    # Refuse rather than rescale. A silent x100 here would contradict the published method,
    # which now states that a row is refused if either vector is off-scale.
    return None if max(a) <= 1.0 else a


def run_index(kind: str) -> dict[str, list[Path]]:
    """job name -> every retained run directory for it, INCLUDING content-identical aliases.

    Two separate hazards live here, and both bit this comparison before it was written down.

    First, content-addressed reuse records a run under the first job name that produced it
    and lists every job with byte-identical OUTPUT under `identical_jobs`. Looking up by
    `job` alone therefore misses any candidate whose fold duplicates another's -- which
    silently dropped ACHE, because the v9 candidate `HippoAChE-AlkaPept-X2` folds to the same
    bytes as the retired v8 candidate `BasalAChE-GorgeBlock-B1` and so has no run of its own
    name. The alias is not a workaround: two identical outputs ARE one computation.

    Second, aliases accumulate ACROSS study versions. `HippoAChE-AlkaPept-X2_native` resolves
    to two msa-specificity runs -- one folded against the 583-residue untrimmed ACHE chain
    from before the construct correction, one against the 543-residue corrected construct.
    Picking either by manifest order is picking by accident, so this returns ALL of them and
    the caller selects on evidence: the run whose chain A actually holds the construct the
    study says it folded.
    """
    idx: dict[str, list[Path]] = {}
    for r in json.loads(MANIFEST.read_text())["runs"]:
        if r.get("kind") != kind:
            continue
        d = REPO / r["path"]
        for name in [r["job"], *(r.get("identical_jobs") or [])]:
            idx.setdefault(name, []).append(d)
    return idx


def select_run(cands: list[Path], want_len: int) -> tuple[Path | None, list[int]]:
    """The run whose chain A holds exactly `want_len` residues, chosen deterministically.

    Returns the observed chain A lengths alongside, so a miss is reported as what was found
    rather than as a bare absence.

    The tie-break is the run directory NAME, which is the content hash of the run. It used to
    be the cif's mtime, which git does not preserve, so the published `boltz_run` depended on
    which rescue pass touched the directory last: during one audit this generator, at the same
    commit, wrote 13 of 14 paths differently between two runs minutes apart with every
    scientific number identical -- enough to flip the repository's own staleness test to FAIL
    while nothing was stale.
    """
    seen: list[int] = []
    match: list[tuple[str, Path]] = []
    for d in cands:
        v = boltz_chain_a_plddt(d)
        if v is None:
            continue
        seen.append(len(v))
        if len(v) == want_len:
            match.append((d.name, d))
    if not match:
        return None, sorted(set(seen))
    return max(match)[1], sorted(set(seen))


def analyse() -> None:
    reg = registry()
    downloaded = sorted(p.name for p in AFDB_DIR.iterdir() if p.is_dir())
    arms: dict[str, dict] = {}
    seen_targets: set[str] = set()

    for arm, study_path, kind, arm_note in ARMS:
        study = json.loads((REPO / study_path).read_text())
        idx = run_index(kind)
        # One receptor construct per target, but several candidates fold against it, so a
        # target can have two or three native runs of the same receptor with different
        # peptides. `setdefault` kept the first and discarded the rest in silence: 13 native
        # folds became 7 rows, in an artefact whose stated purpose is that coverage can never
        # be over-read. Six disappeared -- and NTRK2's alternates span 0.700 to 0.758 in arm
        # A, wide enough that which one happened to be first in the JSON moves the published
        # median. The first is still the row, because a target must contribute one, but every
        # alternate is now measured and listed beside it.
        chosen: dict[str, dict] = {}
        alternates: dict[str, list[dict]] = {}
        for row in study["rows"]:
            if row.get("kind") != "native" or not row.get("ok"):
                continue
            if row["target"] in chosen:
                alternates.setdefault(row["target"], []).append(row)
            else:
                chosen[row["target"]] = row

        rows, skipped = [], []
        for symbol in downloaded:
            seen_targets.add(symbol)
            row = chosen.get(symbol)
            if row is None:
                skipped.append({"target": symbol, "uniprot": reg[symbol]["uniprot"],
                                "reason": "no Boltz-2 receptor fold in this study; the "
                                          "target carries no designed candidate"})
                continue
            job = f"{row['code']}_native"
            lo, hi = row["construct"]["canonical_span"]
            want = hi - lo + 1
            cands = idx.get(job, [])
            if not cands:
                skipped.append({"target": symbol, "uniprot": reg[symbol]["uniprot"],
                                "reason": f"run for {job} is not under custody"})
                continue
            run, seen = select_run(cands, want)
            if run is None:
                skipped.append({"target": symbol, "uniprot": reg[symbol]["uniprot"],
                                "reason": f"{len(cands)} retained run(s) for {job} hold chain "
                                          f"A of {seen} residues; the study says its construct "
                                          f"span {lo}-{hi} is {want}. Refusing to align two "
                                          "different things."})
                continue
            boltz = boltz_chain_a_plddt(run)
            af = afdb_plddt(symbol)
            if boltz is None or af is None:
                skipped.append({"target": symbol, "uniprot": reg[symbol]["uniprot"],
                                "reason": "a per-residue pLDDT vector could not be read"})
                continue
            by_pos, files = af
            pairs = [(by_pos[lo + i], boltz[i]) for i in range(len(boltz)) if lo + i in by_pos]
            if len(pairs) < 3:
                skipped.append({"target": symbol, "uniprot": reg[symbol]["uniprot"],
                                "reason": "fewer than 3 residues are shared by both models"})
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            r = pearson(xs, ys)
            alts = []
            for other in alternates.get(symbol, []):
                orun, _seen = select_run(idx.get(f"{other['code']}_native", []), want)
                if orun is None:
                    continue
                ov = boltz_chain_a_plddt(orun)
                if ov is None or len(ov) != want:
                    continue
                opairs = [(by_pos[lo + i], ov[i]) for i in range(len(ov)) if lo + i in by_pos]
                orr = pearson([q[0] for q in opairs], [q[1] for q in opairs])
                alts.append({"boltz_job": f"{other['code']}_native",
                             "boltz_run": str(orun.relative_to(REPO)),
                             "pearson_r": None if orr is None else round(orr, 4),
                             "boltz_mean_plddt": round(
                                 statistics.fmean([q[1] for q in opairs]), 2)})
            rows.append({
                "target": symbol, "uniprot": reg[symbol]["uniprot"],
                "n_residues_compared": len(pairs),
                "construct_span_canonical": [lo, hi],
                "construct_basis": row["construct"]["basis"],
                "effective_n_after_autocorrelation": effective_n(xs, ys),
                "afdb_mean_plddt": round(statistics.fmean(xs), 2),
                "boltz_mean_plddt": round(statistics.fmean(ys), 2),
                "pearson_r": None if r is None else round(r, 4),
                "shift_null": shift_null(xs, ys),
                "boltz_job": job,
                "boltz_run": str(run.relative_to(REPO)),
                "boltz_run_selected_by": (
                    f"chain A holds {len(boltz)} residues, matching the construct span. "
                    "Among retained runs that match, the one whose content-hash directory "
                    "name sorts last is taken, which is deterministic across clones"),
                "other_native_folds_of_this_receptor": alts,
                "afdb_files": files,
            })

        rs = [x["pearson_r"] for x in rows if x["pearson_r"] is not None]
        arms[arm] = {
            "note": arm_note, "study": study_path,
            "plan": study.get("analysis", {}).get("prespec_hash"),
            "n_compared": len(rows),
            "pearson_r_min": round(min(rs), 4) if rs else None,
            "pearson_r_median": round(statistics.median(rs), 4) if rs else None,
            "pearson_r_max": round(max(rs), 4) if rs else None,
            "mean_offset_afdb_minus_boltz": (
                round(statistics.fmean([x["afdb_mean_plddt"] - x["boltz_mean_plddt"]
                                        for x in rows]), 2) if rows else None),
            "rows": sorted(rows, key=lambda x: x["target"]),
            "not_compared": sorted(skipped, key=lambda x: x["target"]),
        }

    a, b = arms["boltz_single_sequence"], arms["boltz_full_msa"]
    paired = {x["target"]: x["pearson_r"] for x in a["rows"] if x["pearson_r"] is not None}
    shift_by_target = {x["target"]: round(x["pearson_r"] - paired[x["target"]], 4)
                       for x in b["rows"]
                       if x["target"] in paired and x["pearson_r"] is not None}
    shifts = list(shift_by_target.values())
    # An exact two-sided sign test, reported so the direction is not asserted as a result on
    # seven targets without the reader being told how weak seven is.
    n_pos = sum(1 for x in shifts if x > 0)
    n_eff = sum(1 for x in shifts if x != 0)
    sign_p = (min(1.0, 2 * sum(math.comb(n_eff, k)
                               for k in range(min(n_pos, n_eff - n_pos) + 1)) / 2 ** n_eff)
              if n_eff else 1.0)

    # cbc.provenance.git_sha marks a dirty tree; a bare commit here would claim that a
    # checkout of it reproduces this artefact, which it does not while the tree is modified.
    sha = git_sha(REPO)

    artefact = {
        "artefact": "alphafold_db_vs_boltz2",
        "status": "EXPLORATORY -- not a pre-registered study, and labelled so deliberately. "
                  "It has no hypothesis, no verdict and no place in the numbered slate.",
        "generator": "platform/studies/alphafold_db_compare.py",
        "git_sha": sha,
        "question": "Do two independent predictors agree about WHERE each receptor construct "
                    "is confidently folded?",
        "method": "For every registry target with a Boltz-2 receptor fold, take AlphaFold "
                  "DB's per-residue pLDDT over the construct's canonical span and correlate "
                  "it against Boltz-2's chain-A per-residue pLDDT, residue by residue. Both "
                  "vectors are read from the mmCIF B-factor column by the same parser the "
                  "workbench uses on user-supplied predictor output. Both vectors are "
                  "checked to lie on 0-100 before any mean is taken, and a row is refused "
                  "rather than rescaled if either does not; no file in this repository "
                  "triggers that, because every model under custody already writes 0-100.",
        "confounds": [
            "AlphaFold DB is a MONOMER prediction. Boltz-2 folded the receptor inside a "
            "two-chain complex with a peptide. Both arms carry this confound, so no offset "
            "in mean pLDDT is evidence that either model is more accurate.",
            "Arm A additionally confounds the MSA: AlphaFold DB used a full MSA and study #9 "
            "used none. Arm B holds the MSA constant and is the arm to read.",
            "pLDDT is a self-reported confidence, not accuracy. Agreement between two models "
            "about where they are confident is not agreement about where they are right.",
            "The correlation is computed over residues within one protein, which are not "
            "independent: confidence runs in contiguous stretches, so the effective sample "
            "size is far below n_residues_compared and no p-value is reported for r. Each row "
            "carries effective_n_after_autocorrelation for this reason -- on TREM2 the 156 "
            "residues are worth a single-figure number of independent observations, which "
            "makes the largest r in the set the least supported number in it.",
        ],
        "what_this_does_support": "The two models agree about which residues of each "
                                  "receptor are well determined, and that agreement is not an "
                                  "artefact of their two confidence distributions happening "
                                  "to have similar shape: mis-registering one profile against "
                                  "the other destroys it in every target-arm (see shift_null "
                                  "per row, and read its note for what that null does not "
                                  "rule out). The models have different "
                                  "weights, a different architecture and a different "
                                  "inference path -- but NOT independent training data: both "
                                  "are trained predominantly on the PDB, and both confidence "
                                  "heads are trained to predict lDDT, so some of this "
                                  "agreement is shared supervision rather than independent "
                                  "corroboration. It is a check that the receptor folds are "
                                  "not arbitrary. It is not a check on the peptide, on the "
                                  "interface, or on any claim in the slate -- whose answer "
                                  "remains negative.",
        "source": {
            "name": "AlphaFold Protein Structure Database",
            "url": "https://alphafold.ebi.ac.uk/",
            "licence": "CC BY 4.0",
            "cite": "Jumper J et al. Nature 596:583-589 (2021); "
                    "Varadi M et al. Nucleic Acids Res 52:D368-D375 (2024)",
            "note": "Downloaded, not computed here. AlphaFold Server was NOT used: its terms "
                    "prohibit automated use for protein-ligand and protein-peptide binding "
                    "prediction, which is what studies #9 and #10 do.",
        },
        "coverage": {
            "registry_targets": len(reg),
            "downloaded": len(downloaded),
            "targets": downloaded,
            "compared_in_at_least_one_arm": sorted(
                {x["target"] for arm in arms.values() for x in arm["rows"]}),
            "note": "Every registry accession is downloaded. A target is compared only where "
                    "a Boltz-2 receptor fold exists; the rest are listed per arm under "
                    "not_compared with a reason.",
        },
        "arms": arms,
        "arm_agreement": {
            "n_targets_in_both": len(shifts),
            "median_shift_in_r_when_boltz_gets_an_msa": (
                round(statistics.median(shifts), 4) if shifts else None),
            # The median alone was doing the work of a conclusion. The distribution is
            # bimodal on n=7, so mean and median disagree by half, and an unlabelled array of
            # shifts forced a reader to reconstruct the target order from `rows`.
            "mean_shift_in_r_when_boltz_gets_an_msa": (
                round(statistics.fmean(shifts), 4) if shifts else None),
            "n_positive_shifts": n_pos,
            "sign_test_two_sided_p": round(sign_p, 4) if shifts else None,
            "per_target_shift": shift_by_target,
            "depends_on_which_native_fold_was_taken": (
                "Each target contributes the FIRST native row in the study JSON, and six of "
                "the thirteen native folds are alternates listed per row under "
                "other_native_folds_of_this_receptor. The summary above is not robust to that "
                "pick: TREM2's chosen shift is negative while its alternate is positive, so "
                "taking the other fold would make all seven shifts positive and move the sign "
                "test from p = 0.125 to p = 0.0156. Read the direction, not the test."),
            "reading": "Giving Boltz-2 an MSA moved its confidence profile closer to "
                       "AlphaFold's, substantially so on nearly half the set: six of seven "
                       "shifts are positive and three exceed +0.22. The distribution is "
                       "bimodal -- four targets near zero, three near +0.24 -- so the mean "
                       "and the median differ by half and the median alone hides the effect, "
                       "which is why both are reported. On seven targets, six positives is a "
                       "two-sided sign test p = 0.125: a direction worth reporting, not a "
                       "result worth asserting. (This field previously said a shift near "
                       "zero showed the MSA changed nothing. That was written before the "
                       "numbers came back and should not have survived them.)",
        },
    }
    OUT.write_text(json.dumps(artefact, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}")
    for name, arm in arms.items():
        print(f"  {name:22s} n={arm['n_compared']:2d}  r {arm['pearson_r_min']} .. "
              f"{arm['pearson_r_max']} (median {arm['pearson_r_median']})  "
              f"not compared: {len(arm['not_compared'])}")
    print(f"  arm agreement: median shift in r = "
          f"{artefact['arm_agreement']['median_shift_in_r_when_boltz_gets_an_msa']} "
          f"over {len(shifts)} targets")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch_all()
    if args.analyse or not args.fetch:
        analyse()
