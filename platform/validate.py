#!/usr/bin/env python3
"""The data-integrity gate for CognitionBioChem.

Exits non-zero if any scientific record in the repository fails validation. Run it in CI
and before any release. Applied to the original dataset it fails loudly, which is the
correct behaviour and the whole point: a real pipeline rejects these inputs.

Usage:
    ./.venv/bin/python platform/validate.py [--data data/extracted_raw.json] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbc import chem, peptide, thermo  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

#: |dG - RT ln Kd| above this is a hard failure.
THERMO_TOLERANCE_KCAL = 0.3

#: Targets on the outer face of the plasma membrane or secreted. A peptide with no
#: cell-penetrating mechanism cannot engage anything not on this list.
EXTRACELLULAR_TARGETS = {
    "trkb", "trka", "ngf", "bdnf", "fzd", "frizzled", "nachr", "achr", "ache",
    "glun", "nmda", "grin", "trem2", "tlr4", "pafr", "m1", "chrm", "eaat", "slc1a2",
}
#: Compartments a non-penetrating extracellular peptide provably cannot reach.
CYTOPLASMIC_TARGETS = {
    "zo-1", "zo1", "occludin", "keap1", "nrf2", "gsk-3", "gsk3", "ampk", "lc3",
    "mtor", "creb", "enos", "nos3", "beta-catenin", "p65",
}


class Gate:
    def __init__(self) -> None:
        self.failures: list[dict] = []
        self.counts: dict[str, int] = defaultdict(int)

    def fail(self, category: str, record: str, detail: str) -> None:
        self.failures.append({"category": category, "record": record, "detail": detail})
        self.counts[category] += 1

    # -- checks ---------------------------------------------------------------- #

    def check_chemistry(self, products: list[dict]) -> None:
        for p in products:
            rep = chem.validate_smiles(p["name"], p.get("smiles", ""))
            if not rep.parses:
                self.fail("smiles_unparseable", p["name"],
                          rep.errors[0] if rep.errors else "does not parse")
                continue
            ref = chem.compare_to_reference(p["name"], p["smiles"])
            if ref.get("compared") and not ref["same_constitution"]:
                self.fail("smiles_wrong_molecule", p["name"],
                          f"stored InChIKey {ref['stored_inchikey']} != reference "
                          f"{ref['reference_inchikey']} ({ref['reference']}, "
                          f"PubChem CID {ref['pubchem_cid']})")
            if rep.stereocenters_unspecified:
                self.fail("stereochemistry_undefined", p["name"],
                          f"{rep.stereocenters_unspecified}/{rep.stereocenters_total} "
                          f"stereocentres undefined = up to "
                          f"{rep.implied_stereoisomers:,} stereoisomers")

    def check_sequences(self, records: list[tuple[str, str]]) -> None:
        for name, seq in records:
            rep = peptide.analyze(name, seq)
            if not rep.valid:
                self.fail("sequence_invalid", name,
                          f"non-standard residues {rep.invalid_residues}: "
                          f"{rep.errors[0][:120]}")
                continue
            if rep.n_cysteine and rep.n_cysteine % 2 == 1:
                self.fail("cysteine_parity", name,
                          f"{rep.n_cysteine} cysteines (odd): at least one free thiol, "
                          "and no disulfide connectivity is declared")
            elif rep.n_cysteine >= 4:
                self.fail("disulfide_undeclared", name,
                          f"{rep.n_cysteine} cysteines admit "
                          f"{peptide._double_factorial(rep.n_cysteine - 1)} pairings; "
                          "no connectivity declared, so the folded product is undefined")

    def check_thermo(self, records: list[tuple[str, str]]) -> None:
        for name, affinity in records:
            dg = thermo.parse_dg(affinity)
            kd, kd_text = thermo.parse_kd(affinity)
            if dg is None and kd is None:
                continue
            rep = thermo.check(name, dg, kd, kd_text,
                               tolerance_kcal=THERMO_TOLERANCE_KCAL)
            if rep.consistent is False:
                self.fail("thermodynamic_inconsistency", name,
                          f"dG {dg} kcal/mol implies Kd "
                          f"{thermo.format_kd(rep.kd_implied_by_dg)}, record states "
                          f"{thermo.format_kd(kd)} — gap "
                          f"{rep.discrepancy_kcal:.2f} kcal/mol "
                          f"({rep.discrepancy_orders:.1f} orders of magnitude)")
            if rep.plausible is False:
                self.fail("affinity_implausible", name,
                          f"dG {dg} kcal/mol is tighter than biotin-streptavidin")

    def check_duplicates(self, groups: dict[str, list[tuple[str, dict]]]) -> None:
        for seq, entries in groups.items():
            if len(entries) < 2:
                continue
            names = [n for n, _ in entries]
            metrics = {json.dumps({k: v.get(k) for k in ("affinity", "dg", "plddt")},
                                  sort_keys=True) for _, v in entries}
            detail = f"sequence shared by {names}"
            if len(metrics) > 1:
                detail += (f"; and they carry {len(metrics)} DIFFERENT metric sets — "
                           "one molecule cannot have several binding free energies")
            self.fail("duplicate_sequence", seq[:32] + "...", detail)

    def check_compartments(self, records: list[tuple[str, str, str]]) -> None:
        """An extracellular peptide aimed at a cytoplasmic target cannot work."""
        for name, seq, target in records:
            t = target.lower()
            cyto = [k for k in CYTOPLASMIC_TARGETS if k in t]
            if not cyto:
                continue
            rep = peptide.analyze(name, seq)
            if not rep.valid:
                continue
            penetrating = rep.valid and rep.frac_cationic >= 0.30
            if not penetrating:
                self.fail("compartment_mismatch", name,
                          f"targets {cyto[0]!r}, which is cytoplasmic, with a peptide "
                          f"carrying no cell-penetrating motif (net charge "
                          f"{rep.net_charge_ph74:+.1f}, {rep.frac_cationic:.0%} K/R). "
                          "An extracellular peptide cannot reach a cytosolic protein.")

    def check_residues(self, records: list[tuple[str, str]]) -> None:
        """Residue identities asserted by the data, checked against the real sequence.

        Each entry in data/residue_audit.json was verified by retrieving the UniProt
        sequence and slicing it at the cited position, so a hit here means the dataset
        names an amino acid that is not at that position in any numbering convention.
        """
        audit_path = REPO / "data" / "residue_audit.json"
        if not audit_path.exists():
            return
        audit = json.loads(audit_path.read_text())
        for name, sites in records:
            for f in audit["fabricated"]:
                if f["asserted"] in sites:
                    self.fail("fabricated_residue", name,
                              f"asserts {f['asserted']} for {f['target']}, but "
                              f"{f['uniprot']} position {f['asserted'][3:]} is "
                              f"{f['actual']}. {f['note']}")
            for n in audit["numbering_convention_errors"]:
                if all(r in sites for r in ("Trp84", "Trp286")):
                    self.fail("mixed_numbering_convention", name, n["problem"] + ". "
                              + n["resolution"][:200])
                    break

    def check_placeholder_text(self, records: list[tuple[str, str]]) -> None:
        for name, seq in records:
            if any(w in seq.lower() for w in ("linker", "conjugate", "peptide", "core")):
                if not set(seq) <= set(peptide.STANDARD_AA):
                    self.fail("prose_in_sequence_field", name,
                              f"sequence field contains descriptive prose, not a "
                              f"sequence: {seq!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="CognitionBioChem data-integrity gate")
    ap.add_argument("--data", default=str(REPO / "data" / "extracted_raw.json"))
    ap.add_argument("--json", action="store_true", help="emit machine-readable output")
    a = ap.parse_args()

    raw = json.loads(Path(a.data).read_text())
    g = Gate()

    g.check_chemistry(raw["NATURAL_PRODUCTS_DATA"])

    drugs = raw["FULL_BRAIN_DRUGS_DATA"]
    cands = raw["AF3_CANDIDATES"]

    seq_records = [(d["code"], d.get("sequence", "")) for d in drugs] + \
                  [(c["code"], c.get("fasta", "")) for c in cands]
    g.check_placeholder_text(seq_records)
    g.check_sequences(seq_records)

    g.check_thermo([(d["code"], d.get("affinity", "")) for d in drugs])
    g.check_thermo([(c["code"], f"dG = {c['dg']} kcal/mol") for c in cands
                    if c.get("dg") is not None])

    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for d in drugs:
        groups[d.get("sequence", "")].append((d["code"], d))
    for c in cands:
        groups[c.get("fasta", "")].append((c["code"], c))
    g.check_duplicates(groups)

    g.check_compartments([(d["code"], d.get("sequence", ""),
                           f"{d.get('bindingSites','')} {d.get('targets','')}")
                          for d in drugs])

    g.check_residues([(d["code"], d.get("bindingSites", "")) for d in drugs]
                     + [(p["name"], p.get("residues", ""))
                        for p in raw["NATURAL_PRODUCTS_DATA"]])

    if a.json:
        print(json.dumps({"passed": not g.failures, "counts": dict(g.counts),
                          "failures": g.failures}, indent=1))
    else:
        _report(g)
    return 1 if g.failures else 0


def _report(g: Gate) -> None:
    print("=" * 84)
    print("CognitionBioChem data-integrity gate")
    print("=" * 84)
    if not g.failures:
        print("\nPASS — every record satisfies the data contract.\n")
        return
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for f in g.failures:
        by_cat[f["category"]].append(f)
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        items = by_cat[cat]
        print(f"\n### {cat}  ({len(items)})")
        for f in items[:6]:
            print(f"  - {f['record']}")
            print(f"      {f['detail'][:150]}")
        if len(items) > 6:
            print(f"  ... and {len(items) - 6} more")
    print("\n" + "=" * 84)
    print(f"FAIL — {len(g.failures)} violations across {len(by_cat)} categories")
    print("counts: " + json.dumps(dict(g.counts)))
    print("=" * 84)


if __name__ == "__main__":
    raise SystemExit(main())
