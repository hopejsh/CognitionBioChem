#!/usr/bin/env python3
"""Study #9: the candidate screen, against composition-matched decoys.

This is the study the whole platform was built to make possible, and it could not be run
honestly until study #7 measured whether the pipeline has any sensitivity. That gate is now
OPEN: #7 recovered 7 of 8 memorisable peptide interfaces (DockQ >= 0.23) and established that
ipTM tracks interface correctness at Spearman rho = 0.847, with ZERO false negatives below
ipTM 0.6. So a low score here is evidence about the candidate rather than about the method.

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
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "candidate-screen-v1"
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
}


def _receptor_seq(symbol: str) -> str | None:
    reg = json.loads(REGISTRY.read_text())
    t = reg["targets"].get(symbol)
    if not t:
        return None
    seq, chain = t["sequence"], t.get("chain")
    # Use the mature chain: the signal peptide is cleaved and is not part of the receptor.
    return seq[chain[0] - 1:chain[1]] if chain else seq


def _candidates(limit: int) -> list[dict]:
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
                    "receptor_len": len(rseq)})
    out.sort(key=lambda c: c["receptor_len"])   # cheapest first
    return out[:limit]


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
            "Predict the receptor mature chain plus each peptide with Boltz-2 2.2.1, "
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
            f"Only the {n_cand} candidates whose declared receptor is in the target registry "
            "AND is extracellular are screened. Candidates naming an intracellular target "
            "(Keap1, GSK-3, Nrf2, AMPK) are excluded because a peptide with no "
            "cell-penetrating mechanism cannot reach one, and the platform's own data gate "
            "already flags them. Sequences containing non-standard residues are excluded."),
        known_confounds=(
            "1. Single-sequence mode depresses all arms equally; the native-versus-decoy "
            "CONTRAST is the interpretable quantity, not the absolute level. 2. Three decoys "
            "give a minimum empirical p of 0.25, so no individual candidate can reach "
            "significance — the design tests the SET, and per-candidate p values are "
            "descriptive only. This is stated in advance rather than discovered afterwards. "
            "3. Composition-matched shuffling preserves charge and hydrophobicity but not "
            "secondary-structure propensity, so a helical native competes against shuffles "
            "that may not be helical; this makes the test conservative in the native's "
            "favour. 4. A negative result bounds what THIS pipeline detects at THIS "
            "configuration, not what the molecules do in a cell."),
    )


def run() -> None:
    plan = ps.load(STUDY_ID)
    cands = _candidates(limit=6)
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
                    diffusion_samples=1, recycling_steps=3, timeout=5400)
            except Exception as exc:  # noqa: BLE001
                print(f"raised: {str(exc)[:50]}")
                rows.append({**c, "kind": kind, "peptide_used": pep, "ok": False,
                             "error": str(exc)[:200]})
                continue
            dt = time.time() - t0
            conf = r.get("confidence") or {}
            ok = r.get("returncode") == 0 and conf.get("iptm") is not None
            rec = {**c, "kind": kind, "peptide_used": pep, "ok": ok,
                   "seconds": round(dt, 1), "iptm": conf.get("iptm"),
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
    diff = (statistics.fmean(natives) - statistics.fmean(decoys)) if per else 0.0
    n_below = sum(1 for p in per if p["native_iptm"] < IPTM_FAILED_BAND)

    p1 = 0.0 if n_beat_and_confident > 0 else 1.0
    p2 = 0.0 if diff > 0.1 else 1.0
    p3 = 0.0 if (per and n_below >= len(per) / 2) else 1.0
    raw = [("H1_any_candidate_binds", p1), ("H2_natives_beat_decoys_on_average", p2),
           ("H3_candidates_in_failed_band", p3)]
    order = sorted(range(3), key=lambda i: raw[i][1])
    adj = [0.0] * 3
    rm = 0.0
    for rank, i in enumerate(order):
        rm = max(rm, (3 - rank) * raw[i][1])
        adj[i] = min(1.0, rm)

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
            "wall_clock_seconds_per_fold": round(statistics.fmean(
                [r["seconds"] for r in ok if r.get("seconds")]), 1) if ok else None,
        },
        "per_candidate": per,
        "p_holm": {raw[i][0]: round(adj[i], 5) for i in range(3)},
        "verdicts": {k: ("CONFIRMED" if v == 0 else "FALSIFIED") for k, v in raw},
        "interpretation_key": (
            "Study #7 measured, on 16 peptide-receptor complexes with known answers: ipTM > "
            "0.8 was correct in 9 of 10 cases; ipTM < 0.6 was correct in 0 of 4, with no "
            "false negatives. The gate for this study was OPEN because #7 recovered 7 of 8 "
            "memorisable interfaces, so the pipeline has demonstrated sensitivity and a low "
            "score here is evidence about the candidate rather than about the method."),
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
    for h, v in report["verdicts"].items():
        print(f"  {h:36s} {v:10s} Holm p = {report['p_holm'][h]}")
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
        c = _candidates(limit=6)
        spec = build_prespec(len(c) * (1 + N_DECOYS), len(c))
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
