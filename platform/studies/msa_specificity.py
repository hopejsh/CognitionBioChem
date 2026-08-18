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

from cbc import prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402
from studies.candidate_screen import CANDIDATE_TARGETS, _candidates, _receptor_seq, _scrambles  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "msa-specificity-v1"
WORK = Path("/tmp/cbc_msa10")
RESULT = REPO / "data" / "study_msa_specificity.json"

N_DECOYS = 10
SEED = 1
IPTM_CONFIDENT = 0.8
IPTM_FAILED = 0.6


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
            "here because the receptors range from 212 to 583 residues and ipTM depends on "
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
            "random.Random(1). Predict receptor mature chain plus peptide with Boltz-2 "
            "2.2.1, --use_msa_server, gpu, seed 1, diffusion_samples 1, recycling_steps 3. "
            "For each candidate compute native ipTM minus the mean of its decoys; test the "
            "six differences against zero with a paired t-test and report Cohen's dz. "
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
        known_confounds=(
            "1. The ColabFold MSA server is a remote service whose returned alignment can "
            "change between calls, so this arm confounds MSA CONTENT with MSA PRESENCE; a "
            "rerun may not reproduce byte-identically even at fixed seed. 2. The MSA helps "
            "the RECEPTOR, which has thousands of homologues, far more than the peptide, "
            "which has none — so a rise in ipTM may reflect a better-folded receptor rather "
            "than a better interface. ipTM is interface-restricted, which mitigates but does "
            "not eliminate this. 3. n = 6 paired differences gives a paired t-test little "
            "power; only a large and consistent effect will register. 4. A positive result "
            "here bounds what this pipeline distinguishes, not what the molecules do in a "
            "cell."),
    )


def run() -> None:
    plan = ps.load(STUDY_ID)
    cands = _candidates(limit=6)
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
                    use_msa_server=True, timeout=7200)
            except Exception as exc:  # noqa: BLE001
                print(f"raised: {str(exc)[:40]}")
                rows.append({**c, "kind": kind, "ok": False, "error": str(exc)[:200]})
                continue
            dt = time.time() - t0
            conf = r.get("confidence") or {}
            ok = r.get("returncode") == 0 and conf.get("iptm") is not None
            rec = {**c, "kind": kind, "peptide_used": pep, "ok": ok,
                   "seconds": round(dt, 1), "iptm": conf.get("iptm"),
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

    p1 = t_p if (diffs and statistics.fmean(diffs) > 0) else 1.0
    p2 = 0.0 if n_conf_spec > 0 else 1.0
    p3 = 0.0 if (d9 and statistics.fmean(d9) > 0.15) else 1.0
    raw = [("H1_natives_separate_from_decoys", p1),
           ("H2_a_candidate_is_confident_and_specific", p2),
           ("H3_msa_raises_natives", p3)]
    order = sorted(range(3), key=lambda i: raw[i][1])
    adj = [0.0] * 3
    rm = 0.0
    for rank, i in enumerate(order):
        rm = max(rm, (3 - rank) * raw[i][1])
        adj[i] = min(1.0, rm)

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
            "delta_vs_study9": round(statistics.fmean(d9), 4) if d9 else None,
            "n_candidates_above_0.8": sum(1 for p in per
                                          if p["native_iptm"] > IPTM_CONFIDENT),
            "wall_clock_seconds_per_fold": round(statistics.fmean(
                [r["seconds"] for r in ok if r.get("seconds")]), 1) if ok else None,
        },
        "paired_t_p": round(t_p, 5),
        "per_candidate": per,
        "p_holm": {raw[i][0]: round(adj[i], 5) for i in range(3)},
        "verdicts": {
            "H1_natives_separate_from_decoys": "CONFIRMED" if adj[0] < 0.05 and diffs
                                               and statistics.fmean(diffs) > 0 else "FALSIFIED",
            "H2_a_candidate_is_confident_and_specific": "CONFIRMED" if p2 == 0 else "FALSIFIED",
            "H3_msa_raises_natives": "CONFIRMED" if p3 == 0 else "FALSIFIED",
        },
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
    print(f"candidates in the confident band (>0.8): {m['n_candidates_above_0.8']}")
    print("\nPRE-SPECIFIED VERDICTS")
    for h, v in report["verdicts"].items():
        print(f"  {h:42s} {v:10s} Holm p = {report['p_holm'][h]}")
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
        c = _candidates(limit=6)
        spec = build_prespec(len(c) * (1 + N_DECOYS), len(c))
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
