#!/usr/bin/env python3
"""Study #10: does the candidate screen's negative survive a full MSA?

Study #9 found that not one candidate beat its own composition-matched null, and registered
this confound in advance: "single-sequence mode depresses all arms equally, so the
native-versus-decoy CONTRAST is the interpretable quantity."

That assumption has since been measured, and it is FALSE. On BasalAChE-GorgeBlock-B1 + AChE
at the same seed, enabling the MSA server moved the native from ipTM 0.3402 to 0.7588 while
moving its first decoy from 0.3478 to 0.2986. Without an MSA the contrast was -0.008 (the
decoy scored higher); with one it is +0.460. The MSA does not depress the arms equally, it
separates them. So #9's negative cannot be carried into the MSA setting and this study
re-runs the comparison there.

Design note carried over from #9's failure mode: with a handful of decoys the per-candidate
empirical p has a floor of 1/(N+1) and can never reach significance, so a per-candidate
permutation test would be an unreachable verdict — the exact defect this project's
pre-registration module rejects at registration time. The primary test is therefore PAIRED
ACROSS CANDIDATES: each candidate contributes one native and one decoy mean, and the six
pairs are tested together. Per-candidate empirical p values are reported as descriptive only.

    ./.venv/bin/python platform/studies/msa_specificity.py --register
    ./.venv/bin/python platform/studies/msa_specificity.py --run
    ./.venv/bin/python platform/studies/msa_specificity.py --analyse
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import inference as inf, prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402
from studies.candidate_screen import CANDIDATE_TARGETS, _candidates, _receptor_seq, _scrambles  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "msa-specificity-v9"
WORK = Path("/tmp/cbc_msa10")
RESULT = REPO / "data" / "study_msa_specificity.json"

N_DECOYS = 10
SEED = 1
IPTM_CONFIDENT = 0.8
IPTM_FAILED = 0.6



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
            "With a full MSA rather than single-sequence mode, is each candidate's interface "
            "with its declared receptor distinguishable from the interfaces the same model "
            "assigns to sequences of identical amino-acid composition in random order?"),
        primary_metric="paired_native_minus_decoy_mean",
        primary_metric_justification=(
            "The primary test is paired ACROSS candidates: each candidate contributes one "
            "native ipTM and the mean ipTM of its own decoys, and the resulting differences "
            "are tested against zero. This is chosen over a per-candidate permutation p "
            "because with N decoys the empirical p has a hard floor of 1/(N+1); at N=10 that "
            "floor is 0.091, so a per-candidate test could never reach alpha=0.05 and would "
            "be an unreachable verdict — exactly the defect this project's registration "
            "module rejects. Pairing also removes between-receptor variation, which is large "
            "here because the receptors range from 156 to 608 residues and ipTM depends on "
            "chain length. Per-candidate empirical p values are reported as descriptive."),
        decision_threshold=(
            "H1 confirmed if the mean paired difference (native minus its own decoy mean) is "
            "positive with a paired t-test p < 0.05; H2 confirmed if at least one candidate "
            "both beats every one of its decoys and reaches ipTM > 0.8; H3 confirmed if the "
            "MSA arm raises mean native ipTM by more than 0.15 over the single-sequence "
            "values measured in study #9."),
        n_planned=n_folds,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed: each candidate is predicted once with its receptor and once with each of "
            "10 composition-matched decoys, all with --use_msa_server at seed 1, in a fixed "
            "order. Nothing is added or removed after the first prediction. Technical "
            "failures are recorded with their reason and excluded; a candidate retaining "
            "fewer than 5 usable decoys is dropped from the paired test with that stated."),
        analysis_plan=(
            "Reuse the exact candidate set and RNG seed of study #9 so the only changed "
            "variable is the MSA. Build 10 composition-matched shuffles per candidate with "
            "random.Random(1). Predict the receptor ligand-accessible construct (extracellular "
            "topological domain for a membrane receptor, mature chain for a soluble one) "
            "plus peptide with Boltz-2 "
            "2.2.1, --use_msa_server, gpu, seed 1, diffusion_samples 1, recycling_steps 3. "
            "For each candidate compute native ipTM minus the mean of its decoys; test the "
            "the per-candidate differences against zero with a paired t-test and report "
            "Cohen's dz. "
            "Compare native ipTM against study #9's single-sequence value for the same "
            "candidate. Holm across the three hypotheses."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_natives_separate_from_decoys",
                statement=("With a full MSA the designed sequences score higher than their "
                           "own composition-matched shuffles."),
                predicted_by=("the pilot measurement, where MSA moved one native from 0.3402 "
                              "to 0.7588 while moving its decoy from 0.3478 to 0.2986"),
                confirmed_if="mean paired difference > 0 with paired t-test p < 0.05",
                falsified_if="mean paired difference <= 0 or p >= 0.05"),
            ps.Hypothesis(
                name="H2_a_candidate_is_confident_and_specific",
                statement=("At least one candidate is both better than its null and "
                           "confident in absolute terms."),
                predicted_by="the platform's original claim that these are targeted binders",
                confirmed_if="some candidate beats all its decoys AND has native ipTM > 0.8",
                falsified_if="no candidate satisfies both"),
            ps.Hypothesis(
                name="H3_msa_raises_natives",
                statement=("The MSA materially raises native ipTM relative to study #9's "
                           "single-sequence run, i.e. #9's confound was real."),
                predicted_by="the pilot, and the fact that these receptors have many homologues",
                confirmed_if="mean native ipTM exceeds study #9's by more than 0.15",
                falsified_if="the increase is 0.15 or less"),
        ),
        secondary_metrics=(
            "mean_native_iptm", "mean_decoy_iptm", "cohens_dz",
            "per_candidate_empirical_p", "n_candidates_beating_all_decoys",
            "delta_vs_study9", "n_candidates_above_0.8", "wall_clock_seconds_per_fold",
        ),
        exclusions=(
            f"The same {n_cand} candidates as study #9: those whose declared receptor is in "
            "the target registry and is extracellular. Reusing the set and the RNG seed is "
            "deliberate — with everything else held fixed, any difference is attributable to "
            "the MSA alone."),
        supersedes="msa-specificity-v8",
        supersedes_reason=(
            "Synchronised with candidate-screen-v8: coverage() no longer short-circuits on the hand-written map, the oligomeric flag no longer excludes, and the two GRIN2A candidates the criterion admits are screened, giving 13 distinct designs. The power caveat is now derived from n_cand rather than typed, because that string had gone stale three times. No hypothesis, threshold or decision rule changes."),
        known_confounds=(
            "4. STUDY #7'S BANDS ARE AN EXTRAPOLATION HERE, AND ARE LABELLED AS ONE. #7 calibrated ipTM against DockQ on 16 complexes whose peptides were 7-17 residues and whose receptors were 80-304. These candidates are 31-47 residues, longer than anything #7 measured, on receptors of 156-608. No candidate lies inside the calibrated peptide range, and only TREM2 (156 aa) and CHRNA7 (211 aa) lie inside the calibrated receptor range. The absolute thresholds in H1 and H3 are therefore extrapolated, and every verdict that rests on them is reported as extrapolated rather than calibrated. The primary metric does not depend on them: the native-versus-decoy contrast is a within-candidate comparison whose reference distribution is generated inside this study. "
            "1. The ColabFold MSA server is a remote service whose returned alignment can "
            "change between calls, so this arm confounds MSA CONTENT with MSA PRESENCE; a "
            "rerun may not reproduce byte-identically even at fixed seed. 2. The MSA helps "
            "the RECEPTOR, which has thousands of homologues, far more than the peptide, "
            "which has none — so a rise in ipTM may reflect a better-folded receptor rather "
            "than a better interface. ipTM is interface-restricted, which mitigates but does "
            f"not eliminate this. 3. n = {n_cand} paired differences gives a paired t-test "
            "little "
            "power; only a large and consistent effect will register. 4. A positive result "
            "here bounds what this pipeline distinguishes, not what the molecules do in a "
            "cell."),
    )


def run() -> None:
    plan = ps.load(STUDY_ID)
    cands = _candidates(limit=None)
    prior = {}
    p9 = REPO / "data" / "study_candidate_screen.json"
    if p9.exists():
        for r in json.loads(p9.read_text())["rows"]:
            if r.get("ok") and r["kind"] == "native":
                prior[r["code"]] = r["iptm"]

    rows: list[dict] = []
    total = len(cands) * (1 + N_DECOYS)
    i = 0
    for c in cands:
        rseq = _receptor_seq(c["target"])
        variants = [("native", c["peptide"])] + [
            (f"decoy{k}", s) for k, s in enumerate(_scrambles(c["peptide"], N_DECOYS, SEED))]
        for kind, pep in variants:
            i += 1
            print(f"[{i}/{total}] {c['code'][:24]:26s} {kind:8s} {c['target']:7s} ",
                  end="", flush=True)
            t0 = time.time()
            try:
                r = st.run_boltz(
                    [st.Chain("A", rseq, "protein", msa=None),
                     st.Chain("B", pep, "protein", msa=None)],
                    WORK / f"{c['code']}_{kind}", accelerator="gpu", seed=SEED,
                    diffusion_samples=1, recycling_steps=3,
                    use_msa_server=True, timeout=7200, reuse=True)
            except Exception as exc:  # noqa: BLE001
                print(f"raised: {str(exc)[:40]}")
                rows.append({**c, "kind": kind, "ok": False, "error": str(exc)[:200]})
                continue
            dt = time.time() - t0
            conf = r.get("confidence") or {}
            reused = bool(r.get("reused"))
            ok = r.get("returncode") == 0 and conf.get("iptm") is not None
            rec = {**c, "kind": kind, "peptide_used": pep, "ok": ok,
                   "seconds": round(dt, 1), "reused": reused, "iptm": conf.get("iptm"),
                   "ptm": conf.get("ptm"), "complex_plddt": conf.get("complex_plddt"),
                   "iptm_study9": prior.get(c["code"]) if kind == "native" else None}
            if ok:
                extra = ""
                if kind == "native" and prior.get(c["code"]) is not None:
                    extra = f"  (#9 no-MSA: {prior[c['code']]:.4f})"
                print(f"{dt:6.1f}s  ipTM={rec['iptm']:.4f}{extra}")
            else:
                rec["error"] = (r.get("stderr_tail") or "")[-150:]
                print(f"{dt:6.1f}s  FAILED")
            rows.append(rec)
            RESULT.write_text(json.dumps(
                {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
                 "n_observed": sum(1 for x in rows if x.get("ok")), "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")



def _beats_all_null(observed: int, n_candidates: int, n_decoys: int) -> dict:
    """How often would this many candidates beat all their own decoys by chance?"""
    from math import comb
    p0 = 1.0 / (n_decoys + 1)
    tail = sum(comb(n_candidates, x) * p0 ** x * (1 - p0) ** (n_candidates - x)
               for x in range(observed, n_candidates + 1))
    return {
        "per_candidate_null_probability": round(p0, 4),
        "expected_under_null": round(n_candidates * p0, 3),
        "observed": observed,
        "p_at_least_observed": round(tail, 4),
        "interpretation": (
            f"with {n_decoys} decoys each, a candidate beats all of them with probability "
            f"{p0:.4f} under the null, so {n_candidates * p0:.2f} of {n_candidates} are "
            f"expected to do so by chance; observing {observed} has probability "
            f"{tail:.3f}."),
    }

def analyse() -> int:
    from scipy import stats
    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("ok")]
    by: dict[str, dict] = {}
    for r in ok:
        d = by.setdefault(r["code"], {"target": r["target"], "native": None,
                                      "decoys": [], "study9": None})
        if r["kind"] == "native":
            d["native"] = r["iptm"]
            d["study9"] = r.get("iptm_study9")
        else:
            d["decoys"].append(r["iptm"])

    per, diffs = [], []
    for code, d in by.items():
        if d["native"] is None or len(d["decoys"]) < 5:
            continue
        dm = statistics.fmean(d["decoys"])
        n_ge = sum(1 for x in d["decoys"] if x >= d["native"])
        per.append({
            "code": code, "target": d["target"], "native_iptm": round(d["native"], 4),
            "n_decoys": len(d["decoys"]), "decoy_mean": round(dm, 4),
            "decoy_max": round(max(d["decoys"]), 4),
            "difference": round(d["native"] - dm, 4),
            "beats_all_decoys": all(d["native"] > x for x in d["decoys"]),
            "empirical_p": round((1 + n_ge) / (len(d["decoys"]) + 1), 4),
            "iptm_study9": d["study9"],
            "delta_vs_study9": (round(d["native"] - d["study9"], 4)
                                if d["study9"] is not None else None),
            "band": ("confident" if d["native"] > IPTM_CONFIDENT
                     else "failed" if d["native"] < IPTM_FAILED else "grey"),
        })
        diffs.append(d["native"] - dm)
    per.sort(key=lambda x: -x["difference"])

    t_p = 1.0
    dz = None
    if len(diffs) >= 3 and statistics.pstdev(diffs) > 0:
        tt = stats.ttest_1samp(diffs, 0.0)
        t_p = float(tt.pvalue)
        dz = statistics.fmean(diffs) / statistics.stdev(diffs)

    natives = [p["native_iptm"] for p in per]
    d9 = [p["delta_vs_study9"] for p in per if p["delta_vs_study9"] is not None]
    n_conf_spec = sum(1 for p in per
                      if p["beats_all_decoys"] and p["native_iptm"] > IPTM_CONFIDENT)

    # Only H1 is a test (paired t on the per-candidate native-minus-decoy-mean differences).
    # H2 and H3 are threshold criteria. Encoding them as p = 0.0 put them at the head of the
    # Holm step-down and stripped the multiplier off the one real test. See cbc/inference.py.
    ruling = inf.decide(criteria={
        "H2_a_candidate_is_confident_and_specific": inf.Criterion(
            n_conf_spec > 0, n_conf_spec,
            f"at least one candidate beats all decoys AND ipTM > {IPTM_CONFIDENT}"),
        "H3_msa_raises_natives": inf.Criterion(
            bool(d9) and statistics.fmean(d9) > 0.15,
            round(statistics.fmean(d9), 4) if d9 else None,
            "mean native ipTM gain over the single-sequence arm > 0.15"),
    }, tests=({"H1_natives_separate_from_decoys": t_p}
              if (t_p is not None and 0.0 < t_p <= 1.0) else {}))
    # The test is two-sided, so a significant result in the WRONG direction must not confirm
    # "natives separate from decoys". Direction is checked separately from significance, and
    # both are reported. Gating the test's inclusion on direction, as an earlier version did,
    # simply hid the p-value whenever the effect pointed the other way.
    _mean_diff = statistics.fmean(diffs) if diffs else 0.0
    if _mean_diff <= 0:
        ruling["verdicts"]["H1_natives_separate_from_decoys"] = "FALSIFIED"
    if "H1_natives_separate_from_decoys" not in ruling["verdicts"]:
        ruling["verdicts"]["H1_natives_separate_from_decoys"] = "FALSIFIED"

    report = {
        "study_id": STUDY_ID, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(ok), "primary_metric": "paired_native_minus_decoy_mean",
        "metrics": {
            "paired_native_minus_decoy_mean": round(statistics.fmean(diffs), 4) if diffs else None,
            "mean_native_iptm": round(statistics.fmean(natives), 4) if natives else None,
            "mean_decoy_iptm": round(statistics.fmean(
                [x for p in per for x in [p["decoy_mean"]]]), 4) if per else None,
            "cohens_dz": round(dz, 4) if dz is not None else None,
            "per_candidate_empirical_p": {p["code"]: p["empirical_p"] for p in per},
            "n_candidates_beating_all_decoys": sum(1 for p in per if p["beats_all_decoys"]),
            # A candidate beating all N of its own decoys has probability 1/(N+1) under the
            # null, so with 10 candidates screened, some are EXPECTED to do it by chance.
            # Reporting the count without this number invites reading a chance outcome as a
            # hit -- which is the exact error the composition-matched null exists to prevent,
            # reappearing one level up at the level of the screen rather than the candidate.
            "beats_all_decoys_null": _beats_all_null(
                sum(1 for p in per if p["beats_all_decoys"]), len(per), N_DECOYS),
            "delta_vs_study9": round(statistics.fmean(d9), 4) if d9 else None,
            "n_candidates_above_0.8": sum(1 for p in per
                                          if p["native_iptm"] > IPTM_CONFIDENT),
            "wall_clock_seconds_per_fold": inf.wall_clock(ok),
        },
        "paired_t_p": round(t_p, 5),
        "per_candidate": per,
        **ruling,
        "failures": [{"code": r["code"], "kind": r.get("kind"),
                      "error": str(r.get("error"))[:120]}
                     for r in payload["rows"] if not r.get("ok")],
    }
    report["prespec_audit"] = ps.verify_result(STUDY_ID, report)
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 100)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   "
          f"{len(per)} candidates, {len(ok)} folds")
    print("=" * 100)
    print(f"\nPRIMARY  mean paired (native - own decoy mean) = "
          f"{m['paired_native_minus_decoy_mean']}   paired t p = {report['paired_t_p']}"
          f"   Cohen's dz = {m['cohens_dz']}")
    print(f"\n{'candidate':26s} {'target':8s} {'#9 noMSA':>9s} {'native':>8s} {'delta':>7s} "
          f"{'decoy mn':>9s} {'decoy mx':>9s} {'diff':>7s} {'p':>6s} beats")
    for p in per:
        s9 = f"{p['iptm_study9']:.4f}" if p["iptm_study9"] is not None else "   -  "
        dv = f"{p['delta_vs_study9']:+.3f}" if p["delta_vs_study9"] is not None else "   -  "
        print(f"{p['code'][:25]:26s} {p['target']:8s} {s9:>9s} {p['native_iptm']:8.4f} "
              f"{dv:>7s} {p['decoy_mean']:9.4f} {p['decoy_max']:9.4f} "
              f"{p['difference']:+7.4f} {p['empirical_p']:6.3f} "
              f"{'YES' if p['beats_all_decoys'] else 'no'}")
    print(f"\nmean native ipTM {m['mean_native_iptm']} vs mean decoy {m['mean_decoy_iptm']}")
    print(f"mean rise over study #9's single-sequence run: {m['delta_vs_study9']}")
    print(f"candidates beating ALL their decoys: {m['n_candidates_beating_all_decoys']}/{len(per)}")
    print("  " + m["beats_all_decoys_null"]["interpretation"])
    print(f"candidates in the confident band (>0.8): {m['n_candidates_above_0.8']}")
    print("\nPRE-SPECIFIED VERDICTS")
    print(inf.format_verdicts(report))
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
        print(f"  hash {spec.hash()}")
        print(f"  {len(c)} candidates x {1 + N_DECOYS} = {spec.n_planned} folds")
        print(f"  min attainable adjusted p = {spec.min_attainable_p():.4g} (reachable)")
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
