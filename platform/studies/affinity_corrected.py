#!/usr/bin/env python3
"""Study #8: the affinity head against corrected references, with the noise floor measured.

Study v1 (`ache-affinity-ranking-v1`) found Spearman rho = 0.304, CI spanning zero, and named
reference quality as the binding limit: 13 of 17 references rested on a SINGLE ChEMBL record
because `build_target_corpus` draws a flat activity budget across a whole target rather than
retrieving every record per compound. For huperzine A that single record sat at the 17th
percentile of 25 records spanning 3.99 log10 units.

This study repeats the analysis on the SAME predictions with complete references, so the
question "was reference quality the limit?" is answered by measurement rather than assertion.
Re-using the predictions is deliberate: changing only one variable is what makes the
comparison interpretable, and it costs no new inference.

The second contribution is a measured noise floor. Each reference now carries its own log10
dispersion across independent assays, so the model's error can be compared against the
error of the thing it is being scored against — which study v1 could only cite from the
literature (Kalliokoski's 0.68 log10) rather than measure in situ.

    ./.venv/bin/python platform/studies/affinity_corrected.py --register
    ./.venv/bin/python platform/studies/affinity_corrected.py --run
    ./.venv/bin/python platform/studies/affinity_corrected.py --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import corpus, inference as inf, prespec as ps  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "affinity-corrected-v1"
V1 = REPO / "data" / "study_ache_affinity.json"
RESULT = REPO / "data" / "study_affinity_corrected.json"
TARGET = "CHEMBL220"      # human acetylcholinesterase



def prespec_args() -> tuple:
    """The arguments --register builds the plan with.

    Named once so the registration path and the hash-stability test cannot disagree.
    Without it the test skipped this study, and the skip was reported with a
    hard-coded True — a check that could not fail, covering 3 of 8 studies.
    """
    return (len([r for r in json.loads(V1.read_text())["rows"] if r.get("ok")]),)

def build_prespec(n: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "Does the Boltz-2 affinity head rank AChE inhibitor potency once each reference "
            "value is the median over ALL ChEMBL records for that compound-target pair "
            "rather than whichever single record a flat activity budget happened to "
            "capture? And how does the model's error compare with the measured dispersion "
            "of the references themselves?"),
        primary_metric="spearman_rho_corrected",
        primary_metric_justification=(
            "Rank correlation against corrected references is the direct successor to study "
            "v1's primary metric, so the two are comparable and the effect of the reference "
            "fix is readable as a difference. Rank rather than absolute error because the "
            "head is fitted to pooled Ki/Kd/IC50/EC50 labels and its absolute level is an "
            "uncalibrated corpus-average offset, so only its ordering has a defined "
            "referent. The same predictions are reused deliberately: with the model output "
            "held fixed, any change in rho is attributable to the references alone."),
        decision_threshold=(
            "H1 confirmed if Spearman rho with corrected references exceeds 0.5 and its "
            "bootstrap 95% CI excludes zero; H2 confirmed if rho improves by more than 0.15 "
            "over study v1's 0.304; H3 confirmed if the model's median absolute error "
            "exceeds the median reference dispersion, i.e. the model is the larger error "
            "term."),
        n_planned=n,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed: every compound scored in study v1 that also returns at least one ChEMBL "
            "activity record under complete retrieval is included, exactly once. No new "
            "prediction is made and no compound is added. Compounds whose complete retrieval "
            "returns nothing are excluded with the reason recorded."),
        analysis_plan=(
            "For each compound from study v1, retrieve every IC50/Ki/Kd/EC50/AC50/XC50 "
            "record against CHEMBL220 via the ChEMBL Elasticsearch backend, discarding "
            "inequality-qualified values because a bound is not a measurement. The reference "
            "is the median in nM; the reference dispersion is the standard deviation of "
            "log10 values across records. Predicted pIC50 is 6 - affinity_pred_value, "
            "unchanged from v1. Report Spearman rho with a bootstrap 95% CI (10000 "
            "resamples, seed 0), the change from v1, and the model error against the "
            "reference dispersion. Holm across the three hypotheses."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_ranking_with_good_references",
                statement=("With complete references the affinity head ranks AChE potency "
                           "better than chance."),
                predicted_by="the hypothesis that reference quality was v1's binding limit",
                confirmed_if="Spearman rho > 0.5 and the bootstrap 95% CI excludes zero",
                falsified_if="rho <= 0.5 or the CI includes zero"),
            ps.Hypothesis(
                name="H2_reference_fix_matters",
                statement=("Correcting the references materially improves the measured "
                           "correlation, i.e. v1 was measuring reference noise."),
                predicted_by="the reference-quality explanation of v1's null result",
                confirmed_if="rho improves by more than 0.15 over v1's 0.304",
                falsified_if=("rho improves by 0.15 or less, which would mean the "
                              "references were not the limit and the model is")),
            ps.Hypothesis(
                name="H3_model_dominates_error",
                statement=("The model's error is larger than the measurement's, so the "
                           "model is the term worth improving."),
                predicted_by=("the alternative explanation, that the model rather than the "
                              "references limits v1"),
                confirmed_if=("median |predicted - reference| in log10 exceeds the median "
                              "reference log10 dispersion"),
                falsified_if=("model error does not exceed reference dispersion, in which "
                              "case the two are not separable at this n and no claim about "
                              "model accuracy is licensed")),
        ),
        secondary_metrics=(
            "rho_v1", "delta_rho", "median_absolute_error_log10",
            "median_reference_log10_sd", "median_records_per_compound",
            "n_compounds_with_single_record", "max_reference_log10_spread",
            "pearson_r", "kendall_tau",
        ),
        exclusions=(
            "Compounds from study v1 for which complete retrieval returns no usable record "
            "are excluded and listed. Inequality-qualified activities (>, <) are discarded "
            "before forming the reference because a bound averaged with measurements biases "
            "the result."),
        known_confounds=(
            "1. The predictions are reused from study v1 and were made in single-sequence "
            "mode, so their absolute quality is a lower bound; only the reference variable "
            "changed. 2. Medians pool IC50, Ki and Kd, which are different physical "
            "quantities — this is the same pooling the head itself was trained under, so it "
            "is consistent, but it is not a clean thermodynamic reference. 3. One target "
            "only, so nothing generalises beyond AChE. 4. n is under 20, so the bootstrap "
            "interval on rho is wide and H2's 0.15 threshold is comparable to the sampling "
            "noise on rho itself."),
    )


def run() -> None:
    plan = ps.load(STUDY_ID)
    v1 = json.loads(V1.read_text())
    rows = []
    src = [r for r in v1["rows"] if r.get("ok")]
    for i, r in enumerate(src, 1):
        cid = r["chembl"]
        print(f"[{i}/{len(src)}] {r['name'][:28]:30s} ", end="", flush=True)
        try:
            ref = corpus.reference_potency(cid, TARGET)
        except Exception as exc:  # noqa: BLE001
            print(f"retrieval failed: {str(exc)[:50]}")
            rows.append({**r, "corrected": False, "error": str(exc)[:200]})
            continue
        if not ref.get("median_nm"):
            print("no usable records")
            rows.append({**r, "corrected": False, "error": "no records"})
            continue
        rec = {**r, "corrected": True, "reference": ref,
               "meas_pic50_v1": r["meas_pic50"],
               "meas_pic50_corrected": -math.log10(ref["median_nm"] * 1e-9)}
        rec["error_log10_corrected"] = rec["pred_pic50"] - rec["meas_pic50_corrected"]
        rows.append(rec)
        print(f"n={ref['n']:2d} assays={ref['n_assays']:2d}  median={ref['median_nm']:>9.4g} nM  "
              f"spread={ref['log10_spread']:.2f}  (v1 used {r['nm']:.4g} nM)")

    RESULT.write_text(json.dumps(
        {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
         "n_observed": sum(1 for r in rows if r.get("corrected")), "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")


def analyse() -> int:
    from scipy import stats
    import numpy as np

    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("corrected")]
    if len(ok) < 4:
        print(f"only {len(ok)} usable; cannot analyse")
        return 1

    pred = np.array([r["pred_pic50"] for r in ok])
    meas = np.array([r["meas_pic50_corrected"] for r in ok])
    err = np.abs(pred - meas)
    disp = [r["reference"]["log10_sd"] for r in ok
            if r["reference"].get("log10_sd") is not None]

    rr = stats.spearmanr(pred, meas)
    rho, p_rho = float(rr.statistic), float(rr.pvalue)
    rng = np.random.default_rng(0)
    boot = [stats.spearmanr(pred[s], meas[s]).statistic
            for s in (rng.integers(0, len(ok), len(ok)) for _ in range(10000))]
    boot = [b for b in boot if not math.isnan(b)]
    ci = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))

    rho_v1 = 0.304
    delta = rho - rho_v1
    med_err = float(np.median(err))
    med_disp = float(statistics.median(disp)) if disp else None

    # H1 is decided by a bootstrap interval, H2 and H3 by threshold comparisons. None is a
    # test statistic, so this study emits no p-values. See cbc/inference.py.
    ruling = inf.decide(criteria={
        "H1_ranking_with_good_references": inf.Criterion(
            rho > 0.5 and ci[0] > 0, [round(rho, 4), [round(ci[0], 4), round(ci[1], 4)]],
            "Spearman rho > 0.5 with a bootstrap 95% CI excluding 0"),
        "H2_reference_fix_matters": inf.Criterion(
            delta > 0.15, round(delta, 4),
            "correcting the references moves rho by more than 0.15"),
        "H3_model_dominates_error": inf.Criterion(
            med_disp is not None and med_err > med_disp,
            [round(med_err, 4), round(med_disp, 4) if med_disp is not None else None],
            "median model error exceeds median inter-laboratory dispersion"),
    }, tests={})

    singles = sum(1 for r in ok if r["reference"]["n"] == 1)
    report = {
        "study_id": STUDY_ID, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(ok), "primary_metric": "spearman_rho_corrected",
        "metrics": {
            "spearman_rho_corrected": round(rho, 4),
            "rho_v1": rho_v1, "delta_rho": round(delta, 4),
            "median_absolute_error_log10": round(med_err, 4),
            "median_reference_log10_sd": round(med_disp, 4) if med_disp else None,
            "median_records_per_compound": statistics.median(
                [r["reference"]["n"] for r in ok]),
            "n_compounds_with_single_record": singles,
            "max_reference_log10_spread": round(max(
                r["reference"]["log10_spread"] for r in ok), 3),
            "pearson_r": round(float(stats.pearsonr(pred, meas).statistic), 4),
            "kendall_tau": round(float(stats.kendalltau(pred, meas).statistic), 4),
        },
        "spearman_ci95": [round(c, 4) for c in ci],
        "spearman_p": round(p_rho, 5),
        **ruling,
        "per_compound": [
            {"name": r["name"], "records": r["reference"]["n"],
             "v1_nm": r["nm"], "corrected_nm": r["reference"]["median_nm"],
             "log10_spread": r["reference"]["log10_spread"],
             "pred_pic50": round(r["pred_pic50"], 3),
             "error_v1": round(r["error_log10"], 3),
             "error_corrected": round(r["error_log10_corrected"], 3)}
            for r in sorted(ok, key=lambda x: -abs(x["error_log10_corrected"]))],
    }
    report["prespec_audit"] = ps.verify_result(STUDY_ID, report)
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 94)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   n = {len(ok)}")
    print("=" * 94)
    print(f"\nPRIMARY  Spearman rho (corrected references) = {m['spearman_rho_corrected']}")
    print(f"         95% CI {report['spearman_ci95']}   p = {report['spearman_p']}")
    print(f"         study v1 with single-record references: {m['rho_v1']}   "
          f"change {m['delta_rho']:+.4f}")
    print(f"\nREFERENCE QUALITY  median {m['median_records_per_compound']} records/compound "
          f"(v1 effectively 1), {m['n_compounds_with_single_record']} still single-record, "
          f"widest spread {m['max_reference_log10_spread']} log10")
    print(f"\nERROR DECOMPOSITION")
    print(f"  model median |error|        {m['median_absolute_error_log10']} log10")
    print(f"  reference median dispersion {m['median_reference_log10_sd']} log10")
    print(f"  -> {'model' if ruling['criteria']['H3_model_dominates_error']['met'] else 'reference'} is the larger error term")
    print("\nPER COMPOUND (largest corrected error first)")
    print(f"  {'compound':30s} {'recs':>4s} {'v1 nM':>10s} {'corr nM':>10s} "
          f"{'err v1':>7s} {'err corr':>9s}")
    for r in report["per_compound"]:
        print(f"  {r['name'][:29]:30s} {r['records']:4d} {r['v1_nm']:>10.4g} "
              f"{r['corrected_nm']:>10.4g} {r['error_v1']:>+7.2f} {r['error_corrected']:>+9.2f}")
    print("\nPRE-SPECIFIED VERDICTS")
    print(inf.format_verdicts(report))
    a = report["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 94)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    for f in ("register", "run", "analyse"):
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
        print(f"  hash {spec.hash()}   n = {n}")
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
