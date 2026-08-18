#!/usr/bin/env python3
"""Study #2: how much of a structural number is the sampler rather than the molecule?

The platform has published 22 pLDDT values and compared them against legacy values with
deltas of 10-46 units, without knowing the across-seed envelope of the quantity being
compared. A difference is only interpretable against the noise of the measurement that
produced it. This measures that noise.

Design: a two-level variance decomposition, reported SEPARATELY for each metric, because
pLDDT, pTM and ipTM have different distributions and an SD measured on one does not license
an inference about another.

  Level 1  same seed, repeated runs   -> nondeterminism (floating-point, MPS reduction order)
  Level 2  different seeds            -> sampler variance
  Factor   MSA mode                   -> msa=empty vs --use_msa_server
  Arm D    two-chain complexes        -> ipTM and interface PAE, undefined for a lone chain

    ./.venv/bin/python platform/studies/inference_variance.py --register
    ./.venv/bin/python platform/studies/inference_variance.py --run
    ./.venv/bin/python platform/studies/inference_variance.py --analyse
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "inference-variance-v1"
WORK = Path("/tmp/cbc_variance")
RESULT = REPO / "data" / "study_inference_variance.json"
ACHE_MATURE = Path("/tmp/ache_mature.txt")

SEEDS = (1, 2, 3, 4, 5)
N_REPLICATES = 3          # same-seed repeats, for the determinism arm
N_CANDIDATES = 6
N_COMPLEX = 3             # complexes are ~6x the cost of a lone chain


def pick_candidates() -> list[tuple[str, str]]:
    """Six valid candidates spanning the observed pLDDT range, chosen deterministically."""
    raw = json.loads((REPO / "data" / "extracted_raw.json").read_text())
    valid = [(d["code"], d["sequence"]) for d in raw["FULL_BRAIN_DRUGS_DATA"]
             if re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]{5,}", d.get("sequence", ""))]
    prev = REPO / "data" / "real_vs_hardcoded.json"
    if prev.exists():
        rows = {r["code"]: r for r in json.loads(prev.read_text())["rows"]
                if r.get("real", {}).get("ok")}
        scored = [(c, s, rows[c]["real"]["plddt_mean"]) for c, s in valid if c in rows]
        scored.sort(key=lambda t: t[2])
        if len(scored) >= N_CANDIDATES:
            step = (len(scored) - 1) / (N_CANDIDATES - 1)
            return [(scored[round(i * step)][0], scored[round(i * step)][1])
                    for i in range(N_CANDIDATES)]
    return valid[:N_CANDIDATES]


def build_prespec(cands: list[tuple[str, str]]) -> ps.Prespecification:
    n_folds = (N_CANDIDATES * N_REPLICATES
               + N_CANDIDATES * (len(SEEDS) - 1)
               + N_CANDIDATES * len(SEEDS)
               + N_COMPLEX * len(SEEDS))
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "For each structural metric this platform reports, how large is a difference "
            "before it means anything? Specifically: what fraction of the observed variance "
            "in complex_plddt, pTM, ipTM and interface PAE is attributable to the sampler "
            "(seed) and to run-to-run nondeterminism, rather than to the molecule?"),
        primary_metric="across_seed_sd_complex_plddt",
        primary_metric_justification=(
            "The across-seed standard deviation of complex_plddt is the quantity that sets "
            "the resolution of every pLDDT comparison the platform has already published. "
            "It is chosen as primary because the platform's headline claim — that legacy "
            "values overstated pLDDT by 10-46 units — is only interpretable relative to it. "
            "It is measured per candidate and then pooled, rather than pooled directly, "
            "because candidates differ in intrinsic predictability and pooling first would "
            "confound between-candidate signal with within-candidate noise. Metrics are "
            "reported SEPARATELY and never substituted for one another: pTM, ipTM and "
            "interface PAE have different supports and different distributions, and an SD "
            "measured on one licenses no inference about another."),
        decision_threshold=(
            "H1 confirmed if the pooled across-seed SD of complex_plddt (0-100 scale) is "
            "below 2.0 units; H2 confirmed if same-seed repeats are bit-identical on "
            "complex_plddt for every candidate; H3 confirmed if enabling the MSA server "
            "changes mean complex_plddt by less than the across-seed SD measured in H1."),
        n_planned=n_folds,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed design: every (candidate, seed, arm) cell is run exactly once, in a fixed "
            "order, with no interim analysis. A cell that fails technically is reported as a "
            "failure with its error and excluded with the exclusion stated. No candidate is "
            "added or removed after the first fold begins."),
        analysis_plan=(
            "Arm A (determinism): each of 6 candidates at seed=1, repeated 3 times, "
            "msa=empty. Report the exact set of distinct complex_plddt values per candidate. "
            "Arm B (sampler): each candidate at seeds 1-5, msa=empty, one run per seed; "
            "report per-candidate SD and the pooled SD as sqrt(mean of per-candidate "
            "variances). Arm C (MSA factor): the same 6 candidates at seeds 1-5 with "
            "--use_msa_server and the msa key omitted; compare arm means by paired t-test "
            "across candidates. Arm D (interface): 3 candidates co-folded with human AChE "
            "P22303 mature chain at seeds 1-5, msa=empty; report ipTM and minimum interface "
            "PAE per seed with their SDs. Holm across the three hypotheses. All metrics "
            "reported separately; no metric is pooled across arms."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_seed_noise_small",
                statement=("Across-seed variation in complex_plddt is small enough that the "
                           "platform's published 10-46 unit legacy deltas are resolvable."),
                predicted_by="the platform's existing comparison, which assumes this",
                confirmed_if="pooled across-seed SD of complex_plddt < 2.0 units",
                falsified_if="pooled across-seed SD of complex_plddt >= 2.0 units"),
            ps.Hypothesis(
                name="H2_same_seed_deterministic",
                statement=("Fixing the seed makes a run bit-reproducible on this hardware."),
                predicted_by="the seeding fix applied earlier in this project",
                confirmed_if=("every candidate yields exactly one distinct complex_plddt "
                              "value across its 3 same-seed replicates"),
                falsified_if=("any candidate yields more than one distinct complex_plddt "
                              "value across its same-seed replicates")),
            ps.Hypothesis(
                name="H3_msa_immaterial_for_designed_sequences",
                statement=("For hand-assembled motif concatenations, which have no natural "
                           "homologues, enabling an MSA search changes the prediction by "
                           "less than seed noise."),
                predicted_by=("the observation that a designed amphipathic peptide moved "
                              "0.0005 in complex_plddt when the MSA server was enabled"),
                confirmed_if=("|mean(with MSA) - mean(without MSA)| < the pooled across-seed "
                              "SD from H1, and the paired t-test across candidates does not "
                              "reject at Holm-adjusted 0.05"),
                falsified_if=("the difference exceeds the across-seed SD, or the paired "
                              "t-test rejects at Holm-adjusted 0.05")),
        ),
        secondary_metrics=(
            "across_seed_sd_ptm", "across_seed_sd_iptm",
            "across_seed_sd_interface_pae_min", "per_residue_plddt_sd",
            "same_seed_distinct_values", "msa_mean_shift", "wall_clock_seconds_per_fold",
        ),
        exclusions=(
            "Sequences containing non-standard residues are excluded before registration. "
            "Arm D uses the 3 candidates with the highest, median and lowest mean pLDDT from "
            "the existing single-chain runs, fixed before any variance fold is executed."),
        known_confounds=(
            "1. Seeding fixes the noise draw but not floating-point reduction order on Metal, "
            "and Boltz has a documented aten::linalg_svd CPU fallback, so H2 may fail for "
            "reasons that are hardware rather than software. 2. The MSA server is a remote "
            "service whose returned alignment may change between calls, so arm C confounds "
            "MSA content with MSA presence. 3. All candidates come from one design family, "
            "so the variance measured here may not transfer to natural sequences. "
            "4. n=5 seeds gives a poorly determined SD; the estimate carries roughly 30% "
            "relative uncertainty and is reported with that caveat."),
    )


def _fold(code: str, chains, tag: str, seed: int, msa_server: bool) -> dict:
    out = WORK / f"{code}_{tag}_s{seed}"
    t0 = time.time()
    r = st.run_boltz(chains, out, accelerator="gpu", seed=seed,
                     diffusion_samples=1, recycling_steps=3,
                     use_msa_server=msa_server, timeout=3600)
    dt = time.time() - t0
    c = r.get("confidence") or {}
    rec = {"code": code, "arm": tag, "seed": seed, "seconds": round(dt, 1),
           "returncode": r.get("returncode"),
           "complex_plddt": c.get("complex_plddt"), "ptm": c.get("ptm"),
           "iptm": c.get("iptm"), "confidence_score": c.get("confidence_score")}
    if r.get("returncode") == 0 and r.get("files", {}).get("model"):
        rec["model"] = r["files"]["model"]
        try:
            from cbc import predictor as P
            pred = P.load(Path(r["files"]["model"]).parent)
            if pred.plddt:
                rec["per_residue_plddt_sd"] = round(statistics.pstdev(pred.plddt), 3)
            if len(pred.chains) >= 2:
                ip = pred.interface_pae(pred.chains[0], pred.chains[1])
                if ip:
                    rec["interface_pae_min"] = ip["min_pae"]
                    rec["interface_pae_mean"] = ip["mean_pae"]
        except Exception as exc:  # noqa: BLE001
            rec["parse_error"] = str(exc)[:200]
    return rec


def run() -> None:
    plan = ps.load(STUDY_ID)
    cands = pick_candidates()
    rows: list[dict] = []
    total = (len(cands) * N_REPLICATES + len(cands) * (len(SEEDS) - 1)
             + len(cands) * len(SEEDS) + N_COMPLEX * len(SEEDS))
    i = 0

    def log(rec):
        nonlocal i
        i += 1
        v = rec.get("complex_plddt")
        print(f"[{i}/{total}] {rec['arm']:9s} {rec['code'][:26]:28s} seed={rec['seed']} "
              f"{rec['seconds']:6.1f}s  plddt={v if v is None else round(v, 6)}", flush=True)

    print("ARM A — same-seed determinism")
    for code, seq in cands:
        for rep in range(N_REPLICATES):
            r = _fold(code, [st.Chain("A", seq, "protein", msa="empty")],
                      f"A{rep}", 1, False)
            r["replicate"] = rep
            rows.append(r); log(r)

    print("\nARM B — across-seed sampler variance")
    for code, seq in cands:
        for s in SEEDS[1:]:
            r = _fold(code, [st.Chain("A", seq, "protein", msa="empty")], "B", s, False)
            rows.append(r); log(r)

    print("\nARM C — MSA server factor")
    for code, seq in cands:
        for s in SEEDS:
            r = _fold(code, [st.Chain("A", seq, "protein", msa=None)], "C", s, True)
            rows.append(r); log(r)

    print("\nARM D — two-chain complexes (ipTM, interface PAE)")
    prot = ACHE_MATURE.read_text().strip() if ACHE_MATURE.exists() else None
    if prot:
        for code, seq in cands[:: max(1, len(cands) // N_COMPLEX)][:N_COMPLEX]:
            for s in SEEDS:
                r = _fold(code, [st.Chain("A", prot, "protein", msa="empty"),
                                 st.Chain("B", seq, "protein", msa="empty")], "D", s, False)
                rows.append(r); log(r)
    else:
        print("  SKIPPED: no AChE sequence at", ACHE_MATURE)

    RESULT.write_text(json.dumps(
        {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
         "n_observed": sum(1 for r in rows if r["returncode"] == 0),
         "candidates": [c for c, _ in cands], "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()

    if a.register:
        spec = build_prespec(pick_candidates())
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        path = spec.register()
        print(f"registered {path.relative_to(REPO)}")
        print(f"  hash {spec.hash()}")
        print(f"  planned folds: {spec.n_planned}")
        for h in spec.hypotheses:
            print(f"  {h.name:36s} {h.confirmed_if[:60]}")
        return 0
    if a.run:
        run()
        return 0
    if a.analyse:
        from cbc import variance_analysis
        return variance_analysis.main(RESULT, STUDY_ID)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
