#!/usr/bin/env python3
"""Two-level variance decomposition for the inference-variance study.

Every metric is analysed and reported SEPARATELY. pLDDT, pTM, ipTM and interface PAE have
different supports and different distributions, and a standard deviation measured on one
licenses no inference about another -- a conflation that occurred during review and is the
reason this study exists.

Pooling is done as sqrt(mean of per-candidate variances), not as the SD of the pooled values.
The latter would add between-candidate signal to a within-candidate noise estimate and
inflate it, which would make the noise floor look worse than it is and wrongly protect the
platform's published comparisons from scrutiny.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from . import prespec as ps

#: Boltz reports confidence on 0-1; pLDDT is conventionally 0-100.
PLDDT_SCALE = 100.0


def _by(rows: list[dict], arm: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("arm", "").startswith(arm) and r.get("returncode") == 0:
            out.setdefault(r["code"], []).append(r)
    return out


def pooled_sd(per_candidate: dict[str, list[float]]) -> tuple[float | None, dict[str, float]]:
    """sqrt(mean of within-candidate variances), plus each candidate's own SD."""
    sds: dict[str, float] = {}
    variances: list[float] = []
    for code, vals in per_candidate.items():
        if len(vals) < 2:
            continue
        sd = statistics.stdev(vals)
        sds[code] = sd
        variances.append(sd ** 2)
    if not variances:
        return None, sds
    return math.sqrt(statistics.fmean(variances)), sds


def analyse(path: Path, study_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    rows = payload["rows"]

    # ---- Arm A: same-seed determinism ------------------------------------- #
    armA = _by(rows, "A")
    determinism = {}
    for code, rs in armA.items():
        vals = [r["complex_plddt"] for r in rs if r.get("complex_plddt") is not None]
        determinism[code] = {
            "n_replicates": len(vals),
            "distinct_values": len(set(vals)),
            "values": sorted(set(vals)),
            "spread": (max(vals) - min(vals)) if len(vals) > 1 else 0.0,
        }
    all_deterministic = all(d["distinct_values"] <= 1 for d in determinism.values())

    # ---- Arm B: across-seed sampler variance ------------------------------ #
    # Seed 1 comes from arm A (one replicate, since they are identical when deterministic).
    per_cand_plddt: dict[str, list[float]] = {}
    per_cand_ptm: dict[str, list[float]] = {}
    for code, rs in armA.items():
        if rs:
            per_cand_plddt.setdefault(code, []).append(rs[0]["complex_plddt"])
            if rs[0].get("ptm") is not None:
                per_cand_ptm.setdefault(code, []).append(rs[0]["ptm"])
    for code, rs in _by(rows, "B").items():
        for r in rs:
            if r.get("complex_plddt") is not None:
                per_cand_plddt.setdefault(code, []).append(r["complex_plddt"])
            if r.get("ptm") is not None:
                per_cand_ptm.setdefault(code, []).append(r["ptm"])

    sd_plddt_raw, sds_plddt = pooled_sd(per_cand_plddt)
    sd_plddt = sd_plddt_raw * PLDDT_SCALE if sd_plddt_raw is not None else None
    sd_ptm, _ = pooled_sd(per_cand_ptm)

    # ---- Arm C: MSA factor, paired across candidates ---------------------- #
    msa_rows = _by(rows, "C")
    paired: list[tuple[str, float, float]] = []
    for code, rs in msa_rows.items():
        with_msa = [r["complex_plddt"] for r in rs if r.get("complex_plddt") is not None]
        without = per_cand_plddt.get(code, [])
        if with_msa and without:
            paired.append((code, statistics.fmean(without), statistics.fmean(with_msa)))
    msa_shift = msa_p = None
    if len(paired) >= 2:
        diffs = [(w - o) * PLDDT_SCALE for _, o, w in paired]
        msa_shift = statistics.fmean(diffs)
        sd_d = statistics.stdev(diffs)
        if sd_d > 0:
            t = msa_shift / (sd_d / math.sqrt(len(diffs)))
            try:
                from scipy import stats
                msa_p = float(2 * (1 - stats.t.cdf(abs(t), len(diffs) - 1)))
            except ImportError:
                msa_p = None

    # ---- Arm D: interface metrics ----------------------------------------- #
    iptm: dict[str, list[float]] = {}
    ipae: dict[str, list[float]] = {}
    for code, rs in _by(rows, "D").items():
        for r in rs:
            if r.get("iptm") is not None:
                iptm.setdefault(code, []).append(r["iptm"])
            if r.get("interface_pae_min") is not None:
                ipae.setdefault(code, []).append(r["interface_pae_min"])
    sd_iptm, sds_iptm = pooled_sd(iptm)
    sd_ipae, sds_ipae = pooled_sd(ipae)

    # ---- Holm across the three pre-specified hypotheses ------------------- #
    # H1 and H2 are threshold comparisons, not tests; they carry p = 0 or 1 by construction
    # so that Holm is well defined and the reported adjustment stays honest about that.
    p1 = 0.0 if (sd_plddt is not None and sd_plddt < 2.0) else 1.0
    p2 = 0.0 if all_deterministic else 1.0
    p3 = msa_p if msa_p is not None else 1.0
    raw = [("H1_seed_noise_small", p1), ("H2_same_seed_deterministic", p2),
           ("H3_msa_immaterial_for_designed_sequences", p3)]
    order = sorted(range(3), key=lambda i: raw[i][1])
    adj = [0.0] * 3
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (3 - rank) * raw[i][1])
        adj[i] = min(1.0, running)

    h3_ok = (msa_shift is not None and sd_plddt is not None
             and abs(msa_shift) < sd_plddt and adj[2] >= 0.05)

    verdicts = {
        "H1_seed_noise_small": "CONFIRMED" if p1 == 0.0 else "FALSIFIED",
        "H2_same_seed_deterministic": "CONFIRMED" if all_deterministic else "FALSIFIED",
        "H3_msa_immaterial_for_designed_sequences": "CONFIRMED" if h3_ok else "FALSIFIED",
    }

    times = [r["seconds"] for r in rows if r.get("returncode") == 0]
    report = {
        "study_id": study_id,
        "prespec_hash": payload["prespec_hash"],
        "n_observed": payload["n_observed"],
        "primary_metric": "across_seed_sd_complex_plddt",
        "metrics": {
            "across_seed_sd_complex_plddt": round(sd_plddt, 4) if sd_plddt else None,
            "across_seed_sd_ptm": round(sd_ptm, 5) if sd_ptm else None,
            "across_seed_sd_iptm": round(sd_iptm, 5) if sd_iptm else None,
            "across_seed_sd_interface_pae_min": round(sd_ipae, 4) if sd_ipae else None,
            "same_seed_distinct_values": {c: d["distinct_values"]
                                          for c, d in determinism.items()},
            "msa_mean_shift": round(msa_shift, 4) if msa_shift is not None else None,
            "wall_clock_seconds_per_fold": round(statistics.fmean(times), 1) if times else None,
            "per_residue_plddt_sd": None,
        },
        "per_candidate_sd_plddt": {c: round(v * PLDDT_SCALE, 3)
                                   for c, v in sds_plddt.items()},
        "per_candidate_sd_iptm": {c: round(v, 4) for c, v in sds_iptm.items()},
        "per_candidate_sd_interface_pae": {c: round(v, 3) for c, v in sds_ipae.items()},
        "determinism": determinism,
        "msa_paired": [{"code": c, "without": round(o, 6), "with": round(w, 6)}
                       for c, o, w in paired],
        "p_raw": {k: v for k, v in raw},
        "p_holm": {raw[i][0]: round(adj[i], 5) for i in range(3)},
        "verdicts": verdicts,
    }
    report["prespec_audit"] = ps.verify_result(study_id, report)
    return report


def main(path: Path, study_id: str) -> int:
    rep = analyse(path, study_id)
    m = rep["metrics"]
    print("=" * 92)
    print(f"STUDY {study_id}   prespec {rep['prespec_hash'][:12]}   "
          f"n = {rep['n_observed']} folds")
    print("=" * 92)

    sd = m["across_seed_sd_complex_plddt"]
    print(f"\nPRIMARY  across-seed SD of complex_plddt = "
          f"{sd if sd is None else f'{sd:.3f}'} pLDDT units")
    print("\nPER-CANDIDATE across-seed SD (pLDDT units)")
    for c, v in sorted(rep["per_candidate_sd_plddt"].items(), key=lambda kv: -kv[1]):
        print(f"  {c[:30]:32s} {v:6.3f}")

    print("\nSAME-SEED DETERMINISM (distinct values across 3 replicates)")
    for c, d in rep["determinism"].items():
        mark = "identical" if d["distinct_values"] <= 1 else f"{d['distinct_values']} DIFFER"
        print(f"  {c[:30]:32s} {mark:12s} spread {d['spread']:.3e}")

    print("\nOTHER METRICS, reported separately")
    for k in ("across_seed_sd_ptm", "across_seed_sd_iptm",
              "across_seed_sd_interface_pae_min", "msa_mean_shift",
              "wall_clock_seconds_per_fold"):
        print(f"  {k:36s} {m[k]}")

    if rep["msa_paired"]:
        print("\nMSA FACTOR (paired, complex_plddt)")
        for p in rep["msa_paired"]:
            print(f"  {p['code'][:30]:32s} without {p['without']:.6f}  "
                  f"with {p['with']:.6f}  Δ {(p['with']-p['without'])*100:+.3f}")

    print("\nPRE-SPECIFIED VERDICTS")
    for h, v in rep["verdicts"].items():
        print(f"  {h:42s} {v:10s} Holm p = {rep['p_holm'][h]}")

    a = rep["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 92)

    out = Path(path).with_name("study_inference_variance_analysis.json")
    out.write_text(json.dumps(rep, indent=1))
    print(f"wrote {out.name}")
    return 0
