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
import re
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
            # CYTOPLASMIC_TARGETS is a set, so iterating it yields matches in hash order and
            # Python randomises string hashing per process. Reporting cyto[0] therefore made
            # this record read 'keap1' in one run and 'nrf2' in the next, and the artefact
            # served to the Validation tab changed between runs while its counts stayed put.
            # Sort, and name every cytoplasmic target the record mentions rather than one.
            cyto = sorted(k for k in CYTOPLASMIC_TARGETS if k in t)
            if not cyto:
                continue
            rep = peptide.analyze(name, seq)
            if not rep.valid:
                continue
            penetrating = rep.valid and rep.frac_cationic >= 0.30
            if not penetrating:
                self.fail("compartment_mismatch", name,
                          f"targets {', '.join(repr(c) for c in cyto)}, which "
                          f"{'is' if len(cyto) == 1 else 'are'} cytoplasmic, with a peptide "
                          f"carrying no cell-penetrating motif (net charge "
                          f"{rep.net_charge_ph74:+.1f}, {rep.frac_cationic:.0%} K/R). "
                          "An extracellular peptide cannot reach a cytosolic protein.")

    def check_residues(self, records: list[tuple[str, str]]) -> None:
        """Resolve every residue annotation against the target registry.

        This replaces a static list of eight known-bad annotations with live resolution:
        each `Xaa123` token in a binding-site string is looked up in the UniProt sequence
        under both the canonical and the mature-chain convention, and the annotation is a
        failure only if it is false under BOTH. That distinction is the whole point — a
        mismatch under one convention is a numbering problem, a mismatch under every
        convention is a wrong residue identity.

        Resolving live also catches annotations nobody thought to audit, and catches the
        subtler case where an annotation happens to resolve under a convention different
        from the one its neighbours in the same string use.
        """
        reg_path = REPO / "data" / "target_registry.json"
        if not reg_path.exists():
            return
        from cbc import registry as R
        reg = json.loads(reg_path.read_text())

        def record_for(sym: str):
            t = reg["targets"][sym]
            return R.TargetRecord(
                symbol=sym, uniprot=t["uniprot"], length=t["length"],
                sequence=t["sequence"],
                signal_peptide=tuple(t["signal_peptide"]) if t["signal_peptide"] else None,
                chain=tuple(t["chain"]) if t["chain"] else None)

        # Which target a binding-site string refers to. Aliases are matched with word
        # boundaries: a bare substring test let the CHRM1 alias "M1" match "TM1", i.e. the
        # transmembrane-helix label in "PAFR His14 (TM1), Tyr200 (TM5)", and attributed
        # PAFR's residues to the muscarinic receptor.
        ALIASES = {
            "ACHE": ("AChE", "acetylcholinesterase"), "NTRK2": ("TrkB",),
            "NTRK1": ("TrkA",), "KEAP1": ("Keap1",), "TREM2": ("Trem2", "TREM2"),
            "FZD8": ("Frizzled-8", "FZD8", "Fzd"), "GRIN2A": ("GluN2A",),
            "GRIN2B": ("GluN2B",), "CHRNA7": ("nAChR", "α7", "alpha-7"),
            "TLR4": ("TLR4",), "PTAFR": ("PAFR",), "CHRM1": ("M1",),
            "GSK3B": ("GSK-3", "GSK3"), "SLC1A2": ("EAAT2",), "NOS3": ("eNOS",),
            "NFE2L2": ("Nrf2",),
        }
        #: Proteins these strings name that are NOT in the registry. A residue belonging to
        #: one of them cannot be resolved here, and must be reported as unresolvable rather
        #: than silently re-checked against whichever registry target shares the string.
        OUT_OF_REGISTRY = ("BACE1", "GABA_A", "GABA-A", "AMPK", "Aβ", "Abeta", "LC3",
                           "ZO-1", "occludin", "ER-β", "mTOR", "PSD-95", "APP")
        token = re.compile(r"\b([A-Z][a-z]{2})(\d+)\b")

        def _alias_in(text: str, alias: str) -> bool:
            return re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
                             text, re.I) is not None

        for name, sites in records:
            # A binding-site string routinely names SEVERAL proteins, e.g.
            #   "AMPK α-subunit kinase domain (Lys45, Arg67); TrkB Ig-like D5 (Asp298)"
            # Checking every token against every matched target made residues that are
            # correct for one protein fail against another and be reported as fabricated.
            # Tokens are therefore scoped to the clause that names their own target.
            segments = [seg for seg in re.split(r"[;&]", sites) if seg.strip()]
            conventions_used: set[str] = set()
            # '&' joins two DIFFERENT proteins in some records ("Trem2 Ig domain & Keap1
            # Kelch domain") and two sub-sites of ONE protein in others ("AChE CAS (Trp84,
            # Phe330, Tyr121) & PAS (Trp286, Tyr72, Tyr341)"). Splitting on it unconditionally
            # strips the protein name off the second kind, so those residues matched no target
            # and were skipped with no record at all -- an unlogged under-count of the gate's
            # own headline numbers. A clause that names no target now INHERITS the last target
            # named in the same record, and if there is none it is reported as unresolvable
            # rather than dropped.
            carried: str | None = None
            for seg in segments:
                matched = [sym for sym, al in ALIASES.items()
                           if sym in reg["targets"] and any(_alias_in(seg, a) for a in al)]
                if len(matched) > 1:
                    self.fail("unresolvable_residue_attribution", name,
                              f"clause {seg.strip()[:70]!r} names more than one registry "
                              f"target {matched}; its residues cannot be attributed to "
                              f"one protein and were not checked")
                    carried = None
                    continue
                if not matched:
                    if not token.search(seg):
                        continue                       # no residues in it; nothing to lose
                    if carried and not any(_alias_in(seg, o) for o in OUT_OF_REGISTRY):
                        matched = [carried]            # sub-site of the protein just named
                    else:
                        self.fail("unresolvable_residue_attribution", name,
                                  f"clause {seg.strip()[:70]!r} carries residue tokens but "
                                  "names no target this registry can resolve; it was not "
                                  "checked, and that omission is now on the record")
                        carried = None
                        continue
                sym = matched[0]
                carried = sym
                if any(_alias_in(seg, o) for o in OUT_OF_REGISTRY):
                    self.fail("unresolvable_residue_attribution", name,
                              f"clause {seg.strip()[:70]!r} names both {sym} and a protein "
                              f"outside the registry; residues cannot be attributed and "
                              f"were not checked")
                    continue
                rec = record_for(sym)
                for m in token.finditer(seg):
                    ann = m.group(0)
                    res = rec.check_annotation(ann)
                    if not res.get("parsed"):
                        continue
                    if not res["valid"]:
                        self.fail(
                            "fabricated_residue", name,
                            f"asserts {ann} for {sym} ({rec.uniprot}) in clause "
                            f"{seg.strip()[:50]!r}, but position {res['position']} is "
                            f"{res['canonical']} in canonical numbering and {res['mature']} "
                            f"in mature numbering. Wrong under every convention, so this is "
                            f"a residue-identity error, not a numbering-convention one.")
                    elif len(res["resolves_in"]) == 1:
                        conventions_used.add(res["resolves_in"][0])
            if len(conventions_used) > 1:
                self.fail(
                    "mixed_numbering_convention", name,
                    f"one binding-site string uses more than one numbering convention "
                    f"({sorted(conventions_used)}). Every residue position must be "
                    f"accompanied by its (accession, convention) pair; see "
                    f"data/target_registry.json.")

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
