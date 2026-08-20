#!/usr/bin/env python3
"""Study: does the Boltz-2 affinity head rank AChE inhibitor potency, and does its error
carry a memorization signature?

This study exists to settle a specific dispute. One reviewer held that the single Huperzine A
result (2.41 log error) is strong evidence against the affinity head; another held that a
cherry-picked n=1 licenses nothing. Both are arguing because n=1. This raises n to 17 and
pre-registers the decision rule before any prediction is made.

    ./.venv/bin/python platform/studies/ache_affinity_benchmark.py --register
    ./.venv/bin/python platform/studies/ache_affinity_benchmark.py --run
    ./.venv/bin/python platform/studies/ache_affinity_benchmark.py --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import inference as inf, prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "ache-affinity-ranking-v1"
BENCH = REPO / "data" / "study_inputs" / "ache_bench.json"
WORK = Path("/tmp/ache_affinity")
RESULT = REPO / "data" / "study_ache_affinity.json"

#: Human AChE, UniProt P22303, mature chain (SIGNAL 1-31, CHAIN 32-614).
ACHE_MATURE = REPO / "data" / "study_inputs" / "ache_mature.txt"



def prespec_args() -> tuple:
    """The arguments --register builds the plan with.

    Named once so the registration path and the hash-stability test cannot disagree
    about them: the test previously guessed, guessed wrong for the two-argument
    studies, and reported drift that did not exist.
    """
    return (len(json.loads(BENCH.read_text())),)

def build_prespec(n: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "Does the Boltz-2 affinity head rank the potency of AChE inhibitors on this "
            "hardware in single-sequence mode, and does its per-compound error correlate "
            "with how heavily that compound has been assayed (a memorization signature)?"),
        primary_metric="spearman_rho_predicted_vs_measured_pIC50",
        primary_metric_justification=(
            "Rank correlation, not absolute error, is the primary metric for three reasons. "
            "(1) The head was trained on POOLED Ki/Kd/IC50/EC50 labels, so its output has no "
            "single physical referent and its absolute scale is not interpretable, whereas "
            "its ordering can be. (2) The reference values are medians over ChEMBL records "
            "from different laboratories and assay conditions, carrying an inter-laboratory "
            "uncertainty that absolute error would attribute to the model. (3) The decision "
            "the platform would actually make with this model is a ranking decision — which "
            "compound to pursue — so ranking is the task-relevant quantity. Absolute error "
            "is retained as a SECONDARY metric because it is what the disputed Huperzine A "
            "observation measured, and dropping it would make this study unable to speak to "
            "the dispute it was designed to settle."),
        decision_threshold=(
            "H1 confirmed if Spearman rho > 0.4 with Holm-adjusted p < 0.05; "
            "H2 confirmed if Spearman(|error|, n_chembl_records) < -0.3 with Holm-adjusted "
            "p < 0.05; H3 confirmed if the Huperzine A absolute error is within 2 SD of the "
            "mean absolute error across the set."),
        n_planned=n,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed n: every compound in the pre-built set is predicted exactly once with "
            "seed=1. No interim analysis, no compound added or removed after predictions "
            "begin. A compound whose prediction fails technically is reported as a failure "
            "and excluded from the correlation with the exclusion stated, not silently "
            "dropped."),
        analysis_plan=(
            "For each compound, predict the AChE(P22303 mature chain) + ligand complex with "
            "Boltz-2 2.2.1, msa=empty, accelerator=gpu(MPS), recycling_steps=3, "
            "diffusion_samples=1, seed=1. Read affinity_pred_value y and convert to a "
            "predicted pIC50 as 6 - y (y is log10 IC50 in uM). Measured pIC50 is "
            "-log10(median ChEMBL value in M). Compute Spearman rho (scipy.stats.spearmanr) "
            "for H1, Spearman of absolute error against the compound's ChEMBL record count "
            "for H2, and a z-score for Huperzine A for H3. Apply Holm across the three "
            "tests. Report rho with a bootstrap 95% CI (10000 resamples, seed 0)."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_ranking_ability",
                statement=("The affinity head ranks AChE inhibitor potency better than "
                           "chance in this configuration."),
                predicted_by="position B (the head is usable; the single result was noise)",
                confirmed_if="Spearman rho > 0.4 and Holm-adjusted p < 0.05",
                falsified_if=("Spearman rho <= 0.4, or the bootstrap 95% CI for rho "
                              "includes 0")),
            ps.Hypothesis(
                name="H2_memorization_signature",
                statement=("Prediction error is smaller for compounds with more ChEMBL "
                           "records, i.e. the head performs better on well-studied "
                           "compounds, which is the signature of memorization rather than "
                           "generalization."),
                predicted_by="position A (heavily assayed pairs are likely memorized)",
                confirmed_if=("Spearman(|error|, n_chembl_records) < -0.3 with "
                              "Holm-adjusted p < 0.05"),
                falsified_if=("Spearman(|error|, n_chembl_records) >= -0.3, or its "
                              "Holm-adjusted p >= 0.05")),
            ps.Hypothesis(
                name="H3_huperzine_representative",
                statement=("The disputed Huperzine A error is representative of the "
                           "method's typical error rather than an outlier."),
                predicted_by="position B (the single result was cherry-picked and atypical)",
                confirmed_if=("the Huperzine A absolute error lies within 2 SD of the mean "
                              "absolute error across the set"),
                falsified_if=("the Huperzine A absolute error lies more than 2 SD from the "
                              "mean absolute error")),
        ),
        secondary_metrics=(
            "mean_absolute_error_log10",
            "rmse_log10",
            "pearson_r_pIC50",
            "kendall_tau",
            "huperzine_absolute_error_log10",
            "fraction_within_1_log",
        ),
        exclusions=(
            "Compounds without a measured IC50/Ki/Kd against CHEMBL220, without a parseable "
            "structure, or above the affinity head's documented 128-heavy-atom limit are "
            "excluded before registration, not after seeing predictions."),
        known_confounds=(
            "1. Single-sequence mode (msa=empty) is documented by Boltz to degrade accuracy, "
            "so this measures a lower bound on the method's capability, not its ceiling. "
            "2. ChEMBL record count is a proxy for how well studied a compound is, not for "
            "membership in the training set; Boltz-2 has not published an enumerable "
            "affinity training split, so H2 tests a signature of memorization rather than "
            "memorization itself. 3. Reference values are medians across heterogeneous "
            "assays and organisms. 4. The set is 17 compounds from one target, so nothing "
            "here generalizes to other targets."),
    )


def run_predictions() -> dict:
    rows = json.loads(BENCH.read_text())
    prot = ACHE_MATURE.read_text().strip()
    plan = ps.load(STUDY_ID)
    out: list[dict] = []

    for i, r in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {r['name'][:32]:34s} ", end="", flush=True)
        d = WORK / r["chembl"]
        try:
            res = st.run_boltz(
                [st.Chain("A", prot, "protein", msa="empty"),
                 st.Chain("B", r["smiles"], "smiles")],
                d, affinity_binder="B", accelerator="gpu",
                recycling_steps=3, diffusion_samples=1, seed=1)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {exc}")
            out.append({**r, "ok": False, "error": str(exc)[:300]})
            continue
        if res.get("returncode") != 0:
            print("FAILED")
            out.append({**r, "ok": False,
                        "error": (res.get("stderr_tail") or "")[-300:]})
            continue
        aff = res.get("affinity") or {}
        y = aff.get("affinity_pred_value")
        rec = {**r, "ok": y is not None, "y": y,
               "pred_pic50": (6 - y) if y is not None else None,
               "meas_pic50": -math.log10(r["nm"] * 1e-9),
               "binary_prob": aff.get("affinity_probability_binary"),
               "confidence": res.get("confidence", {}).get("confidence_score"),
               "iptm": res.get("confidence", {}).get("iptm")}
        if rec["ok"]:
            rec["error_log10"] = rec["pred_pic50"] - rec["meas_pic50"]
            print(f"y={y:+.3f}  pred pIC50 {rec['pred_pic50']:.2f}  "
                  f"meas {rec['meas_pic50']:.2f}  err {rec['error_log10']:+.2f}")
        else:
            print("no affinity value returned")
        out.append(rec)

    payload = {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
               "n_observed": sum(1 for r in out if r.get("ok")),
               "rows": out}
    RESULT.write_text(json.dumps(payload, indent=1))
    return payload


def analyse() -> int:
    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("ok")]
    if len(ok) < 3:
        print(f"only {len(ok)} successful predictions; cannot analyse")
        return 1

    from scipy import stats
    import numpy as np

    pred = np.array([r["pred_pic50"] for r in ok])
    meas = np.array([r["meas_pic50"] for r in ok])
    err = np.abs(pred - meas)
    nrec = np.array([r["n_records"] for r in ok])

    rho, p1 = stats.spearmanr(pred, meas)
    rho2, p2 = stats.spearmanr(err, nrec)
    hup = next((r for r in ok if "HUPERZINE" in r["name"].upper()), None)
    hup_err = abs(hup["error_log10"]) if hup else None
    z = ((hup_err - err.mean()) / err.std(ddof=1)) if hup_err is not None else None
    p3 = 2 * (1 - stats.norm.cdf(abs(z))) if z is not None else 1.0

    # All three ARE genuine tests here (two Spearman p-values and a two-sided z), so this is
    # the one study whose Holm family was legitimate. It goes through the shared path anyway,
    # which validates that every member really is a p-value rather than a 0/1 sentinel.
    tests = {}
    for name, pv in (("H1_ranking_ability", p1), ("H2_memorization_signature", p2),
                     ("H3_huperzine_representative", p3)):
        tests[name] = float(min(max(float(pv), 1e-300), 1.0))
    ruling = inf.decide(criteria={}, tests=tests)
    adj = [ruling["p_holm"][n] for n in
           ("H1_ranking_ability", "H2_memorization_signature", "H3_huperzine_representative")]

    rng = np.random.default_rng(0)
    boot = [stats.spearmanr(pred[s], meas[s]).statistic
            for s in (rng.integers(0, len(ok), len(ok)) for _ in range(10000))]
    boot = [b for b in boot if not math.isnan(b)]
    ci = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))

    verdicts = {
        "H1_ranking_ability": "CONFIRMED" if (rho > 0.4 and adj[0] < 0.05 and ci[0] > 0)
                              else "FALSIFIED",
        "H2_memorization_signature": "CONFIRMED" if (rho2 < -0.3 and adj[1] < 0.05)
                                     else "FALSIFIED",
        # Decided by the effect size, not by the test: H3 asks whether Huperzine A is
        # REPRESENTATIVE, which is confirmed by the absence of a deviation. Its p is reported
        # for completeness but must not gate the verdict, because failing to reject is not
        # evidence of equivalence and the adjusted p only ever moves in the permissive
        # direction. See cbc/inference.py.
        "H3_huperzine_representative": "CONFIRMED" if (z is not None and abs(z) <= 2)
                                       else "FALSIFIED",
    }
    metrics = {
        "spearman_rho_predicted_vs_measured_pIC50": round(float(rho), 4),
        "mean_absolute_error_log10": round(float(err.mean()), 4),
        "rmse_log10": round(float(np.sqrt(((pred - meas) ** 2).mean())), 4),
        "pearson_r_pIC50": round(float(stats.pearsonr(pred, meas).statistic), 4),
        "kendall_tau": round(float(stats.kendalltau(pred, meas).statistic), 4),
        "huperzine_absolute_error_log10": round(hup_err, 4) if hup_err else None,
        "fraction_within_1_log": round(float((err <= 1).mean()), 4),
    }
    report = {
        **{k: payload[k] for k in ("study_id", "prespec_hash")},
        "n_observed": len(ok),
        "primary_metric": "spearman_rho_predicted_vs_measured_pIC50",
        "metrics": metrics,
        "spearman_ci95": [round(c, 4) for c in ci],
        "memorization_rho": round(float(rho2), 4),
        "huperzine_z": round(float(z), 3) if z is not None else None,
        **{k: v for k, v in ruling.items() if k != "verdicts"},
        "verdicts": verdicts,
    }
    audit = ps.verify_result(STUDY_ID, report)
    report["prespec_audit"] = audit
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    print("=" * 88)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   n = {len(ok)}")
    print("=" * 88)
    print(f"\nPRIMARY  Spearman rho = {rho:.3f}  95% CI [{ci[0]:.3f}, {ci[1]:.3f}]  "
          f"raw p = {p1:.4g}  Holm p = {adj[0]:.4g}")
    print("\nSECONDARY")
    for k, v in metrics.items():
        if k != report["primary_metric"]:
            print(f"  {k:38s} {v}")
    print("\nPRE-SPECIFIED VERDICTS")
    for h, v in verdicts.items():
        print(f"  {h:32s} {v:10s} Holm p = {report['p_holm'][h]:.4g}")
    print(f"\nmemorization Spearman(|err|, n_records) = {rho2:+.3f}")
    if z is not None:
        print(f"Huperzine A |err| = {hup_err:.2f} log, z = {z:+.2f} vs the set mean "
              f"{err.mean():.2f} +/- {err.std(ddof=1):.2f}")
    print(f"\nprespec audit: {'CONFIRMATORY' if audit['confirmatory'] else 'DEVIATIONS'}")
    for d in audit["deviations"]:
        print("  -", d)
    print("=" * 88)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()

    if a.register:
        rows = json.loads(BENCH.read_text())
        spec = build_prespec(*prespec_args())
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        path = spec.register()
        print(f"registered {path.relative_to(REPO)}")
        print(f"  hash {spec.hash()}")
        print(f"  n = {spec.n_planned}, K = {spec.n_comparisons}, "
              f"{spec.multiplicity_correction}, alpha = {spec.alpha}")
        print(f"  min attainable adjusted p = {spec.min_attainable_p():.4g}  (reachable)")
        for h in spec.hypotheses:
            print(f"  {h.name:32s} predicted by {h.predicted_by[:44]}")
        return 0
    if a.run:
        run_predictions()
        return 0
    if a.analyse:
        return analyse()
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
