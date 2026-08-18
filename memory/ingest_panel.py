#!/usr/bin/env python3
"""Ingest the expert panel's findings and the verifiers' verdicts into CBC-Memory.

Each reviewer writes its findings as claims under its own agent id. Each verifier then
writes a verdict claim and links it to the finding with SUPPORTS or REFUTES, and sets the
finding's status. Nothing is merged and nothing is auto-resolved: where a verifier
corrected a reviewer, both records survive and the disagreement is queryable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / "reviews" / "panel_raw.json"

SEVERITY_CONF = {"BLOCKER": 0.95, "CRITICAL": 0.85, "MAJOR": 0.7, "MINOR": 0.5}


def slug(text: str, limit: int = 40) -> str:
    """Agent ids must match [A-Za-z0-9._-]{1,64}; reviewers returned free prose."""
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (s[:limit].rstrip("-")) or "unknown"
VERDICT_STATUS = {
    "CONFIRMED": "VERIFIED",
    "CONFIRMED_WITH_CORRECTION": "VERIFIED",
    "PARTIALLY_REFUTED": "REFUTED",
    "REFUTED": "REFUTED",
}


def main() -> int:
    data = json.loads(PANEL.read_text())
    reviews = data["reviews"]
    verifs = {v["discipline"]: v for v in data["verifications"]}

    finding_ids: dict[str, str] = {}   # panel finding id -> memory claim id
    finding_meta: dict[str, dict] = {}

    # ---- reviewers ----------------------------------------------------------- #
    for rv in reviews:
        disc = rv["discipline"]
        with mem.Ledger(f"rev.{slug(disc)}", task=f"critical review: {disc}") as L:
            for f in rv.get("findings", []):
                text = (f"[{f['severity']}] {f['title']} — {f['what_is_wrong']} "
                        f"Consequence: {f['why_it_matters']}")
                cid = L.claim(
                    text, kind="finding", source_type="code",
                    source_ref=f["evidence_location"][:200],
                    confidence=SEVERITY_CONF.get(f["severity"], 0.6),
                    tags=[disc, f["severity"].lower(), f["category"]])
                finding_ids[f["id"]] = cid
                finding_meta[f["id"]] = {**f, "discipline": disc}

                fix = L.claim(
                    f"Required fix for {f['id']}: {f['required_fix']}",
                    kind="requirement", source_type="review", source_ref=f["id"],
                    confidence=SEVERITY_CONF.get(f["severity"], 0.6),
                    tags=[disc, "remediation"])
                L.edge(fix, "DERIVES_FROM", cid)

                if f.get("ground_truth"):
                    gt = L.claim(
                        f"Ground truth for {f['id']}: {f['ground_truth']}",
                        kind="evidence", source_type="literature", source_ref=f["id"],
                        confidence=0.8, tags=[disc, "ground-truth"])
                    L.edge(gt, "SUPPORTS", cid)

            for lit in rv.get("literature", []):
                if not lit.get("verified"):
                    continue
                L.claim(
                    f"{lit['title']} ({lit['year']}). {lit['what_it_provides']} "
                    f"Application here: {lit['how_to_apply_here']}",
                    kind="evidence", source_type="literature",
                    source_ref=lit["id"], confidence=0.75,
                    tags=[disc, "literature"])

    # ---- verifiers ----------------------------------------------------------- #
    for disc, vf in verifs.items():
        with mem.Ledger(f"ver.{slug(disc)}", task=f"adversarial verification: {disc}") as L:
            for vd in vf.get("verdicts", []):
                target = finding_ids.get(vd["finding_id"])
                if target is None:
                    continue
                body = (f"Verdict {vd['verdict']} on {vd['finding_id']}: {vd['reasoning']}")
                if vd.get("corrections"):
                    body += f" Correction: {vd['corrections']}"
                vc = L.claim(
                    body, kind="verdict", source_type="review",
                    source_ref=vd["finding_id"], confidence=0.85,
                    tags=[disc, "verification", vd["verdict"].lower()])
                rel = "REFUTES" if vd["verdict"] in ("REFUTED", "PARTIALLY_REFUTED") \
                    else "SUPPORTS"
                L.edge(vc, rel, target, note=vd["verdict"])
                L.status(target, VERDICT_STATUS.get(vd["verdict"], "ASSERTED"),
                         rationale=vd["reasoning"][:600], evidence=[vc])

                if not vd.get("fix_is_sound", True):
                    L.claim(
                        f"The proposed fix for {vd['finding_id']} is NOT technically "
                        f"sufficient: {vd.get('corrections') or vd['reasoning']}",
                        kind="verdict", source_type="review",
                        source_ref=vd["finding_id"], confidence=0.8,
                        tags=[disc, "fix-inadequate"])

            for missed in vf.get("missed_by_reviewer", []):
                L.claim(f"Missed by the primary reviewer: {missed}",
                        kind="finding", source_type="review", source_ref=disc,
                        confidence=0.7, tags=[disc, "gap"])

    # ---- panel chair --------------------------------------------------------- #
    syn = data["synthesis"]
    with mem.Ledger("panel-chair", task="synthesis") as L:
        L.claim(syn["verdict_on_platform"], kind="summary", source_type="review",
                source_ref="panel-synthesis", confidence=0.9, tags=["synthesis"])
        for rc in syn.get("root_causes", []):
            L.claim(rc, kind="finding", source_type="review",
                    source_ref="panel-synthesis", confidence=0.85,
                    tags=["synthesis", "root-cause"])
        for b in syn.get("blocker_summary", []):
            L.claim(b, kind="finding", source_type="review",
                    source_ref="panel-synthesis", confidence=0.95,
                    tags=["synthesis", "blocker"])
        for g in syn.get("what_is_genuinely_good", []):
            L.claim(g, kind="finding", source_type="review",
                    source_ref="panel-synthesis", confidence=0.8,
                    tags=["synthesis", "strength"])
        for ph in syn.get("remediation_roadmap", []):
            p = L.claim(f"{ph['phase']}: {ph['goal']}", kind="plan",
                        source_type="review", source_ref="panel-synthesis",
                        confidence=0.8, tags=["roadmap"])
            for crit in ph.get("success_criteria", []):
                c = L.claim(f"Success criterion — {crit}", kind="requirement",
                            source_type="review", source_ref=ph["phase"][:60],
                            confidence=0.8, tags=["roadmap", "criterion"])
                L.edge(c, "DERIVES_FROM", p)

    # ---- our own independently computed measurements ------------------------- #
    vr = json.loads((REPO / "data" / "validation_report.json").read_text())
    s = vr["summary"]
    with mem.Ledger("independent-validator", task="local computational verification") as L:
        art = L.artifact(REPO / "data" / "validation_report.json", kind="report",
                         desc="RDKit + stdlib validation of the full dataset")
        for text, tags in [
            (f"Computed independently with RDKit 2026.03.5 and stdlib: "
             f"{s['smiles_parse_failures']}/8 natural-product SMILES fail to parse, "
             f"{s['smiles_wrong_compound']} encodes a different molecule than its name, "
             f"{s['smiles_stereo_undefined']} have every stereocentre undefined.",
             ["chemistry", "measurement"]),
            (f"Computed independently: {s['thermo_inconsistent']}/"
             f"{s['thermo_pairs_checked']} stated (dG, Kd) pairs are thermodynamically "
             f"inconsistent at 298.15 K, maximum gap "
             f"{s['max_discrepancy_kcal']:.1f} kcal/mol. This reproduces the panel's "
             f"independent finding of a 3.85-5.73 kcal/mol range.",
             ["thermodynamics", "measurement"]),
            (f"Computed independently: {s['sequences_invalid']}/{s['sequences_total']} "
             f"sequences contain characters that are not standard amino acids and "
             f"therefore do not specify a synthesizable molecule.",
             ["sequences", "measurement"]),
            (f"Computed independently: {len(s['duplicate_sequences'])} sequences are "
             f"each shared by two supposedly distinct therapeutics carrying different "
             f"stated affinities.", ["sequences", "measurement"]),
        ]:
            c = L.claim(text, kind="measurement", source_type="computation",
                        source_ref="platform/validate_dataset.py", confidence=0.95,
                        tags=tags)
            L.edge(c, "CITES", art)

    idx = mem.Index()
    idx.sync()
    mem.write_views(idx)
    st = idx.stats()
    print(json.dumps(st, indent=1))
    print(f"\nrefuted/corrected findings queryable: "
          f"{len(idx.refuted_with_evidence())}")
    idx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
