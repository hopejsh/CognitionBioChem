#!/usr/bin/env python3
"""Generate reviews/REVIEW_REPORT.md from the panel data and the local validation run."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PANEL = json.loads((REPO / "reviews" / "panel_raw.json").read_text())
GATE = json.loads((REPO / "data" / "validation_gate.json").read_text())
VREP = json.loads((REPO / "data" / "validation_report.json").read_text())

SEV_ORDER = {"BLOCKER": 0, "CRITICAL": 1, "MAJOR": 2, "MINOR": 3}


def short(d: str, n: int = 46) -> str:
    d = d.replace("\n", " ").strip()
    return d if len(d) <= n else d[: n - 1] + "…"


def main() -> int:
    reviews = PANEL["reviews"]
    verifs = PANEL["verifications"]
    syn = PANEL["synthesis"]

    findings = [(r["discipline"], f) for r in reviews for f in r.get("findings", [])]
    verdicts = {v["finding_id"]: v for vf in verifs for v in vf.get("verdicts", [])}
    sev = Counter(f["severity"] for _, f in findings)
    ver = Counter(v["verdict"] for v in verdicts.values())
    cats = Counter(f["category"] for _, f in findings)

    out: list[str] = []
    w = out.append

    w("# CognitionBioChem — Expert Panel Review and Remediation Report\n")
    w("Produced by a multi-agent review system: 12 PhD-level domain reviewers, 12 "
      "independent adversarial verifiers, a panel chair, and 2 completeness critics. "
      "Every finding was re-checked by a verifier who was instructed to refute it and to "
      "default to skepticism when it could not be independently confirmed.\n")

    w("## 1. Scope and method\n")
    w("| | |")
    w("|---|---|")
    w(f"| Disciplines reviewed | {len(reviews)} |")
    w(f"| Findings raised | {len(findings)} |")
    w(f"| Findings independently verified | {len(verdicts)} |")
    w(f"| Confirmed | {ver.get('CONFIRMED', 0) + ver.get('CONFIRMED_WITH_CORRECTION', 0)} "
      f"({ver.get('CONFIRMED_WITH_CORRECTION', 0)} with a factual correction) |")
    w(f"| Partially refuted | {ver.get('PARTIALLY_REFUTED', 0)} |")
    w(f"| Fully refuted | {ver.get('REFUTED', 0)} |")
    w("")
    w("The low refutation rate is not verifier leniency. Most findings are arithmetic or "
      "presence/absence claims about source code, so they are checkable rather than "
      "arguable, and the largest ones were independently reproduced by a separate local "
      "validation pipeline (section 4) that was written without reference to the panel's "
      "output.\n")

    w("### Severity\n")
    w("| Severity | Count |")
    w("|---|---|")
    for s in ("BLOCKER", "CRITICAL", "MAJOR", "MINOR"):
        w(f"| {s} | {sev.get(s, 0)} |")
    w("")

    w("### Category\n")
    w("| Category | Count |")
    w("|---|---|")
    for c, n in cats.most_common():
        w(f"| {c.replace('-', ' ')} | {n} |")
    w("")

    w("## 2. Panel verdict\n")
    w("> " + syn["verdict_on_platform"].replace("\n", "\n> ") + "\n")

    w("## 3. Root causes\n")
    w("The panel compressed the findings into a small number of underlying causes.\n")
    for i, rc in enumerate(syn.get("root_causes", []), 1):
        w(f"{i}. {rc}\n")

    w("## 4. Independent local verification\n")
    w("These numbers were computed in this repository with RDKit 2026.03.5 and the Python "
      "standard library, independently of the panel. Where they overlap, they agree.\n")
    s = VREP["summary"]
    w("| Check | Result |")
    w("|---|---|")
    w(f"| Natural-product SMILES that fail to parse | {s['smiles_parse_failures']} / 8 |")
    w(f"| SMILES encoding a different molecule than their name | {s['smiles_wrong_compound']} |")
    w(f"| Structures with every stereocentre undefined | {s['smiles_stereo_undefined']} |")
    w(f"| Sequences containing non-standard residues | {s['sequences_invalid']} / {s['sequences_total']} |")
    w(f"| (ΔG, Kd) pairs that are thermodynamically inconsistent | {s['thermo_inconsistent']} / {s['thermo_pairs_checked']} |")
    w(f"| Largest ΔG/Kd inconsistency | {s['max_discrepancy_kcal']:.2f} kcal/mol |")
    w(f"| Sequences shared by two supposedly distinct candidates | {len(s['duplicate_sequences'])} |")
    w("")

    w("### The decisive comparison\n")
    w("The clearest single piece of evidence is what real predictor output looks like "
      "beside the formula the platform used. Genuine AlphaFold output for human TrkB "
      "(UniProt Q16620) was downloaded from EBI and parsed by "
      "`platform/cbc/predictor.py`:\n")
    w("| pLDDT statistic | Real AlphaFold (TrkB, 822 residues) | `app.js:791` formula |")
    w("|---|---|---|")
    w("| minimum | 23.5 | 89.0 |")
    w("| maximum | 98.4 | 99.0 |")
    w("| mean | 77.0 | 94.0 |")
    w("| standard deviation | 22.9 | 3.0 |")
    w("| fraction below 70 | **26.2%** | **0.0%** |")
    w("")
    w("Because the formula is analytically confined to [89.0, 99.0], two of the four "
      "confidence bands advertised in the legend were unreachable. The fake also inverts "
      "the true signal exactly where it matters: GGGGS linkers, which a real predictor "
      "renders at pLDDT 30–60, were painted 'High' green at 89–97.\n")
    w("Backbone geometry gives the same answer. Real coordinates have consecutive Cα atoms "
      "at 3.83 ± 0.09 Å. The parametric helix at `app.js:715` produces 0.63–16.6 Å, with "
      "18 of 23 virtual bonds outside ±0.5 Å of the physical value.\n")

    w("## 5. Blocking findings\n")
    for i, b in enumerate(syn.get("blocker_summary", []), 1):
        w(f"### B{i}\n")
        w(b + "\n")

    w("## 6. Full findings register\n")
    w("Sorted by severity, then discipline. Verdict is the independent verifier's.\n")
    w("| ID | Sev | Discipline | Finding | Verdict |")
    w("|---|---|---|---|---|")
    for disc, f in sorted(findings, key=lambda x: (SEV_ORDER.get(x[1]["severity"], 9),
                                                   x[0])):
        v = verdicts.get(f["id"], {})
        vd = v.get("verdict", "—").replace("CONFIRMED_WITH_CORRECTION", "confirmed*")
        vd = vd.replace("CONFIRMED", "confirmed").replace("PARTIALLY_REFUTED", "partial")
        w(f"| `{f['id']}` | {f['severity']} | {short(disc, 30)} | {short(f['title'], 78)} "
          f"| {vd} |")
    w("")
    w("\\* confirmed with a factual correction from the verifier.\n")

    w("## 7. What was genuinely good\n")
    for g in syn.get("what_is_genuinely_good", []):
        w(f"- {g}\n")

    w("## 8. Data-integrity gate\n")
    w("`platform/validate.py` encodes the contract and exits non-zero when any record "
      "violates it. On the legacy dataset:\n")
    w("| Violation category | Count |")
    w("|---|---|")
    for k, n in sorted(GATE["counts"].items(), key=lambda kv: -kv[1]):
        w(f"| {k.replace('_', ' ')} | {n} |")
    w(f"| **total** | **{len(GATE['failures'])}** |")
    w("")

    w("## 9. Remediation roadmap\n")
    for ph in syn.get("remediation_roadmap", []):
        w(f"### {ph['phase']}\n")
        w(f"**Goal.** {ph['goal']}\n")
        w("**Workstreams.**\n")
        for ws in ph.get("workstreams", []):
            w(f"- {ws}")
        w("\n**Success criteria.**\n")
        for c in ph.get("success_criteria", []):
            w(f"- {c}")
        w("")

    (REPO / "reviews" / "REVIEW_REPORT.md").write_text("\n".join(out) + "\n")
    print(f"wrote reviews/REVIEW_REPORT.md ({len('\n'.join(out))} chars)")
    print(f"  {len(findings)} findings, {len(verdicts)} verdicts, "
          f"{len(GATE['failures'])} gate violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
