#!/usr/bin/env python3
"""Build data/dataset.json: the honest, provenance-carrying data layer.

Rules enforced here, so the UI cannot violate them:
  * Every scientific value is a {value, units, provenance} record.
  * Values this repo can compute (MW, charge, pI, GRAVY, formula, InChIKey) are COMPUTED
    and carry the software version.
  * Values retrieved from a public database are DATABASE and carry the accession.
  * Values that were hand-typed in the original app and cannot be reproduced
    (dG, Kd, pLDDT, hERG IC50, seizure index, efficacy percentages) are NOT emitted as
    results. They are preserved verbatim under `retracted_claims` so the record of what
    was previously asserted is not lost, and the live field becomes NOT_COMPUTED.

That last rule is the point. Deleting the numbers would hide the history; re-labelling
them as results would repeat the original error. Both are avoided.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbc import chem, peptide, provenance as pv, thermo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "extracted_raw.json"
CURATED = REPO / "data" / "curated.json"
OUT = REPO / "data" / "dataset.json"

RDKIT_VER = "RDKit 2026.03.5"
STDLIB_VER = f"python {sys.version.split()[0]} stdlib"

#: Fields in the original data that asserted a computation nobody performed.
UNREPRODUCIBLE = ("affinity", "safety")


def curated() -> dict:
    return json.loads(CURATED.read_text()) if CURATED.exists() else {}


def build_natural_products(raw: list[dict], cur: dict) -> list[dict]:
    by_name = {c["name"].lower(): c for c in (cur.get("chemistry", {}) or {}).get("compounds", [])}
    out = []
    for p in raw:
        name = p["name"]
        short = name.split("(")[0].strip().lower()
        ref = next((v for k, v in by_name.items() if short.split()[0] in k), None)

        rec: dict = {"name": name, "class": p.get("class", ""),
                     "target_text": p.get("target", ""),
                     "signaling_text": p.get("signaling", ""),
                     "description": p.get("description", "")}

        smiles = (ref or {}).get("isomeric_smiles")
        if smiles:
            rec["smiles"] = pv.database(smiles, "SMILES",
                                        f"PubChem CID {ref['pubchem_cid']}",
                                        label="Isomeric SMILES").to_dict()
            rep = chem.validate_smiles(name, smiles)
            rec["inchikey"] = pv.computed(rep.inchikey, "", "RDKit MolToInchiKey",
                                          RDKIT_VER, label="InChIKey").to_dict()
            rec["formula"] = pv.computed(rep.formula, "", "RDKit CalcMolFormula",
                                         RDKIT_VER, label="Molecular formula").to_dict()
            rec["mol_weight"] = pv.computed(rep.mol_weight, "Da", "RDKit Descriptors.MolWt",
                                            RDKIT_VER, label="Molecular weight",
                                            uncertainty="exact for a defined structure"
                                            ).to_dict()
            rec["clogp"] = pv.computed(rep.clogp, "", "RDKit Crippen MolLogP", RDKIT_VER,
                                       label="cLogP",
                                       uncertainty="Crippen estimate, ~1 log unit",
                                       applicability="drug-like organics").to_dict()
            rec["tpsa"] = pv.computed(rep.tpsa, "A^2", "RDKit TPSA", RDKIT_VER,
                                      label="Topological polar surface area").to_dict()
            rec["stereocenters_defined"] = pv.computed(
                (rep.stereocenters_total or 0) - (rep.stereocenters_unspecified or 0),
                "centres", "RDKit FindMolChiralCenters", RDKIT_VER,
                label="Defined stereocentres").to_dict()
            rec["cns_flags"] = rep.cns_mpo_flags
            rec["validation"] = {"parses": True, "warnings": rep.warnings}
        else:
            rec["smiles"] = pv.not_computed(
                "SMILES", label="Isomeric SMILES",
                note="The structure stored in the original app did not parse or encoded a "
                     "different molecule. A verified structure has not yet been curated."
            ).to_dict()
            rec["validation"] = {"parses": False,
                                 "original_smiles_field": p.get("smiles", "")}
        rec["binding_residues_text"] = {
            "value": p.get("residues", ""),
            "provenance": pv.Provenance(
                pv.Status.PLACEHOLDER,
                note="Residue numbers copied from the original app. They mix organism "
                     "numbering conventions (Torpedo californica AChE Trp84/Phe330 "
                     "alongside human Trp286/Tyr341) and must be re-derived against one "
                     "declared reference structure before use.").to_dict()}
        out.append(rec)
    return out


def build_candidate(name: str, seq: str, extra: dict, cur: dict) -> dict:
    rep = peptide.analyze(name, seq)
    rec: dict = {"code": name, "sequence": seq, "valid": rep.valid,
                 "errors": rep.errors, "liabilities": rep.liabilities}

    if rep.valid:
        rec["length"] = rep.length
        rec["mol_weight"] = pv.computed(
            rep.mol_weight, "Da", "sum of average residue masses + H2O", STDLIB_VER,
            label="Molecular weight").to_dict()
        rec["net_charge"] = pv.computed(
            rep.net_charge_ph74, "e", "Henderson-Hasselbalch over ionizable groups, "
            "EMBOSS pKa set, pH 7.4", STDLIB_VER, label="Net charge (pH 7.4)").to_dict()
        rec["isoelectric_point"] = pv.computed(
            rep.isoelectric_point, "pH", "bisection on net charge", STDLIB_VER,
            label="Isoelectric point").to_dict()
        rec["gravy"] = pv.computed(
            rep.gravy, "", "Kyte-Doolittle mean hydropathy", STDLIB_VER,
            label="GRAVY").to_dict()
        rec["cysteines"] = pv.computed(
            rep.n_cysteine, "residues", "sequence count", STDLIB_VER,
            label="Cysteine count").to_dict()
        rec["disulfide_connectivity"] = pv.not_computed(
            label="Disulfide connectivity",
            note="Not declared anywhere in the source data. With an even cysteine count "
                 "the folded product is ambiguous until connectivity is specified.").to_dict()
    else:
        for f in ("mol_weight", "net_charge", "isoelectric_point", "gravy"):
            rec[f] = pv.not_computed(
                label=f, note="Sequence contains non-standard residues, so no "
                              "physicochemical property is defined.").to_dict()

    # --- the values the original app asserted, now honestly unavailable ---------- #
    rec["binding_free_energy"] = pv.not_computed(
        "kcal/mol", label="Binding free energy (ΔG)",
        note="Not computed. No docking, MM-GBSA or FEP calculation has been performed in "
             "this repository, and structure predictors do not output free energies.").to_dict()
    rec["dissociation_constant"] = pv.not_computed(
        "M", label="Dissociation constant (Kd)",
        note="Not computed and not measured.").to_dict()
    rec["plddt"] = pv.not_computed(
        "0-100", label="pLDDT",
        note="No structure prediction has been run for this sequence. Submit the FASTA to "
             "a predictor and load the returned mmCIF and confidence JSON to populate "
             "this field with real per-residue values.").to_dict()
    rec["herg"] = pv.not_computed(
        "uM", label="hERG IC50",
        note="Not computed. hERG models are also largely outside their applicability "
             "domain for a multi-kDa polycationic peptide; membrane lysis and "
             "immunogenicity are the more relevant liabilities for this modality.").to_dict()

    retracted = {k: extra[k] for k in UNREPRODUCIBLE if extra.get(k)}
    if retracted:
        rec["retracted_claims"] = {
            "values": retracted,
            "reason": "These strings were present in the original app as though they were "
                      "computed results. No calculation produced them. They are preserved "
                      "here for the record and are not displayed as results.",
        }
        dg = thermo.parse_dg(extra.get("affinity", ""))
        kd, _ = thermo.parse_kd(extra.get("affinity", ""))
        if dg is not None and kd is not None:
            t = thermo.check(name, dg, kd)
            rec["retracted_claims"]["thermodynamic_audit"] = {
                # The two stated numbers are the discredited ones: they are quoted here
                # as PLACEHOLDER so they can never be mistaken for results again.
                "stated_dg": pv.placeholder(
                    dg, "kcal/mol", label="ΔG as originally asserted",
                    note="Retracted. No calculation produced this value.").to_dict(),
                "stated_kd": pv.placeholder(
                    kd, "M", label="Kd as originally asserted",
                    note="Retracted. No calculation produced this value.").to_dict(),
                # The audit itself is ours, and is computed.
                "kd_implied_by_stated_dg": pv.computed(
                    thermo.format_kd(t.kd_implied_by_dg), "", "Kd = exp(ΔG / RT), "
                    "RT = 0.59248 kcal/mol at 298.15 K", STDLIB_VER,
                    label="Kd implied by the stated ΔG").to_dict(),
                "discrepancy": pv.computed(
                    round(t.discrepancy_kcal, 2), "kcal/mol",
                    "|ΔG_stated − RT·ln(Kd_stated)| at 298.15 K", STDLIB_VER,
                    label="Internal inconsistency").to_dict(),
                "discrepancy_orders": pv.computed(
                    round(t.discrepancy_orders, 1), "log10 units",
                    "|log10(Kd_stated / Kd_implied)|", STDLIB_VER,
                    label="Inconsistency in orders of magnitude").to_dict(),
                "verdict": "internally inconsistent at 298.15 K",
            }
    for k in ("region", "name", "chemStruct", "bindingSites", "targets", "mechanism",
              "target"):
        if extra.get(k):
            rec[k] = extra[k]
    return rec


def main() -> int:
    raw = json.loads(RAW.read_text())
    cur = curated()

    ds = {
        "schema_version": "1.0",
        "built": date.today().isoformat(),
        "git_sha": pv.git_sha(),
        "disclosure": {
            "headline": "No structure prediction has been run in this repository.",
            "detail": (
                "This platform can parse, validate and display genuine structure-predictor "
                "output, and it computes real physicochemical and chemical properties. It "
                "does not itself run AlphaFold3 or any other predictor, and it contains no "
                "binding-affinity calculation. Every field is labelled with its provenance; "
                "fields marked 'not computed' are honestly empty rather than filled with an "
                "estimate. Values asserted by an earlier version of this project that no "
                "calculation supports are preserved under 'retracted_claims' and are not "
                "displayed as results."),
            "sequences": (
                "The peptide sequences are hand-assembled concatenations of published "
                "natural motifs joined by GGGGS linkers. They are a hypothesis catalogue, "
                "not de novo designs: no generative model produced them."),
        },
        "natural_products": build_natural_products(raw["NATURAL_PRODUCTS_DATA"], cur),
        "brain_regions": raw["BRAIN_REGIONS_DATA"],
        "candidates": [],
    }

    for d in raw["FULL_BRAIN_DRUGS_DATA"]:
        ds["candidates"].append(
            build_candidate(d["code"], d.get("sequence", ""), d, cur))
    for c in raw["AF3_CANDIDATES"]:
        ds["candidates"].append(
            build_candidate(c["code"], c.get("fasta", ""),
                            {"target": c.get("target", "")}, cur))

    if cur.get("motifs"):
        ds["motif_provenance"] = cur["motifs"]
    if cur.get("targets"):
        ds["target_records"] = cur["targets"]

    OUT.write_text(json.dumps(ds, indent=1))

    n_valid = sum(1 for c in ds["candidates"] if c["valid"])
    n_chem = sum(1 for n in ds["natural_products"] if n["validation"]["parses"])
    print(f"wrote {OUT.relative_to(REPO)}")
    print(f"  candidates:        {len(ds['candidates'])} ({n_valid} with a valid sequence)")
    print(f"  natural products:  {len(ds['natural_products'])} ({n_chem} with a verified structure)")
    print(f"  retracted claims:  {sum(1 for c in ds['candidates'] if 'retracted_claims' in c)}")
    print(f"  motif provenance:  {'yes' if cur.get('motifs') else 'pending curation'}")
    print(f"  target records:    {'yes' if cur.get('targets') else 'pending curation'}")

    problems = pv.audit({"natural_products": ds["natural_products"],
                         "candidates": ds["candidates"]})
    if problems:
        print(f"\n  PROVENANCE AUDIT: {len(problems)} bare numeric values found")
        for p in problems[:10]:
            print("   -", p)
        return 1
    print("\n  PROVENANCE AUDIT: clean — every numeric value carries a provenance record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
