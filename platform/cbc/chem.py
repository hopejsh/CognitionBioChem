#!/usr/bin/env python3
"""Chemistry validation for CognitionBioChem.

Every value this module returns is computed from the structure, never asserted.
Requires RDKit (see platform/requirements.txt); degrades to a clear error rather than
silently guessing when RDKit is unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors
    from rdkit.Chem.inchi import MolToInchiKey
    RDKIT = True
    RDLogger.DisableLog("rdApp.*")  # we surface parse errors ourselves
except ImportError:  # pragma: no cover
    RDKIT = False


@dataclass
class SmilesReport:
    """Result of validating one SMILES string."""

    name: str
    smiles_input: str
    parses: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    canonical_smiles: str | None = None
    inchikey: str | None = None
    formula: str | None = None
    mol_weight: float | None = None
    exact_mass: float | None = None
    heavy_atoms: int | None = None
    # stereochemistry
    stereocenters_total: int | None = None
    stereocenters_unspecified: int | None = None
    implied_stereoisomers: int | None = None
    # developability descriptors
    clogp: float | None = None
    tpsa: float | None = None
    hbd: int | None = None
    hba: int | None = None
    rotatable_bonds: int | None = None
    aromatic_rings: int | None = None
    lipinski_violations: int | None = None
    cns_mpo_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _looks_like_formula(s: str) -> bool:
    """A molecular formula in a SMILES field is a common and fatal data-entry error:
    it may parse as a valid (wrong) molecule, or not at all, but either way no
    cheminformatics operation on it is meaningful."""
    import re
    core = s.split("(")[0].strip()
    return bool(re.fullmatch(r"(?:[A-Z][a-z]?\d{0,3})+", core)) and any(
        ch.isdigit() for ch in core) and len(core) >= 4


def validate_smiles(name: str, smiles: str, expected_formula: str | None = None
                    ) -> SmilesReport:
    """Parse and characterize a SMILES string."""
    rep = SmilesReport(name=name, smiles_input=smiles, parses=False)
    if not RDKIT:
        rep.errors.append("RDKit is not installed; cannot validate chemistry")
        return rep

    # Parse first, then diagnose. Checking "does this look like a formula" up front
    # false-positives on real SMILES: 'CC1CCC2(CCC3(...' truncates at the first paren to
    # 'CC1CCC2', which matches an element-plus-count pattern perfectly.
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        if _looks_like_formula(smiles):
            rep.errors.append(
                f"field contains a molecular formula, not a SMILES string: {smiles!r}. "
                "No structure-based computation is possible on this record.")
            return rep
        # Re-parse with sanitization off to report *why* it failed.
        raw = Chem.MolFromSmiles(smiles, sanitize=False)
        if raw is None:
            rep.errors.append("SMILES is syntactically invalid and cannot be parsed")
        else:
            try:
                Chem.SanitizeMol(raw)
            except Exception as exc:  # noqa: BLE001
                rep.errors.append(f"SMILES parses but fails sanitization: {exc}")
        return rep

    rep.parses = True
    rep.canonical_smiles = Chem.MolToSmiles(mol)
    try:
        rep.inchikey = MolToInchiKey(mol)
    except Exception:  # noqa: BLE001
        rep.warnings.append("InChIKey generation failed")
    rep.formula = rdMolDescriptors.CalcMolFormula(mol)
    rep.mol_weight = round(Descriptors.MolWt(mol), 3)
    rep.exact_mass = round(Descriptors.ExactMolWt(mol), 4)
    rep.heavy_atoms = mol.GetNumHeavyAtoms()

    centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)
    rep.stereocenters_total = len(centers)
    unspec = [c for c in centers if c[1] == "?"]
    rep.stereocenters_unspecified = len(unspec)
    if unspec:
        rep.implied_stereoisomers = 2 ** len(unspec)
        rep.warnings.append(
            f"{len(unspec)} of {len(centers)} stereocentres are unspecified, so this "
            f"flat structure denotes up to {2 ** len(unspec):,} distinct stereoisomers. "
            "For a natural product whose activity is stereospecific, that makes the "
            "record biologically ambiguous.")

    rep.clogp = round(Crippen.MolLogP(mol), 3)
    rep.tpsa = round(Descriptors.TPSA(mol), 2)
    rep.hbd = rdMolDescriptors.CalcNumHBD(mol)
    rep.hba = rdMolDescriptors.CalcNumHBA(mol)
    rep.rotatable_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
    rep.aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)

    viol = sum([rep.mol_weight > 500, rep.clogp > 5, rep.hbd > 5, rep.hba > 10])
    rep.lipinski_violations = viol

    # CNS exposure heuristics (Wager et al., ACS Chem Neurosci 2010, CNS MPO).
    if rep.mol_weight > 360:
        rep.cns_mpo_flags.append(f"MW {rep.mol_weight:.0f} > 360 (CNS MPO desirable limit)")
    if rep.tpsa > 90:
        rep.cns_mpo_flags.append(f"TPSA {rep.tpsa:.0f} > 90 A^2 (poor CNS permeability)")
    if rep.hbd > 3:
        rep.cns_mpo_flags.append(f"HBD {rep.hbd} > 3 (CNS MPO desirable limit)")
    if rep.clogp > 5:
        rep.cns_mpo_flags.append(f"cLogP {rep.clogp:.1f} > 5")

    if expected_formula:
        got = (rep.formula or "").replace("+", "").replace("-", "")
        if got != expected_formula.replace(" ", ""):
            rep.errors.append(
                f"formula mismatch: structure gives {rep.formula}, "
                f"record claims {expected_formula}")
    return rep


# Reference structures for the eight natural products, from PubChem canonical SMILES.
# Used to check whether the platform's stored structure is the compound it names.
REFERENCE = {
    "Huperzine A": ("CC=C1C2CC3=C(C1(CC(=C2)C)N)C=CC(=O)N3", "C15H18N2O", 5321310),
    "Curcumin": ("COC1=CC(=CC=C1O)/C=C/C(=O)CC(=O)/C=C/C2=CC(=C(C=C2)O)OC",
                 "C21H20O6", 969516),
    "Baicalein": ("C1=CC=C(C=C1)C2=CC(=O)C3=C(O2)C=C(C(=C3O)O)O", "C15H10O5", 5281605),
    "Ginkgolide B": ("CC1C(=O)OC2C13C(C4(C5C3(C6(C(C5O)(OC6=O)C(C)(C)C)OC4=O)O)O)O",
                     "C20H24O10", 65243),
    "Asiatic acid": ("CC1CCC2(CCC3(C(=CCC4C3(CCC5C4(CC(C(C5(C)CO)O)O)C)C)C2C1C)C)C(=O)O",
                     "C30H48O5", 119034),
}


def compare_to_reference(name: str, smiles: str) -> dict[str, Any]:
    """Is the stored structure actually the compound it is named after?

    Compares InChIKey skeletons (first block), which ignores stereochemistry and
    protonation, so a match here means the constitution is right even if stereo is not.
    """
    key = next((k for k in REFERENCE if k.lower().split()[0] in name.lower()), None)
    if key is None or not RDKIT:
        return {"compared": False, "reason": "no reference structure on file"}
    ref_smiles, ref_formula, cid = REFERENCE[key]
    ref = Chem.MolFromSmiles(ref_smiles)
    got = Chem.MolFromSmiles(smiles)
    if ref is None or got is None:
        return {"compared": False, "reason": "one side failed to parse",
                "reference": key, "pubchem_cid": cid}
    rk, gk = MolToInchiKey(ref), MolToInchiKey(got)
    return {
        "compared": True,
        "reference": key,
        "pubchem_cid": cid,
        "reference_formula": ref_formula,
        "reference_inchikey": rk,
        "stored_inchikey": gk,
        "identical": rk == gk,
        "same_constitution": rk.split("-")[0] == gk.split("-")[0],
        "stored_formula": rdMolDescriptors.CalcMolFormula(got),
    }
