#!/usr/bin/env python3
"""Run every validator over the CognitionBioChem dataset and emit a machine-readable report.

Usage:  ./.venv/bin/python platform/validate_dataset.py
Output: data/validation_report.json  +  a human summary on stdout
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbc import chem, peptide, thermo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "extracted_raw.json"
OUT = REPO / "data" / "validation_report.json"


def main() -> int:
    raw = json.loads(RAW.read_text())
    report: dict = {"natural_products": [], "af3_candidates": [], "drugs": [],
                    "summary": {}}

    # ---------------- Natural products: chemistry ---------------------------- #
    for np_ in raw["NATURAL_PRODUCTS_DATA"]:
        r = chem.validate_smiles(np_["name"], np_["smiles"])
        d = r.to_dict()
        d["reference_check"] = chem.compare_to_reference(np_["name"], np_["smiles"]) \
            if r.parses else {"compared": False, "reason": "did not parse"}
        report["natural_products"].append(d)

    # ---------------- AF3 candidates: sequences + thermodynamics -------------- #
    for c in raw["AF3_CANDIDATES"]:
        p = peptide.analyze(c["code"], c["fasta"])
        t = thermo.check(c["code"], dg=c.get("dg"), kd_molar=None)
        report["af3_candidates"].append({
            "code": c["code"], "target": c["target"],
            "stated_plddt": c.get("plddt"), "stated_dg": c.get("dg"),
            "stated_cei": c.get("cei"),
            "peptide": p.to_dict(), "thermo": t.to_dict(),
        })

    # ---------------- 25 drugs: sequences + thermodynamics -------------------- #
    for dr in raw["FULL_BRAIN_DRUGS_DATA"]:
        aff = dr.get("affinity", "")
        dg = thermo.parse_dg(aff)
        kd, kd_text = thermo.parse_kd(aff)
        t = thermo.check(dr["code"], dg=dg, kd_molar=kd, kd_text=kd_text)
        p = peptide.analyze(dr["code"], dr.get("sequence", ""))
        plddt = re.search(r"pLDDT\s*=\s*([\d.]+)", aff)
        report["drugs"].append({
            "id": dr["id"], "code": dr["code"], "region": dr["region"],
            "affinity_string": aff, "safety_string": dr.get("safety", ""),
            "stated_plddt": float(plddt.group(1)) if plddt else None,
            "peptide": p.to_dict(), "thermo": t.to_dict(),
        })

    # ---------------- Cross-cutting checks ------------------------------------ #
    seqs: dict[str, list[str]] = {}
    for dr in raw["FULL_BRAIN_DRUGS_DATA"]:
        seqs.setdefault(dr.get("sequence", ""), []).append(dr["code"])
    duplicates = {s: c for s, c in seqs.items() if len(c) > 1}

    all_pep = ([d["peptide"] for d in report["drugs"]]
               + [c["peptide"] for c in report["af3_candidates"]])
    all_thermo = ([d["thermo"] for d in report["drugs"]]
                  + [c["thermo"] for c in report["af3_candidates"]])

    report["summary"] = {
        "natural_products_total": len(report["natural_products"]),
        "smiles_parse_failures": sum(
            1 for n in report["natural_products"] if not n["parses"]),
        "smiles_wrong_compound": sum(
            1 for n in report["natural_products"]
            if n["reference_check"].get("compared")
            and not n["reference_check"].get("same_constitution")),
        "smiles_stereo_undefined": sum(
            1 for n in report["natural_products"]
            if (n.get("stereocenters_unspecified") or 0) > 0),
        "sequences_total": len(all_pep),
        "sequences_invalid": sum(1 for p in all_pep if not p["valid"]),
        "sequences_with_liabilities": sum(1 for p in all_pep if p["liabilities"]),
        "duplicate_sequences": {s[:40] + "...": c for s, c in duplicates.items()},
        "thermo_pairs_checked": sum(
            1 for t in all_thermo if t["consistent"] is not None),
        "thermo_inconsistent": sum(1 for t in all_thermo if t["consistent"] is False),
        "thermo_implausible": sum(1 for t in all_thermo if t["plausible"] is False),
        "max_discrepancy_kcal": max(
            (t["discrepancy_kcal"] or 0) for t in all_thermo) if all_thermo else 0,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1))
    _print_summary(report)
    return 0


def _print_summary(rep: dict) -> None:
    s = rep["summary"]
    print("=" * 88)
    print("CognitionBioChem dataset validation -- every number below is computed")
    print("=" * 88)

    print("\n--- CHEMISTRY: 8 natural product SMILES ---")
    for n in rep["natural_products"]:
        status = "OK   " if n["parses"] and not n["errors"] else "FAIL "
        print(f"{status} {n['name'][:45]:47s} ", end="")
        if not n["parses"]:
            print(f"\n        -> {n['errors'][0][:120]}")
            continue
        rc = n["reference_check"]
        if rc.get("compared"):
            same = rc["same_constitution"]
            print(f"{n['formula']:12s} {'MATCHES ref' if same else 'WRONG STRUCTURE'}")
            if not same:
                print(f"        -> stored InChIKey  {rc['stored_inchikey']}")
                print(f"           reference        {rc['reference_inchikey']} "
                      f"({rc['reference']}, PubChem CID {rc['pubchem_cid']})")
                if rc["stored_formula"] == rc["reference_formula"]:
                    print("           same formula, different connectivity: a positional"
                          " isomer, not the named compound")
                else:
                    print(f"           formula differs: {rc['stored_formula']} vs "
                          f"{rc['reference_formula']}")
        else:
            print(f"{n['formula']:12s} (no reference on file)")
        if n["stereocenters_unspecified"]:
            print(f"        -> {n['stereocenters_unspecified']}/"
                  f"{n['stereocenters_total']} stereocentres undefined = "
                  f"{n['implied_stereoisomers']:,} possible stereoisomers")

    print("\n--- SEQUENCES: invalid residues ---")
    bad = [p for p in ([d["peptide"] for d in rep["drugs"]]
                       + [c["peptide"] for c in rep["af3_candidates"]])
           if not p["valid"]]
    if not bad:
        print("  none")
    for p in bad:
        print(f"  FAIL {p['name']:28s} {p['invalid_residues']}")
        print(f"       {p['errors'][0][:130]}")

    print("\n--- THERMODYNAMICS: stated dG vs stated Kd ---")
    rows = [d for d in rep["drugs"] if d["thermo"]["consistent"] is not None]
    print(f"  {'candidate':30s} {'dG':>7s} {'Kd stated':>12s} "
          f"{'Kd implied by dG':>18s} {'gap':>10s}")
    for d in rows[:8]:
        t = d["thermo"]
        print(f"  {d['code'][:29]:30s} {t['dg_stated']:>7.1f} "
              f"{thermo.format_kd(t['kd_stated_molar']):>12s} "
              f"{thermo.format_kd(t['kd_implied_by_dg']):>18s} "
              f"{t['discrepancy_kcal']:>7.1f} kcal")
    if len(rows) > 8:
        print(f"  ... and {len(rows) - 8} more")
    print(f"\n  inconsistent pairs: {s['thermo_inconsistent']}/{s['thermo_pairs_checked']}"
          f"   max gap: {s['max_discrepancy_kcal']:.1f} kcal/mol")

    print("\n--- DUPLICATE SEQUENCES ---")
    if not s["duplicate_sequences"]:
        print("  none")
    for seq, codes in s["duplicate_sequences"].items():
        print(f"  {len(codes)}x  {codes}")
        print(f"       {seq}")

    print("\n--- SUMMARY ---")
    for k, v in s.items():
        if k != "duplicate_sequences":
            print(f"  {k:34s} {v}")
    print("=" * 88)


if __name__ == "__main__":
    raise SystemExit(main())
