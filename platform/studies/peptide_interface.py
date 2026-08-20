#!/usr/bin/env python3
"""Study #7: peptide-receptor interface accuracy, calibration, and assay power.

This study answers the two questions that gate everything downstream:

  CALIBRATION   Given an ipTM on a peptide-receptor complex predicted on this hardware,
                what is the probability the interface is actually right?
  POWER         If a genuine peptide binder were in the candidate set, would this pipeline
                find it?

The second is the gate for study #9. A screen that cannot recover KNOWN binders cannot
license a positive claim about unknown ones, and running it anyway would produce negatives
that are indistinguishable from method failure. So the honest sequence is to measure the
recovery rate on complexes whose answer is known, and only then decide whether predicting the
platform's own candidates can mean anything.

Scoring uses DockQ, the CAPRI-standard measure, from the reference implementation. DockQ 2.1.3
pins numpy<2 while this project's scipy/pandas/prodigy stack needs numpy>=2, so DockQ lives in
its own environment (.venvdockq) and is invoked as a subprocess rather than compromising
either side.

    ./.venv/bin/python platform/studies/peptide_interface.py --curate
    ./.venv/bin/python platform/studies/peptide_interface.py --register
    ./.venv/bin/python platform/studies/peptide_interface.py --run
    ./.venv/bin/python platform/studies/peptide_interface.py --analyse
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import inference as inf, posebench as pb, prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "peptide-interface-v1"
SET = REPO / "data" / "peptide_benchmark_set.json"
WORK = Path("/tmp/cbc_pep")
REFS = Path("/tmp/cbc_pep_refs")
RESULT = REPO / "data" / "study_peptide_interface.json"
DOCKQ = REPO / ".venvdockq" / "bin" / "DockQ"

#: CAPRI acceptable-quality threshold. Below this the model is simply wrong.
DOCKQ_ACCEPTABLE = 0.23
#: AlphaFold3's published interpretation bands for ipTM.
IPTM_CONFIDENT = 0.8
IPTM_FAILED = 0.6


def curate(n_per: int = 8) -> None:
    """Build the stratified set. Pre-cutoff complexes could be in training; post could not."""
    out: list[dict] = []
    for split, (a, b) in (("pre_cutoff", ("2015-01-01", "2023-05-31")),
                          ("post_cutoff", ("2023-07-01", "2026-06-30"))):
        seen_rec: set[str] = set()
        ids = pb.search_peptide_complexes(a, b, limit=300)
        print(f"{split}: {len(ids)} candidates")
        for pid in ids:
            if sum(1 for e in out if e["split"] == split) >= n_per:
                break
            d = pb.describe_peptide_complex(pid)
            if not d:
                continue
            # One entry per receptor, so no single well-studied target dominates a stratum.
            key = d["receptor_uniprot"] or d["receptor_seq"][:40]
            if key in seen_rec:
                continue
            seen_rec.add(key)
            d["split"] = split
            out.append(d)
            print(f"  {d['pdb_id']} {d['deposited']} pep={d['peptide_len']:2d}aa "
                  f"rec={d['receptor_len']:3d}aa {d['receptor_uniprot']}")
    SET.write_text(json.dumps(out, indent=1))
    print(f"\ncurated {len(out)} complexes -> {SET.relative_to(REPO)}")



def prespec_args() -> tuple:
    """The arguments --register builds the plan with.

    Named once so the registration path and the hash-stability test cannot disagree
    about them: the test previously guessed, guessed wrong for the two-argument
    studies, and reported drift that did not exist.
    """
    return (len(json.loads(SET.read_text())),)

def build_prespec(n: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "On peptide-receptor complexes predicted with Boltz-2 on this hardware, what "
            "fraction of interfaces reach CAPRI acceptable quality, how well does ipTM "
            "predict that, and does the pipeline have enough sensitivity for a screen of "
            "unknown candidates to be interpretable?"),
        primary_metric="fraction_dockq_acceptable",
        primary_metric_justification=(
            "The fraction of predictions reaching DockQ >= 0.23 is the CAPRI acceptable-"
            "quality rate, the field's standard success criterion for a docked complex, so "
            "it is directly comparable to published numbers and is the quantity that "
            "determines whether a screen has any sensitivity. It is preferred over mean "
            "DockQ because DockQ is a bounded composite of three terms and its mean is not "
            "interpretable as a physical quantity, and preferred over ipTM because ipTM is "
            "the model's self-assessment — using it to score itself would measure "
            "confidence rather than correctness. This study exists precisely to test "
            "whether that self-assessment is trustworthy, so it cannot also be the "
            "criterion."),
        decision_threshold=(
            "H1 confirmed if the overall fraction_dockq_acceptable > 0.3; H2 confirmed if "
            "Spearman rho between ipTM and DockQ exceeds 0.6 with p < 0.05; H3 (THE GATE) "
            "confirmed if the pre-cutoff stratum — complexes whose answer the model could "
            "have memorised — reaches fraction_dockq_acceptable > 0.5."),
        n_planned=n,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed: each curated complex is predicted exactly once at seed 1 in a fixed "
            "order, then scored with DockQ. No complex is added or removed after the first "
            "prediction. Technical failures are recorded with their reason and excluded."),
        analysis_plan=(
            "Predict each complex with Boltz-2 2.2.1 from the two deposited construct "
            "sequences, msa=empty, gpu, seed 1, diffusion_samples 1. Score against the "
            "crystal with DockQ 2.1.3 using an explicit chain mapping from the predicted "
            "chains to the deposited receptor and peptide chains. Report "
            "fraction_dockq_acceptable overall and per stratum with Wilson 95% intervals, "
            "Spearman rho between ipTM and DockQ, and the confusion matrix of the AlphaFold3 "
            "ipTM bands (>0.8 confident, <0.6 failed) against CAPRI acceptable. Holm across "
            "the three hypotheses."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_overall_accuracy",
                statement=("The pipeline reaches CAPRI acceptable quality on a meaningful "
                           "fraction of peptide-receptor complexes."),
                predicted_by="the claim that a co-folding model can dock peptides",
                confirmed_if="fraction_dockq_acceptable > 0.3",
                falsified_if="fraction_dockq_acceptable <= 0.3"),
            ps.Hypothesis(
                name="H2_iptm_calibration",
                statement=("ipTM predicts whether the interface is right, so it can be used "
                           "as a screening filter."),
                predicted_by=("the platform's implicit assumption whenever it reports ipTM "
                              "as evidence about a binder"),
                confirmed_if="Spearman rho(ipTM, DockQ) > 0.6 with p < 0.05",
                falsified_if="Spearman rho <= 0.6 or p >= 0.05"),
            ps.Hypothesis(
                name="H3_assay_power_GATE",
                statement=("The pipeline recovers the majority of interfaces it could have "
                           "memorised. If it cannot do that, it cannot license a positive "
                           "claim about an unknown candidate, and study #9 must not run as "
                           "a positive screen."),
                predicted_by=("the premise of study #9, which assumes the screen can detect "
                              "a true binder"),
                confirmed_if="pre-cutoff stratum fraction_dockq_acceptable > 0.5",
                falsified_if="pre-cutoff stratum fraction_dockq_acceptable <= 0.5"),
        ),
        secondary_metrics=(
            "median_dockq", "mean_iptm", "spearman_iptm_dockq", "fraction_iptm_above_0.8",
            "iptm_band_confusion", "median_irmsd", "median_fnat", "per_entry",
            "wall_clock_seconds_per_complex",
        ),
        exclusions=(
            "Complexes are two-protein-entity X-ray structures under 2.5 A where the shorter "
            "chain is 5-30 residues of standard amino acids and the receptor is 50-350 "
            "residues. One entry per receptor accession per stratum. Entries whose "
            "prediction or DockQ scoring fails technically are recorded and excluded."),
        known_confounds=(
            "1. Predictions run in single-sequence mode, which Boltz documents as degrading "
            "accuracy, so all strata are depressed together; the DIFFERENCE between strata "
            "is more interpretable than the levels. 2. Deposition date bounds when "
            "coordinates could enter a training snapshot but does not prove they did; Boltz's "
            "split is not published. 3. Crystallised peptide complexes are biased toward "
            "peptides that bind well enough to crystallise, so the recovery rate here is an "
            "OPTIMISTIC bound on what a screen of arbitrary designed peptides would achieve. "
            "4. n is small per stratum, so a Wilson interval on a proportion is wide."),
    )


def _dockq(model: Path, native: Path, expected_mapping: str) -> dict:
    """Run DockQ from its isolated environment, preferring the CURATED chain mapping.

    The registered analysis_plan specifies an explicit mapping. An earlier version abandoned
    it wholesale for DockQ's own chain search, because `--mapping` raises KeyError on some
    inputs — but that deviation was applied to all 16 entries and then described as
    "verified", when nothing checked it. Measured entry by entry, the blanket switch was not
    needed and was not harmless:

      * 13 of 16 score identically either way.
      * 4XHV and 4XOE genuinely raise KeyError('A') under the explicit form. Auto is required.
      * 31EE finds NO interface under the curated AB:AC -- the curation named the wrong
        receptor copy; peptide C sits on chain B, not A. Auto is required and is correct.
      * 4S15 differs immaterially (0.031 vs 0.039, both in the incorrect band).
      * 10TC differed by 0.138. DockQ's search silently substituted native chain H, a
        FOUR-residue copy of the curated EIGHT-residue peptide B, and scoring against half
        the resolved peptide inflated the result to 0.969 where the curated mapping gives
        0.831. That entry is the best score in the post-cutoff stratum, so the substitution
        flattered exactly the number the study's headline comparison rests on.

    So: try the curated mapping first, fall back to DockQ's search only when the curated form
    fails, and record per entry which path produced the number.
    """
    if not DOCKQ.exists():
        return {"ok": False, "error": f"DockQ not installed at {DOCKQ}"}
    def _run(args: list[str]):
        try:
            return subprocess.run([str(DOCKQ), str(model), str(native)] + args,
                                  capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            return None

    p = _run(["--mapping", expected_mapping])
    mapping_route = "curated"
    fallback_reason = None
    if p is None:
        return {"ok": False, "error": "DockQ timed out"}
    if p.returncode != 0 or "model:native mapping" not in p.stdout:
        fallback_reason = ((p.stderr or p.stdout).strip().splitlines() or ["unknown"])[-1][:160]
        p = _run([])
        mapping_route = "dockq_search"
        if p is None:
            return {"ok": False, "error": "DockQ timed out"}
        if p.returncode != 0:
            return {"ok": False, "error": (p.stderr or p.stdout)[-250:]}
    out: dict = {"ok": True, "mapping_route": mapping_route,
                 "mapping_fallback_reason": fallback_reason}
    for key, pat in (("dockq", r"^\s*DockQ:\s*([\d.]+)"),
                     ("irmsd", r"^\s*iRMSD:\s*([\d.]+)"),
                     ("lrmsd", r"^\s*LRMSD:\s*([\d.]+)"),
                     ("fnat", r"^\s*fnat:\s*([\d.]+)"),
                     ("clashes", r"^\s*clashes:\s*([\d.]+)")):
        m = re.search(pat, p.stdout, re.M)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r"with\s+(\S+)\s+model:native mapping", p.stdout)
    if m:
        out["mapping_used"] = m.group(1)
        out["mapping_as_expected"] = (m.group(1) == expected_mapping)
    if "dockq" not in out:
        return {"ok": False, "error": "could not parse DockQ output"}
    return out


def run() -> None:
    plan = ps.load(STUDY_ID)
    entries = json.loads(SET.read_text())
    rows: list[dict] = []
    for i, e in enumerate(entries, 1):
        pid = e["pdb_id"]
        print(f"[{i}/{len(entries)}] {pid} {e['split']:12s} ", end="", flush=True)
        try:
            ref = pb.fetch_structure(pid, REFS)
        except Exception as exc:  # noqa: BLE001
            print(f"reference download failed")
            rows.append({**e, "ok": False, "error": f"ref: {exc}"})
            continue
        t0 = time.time()
        try:
            r = st.run_boltz(
                [st.Chain("A", e["receptor_seq"], "protein", msa="empty"),
                 st.Chain("B", e["peptide_seq"], "protein", msa="empty")],
                WORK / pid, accelerator="gpu", seed=1, diffusion_samples=1,
                recycling_steps=3, timeout=3600)
        except Exception as exc:  # noqa: BLE001
            print(f"prediction raised: {str(exc)[:60]}")
            rows.append({**e, "ok": False, "error": str(exc)[:200]})
            continue
        dt = time.time() - t0
        model = (r.get("files") or {}).get("model")
        if r.get("returncode") != 0 or not model:
            print("no model produced")
            rows.append({**e, "ok": False, "seconds": round(dt, 1),
                         "error": (r.get("stderr_tail") or "")[-200:]})
            continue
        c = r.get("confidence") or {}
        mapping = f"AB:{e['receptor_chain']}{e['peptide_chain']}"
        dq = _dockq(Path(model), ref, mapping)
        rec = {**e, "ok": dq.get("ok", False), "seconds": round(dt, 1),
               "iptm": c.get("iptm"), "ptm": c.get("ptm"),
               "complex_plddt": c.get("complex_plddt"),
               "model": model, "mapping": mapping, **dq}
        if dq.get("ok"):
            print(f"{dt:5.1f}s  ipTM={c.get('iptm'):.3f}  DockQ={dq['dockq']:.3f}  "
                  f"fnat={dq.get('fnat', 0):.2f}  "
                  f"{'ACCEPTABLE' if dq['dockq'] >= DOCKQ_ACCEPTABLE else 'incorrect'}")
        else:
            print(f"{dt:5.1f}s  DockQ failed: {dq.get('error', '')[:60]}")
        rows.append(rec)

    RESULT.write_text(json.dumps(
        {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
         "n_observed": sum(1 for r in rows if r.get("ok")), "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def analyse() -> int:
    from scipy import stats
    payload = json.loads(RESULT.read_text())
    ok = [r for r in payload["rows"] if r.get("ok")]
    if len(ok) < 4:
        print(f"only {len(ok)} scored; cannot analyse")
        return 1

    dq = [r["dockq"] for r in ok]
    ip = [r["iptm"] for r in ok if r.get("iptm") is not None]
    acc = [r for r in ok if r["dockq"] >= DOCKQ_ACCEPTABLE]
    f_all = len(acc) / len(ok)

    strata = {}
    for name in ("pre_cutoff", "post_cutoff"):
        rs = [r for r in ok if r["split"] == name]
        k = sum(1 for r in rs if r["dockq"] >= DOCKQ_ACCEPTABLE)
        strata[name] = {"k": k, "n": len(rs),
                        "fraction": round(k / len(rs), 4) if rs else 0.0,
                        "wilson95": [round(v, 4) for v in _wilson(k, len(rs))],
                        "median_dockq": round(statistics.median(
                            [r["dockq"] for r in rs]), 4) if rs else None}

    paired = [(r["iptm"], r["dockq"]) for r in ok if r.get("iptm") is not None]
    rho = p_rho = None
    if len(paired) >= 4:
        rr = stats.spearmanr([a for a, _ in paired], [b for _, b in paired])
        rho, p_rho = float(rr.statistic), float(rr.pvalue)

    band = {"confident_and_acceptable": 0, "confident_but_wrong": 0,
            "failed_band_but_acceptable": 0, "failed_band_and_wrong": 0,
            "grey_and_acceptable": 0, "grey_and_wrong": 0}
    for r in ok:
        if r.get("iptm") is None:
            continue
        good = r["dockq"] >= DOCKQ_ACCEPTABLE
        if r["iptm"] > IPTM_CONFIDENT:
            band["confident_and_acceptable" if good else "confident_but_wrong"] += 1
        elif r["iptm"] < IPTM_FAILED:
            band["failed_band_but_acceptable" if good else "failed_band_and_wrong"] += 1
        else:
            band["grey_and_acceptable" if good else "grey_and_wrong"] += 1

    # H1 and H3 are threshold criteria on a fraction, not tests. They used to be encoded as
    # p = 0.0/1.0 and fed to Holm alongside H2; both fired, took the first two step-down ranks,
    # and left the one genuine test with multiplier 1 — its published "Holm-adjusted" p was
    # byte-identical to its raw p while the artefact claimed a correction. See cbc/inference.py.
    criteria = {
        "H1_overall_accuracy": inf.Criterion(
            f_all > 0.3, round(f_all, 4), "fraction_dockq_acceptable > 0.3"),
        "H3_assay_power_GATE": inf.Criterion(
            strata["pre_cutoff"]["fraction"] > 0.5,
            round(strata["pre_cutoff"]["fraction"], 4), "pre-cutoff fraction > 0.5"),
    }
    tests = ({"H2_iptm_calibration": p_rho}
             if (rho is not None and rho > 0.6 and p_rho is not None and p_rho > 0) else {})
    ruling = inf.decide(criteria, tests)
    if not tests:
        ruling["verdicts"]["H2_iptm_calibration"] = "FALSIFIED"

    gate_open = strata["pre_cutoff"]["fraction"] > 0.5
    report = {
        "study_id": STUDY_ID, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(ok), "primary_metric": "fraction_dockq_acceptable",
        "metrics": {
            "fraction_dockq_acceptable": round(f_all, 4),
            "median_dockq": round(statistics.median(dq), 4),
            "mean_iptm": round(statistics.fmean(ip), 4) if ip else None,
            "spearman_iptm_dockq": round(rho, 4) if rho is not None else None,
            "fraction_iptm_above_0.8": round(
                sum(1 for v in ip if v > IPTM_CONFIDENT) / len(ip), 4) if ip else None,
            "iptm_band_confusion": band,
            "median_irmsd": round(statistics.median(
                [r["irmsd"] for r in ok if "irmsd" in r]), 3),
            "median_fnat": round(statistics.median(
                [r["fnat"] for r in ok if "fnat" in r]), 4),
            "per_entry": {r["pdb_id"]: {"dockq": r["dockq"], "iptm": r.get("iptm"),
                                        "split": r["split"]} for r in ok},
            "wall_clock_seconds_per_complex": inf.wall_clock(ok),
        },
        "strata": strata,
        "chain_mapping": {
            "curated": sorted(r["pdb_id"] for r in ok if r.get("mapping_route") == "curated"),
            "dockq_search_required": {
                r["pdb_id"]: r.get("mapping_fallback_reason")
                for r in ok if r.get("mapping_route") == "dockq_search"},
            "note": ("The registered plan specifies an explicit chain mapping. It is used "
                     "wherever DockQ accepts it. The entries listed under "
                     "dockq_search_required are the only ones where it does not, each with "
                     "the reason DockQ gave; their scores come from DockQ's own chain "
                     "search. This replaces a blanket switch to auto-mapping that was "
                     "described as verified while nothing checked it."),
        },
        "spearman_p": round(p_rho, 5) if p_rho is not None else None,
        **ruling,
        "GATE_FOR_STUDY_9": {
            "open": gate_open,
            "ruling": (
                "OPEN: the pipeline recovers a majority of memorisable interfaces, so a "
                "screen of unknown candidates can in principle detect a true binder."
                if gate_open else
                "CLOSED: the pipeline does not recover a majority of interfaces it could "
                "have memorised. A screen of unknown candidates therefore cannot license a "
                "positive claim, and a negative result from it would be indistinguishable "
                "from method failure. Study #9 may be run only as a negative control, with "
                "that limitation stated as its headline rather than its footnote."),
        },
        "failures": [{"pdb_id": r["pdb_id"], "split": r.get("split"),
                      "error": str(r.get("error"))[:150]}
                     for r in payload["rows"] if not r.get("ok")],
    }
    audit = ps.verify_result(STUDY_ID, report)
    # Declared deviation. The registered analysis_plan says "using an explicit chain
    # mapping". That was changed to DockQ's own chain search after the explicit form was
    # measured to fail non-deterministically: on 4XHV `--mapping AB:AB` raises KeyError
    # inside DockQ while the identical files score 0.899 under auto-mapping, and the same
    # explicit form works on 4XOJ. Forcing it would have discarded correct results. The
    # mapping DockQ selects is recorded per entry and checked against the expected one.
    _fallback = {r["pdb_id"]: r.get("mapping_fallback_reason")
                 for r in ok if r.get("mapping_route") == "dockq_search"}
    audit["deviations"].append(
        "analysis_plan specified an explicit DockQ chain mapping. It was used for "
        f"{len(ok) - len(_fallback)} of {len(ok)} entries. DockQ's own chain search was "
        f"needed for {sorted(_fallback)}: 4XHV and 4XOE raise KeyError('A') under the "
        "explicit form, and 31EE finds no interface under the curated AB:AC because the "
        "curation named the wrong receptor copy -- peptide C sits on chain B. An earlier "
        "version applied the search to all entries and called the result verified; that "
        "silently substituted a 4-residue copy of 10TC's 8-residue peptide and inflated its "
        "DockQ from 0.831 to 0.969, the best score in the post-cutoff stratum.")
    audit["confirmatory"] = False
    audit["note"] = ("One declared deviation, made for a measured technical reason and "
                     "recorded rather than absorbed silently.")
    report["prespec_audit"] = audit
    RESULT.write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 94)
    print(f"STUDY {STUDY_ID}   prespec {payload['prespec_hash'][:12]}   n = {len(ok)}")
    print("=" * 94)
    print(f"\nPRIMARY  fraction reaching CAPRI acceptable (DockQ >= {DOCKQ_ACCEPTABLE}) = "
          f"{m['fraction_dockq_acceptable']}")
    print(f"         median DockQ {m['median_dockq']}, median iRMSD {m['median_irmsd']} A, "
          f"median fnat {m['median_fnat']}")
    print("\nBY STRATUM")
    for name, s in strata.items():
        print(f"  {name:12s} {s['k']}/{s['n']} = {s['fraction']:.2f}  "
              f"Wilson95 [{s['wilson95'][0]:.2f}, {s['wilson95'][1]:.2f}]  "
              f"median DockQ {s['median_dockq']}")
    print(f"\nipTM CALIBRATION  Spearman rho = {m['spearman_iptm_dockq']} "
          f"(p = {report['spearman_p']}),  mean ipTM {m['mean_iptm']}")
    print("  band confusion (AlphaFold3 interpretation bands vs CAPRI acceptable):")
    for k, v in m["iptm_band_confusion"].items():
        print(f"    {k:30s} {v}")
    print("\nPER ENTRY (sorted by DockQ)")
    for r in sorted(ok, key=lambda x: -x["dockq"]):
        mark = "ACCEPTABLE" if r["dockq"] >= DOCKQ_ACCEPTABLE else "incorrect"
        print(f"  {r['pdb_id']:6s} {r['split']:12s} DockQ={r['dockq']:.3f}  "
              f"ipTM={r.get('iptm', 0):.3f}  fnat={r.get('fnat', 0):.2f}  {mark}")
    if report["failures"]:
        print("\nFAILURES (recorded, excluded as pre-registered)")
        for f in report["failures"]:
            print(f"  {f['pdb_id']:6s} {str(f['split'])[:12]:12s} {f['error'][:70]}")
    print("\nPRE-SPECIFIED VERDICTS")
    print(inf.format_verdicts(report))
    print("\n" + "=" * 94)
    print("GATE FOR STUDY #9: " + ("OPEN" if gate_open else "CLOSED"))
    print(report["GATE_FOR_STUDY_9"]["ruling"])
    a = report["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 94)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    for f in ("curate", "register", "run", "analyse"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args()
    if a.curate:
        curate()
        return 0
    if a.register:
        spec = build_prespec(*prespec_args())
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        print(f"registered {spec.register().relative_to(REPO)}")
        print(f"  hash {spec.hash()}   n = {spec.n_planned}")
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
