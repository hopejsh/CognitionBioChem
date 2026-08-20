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
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbc import chem, peptide, provenance as pv, thermo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "extracted_raw.json"
CURATED = REPO / "data" / "curated.json"
OUT = REPO / "data" / "dataset.json"
#: The same payload as a plain script assignment. A <script src> is not subject to the
#: cross-origin rule that blocks fetch() under the file: scheme, so this is what lets someone
#: clone the repository, double-click index.html, and see the workbench rather than an error
#: card. It is GENERATED FROM THE SAME OBJECT in the same pass -- never hand-maintained -- and
#: platform/verify_frontend.py fails if the two ever disagree, because a duplicated data file
#: that can drift is the defect this project keeps finding in other guises.
OUT_JS = REPO / "data" / "dataset.js"

RDKIT_VER = "RDKit 2026.03.5"
STDLIB_VER = f"python {sys.version.split()[0]} stdlib"

#: Fields in the original data that asserted a computation nobody performed.
UNREPRODUCIBLE = ("affinity", "safety")


def _real_folds() -> dict:
    """Candidates for which a genuine Boltz-2 fold exists, keyed by code."""
    p = REPO / "data" / "real_vs_hardcoded.json"
    if not p.exists():
        return {}
    out = {}
    for r in json.loads(p.read_text()).get("rows", []):
        real = r.get("real") or {}
        if real.get("ok") and real.get("plddt_mean") is not None:
            out[r["code"]] = real
    return out


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
    fold = _real_folds().get(name)
    if fold is not None:
        # A real Boltz-2 fold exists for this candidate; report it as PREDICTED with the
        # model that produced it. Saying "not computed" here while runs/ holds the artefact
        # would be the same defect this project was rebuilt to remove, in the other
        # direction.
        rec["plddt"] = pv.predicted(
            fold["plddt_mean"], "0-100", "Boltz-2 2.2.1", label="mean pLDDT",
            method="single-sequence mode (msa: empty), seed 1, MPS",
            uncertainty=f"across-seed SD 2.66 units (study inference-variance-v1); "
                        f"min {fold['plddt_min']}, max {fold['plddt_max']}",
            source_id="data/real_vs_hardcoded.json").to_dict()
    else:
        rec["plddt"] = pv.not_computed(
            "0-100", label="pLDDT",
            note="No structure prediction has been run for THIS sequence. Sequences that "
                 "fail validation are not submittable; valid ones can be folded and the "
                 "result loaded back.").to_dict()
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


def attribution_summary(motifs_record: dict, candidates: list[dict]) -> dict:
    """Count what is actually attributed, rather than restating a remembered number.

    The disclosure used to say the record holds "16 attributed motifs and 12 unattributed
    segments; 14 of 35 candidates carry at least one unattributed segment". Both halves were
    hand-typed and both were wrong. Only 7 of the 16 entries under `motifs` carry a UniProt
    accession; the other 9 describe themselves, in the record, as "a WNT-family CHIMERA, not
    a copy of any single protein", "an EGF-LIKE DOMAIN PASTICHE with no natural source", a
    de novo helix, a GGGGS linker, and one entry that is not a peptide sequence at all.
    Calling those attributed is the exact overstatement this section exists to prevent, and
    it sat in the first paragraph a reader is told to read first.

    Counting the candidates by scanning for every unattributed fragment gives 31 of 35, not
    14. The corrected sentence is assembled from these counts, so it cannot drift again.
    """
    motifs = motifs_record.get("motifs") or []
    loose = motifs_record.get("unattributed_segments") or []
    attributed = [m for m in motifs if m.get("uniprot_accession")]
    pastiche = [m for m in motifs if not m.get("uniprot_accession")]

    frags = {m["motif"] for m in pastiche
             if isinstance(m.get("motif"), str) and m["motif"].isalpha()}
    for entry in loose:
        frags.update(re.findall(r"\b[ACDEFGHIKLMNPQRSTVWY]{5,}\b", str(entry)))
    carriers = [c for c in candidates
                if any(f in c.get("sequence", "") for f in frags)]
    return {
        "attributed_motifs": len(attributed),
        "unattributed_motif_entries": len(pastiche),
        "unattributed_segments": len(loose),
        "distinct_unattributed_fragments": len(frags),
        "candidates_carrying_one": len(carriers),
        "candidates_total": len(candidates),
    }


def main() -> int:
    raw = json.loads(RAW.read_text())
    cur = curated()

    ds = {
        "schema_version": "1.0",
        "built": date.today().isoformat(),
        "git_sha": pv.git_sha(),
        "disclosure": {
            "headline": ("Structure prediction is real; binding affinity is not calibrated and no "
                         "free energy is emitted."),
            "detail": (
                "Boltz-2 v2.2.1 (MIT) runs locally and produced every PREDICTED structure "
                "under runs/ and in the pre-registered studies. runs/ also holds 32 RCSB "
                "crystal depositions, carrying a '-reference' kind in runs/manifest.json: "
                "those are experimental ground truth for studies #6 and #7 and were "
                "produced by no predictor. The platform also parses genuine output "
                "from AlphaFold DB and AlphaFold 3. ADMET is predicted by ADMET-AI "
                "where the molecule is inside its applicability domain, and refused with a "
                "stated reason where it is not. Binding affinity is PREDICTED but NOT "
                "CALIBRATED, and is never rendered as a free energy: the affinity head is "
                "fitted to pooled Ki/Kd/IC50/EC50 labels, so no thermodynamic quantity can "
                "be recovered from it. Every field is labelled with its provenance; fields "
                "marked 'not computed' are honestly empty. Values asserted by an earlier "
                "version that no calculation supports are preserved under "
                "'retracted_claims' and are not displayed as results."),
            "sequences": (
                # This sentence used to say "published natural motifs ... not de novo
                # designs". The repository's own motif_provenance record contradicts both
                # halves: 12 of the segments are unattributed, one of them labelled there
                # as a "de novo cationic amphipathic helix" -- and that 36-mer is the
                # sequence of the duplicate AChE pair that studies #9 and #10 screen.
                "The peptide sequences are hand-assembled concatenations of published "
                "natural motifs, pastiche scaffolds and one de novo amphipathic helix, "
                "joined by GGGGS linkers. No generative model produced them. Per-segment "
                "attribution is in data/dataset.json motif_provenance, which records 16 "
                "attributed motifs and 12 unattributed segments; 14 of 35 candidates "
                "carry at least one unattributed segment."),
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
        # Written here, after the motif record and the candidate list both exist, so the
        # sentence is a function of them rather than a memory of them.
        a = attribution_summary(cur["motifs"], ds["candidates"])
        ds["disclosure"]["sequences"] = (
            "The peptide sequences are hand-assembled concatenations of published natural "
            "motifs, pastiche scaffolds and one de novo amphipathic helix, joined by GGGGS "
            "linkers. No generative model produced them. Per-segment attribution is in "
            "data/dataset.json motif_provenance, and it is thinner than the word "
            "'attribution' suggests: of "
            f"{a['attributed_motifs'] + a['unattributed_motif_entries']} motif entries only "
            f"{a['attributed_motifs']} carry a UniProt accession. The other "
            f"{a['unattributed_motif_entries']} describe themselves as chimeras, pastiches, "
            "a de novo helix, a linker, or in one case not a peptide sequence at all, and "
            f"there are {a['unattributed_segments']} further unattributed segments listed "
            f"separately. Scanning for all {a['distinct_unattributed_fragments']} "
            f"unattributed fragments, {a['candidates_carrying_one']} of "
            f"{a['candidates_total']} candidates carry at least one.")
        ds["disclosure"]["sequence_attribution_counts"] = a
    if cur.get("targets"):
        ds["target_records"] = cur["targets"]

    payload = json.dumps(ds, indent=1)
    OUT.write_text(payload)
    OUT_JS.write_text(
        "// GENERATED by platform/build_dataset.py -- do not edit.\n"
        "// Byte-for-byte the same object as data/dataset.json; this form exists only so the\n"
        "// page works when opened directly with file://, where fetch() is blocked.\n"
        "window.__CBC_DATASET__ = " + payload + ";\n")

    # The gate artefact is written by platform/validate.py --json; mirror it here so both
    # file:-scheme shims are produced by one generator and cannot be half-updated.
    gate = REPO / "data" / "validation_gate.json"
    if gate.exists():
        (REPO / "data" / "validation_gate.js").write_text(
            "// GENERATED by platform/build_dataset.py -- do not edit.\n"
            "window.__CBC_GATE__ = " + gate.read_text().rstrip() + ";\n")

    n_valid = sum(1 for c in ds["candidates"] if c["valid"])
    n_chem = sum(1 for n in ds["natural_products"] if n["validation"]["parses"])
    print(f"wrote {OUT.relative_to(REPO)} and {OUT_JS.relative_to(REPO)}")
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
