#!/usr/bin/env python3
"""Study #11: can PRODIGY's predicted dG discriminate between peptide candidates?

PRODIGY (Vangone & Bonvin, eLife 2015) is the obvious candidate for putting a real number in
the platform's empty binding-affinity field: it needs only a structure, and structures now
exist. This study tests whether it can carry any peptide-specific signal here, BEFORE it is
wired in.

The falsification hypothesis is mechanistic, not statistical. PRODIGY is

    dG = -0.09459*IC_cc - 0.10007*IC_ca + 0.19577*IC_pp - 0.22671*IC_pa
         + 0.18681*%NIS_apolar + 0.13810*%NIS_charged - 15.9433

and the two %NIS terms are computed over the WHOLE assembled complex. For a 26-47mer peptide
against the 583-residue AChE, the non-interacting surface is essentially AChE's own surface;
the peptide barely perturbs it. The prediction should therefore collapse toward
(intercept + AChE's NIS contribution), modulated only by a handful of interface-contact
counts. If so, the spread across different peptides will be small relative to the -4.3 to
-18.6 kcal/mol range the regression was fit on, and comparable to the spread produced by
merely changing the random seed on ONE peptide.

That last comparison is the decisive one, and it is available for free: study #2 already
produced 3 candidates x 5 seeds against the same receptor, so between-peptide variation and
within-peptide sampler noise can be measured on the same structures.

Applicability, established by retrieval: the word "peptid" occurs ZERO times in the eLife
full text. PRODIGY was fitted on 81 crystal structures of globular protein-protein complexes
with interface BSA 808-3370 A^2, and the authors publish no applicability statement covering
peptides. Any value it produces here is an out-of-domain extrapolation.

    ./.venv/bin/python platform/studies/prodigy_falsification.py --register
    ./.venv/bin/python platform/studies/prodigy_falsification.py --run
    ./.venv/bin/python platform/studies/prodigy_falsification.py --analyse
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import prespec as ps  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "prodigy-discrimination-v1"
ARM_D = Path("/tmp/cbc_variance")
RESULT = REPO / "data" / "study_prodigy.json"

#: The dG range the IC-NIS regression was fitted on (eLife 2015 training set).
FIT_RANGE = (-18.6, -4.3)
FIT_SPAN = FIT_RANGE[1] - FIT_RANGE[0]      # 14.3 kcal/mol


def build_prespec(n: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "Applied to peptide-receptor complexes predicted by Boltz-2, does PRODIGY's "
            "IC-NIS binding-affinity model produce values that discriminate between "
            "different peptide candidates, or does it collapse toward a near-constant set "
            "by the receptor's non-interacting surface?"),
        primary_metric="discrimination_ratio",
        primary_metric_justification=(
            "The discrimination ratio is the between-candidate SD of predicted dG divided by "
            "the within-candidate across-seed SD, on the same structures. It is the right "
            "primary metric because the question is not whether PRODIGY is accurate — no "
            "measured affinity exists for these candidates, so accuracy is unmeasurable here "
            "— but whether its output carries candidate-specific information at all. A ratio "
            "near 1 means the spread between different molecules is no larger than the "
            "spread produced by rerunning the same molecule with a different random seed, "
            "which is the signature of a prediction determined by something other than the "
            "candidate. Using a signal-to-noise ratio rather than a raw SD also makes the "
            "verdict independent of the units and of PRODIGY's absolute calibration, both of "
            "which are out of domain here."),
        decision_threshold=(
            "H1 confirmed if discrimination_ratio < 2.0; H2 confirmed if the between-"
            "candidate range of predicted dG is less than 20% of the 14.3 kcal/mol range the "
            "IC-NIS model was fitted on; H3 confirmed if the %NIS terms contribute more than "
            "80% of the between-candidate variance in the fitted equation, decomposed term "
            "by term."),
        n_planned=n,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed: every arm-D complex already produced by study inference-variance-v1 is "
            "scored exactly once. No new structure is predicted, no complex is added or "
            "removed after scoring begins. A structure PRODIGY cannot parse is reported as a "
            "failure with its error and excluded with the exclusion stated."),
        analysis_plan=(
            "Score each arm-D complex (3 candidates x 5 seeds, AChE chain A + peptide chain "
            "B) with prodigy-prot at 25 C. Record predicted dG, the four IC counts and both "
            "%NIS values. Between-candidate SD is the SD of per-candidate mean dG; "
            "within-candidate SD is pooled as sqrt(mean of per-candidate variances across "
            "seeds); discrimination_ratio is their quotient. Decompose the between-candidate "
            "variance by term by recomputing the fitted equation with each term held at its "
            "grand mean in turn. Holm across the three hypotheses."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_no_discrimination",
                statement=("PRODIGY's predicted dG does not distinguish between different "
                           "peptide candidates any better than reseeding one candidate."),
                predicted_by=("the mechanistic argument that %NIS is set by the receptor, "
                              "not the peptide"),
                confirmed_if="discrimination_ratio < 2.0",
                falsified_if="discrimination_ratio >= 2.0"),
            ps.Hypothesis(
                name="H2_range_collapse",
                statement=("The predicted values occupy a small fraction of the range the "
                           "model was fitted on."),
                predicted_by="the same mechanistic argument",
                confirmed_if=("between-candidate range < 20% of 14.3 kcal/mol, i.e. "
                              "< 2.86 kcal/mol"),
                falsified_if="between-candidate range >= 2.86 kcal/mol"),
            ps.Hypothesis(
                name="H3_nis_dominates",
                statement=("If the values do vary, the variation is driven by the %NIS terms "
                           "rather than by the interface-contact terms."),
                predicted_by=("PRODIGY being usable here would require the OPPOSITE: that "
                              "interface contacts dominate"),
                confirmed_if="%NIS terms account for > 80% of between-candidate variance",
                falsified_if="%NIS terms account for <= 80% of between-candidate variance"),
        ),
        secondary_metrics=(
            "between_candidate_sd", "within_candidate_sd", "between_candidate_range",
            "mean_predicted_dg", "nis_variance_fraction", "ic_counts_per_candidate",
            "fraction_of_fit_range_occupied",
        ),
        exclusions=(
            "Only arm-D complexes from study inference-variance-v1 are scored. Single-chain "
            "structures are excluded by construction: PRODIGY requires two chains, and a "
            "lone peptide has no interface."),
        known_confounds=(
            "1. The structures are Boltz-2 predictions in single-sequence mode, not crystal "
            "structures, and PRODIGY was fitted on crystal structures. A poor interface "
            "prediction would also produce low discrimination, so a confirmed H1 does not by "
            "itself separate 'PRODIGY cannot discriminate' from 'these interfaces are not "
            "real'. Study #2 measured the interface PAE minimum at ~16-17 A for exactly "
            "these complexes, which means the interfaces are NOT confidently placed — this "
            "is stated up front rather than discovered afterwards. 2. Only 3 candidates "
            "against 1 receptor, so nothing here generalises beyond AChE. 3. n=3 for the "
            "between-candidate SD is very small and the ratio is correspondingly imprecise."),
    )


def run() -> None:
    plan = ps.load(STUDY_ID)
    from prodigy_prot.modules.prodigy import Prodigy
    from Bio.PDB import MMCIFParser

    rows: list[dict] = []
    dirs = sorted(d for d in ARM_D.glob("*_D_s*") if d.is_dir())
    parser = MMCIFParser(QUIET=True)

    for i, d in enumerate(dirs, 1):
        cifs = list(d.rglob("*_model_0.cif"))
        code = d.name.split("_D_s")[0]
        seed = int(d.name.split("_D_s")[1])
        if not cifs:
            rows.append({"code": code, "seed": seed, "ok": False, "error": "no cif"})
            continue
        try:
            structure = parser.get_structure("m", str(cifs[0]))
            # Prodigy takes a Bio.PDB Model, not a Structure, and `selection` is a list of
            # comma-joined chain groups that must be disjoint.
            prod = Prodigy(structure[0], selection=["A", "B"], temp=25.0)
            prod.predict(temp=25.0)
            bins = prod.bins
            rec = {
                "code": code, "seed": seed, "ok": True,
                "dg": round(prod.ba_val, 4),
                "kd": prod.kd_val,
                "ic_total": len(prod.ic_network),
                "ic_cc": bins.get("CC", 0), "ic_ca": bins.get("AC", 0),
                "ic_pp": bins.get("PP", 0), "ic_pa": bins.get("AP", 0),
                "ic_cp": bins.get("CP", 0), "ic_aa": bins.get("AA", 0),
                "nis_apolar": round(prod.nis_a, 4), "nis_charged": round(prod.nis_c, 4),
                "structure": str(cifs[0]),
            }
        except Exception as exc:  # noqa: BLE001
            rec = {"code": code, "seed": seed, "ok": False, "error": str(exc)[:250]}
        rows.append(rec)
        head = f"[{i}/{len(dirs)}] {code[:28]:30s} seed={seed}  "
        if rec.get("ok"):
            n_ic = int(rec["ic_cc"] + rec["ic_ca"] + rec["ic_pp"] + rec["ic_pa"])
            print(f"{head}dG={rec['dg']:8.3f}  modelled_ICs={n_ic:3d}  "
                  f"%NIS_apolar={rec['nis_apolar']:.2f}", flush=True)
        else:
            print(f"{head}FAILED: {rec.get('error', '')[:80]}", flush=True)

    RESULT.write_text(json.dumps(
        {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
         "n_observed": sum(1 for r in rows if r.get("ok")), "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")


def analyse() -> int:
    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("ok")]
    if len(ok) < 4:
        print(f"only {len(ok)} scored; cannot analyse")
        return 1

    by: dict[str, list[dict]] = {}
    for r in ok:
        by.setdefault(r["code"], []).append(r)

    means = {c: statistics.fmean(x["dg"] for x in rs) for c, rs in by.items()}
    between_sd = statistics.stdev(means.values()) if len(means) > 1 else 0.0
    variances = [statistics.variance([x["dg"] for x in rs]) for rs in by.values()
                 if len(rs) > 1]
    within_sd = (statistics.fmean(variances)) ** 0.5 if variances else 0.0
    ratio = (between_sd / within_sd) if within_sd > 0 else float("inf")
    brange = max(means.values()) - min(means.values())

    # Term-by-term variance decomposition on the fitted equation.
    COEF = {"ic_cc": -0.09459, "ic_ca": -0.10007, "ic_pp": 0.19577, "ic_pa": -0.22671,
            "nis_apolar": 0.18681, "nis_charged": 0.13810}
    contrib = {k: statistics.stdev([statistics.fmean(x[k] for x in rs) * c
                                    for rs in by.values()]) if len(by) > 1 else 0.0
               for k, c in COEF.items()}
    total = sum(contrib.values()) or 1.0
    nis_frac = (contrib["nis_apolar"] + contrib["nis_charged"]) / total

    p1 = 0.0 if ratio < 2.0 else 1.0
    p2 = 0.0 if brange < 0.20 * 14.3 else 1.0
    p3 = 0.0 if nis_frac > 0.80 else 1.0
    raw = [("H1_no_discrimination", p1), ("H2_range_collapse", p2),
           ("H3_nis_dominates", p3)]
    order = sorted(range(3), key=lambda i: raw[i][1])
    adj = [0.0] * 3
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (3 - rank) * raw[i][1])
        adj[i] = min(1.0, run)

    report = {
        "study_id": STUDY_ID, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(ok), "primary_metric": "discrimination_ratio",
        "metrics": {
            "discrimination_ratio": round(ratio, 3),
            "between_candidate_sd": round(between_sd, 4),
            "within_candidate_sd": round(within_sd, 4),
            "between_candidate_range": round(brange, 4),
            "mean_predicted_dg": round(statistics.fmean(r["dg"] for r in ok), 4),
            "nis_variance_fraction": round(nis_frac, 4),
            "fraction_of_fit_range_occupied": round(brange / 14.3, 4),
            "ic_counts_per_candidate": {
                c: {k: round(statistics.fmean(x[k] for x in rs), 1)
                    for k in ("ic_cc", "ic_ca", "ic_pp", "ic_pa")}
                for c, rs in by.items()},
        },
        "per_candidate_mean_dg": {c: round(v, 3) for c, v in means.items()},
        "term_contributions_sd": {k: round(v, 4) for k, v in contrib.items()},
        "p_holm": {raw[i][0]: round(adj[i], 5) for i in range(3)},
        "verdicts": {
            "H1_no_discrimination": "CONFIRMED" if p1 == 0 else "FALSIFIED",
            "H2_range_collapse": "CONFIRMED" if p2 == 0 else "FALSIFIED",
            "H3_nis_dominates": "CONFIRMED" if p3 == 0 else "FALSIFIED",
        },
    }
    report["prespec_audit"] = ps.verify_result(STUDY_ID, report)
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 90)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   n = {len(ok)}")
    print("=" * 90)
    print(f"\nPRIMARY  discrimination ratio = {m['discrimination_ratio']}")
    print(f"         between-candidate SD {m['between_candidate_sd']} kcal/mol")
    print(f"         within-candidate  SD {m['within_candidate_sd']} kcal/mol (seed noise)")
    print(f"\nrange across candidates: {m['between_candidate_range']} kcal/mol "
          f"= {m['fraction_of_fit_range_occupied']:.1%} of the 14.3 kcal/mol fit range")
    print(f"mean predicted dG: {m['mean_predicted_dg']} kcal/mol")
    print("\nPER-CANDIDATE mean dG and interface contacts")
    for c, v in sorted(report["per_candidate_mean_dg"].items(), key=lambda kv: kv[1]):
        ics = m["ic_counts_per_candidate"][c]
        print(f"  {c[:30]:32s} {v:8.3f}   CC={ics['ic_cc']:5.1f} CA={ics['ic_ca']:5.1f} "
              f"PP={ics['ic_pp']:5.1f} PA={ics['ic_pa']:5.1f}")
    print(f"\n%NIS share of between-candidate variance: {m['nis_variance_fraction']:.1%}")
    print("\nPRE-SPECIFIED VERDICTS")
    for h, v in report["verdicts"].items():
        print(f"  {h:26s} {v:10s} Holm p = {report['p_holm'][h]}")
    a = report["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 90)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    if a.register:
        n = len([d for d in ARM_D.glob("*_D_s*") if d.is_dir()])
        spec = build_prespec(n)
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        print(f"registered {spec.register().relative_to(REPO)}")
        print(f"  hash {spec.hash()}   n = {n} complexes")
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
