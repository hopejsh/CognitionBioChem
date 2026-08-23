#!/usr/bin/env python3
"""Regression suite for the CognitionBioChem platform modules.

Run: ./.venv/bin/python platform/tests/test_platform.py

Where a test encodes a specific finding from the expert review, it says so, so that a
regression puts the original defect back visibly rather than silently.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import chem, peptide, predictor, provenance as pv, thermo  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# Thermodynamics
# --------------------------------------------------------------------------- #

def test_thermo_roundtrip():
    print("\n[thermo] dG <-> Kd inversion is exact")
    for kd in (1e-3, 1e-6, 1e-9, 1e-12):
        dg = thermo.kd_to_dg(kd)
        back = thermo.dg_to_kd(dg)
        check(f"Kd {kd:.0e} round-trips", abs(math.log10(back / kd)) < 1e-9,
              f"dG={dg:.3f}")
    # Textbook anchor: 1 nM at 298.15 K is about -12.3 kcal/mol.
    dg_1nm = thermo.kd_to_dg(1e-9)
    check("Kd = 1 nM gives dG ~ -12.3 kcal/mol", abs(dg_1nm + 12.27) < 0.05,
          f"{dg_1nm:.2f}")


def test_thermo_detects_the_real_defect():
    print("\n[thermo] the platform's own numbers are caught")
    # HippoTrk-Saponin-X1 as shipped: dG -18.4 kcal/mol with Kd 0.32 nM.
    r = thermo.check("X1", dg=-18.4, kd_molar=0.32e-9)
    check("flagged inconsistent", r.consistent is False)
    check("gap is ~5.4 kcal/mol", abs(r.discrepancy_kcal - 5.45) < 0.1,
          f"{r.discrepancy_kcal:.2f}")
    check("implied Kd is far tighter than stated",
          r.kd_implied_by_dg < 1e-12, thermo.format_kd(r.kd_implied_by_dg))
    check("an implausibly tight dG is flagged", thermo.check("Y", -19.5, None).plausible is False)
    check("a reasonable pair passes",
          thermo.check("Z", -12.27, 1e-9).consistent is True)
    check("precision without an interval is flagged",
          any("uncertainty interval" in i for i in thermo.check("W", -12.3, None).issues))


def test_thermo_parsers():
    print("\n[thermo] parsing values out of the legacy prose fields")
    s = "ΔG = -18.4 kcal/mol | Kd = 0.32 nM | AF3 pLDDT = 96.2 / 100"
    check("dG parsed", thermo.parse_dg(s) == -18.4)
    kd, txt = thermo.parse_kd(s)
    check("Kd parsed and converted to molar", abs(kd - 0.32e-9) < 1e-18, str(kd))
    for variant in ("Kd = 5 µM", "Kd = 5 μM", "Kd = 5 uM"):
        # Both the U+00B5 micro sign and the U+03BC Greek mu occur in real data.
        # Compare with a tolerance: the conversion is exact in principle but not in
        # binary floating point.
        got = thermo.parse_kd(variant)[0]
        check(f"{variant!r} parses to 5 uM", got is not None and abs(got - 5e-6) < 1e-18,
              repr(got))


# --------------------------------------------------------------------------- #
# Peptides
# --------------------------------------------------------------------------- #

def test_peptide_rejects_non_residues():
    print("\n[peptide] ambiguity codes and prose are rejected")
    # The exact strings shipped in the platform.
    r = peptide.analyze("X4", "CKCHGMSGSCSTKTCWWGBLCPFRRACPDCH")
    check("'B' makes the sequence invalid", not r.valid)
    check("the offending residue is named", r.invalid_residues == {"B": 1})
    check("the error explains why", "ambiguous" in r.errors[0])

    r2 = peptide.analyze("A4", "His14-Phe174-Linker-Peptide-Conjugate")
    check("prose in the sequence field is rejected", not r2.valid)
    check("no properties are computed for it", r2.mol_weight is None)

    for code in "JOUXZ":
        check(f"'{code}' is rejected", not peptide.analyze("t", f"ACDE{code}FGHI").valid)


def test_peptide_properties():
    print("\n[peptide] computed properties are correct")
    # Glycine: residue 57.0519 + water 18.0153 = 75.07
    g = peptide.analyze("gly", "G")
    check("single glycine MW", abs(g.mol_weight - 75.07) < 0.01, str(g.mol_weight))
    # Poly-lysine is strongly cationic with a basic pI.
    k = peptide.analyze("polyK", "KKKKKKKKKK")
    check("poly-Lys is strongly cationic", k.net_charge_ph74 > 9, str(k.net_charge_ph74))
    check("poly-Lys pI is basic", k.isoelectric_point > 10, str(k.isoelectric_point))
    # Poly-glutamate is the mirror image.
    e = peptide.analyze("polyE", "EEEEEEEEEE")
    check("poly-Glu is strongly anionic", e.net_charge_ph74 < -9, str(e.net_charge_ph74))
    check("poly-Glu pI is acidic", e.isoelectric_point < 4.5, str(e.isoelectric_point))
    # GRAVY sign for a known hydrophobic vs hydrophilic run.
    check("poly-Ile GRAVY is positive", peptide.analyze("i", "IIIIII").gravy > 4)
    check("poly-Arg GRAVY is negative", peptide.analyze("r", "RRRRRR").gravy < -4)


def test_peptide_liabilities():
    print("\n[peptide] developability liabilities are surfaced")
    r = peptide.analyze("B1", "KWWKFLRRFWRRLKKYFEELWKKLAEKYFELLKKYG")
    joined = " ".join(r.liabilities).lower()
    check("cationic amphipathic motif flagged",
          "amphipathic" in joined or "hemolysis" in joined)
    check("BBB limitation flagged", "blood-brain" in joined or "bbb" in joined)

    a = peptide.analyze("B4", "KLVFFAEDVGSNKGAIIGLM")
    check("the amyloid KLVFF core is flagged",
          any("KLVFF" in l for l in a.liabilities))
    check("seeding risk is named",
          any("seeding" in l or "fibrill" in l for l in a.liabilities))

    odd = peptide.analyze("odd", "ACDEFGHC" + "C")
    check("odd cysteine count flagged", any("odd" in l for l in odd.liabilities))
    check("double factorial is right: 5!! = 15", peptide._double_factorial(5) == 15)
    # This read `... or True`, so it could not fail — and its probe sequence had NINE
    # cysteines, which yields the odd-parity liability rather than a pairing count, so even
    # without the `or True` it was testing something other than its name. The property is
    # real and testable with an even-cysteine peptide.
    check("6 cysteines give 15 pairings",
          any("15 distinct disulfide" in l
              for l in peptide.analyze("c6", "CACACACACACA").liabilities))


# --------------------------------------------------------------------------- #
# Chemistry
# --------------------------------------------------------------------------- #

def test_chem_validation():
    print("\n[chem] RDKit validation catches the shipped defects")
    if not chem.RDKIT:
        check("RDKit available", False, "not installed")
        return
    ok = chem.validate_smiles("ethanol", "CCO")
    check("a valid SMILES parses", ok.parses)
    check("formula is computed", ok.formula == "C2H6O", str(ok.formula))
    check("InChIKey is generated", bool(ok.inchikey))

    # The exact strings shipped in the platform.
    cur = chem.validate_smiles(
        "Curcumin", "COC1=C(C=CC(=C1)C=CC(=O)CC(=O)C=CC2=CC(=C(C=C2)O)OCH3)O")
    check("the shipped curcumin SMILES fails ('OCH3' is not valid)", not cur.parses)

    formula_field = chem.validate_smiles("SalB", "C36H30O16 (Caffeic Acid Tetramer)")
    check("a molecular formula in the SMILES field is rejected", not formula_field.parses)
    check("the error says it is a formula",
          "formula" in formula_field.errors[0].lower())

    # A real SMILES that merely begins like a formula must NOT be misclassified.
    asiatic = ("CC1CCC2(CCC3(C(=CCC4C3(CCC5C4(CC(C(C5(C)CO)O)O)C)C)C2C1C)C)C(=O)O")
    check("a real SMILES starting 'CC1CCC2' is not mistaken for a formula",
          chem.validate_smiles("Asiatic acid", asiatic).parses)


def test_chem_stereochemistry():
    print("\n[chem] undefined stereochemistry is quantified")
    if not chem.RDKIT:
        return
    flat = "CC(O)C(N)C(=O)O"
    r = chem.validate_smiles("flat", flat)
    check("undefined stereocentres are counted", (r.stereocenters_unspecified or 0) >= 2,
          str(r.stereocenters_unspecified))
    check("the 2^n stereoisomer count is reported",
          r.implied_stereoisomers == 2 ** r.stereocenters_unspecified)
    check("a warning explains the consequence",
          any("stereoisomer" in w for w in r.warnings))


def test_chem_identity():
    print("\n[chem] a wrong structure under a right name is caught")
    if not chem.RDKIT:
        return
    shipped = "C1=CC=C(C=C1)C2=CC(=O)C3=C(O2)C(=C(C(=C3)O)O)O"
    cmp = chem.compare_to_reference("Baicalein", shipped)
    check("comparison ran", cmp.get("compared") is True)
    check("the shipped baicalein is NOT the real compound",
          cmp.get("same_constitution") is False,
          f"{cmp.get('stored_inchikey')} vs {cmp.get('reference_inchikey')}")
    real = chem.compare_to_reference("Baicalein", chem.REFERENCE["Baicalein"][0])
    check("the reference structure matches itself", real["identical"] is True)


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #

def test_provenance_enforcement():
    print("\n[provenance] the constraint is enforced at construction")
    try:
        pv.Provenance(pv.Status.COMPUTED, method="x")
        ok = False
    except ValueError:
        ok = True
    check("a computed value with no software is rejected", ok)
    try:
        pv.Provenance(pv.Status.LITERATURE)
        ok = False
    except ValueError:
        ok = True
    check("a literature value with no source id is rejected", ok)

    v = pv.computed(1.23, "kcal/mol", "test", "pytest 1.0")
    check("a well-formed computed value is accepted", v.trustworthy)
    check("it renders its number", v.to_display()["display"] == 1.23)

    nc = pv.not_computed("kcal/mol", note="no calculation was run")
    check("not_computed renders no number", nc.to_display()["display"] is None)
    check("not_computed carries the supplied note as its caveat",
          nc.to_display()["caveat"] == "no calculation was run")
    check("not_computed falls back to a default caveat",
          "not been computed" in pv.not_computed("M").to_display()["caveat"])
    check("not_computed is not trustworthy", not nc.trustworthy)

    ph = pv.placeholder(-18.4, "kcal/mol", note="retracted")
    disp = ph.to_display()
    check("placeholder renders no number", disp["display"] is None)
    check("placeholder keeps the value under a distinct key",
          disp["placeholder_value"] == -18.4)
    check("placeholder badge shouts", "PLACEHOLDER" in disp["badge"])


def test_provenance_audit():
    print("\n[provenance] the audit finds bare numbers")
    bad = {"affinity": -18.4, "nested": {"kd": 3.2e-10}}
    problems = pv.audit(bad)
    check("two bare numerics found", len(problems) == 2, str(problems))
    good = {"affinity": pv.computed(-12.3, "kcal/mol", "FEP", "openmm 8.1").to_dict()}
    check("a provenance-carrying value passes", pv.audit(good) == [])
    check("structural keys are exempt", pv.audit({"id": 3, "length": 47}) == [])


def _real_fold_codes() -> set:
    """Candidate codes with a genuine Boltz-2 fold on disk."""
    import json as _j
    p = REPO / "data" / "real_vs_hardcoded.json"
    if not p.exists():
        return set()
    return {r["code"] for r in _j.loads(p.read_text()).get("rows", [])
            if (r.get("real") or {}).get("ok")}


def test_dataset_is_clean():
    print("\n[dataset] the shipped data layer passes its own audit")
    p = REPO / "data" / "dataset.json"
    if not p.exists():
        check("dataset.json exists", False, "run build_dataset.py")
        return
    ds = json.loads(p.read_text())
    problems = pv.audit({"natural_products": ds["natural_products"],
                         "candidates": ds["candidates"]})
    check("no bare numeric values anywhere", not problems, str(problems[:3]))
    check("every candidate has a pLDDT field",
          all("plddt" in c for c in ds["candidates"]))
    # This used to assert that NO pLDDT was ever presented, which was right when nothing
    # had been computed and became wrong the moment real folds existed. A check pinned to a
    # state goes stale when the project improves; the property is what must hold: every
    # pLDDT is either honestly absent, or PREDICTED and traceable to the model that made it.
    statuses = {c["plddt"]["provenance"]["status"] for c in ds["candidates"]}
    check("every pLDDT is either not_computed or predicted",
          statuses <= {"not_computed", "predicted"}, str(statuses))
    predicted = [c for c in ds["candidates"]
                 if c["plddt"]["provenance"]["status"] == "predicted"]
    check("predicted pLDDTs name the model that produced them",
          all(c["plddt"]["provenance"]["software"].startswith("Boltz")
              for c in predicted), f"{len(predicted)} predicted")
    check("predicted pLDDTs carry an uncertainty",
          all(c["plddt"]["provenance"]["uncertainty"] for c in predicted))
    check("predicted pLDDT values are in range",
          all(0 <= c["plddt"]["value"] <= 100 for c in predicted))
    check("a real fold exists for every predicted pLDDT",
          all(c["code"] in _real_fold_codes() for c in predicted))
    check("retracted claims survive",
          sum(1 for c in ds["candidates"] if "retracted_claims" in c) == 25)


# --------------------------------------------------------------------------- #
# Predictor
# --------------------------------------------------------------------------- #

MINI_CIF = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.B_iso_or_equiv
ATOM 1 CA ALA A 1 0.000 0.000 0.000 95.50
ATOM 2 CA GLY A 2 3.800 0.000 0.000 88.20
ATOM 3 CA SER A 3 7.600 0.000 0.000 45.10
ATOM 4 CA VAL A 4 11.400 0.000 0.000 38.70
ATOM 5 CA LEU A 5 15.200 0.000 0.000 92.30
#
"""


def test_predictor_parses_mmcif():
    print("\n[predictor] mmCIF parsing and confidence extraction")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "model.cif").write_text(MINI_CIF)
        (d / "x_predicted_aligned_error.json").write_text(json.dumps(
            [{"predicted_aligned_error": [[0, 1, 2, 3, 4]] * 5,
              "max_predicted_aligned_error": 31.75}]))
        p = predictor.load(d)
        check("format detected", p.source == "alphafold_db", p.source)
        check("5 residues parsed", len(p.residues) == 5)
        check("sequence read from comp ids", p.sequence == "AGSVL", p.sequence)
        check("pLDDT read from the B-factor column", p.plddt[0] == 95.50)
        check("mean pLDDT computed", abs(p.mean_plddt - 71.96) < 0.05, str(p.mean_plddt))
        check("PAE loaded", p.pae is not None and len(p.pae) == 5)
        check("PAE max read from file", p.pae_max == 31.75)

        bands = p.band_fractions()
        check("band fractions sum to 1", abs(sum(bands.values()) - 1.0) < 1e-9)
        check("very-low band is populated", bands["Very low"] == 0.4, str(bands))

        geo = p.geometry_check()
        check("ideal 3.8 A spacing is recognised as protein-like",
              geo["plausible_protein"] and abs(geo["mean_ca_ca"] - 3.8) < 1e-6, str(geo))

        # The synthetic run here is 2 residues long, below the default min_len of 3.
        check("a run shorter than min_len is correctly ignored",
              p.low_confidence_regions() == [])
        low = p.low_confidence_regions(min_len=2)
        check("the low-confidence run is found when min_len allows it",
              len(low) == 1 and low[0]["length"] == 2, str(low))
        check("its mean pLDDT is computed", abs(low[0]["mean_plddt"] - 41.9) < 0.05,
              str(low[0]["mean_plddt"]))


def test_predictor_rejects_synthetic_geometry():
    print("\n[predictor] a parametric curve is caught by the geometry check")
    # Reconstruct the ORIGINAL app.js:715 generator and check it fails.
    import math as m
    seq = "MCVCDRENPVEWVRACPTGKCEGL"
    rows = []
    n = len(seq)
    for i, c in enumerate(seq):
        code = ord(c)
        radius = 6 + (code % 5) * 0.8
        pitch = (i - n / 2) * 0.6
        angle = (i / n) * m.pi * (6 if code % 3 == 0 else 4)
        x, y, z = m.sin(angle) * radius, pitch, m.cos(angle) * radius
        if c in ("C", "P"):
            x *= 1.3; z *= 1.3
        rows.append(f"ATOM {i+1} CA ALA A {i+1} {x:.3f} {y:.3f} {z:.3f} 95.00")
    cif = MINI_CIF.split("ATOM 1")[0] + "\n".join(rows) + "\n#\n"

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "model.cif").write_text(cif)
        p = predictor.load(d)
        geo = p.geometry_check()
        check("the synthetic helix is NOT protein-like",
              geo["plausible_protein"] is False,
              f"mean Ca-Ca {geo['mean_ca_ca']} A, {geo['outliers_beyond_0.5A']}/"
              f"{geo['n_bonds']} outliers")
        check("a warning is raised about the geometry",
              any("not protein-like" in w for w in p.warnings), str(p.warnings))


def test_predictor_flags_suspicious_confidence():
    print("\n[predictor] an implausible confidence floor is flagged")
    rows = [f"ATOM {i+1} CA ALA A {i+1} {i*3.8:.3f} 0.000 0.000 {93 + math.sin(i*0.4)*4:.2f}"
            for i in range(30)]
    cif = MINI_CIF.split("ATOM 1")[0] + "\n".join(rows) + "\n#\n"
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "model.cif").write_text(cif)
        p = predictor.load(d)
        check("a pLDDT floor above 85 is flagged",
              any("minimum pLDDT" in w for w in p.warnings), str(p.warnings))


def test_predictor_on_real_data():
    print("\n[predictor] end-to-end on genuine AlphaFold DB output")
    d = Path("/tmp/afdb_trkb")
    if not (d / "AF-Q16620.cif").exists():
        print("  SKIP  real AlphaFold data not downloaded")
        return
    p = predictor.load(d)
    check("822 residues parsed", len(p.residues) == 822, str(len(p.residues)))
    check("real geometry is protein-like", p.geometry_check()["plausible_protein"])
    check("mean Ca-Ca is ~3.8 A", abs(p.geometry_check()["mean_ca_ca"] - 3.8) < 0.1)
    check("real pLDDT spans a wide range", max(p.plddt) - min(p.plddt) > 50,
          f"{min(p.plddt):.1f}-{max(p.plddt):.1f}")
    check("real output has low-confidence residues",
          sum(1 for v in p.plddt if v < 70) / len(p.plddt) > 0.10,
          f"{sum(1 for v in p.plddt if v < 70) / len(p.plddt):.1%} below 70")
    check("no spurious warnings on genuine data", not p.warnings, str(p.warnings))



# --------------------------------------------------------------------------- #
# Target registry (slate #4)
# --------------------------------------------------------------------------- #

def test_registry_numbering():
    print("\n[registry] numbering conventions resolve against real sequences")
    import json as _json
    from cbc import registry as R
    p = REPO / "data" / "target_registry.json"
    if not p.exists():
        print("  SKIP  registry not built")
        return
    reg = _json.loads(p.read_text())

    def rec(sym):
        t = reg["targets"][sym]
        return R.TargetRecord(
            symbol=sym, uniprot=t["uniprot"], length=t["length"], sequence=t["sequence"],
            signal_peptide=tuple(t["signal_peptide"]) if t["signal_peptide"] else None,
            chain=tuple(t["chain"]) if t["chain"] else None)

    check("all 16 targets present", len(reg["targets"]) == 16, str(len(reg["targets"])))
    # sequence_length_checked is an ASSERTION the builder wrote into the file, so reading it
    # back only proves the builder once thought so. Every construct in studies #9 and #10 is
    # sliced out of these stored sequences, so a silent edit changes what gets folded. Derive
    # the property instead of trusting the flag.
    bad_len = [k for k, t in reg["targets"].items() if len(t["sequence"]) != t["length"]]
    check("every stored sequence really is its stated length", not bad_len, str(bad_len))
    check("the builder's own length flag agrees",
          all(t["sequence_length_checked"] for t in reg["targets"].values()))

    # The derived construct fields must equal what registry.TargetRecord recomputes from the
    # same stored features — otherwise a hand-edit to the JSON silently changes the construct.
    drift = []
    for sym, t in reg["targets"].items():
        r2 = R.TargetRecord(
            symbol=sym, uniprot=t["uniprot"], length=t["length"], sequence=t["sequence"],
            signal_peptide=tuple(t["signal_peptide"]) if t["signal_peptide"] else None,
            chain=tuple(t["chain"]) if t["chain"] else None,
            domains=[R.Feature(**f) for f in t.get("domains", [])],
            topology=[R.Feature(**f) for f in t.get("topology", [])],
            disulfides=[R.Feature(**f) for f in t.get("disulfides", [])],
            isoform_variable=[R.Feature(**f) for f in t.get("isoform_variable", [])],
            subunit=t.get("subunit", ""))
        span = list(r2.ligand_accessible_span) if r2.ligand_accessible_span else None
        if span != (list(t["ligand_accessible_span"]) if t["ligand_accessible_span"] else None):
            drift.append(f"{sym}.span {t['ligand_accessible_span']} vs {span}")
        elif r2.construct_basis != t["construct_basis"]:
            drift.append(f"{sym}.basis {t['construct_basis']} vs {r2.construct_basis}")
    check("stored construct fields equal what the code recomputes", not drift, str(drift[:3]))

    # The offset must be DERIVED from the CHAIN feature, not assumed.
    check("ACHE offset is 31 (SIGNAL 1-31)", rec("ACHE").mature_offset == 31)
    check("CHRNA7 offset is 22", rec("CHRNA7").mature_offset == 22)
    check("PTAFR has no signal peptide, so offset is 0",
          rec("PTAFR").mature_offset == 0)

    # The AChE string mixes conventions: this is the defect the registry exists to expose.
    a = rec("ACHE")
    check("Trp286 resolves ONLY in mature numbering",
          a.check_annotation("Trp286")["resolves_in"] == ["mature"])
    check("Trp317 resolves ONLY in canonical numbering",
          a.check_annotation("Trp317")["resolves_in"] == ["canonical"])
    check("Trp84 (Torpedo) resolves in NEITHER convention",
          not a.check_annotation("Trp84")["valid"])

    # A wrong residue identity is distinguishable from a numbering problem.
    for sym, ann in (("PTAFR", "His14"), ("TREM2", "Lys112"), ("FZD8", "Arg104")):
        check(f"{sym} {ann} is wrong under every convention",
              not rec(sym).check_annotation(ann)["valid"])
    for sym, ann in (("FZD8", "Phe72"), ("TLR4", "Arg264"), ("KEAP1", "Tyr334")):
        check(f"{sym} {ann} is confirmed correct", rec(sym).check_annotation(ann)["valid"])

    # Round-trip conversion.
    check("mature->canonical->mature round-trips",
          a.convert(a.convert(286, "mature", "canonical"), "canonical", "mature") == 286)
    check("canonical 317 == mature 286 for AChE",
          a.convert(286, "mature", "canonical") == 317)



def test_posebench_sequence_alignment():
    print("\n[posebench] residues are paired by sequence, never by residue number")
    from cbc import posebench as pb, physics

    # A crystal numbered from 33 and a model numbered from 1 describe the same protein.
    # Pairing on residue number matches Pro33 to Asp33; only sequence alignment recovers
    # the true correspondence. Measured on 4XH6, number-pairing agreed on residue TYPE for
    # 4.2% of pairs and gave a pocket RMSD of 15.13 A where the truth is 0.56 A.
    def atoms(seq, start, chain="A"):
        out = []
        for i, aa in enumerate(seq):
            three = {v: k for k, v in
                     {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
                      "GLN": "Q", "GLU": "E", "GLY": "G", "LEU": "L", "PRO": "P",
                      "SER": "S", "TYR": "Y", "VAL": "V"}.items()}[aa]
            out.append(physics.Atom(chain=chain, resi=start + i, resn=three, name="CA",
                                    element="C", x=float(i), y=0.0, z=0.0))
        return out

    seq = "PLESQYQVASGLAPRPY"
    ref = atoms(seq, 33)          # crystal author numbering
    pred = atoms(seq, 1)          # model numbering
    corr = pb._sequence_correspondence(ref, pred)
    check("all residues paired", len(corr) == len(seq), f"{len(corr)}/{len(seq)}")
    check("the numbering offset is recovered", corr.get(("A", 33)) == ("A", 1),
          str(corr.get(("A", 33))))
    check("pairing is order-preserving",
          all(corr[("A", 33 + i)] == ("A", 1 + i) for i in range(len(seq))))

    # A pair whose residue types differ must never be emitted.
    mutated = atoms("PLESQYQVASGLAPRPY".replace("Y", "V"), 33)
    corr2 = pb._sequence_correspondence(mutated, pred)
    bad = [(r, p) for r, p in corr2.items()
           if {a.resn for a in mutated if (a.chain, a.resi) == r} !=
              {a.resn for a in pred if (a.chain, a.resi) == p}]
    check("no pair with mismatched residue types is emitted", not bad, str(bad[:3]))


# --------------------------------------------------------------------------- #
# stale-artifact detection                                                     #
# --------------------------------------------------------------------------- #

def test_model_chain_lengths_are_verified():
    """A prediction must be checked against the input it claims to answer.

    Boltz's --override replaces the predictions but not the preprocessing cache under
    boltz_results_*/processed/, which is keyed on the input record name. Re-running into a
    directory whose input.yaml had changed therefore folded the PREVIOUS receptor and wrote a
    result with a zero exit code, fresh timestamps and a plausible ipTM. It was caught only
    because a receptor shortened from 212 to 156 residues returned an ipTM identical to the
    old run to all sixteen digits. This test pins the check that makes that visible.
    """
    print("\n[stale artifacts] a model is checked against the input it answers")
    from cbc.compute import structure as st

    header = "\n".join("_atom_site." + c for c in (
        "group_PDB", "id", "type_symbol", "label_atom_id", "label_alt_id", "label_comp_id",
        "label_seq_id", "auth_seq_id", "pdbx_PDB_ins_code", "label_asym_id"))

    def cif(lengths: dict[str, int]) -> str:
        rows = [f"ATOM {i} N N . GLY {r} {r} ? {ch}"
                for ch, n in lengths.items() for i, r in enumerate(range(1, n + 1), 1)]
        return "loop_\n" + header + "\n" + "\n".join(rows) + "\n"

    tmp = Path(tempfile.mkdtemp())
    good, bad = tmp / "good.cif", tmp / "bad.cif"
    good.write_text(cif({"A": 156, "B": 31}))
    bad.write_text(cif({"A": 212, "B": 31}))
    chains = [st.Chain("A", "G" * 156, "protein", msa="empty"),
              st.Chain("B", "G" * 31, "protein", msa="empty")]

    check("a model matching the request is accepted",
          st._chain_length_mismatch(chains, {"files": {"model": str(good)}}) is None)
    msg = st._chain_length_mismatch(chains, {"files": {"model": str(bad)}})
    check("a model built from a different receptor is rejected", msg is not None, str(msg))
    check("the rejection names both the request and what was found",
          msg is not None and "156" in msg and "212" in msg, str(msg))

    # The column order is declared per file and is not fixed. Assuming it yields one "chain"
    # per residue number, which would make this guard fire on every file and be switched off.
    shuffled = ("loop_\n" + "\n".join("_atom_site." + c for c in (
        "group_PDB", "label_asym_id", "label_seq_id", "type_symbol")) + "\n"
        + "\n".join(f"ATOM {ch} {r} N" for ch, n in {"A": 156, "B": 31}.items()
                     for r in range(1, n + 1)) + "\n")
    other = tmp / "other.cif"; other.write_text(shuffled)
    check("column order is read from the loop header, not assumed",
          st._chain_length_mismatch(chains, {"files": {"model": str(other)}}) is None)
    shutil.rmtree(tmp)


def test_criteria_are_not_published_as_p_values():
    """A threshold criterion must never be reported as a p-value.

    Seven studies encoded pre-specified threshold comparisons as p = 0.0 when met and p = 1.0
    when not, fed them to Holm beside the genuine tests, and published the whole vector under
    the key `p_holm`. Two consequences, and the second is the one that changed a number:
    p = 0.0 is unattainable under any test, and a sentinel always sorts first in the step-down
    and so CONSUMES a multiplier. In study #7 two sentinels took ranks 0 and 1 and left the one
    real test at multiplier 1 — its published "Holm-adjusted" p equalled its raw p exactly,
    while the artefact claimed a correction had been applied.
    """
    print("\n[inference] criteria and tests are kept apart")
    from cbc import inference as inf

    raised = False
    try:
        inf.holm({"H1_threshold": 0.0, "H2_real_test": 3e-05})
    except ValueError:
        raised = True
    check("holm() refuses a 0.0 sentinel", raised)
    for bad in (1.5, -0.1, None, "0.05"):
        try:
            inf.holm({"H": bad}); ok = False
        except ValueError:
            ok = True
        check(f"holm() refuses p={bad!r}", ok)

    # The exact regression: two sentinels must not silently strip the correction off a test.
    r = inf.decide(criteria={"H1": inf.Criterion(True, 0.625, "> 0.3"),
                             "H3": inf.Criterion(True, 0.875, "> 0.5")},
                   tests={"H2": 3e-05})
    check("only genuine tests appear in p_holm", set(r["p_holm"]) == {"H2"}, str(r["p_holm"]))
    check("the family size is reported, so K=1 is visible not hidden",
          r["multiplicity"]["family_size"] == 1)
    check("criteria are excluded from the correction and say so",
          r["multiplicity"]["excluded_from_correction"] == ["H1", "H3"])
    check("a criterion carries its observed value and threshold, never a p",
          set(r["criteria"]["H1"]) >= {"met", "observed", "threshold"}
          and "p" not in r["criteria"]["H1"])

    # A study with no test emits no p_holm key at all rather than a block of zeros and ones.
    r2 = inf.decide(criteria={"H1": inf.Criterion(False, 1.36, "< 2.0")}, tests={})
    check("no p_holm key when nothing was tested", "p_holm" not in r2 and "p_raw" not in r2)

    # Genuine step-down still correct: Holm on (0.01, 0.04, 0.20) -> (0.03, 0.08, 0.20).
    g = inf.holm({"a": 0.01, "b": 0.04, "c": 0.20})
    check("step-down multipliers are K, K-1, ... in order",
          [round(g[k], 10) for k in ("a", "b", "c")] == [0.03, 0.08, 0.20], str(g))
    check("adjusted p is monotone in raw p", g["a"] <= g["b"] <= g["c"])

    # An equivalence claim must be flagged, because adjustment makes it EASIER to confirm.
    eq = inf.Criterion(True, {"p_raw": 0.489}, "does not reject", confirmed_by_absence=True)
    check("a confirmed-by-absence criterion carries that warning in its record",
          "not evidence of equivalence" in eq.to_dict()["note"])

    # And the published artefacts must be free of the defect.
    import glob
    offenders = []
    for f in glob.glob(str(REPO / "data" / "study_*.json")):
        a = json.loads(Path(f).read_text()).get("analysis", {})
        for v in (a.get("p_holm") or {}).values():
            if v == 0.0:
                offenders.append(Path(f).name)
    check("no published artefact contains an unattainable p = 0.0", not offenders,
          str(sorted(set(offenders))))


def test_no_published_number_depends_on_a_tmp_path():
    """Published provenance must point inside the repository, and custody must stay complete.

    data/study_*.json once carried 148 absolute /tmp paths as the sole provenance for every
    DockQ, RMSD, ipTM and PRODIGY value in six studies — paths that resolve to nothing in a
    fresh clone and that the OS may clear on reboot, in a repository whose central claim is
    that a displayed number traces to the bytes that produced it. rescue_runs.py existed to
    close exactly that gap but its SOURCES list had never been extended past the first three
    roots, so each new study silently reopened it.
    """
    print("\n[custody] published artefacts live inside the repository")
    import glob
    import re as _re

    offenders = {}
    for f in glob.glob(str(REPO / "data" / "study_*.json")):
        hits = _re.findall(r'"(/tmp/[^"]*)"', Path(f).read_text())
        if hits:
            offenders[Path(f).name] = len(hits)
    check("no study artefact cites an absolute /tmp path", not offenders, str(offenders))

    manifest = REPO / "runs" / "manifest.json"
    check("a custody manifest exists", manifest.exists())
    if not manifest.exists():
        return
    man = json.loads(manifest.read_text())
    check("the manifest states its retention policy", "retention_policy" in man)
    held = {Path(r["path"]).name for r in man["runs"]}
    check(f"{len(held)} runs are under custody", len(held) >= 200, str(len(held)))

    # Every file the manifest claims must actually be there, with the recorded digest.
    import hashlib
    bad = []
    for r in man["runs"][:40]:
        for fr in r["files"]:
            fp = REPO / r["path"] / fr["file"]
            if not fp.exists():
                bad.append(f"missing {fp.name}")
            elif hashlib.sha256(fp.read_bytes()).hexdigest() != fr["sha256"]:
                bad.append(f"digest mismatch {fp.name}")
    check("sampled custody files match their recorded sha256", not bad, str(bad[:3]))

    # The SOURCES list must cover every work root a study actually writes to, or custody
    # silently misses whatever the newest study produced — which is how this defect arose.
    import importlib.util
    spec = importlib.util.spec_from_file_location("rr", REPO / "platform" / "rescue_runs.py")
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)
    covered = {str(src) for _, src in rr.SOURCES}
    declared = set()
    for f in glob.glob(str(REPO / "platform" / "studies" / "*.py")):
        declared |= set(_re.findall(r'(?:WORK|REFS|ARM_D)\s*=\s*Path\("(/tmp/[^"]+)"\)',
                                    Path(f).read_text()))
    missing = sorted(declared - covered)
    check("rescue_runs.SOURCES covers every work root the studies declare",
          not missing, str(missing))


def test_published_gate_artefact_matches_a_live_run():
    """The Validation tab's artefact must equal what the gate produces now.

    data/validation_gate.json is served to the browser under an explicit reproducibility
    promise, and it had drifted to 91 violations / 13 categories / 11 fabricated residues while
    the tool named in that promise produced 102 / 14 / 23 — every number a visitor saw on that
    tab was wrong, and wrong in the direction of understating the gate's own findings. A
    committed artefact that nothing re-derives is a number waiting to go stale.
    """
    print("\n[gate artefact] the published gate output equals a live run")
    import subprocess
    art = REPO / "data" / "validation_gate.json"
    check("the gate artefact is committed", art.exists())
    if not art.exists():
        return
    r = subprocess.run([sys.executable, str(REPO / "platform" / "validate.py"), "--json"],
                       capture_output=True, text=True, cwd=REPO)
    live = json.loads(r.stdout)
    pub = json.loads(art.read_text())
    # Comparing only the counts left every violation STRING unchecked: the auditor edited a
    # failure record's detail text to a fabrication and all three checks still printed PASS.
    # The tab publishes those strings to a reader, so the whole object is compared.
    check("published counts equal live counts", pub["counts"] == live["counts"],
          f"published {sum(pub['counts'].values())} vs live {sum(live['counts'].values())}")
    check("published pass/fail equals live", pub["passed"] == live["passed"])
    check("the published artefact equals the live run in full, not just in its counts",
          pub == live,
          "records differ" if pub["counts"] == live["counts"] else "counts differ")


def test_chembl_share_alike_carveout_is_complete():
    """Every tracked file carrying ChEMBL content must be named in NOTICE.

    NOTICE places the whole repository under Apache-2.0 and then carves out the ChEMBL-derived
    files as CC BY-SA 3.0 — ENUMERATED BY FILENAME. So a file that carries ChEMBL content and
    is not on that list is offered to downstream recipients under Apache-2.0, which permits
    proprietary sublicensing: a grant this project does not hold and which share-alike forbids.
    An omission here is a licensing defect, not a documentation nit, and the list had already
    drifted once (data/study_inputs/ache_bench.json).
    """
    print("\n[licence] the ChEMBL share-alike carve-out is complete")
    import subprocess
    notice = (REPO / "NOTICE").read_text()
    # --others --exclude-standard includes files staged for a first commit. Restricting this
    # to already-tracked files would blind the check to exactly the case that caused the
    # drift: a NEW ChEMBL-derived file added without being added to NOTICE.
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, capture_output=True, text=True).stdout.split()
    # A bare accession is a factual reference, not copyrightable database content, and a
    # dozen tracked files mention one in prose or in a directory name. What share-alike
    # attaches to is substantive ChEMBL content, so the criterion is an accession ALONGSIDE
    # an actual data value — a structure string or a measured activity. Measured on this
    # repository the two sets differ: 11 files mention an accession, 4 carry content.
    DATA_VALUE = re.compile(
        r'"[^"]*smiles[^"]*"\s*:\s*"[A-Za-z0-9@\[\]()=#\\/+.-]{8,}"'
        r"|^\s*smiles:\s*'?[A-Za-z0-9@\[\]()=#\\/+.-]{8,}"        # YAML form
        r'|"(?:standard_value|activity_value|pref_name)"\s*:', re.I | re.M)
    # Files whose ChEMBL provenance is recorded in the run manifest rather than in the file.
    chembl_run_files = set()
    _man = REPO / "runs" / "manifest.json"
    if _man.exists():
        for r in json.loads(_man.read_text())["runs"]:
            if str(r.get("job", "")).upper().startswith("CHEMBL"):
                for f in r["files"]:
                    chembl_run_files.add(f"{r['path']}/{f['file']}")

    carrying, mentions_only = [], []
    for rel in tracked:
        # The filter used to be rel.endswith(".json"), which meant this guard could not fire
        # on the file type where redistributed ChEMBL content actually sits outside data/:
        # 17 tracked runs/*/input.yaml carry the ligand SMILES the affinity benchmark folded.
        # A green test was being read as a compliance property the test could not see.
        if Path(rel).suffix.lower() not in (".json", ".yaml", ".yml", ".csv", ".tsv", ".md"):
            continue
        try:
            body = (REPO / rel).read_text(errors="ignore")
        except OSError:
            continue
        # A run's input.yaml carries a ligand SMILES but no accession of its own: the
        # provenance link is runs/manifest.json, whose `job` is the CHEMBL id the fold was
        # built from. Checking only for an in-file accession therefore missed exactly the
        # files that redistribute ChEMBL structures outside data/.
        from_chembl = bool(re.search(r"CHEMBL\d{3,}", body)) or rel in chembl_run_files
        if not from_chembl:
            continue
        (carrying if DATA_VALUE.search(body) else mentions_only).append(rel)
    # Globs are honoured only from the ChEMBL section. Scanning the whole file swept up
    # "runs/**" from the Boltz-2 entry, which matches every artefact under runs/ and would
    # have made this check vacuous while still printing PASS -- a guard that cannot fail is
    # worse than no guard, because it is read as evidence.
    # The runs/ carve-out is resolved by RULE, not by glob. "runs/*/input.yaml" in NOTICE
    # matches all 413 input files, so a probe file with a ChEMBL SMILES and no manifest entry
    # at all — definitively outside the 17 carved out — was counted as carrying ChEMBL data
    # and still passed. A runs/ file is covered only when its own manifest run is keyed to a
    # CHEMBL accession, which is exactly the set chembl_run_files already holds.
    covered_by_rule = set(chembl_run_files)

    import fnmatch
    _start = notice.find("ChEMBL")
    _end = notice.find("\n\n", notice.find("NOTE ON SHARE-ALIKE", _start))
    chembl_section = notice[_start:_end if _end > 0 else len(notice)]
    notice_globs = [g for g in re.findall(r"[\w./*-]*\*[\w./*-]*", chembl_section)
                    if "**" not in g]
    missing = []
    for c in carrying:
        if c in chembl_section:
            continue
        if c.startswith("runs/"):
            if c not in covered_by_rule:              # glob in NOTICE does not license it
                missing.append(c)
            continue
        if not any(fnmatch.fnmatch(c, g) for g in notice_globs):
            missing.append(c)
    check(f"{len(carrying)} tracked files carry ChEMBL DATA (not just an accession)",
          bool(carrying), f"{len(mentions_only)} others mention an accession only")
    check("every file carrying ChEMBL data is named in NOTICE", not missing, str(missing))
    check("NOTICE states the share-alike consequence",
          "NOT under Apache-2.0" in notice)

    # NOTICE quotes counts of redistributed files. A count typed once goes stale in silence —
    # the UniProt figure had been 257, arrived at with a length heuristic that also counted
    # RCSB-derived chains. Recompute it from the criterion NOTICE now states.
    import glob as _g2
    canon = {t["sequence"] for t in
             json.loads((REPO / "data" / "target_registry.json").read_text())["targets"].values()
             if isinstance(t.get("sequence"), str)}
    yamls = _g2.glob(str(REPO / "runs" / "*" / "input.yaml"))
    n_uni = 0
    for f in yamls:
        got = re.findall(r"sequence:\s*([A-Z]{40,})", Path(f).read_text())
        if any(any(g in c for c in canon) for g in got):
            n_uni += 1
    check("NOTICE states the UniProt criterion rather than a count that goes stale",
          "substring of a canonical sequence" in notice)
    check(f"that criterion selects a non-empty set ({n_uni} of {len(yamls)} input files)",
          n_uni > 0, f"{n_uni}")

    # NOTICE asserts "no file it selects is left unnamed". That check did not exist -- the
    # only one implemented was n_uni > 0, which can fail only if EVERY input file at once
    # stops containing a registry sequence. Implement what the document claims: each selected
    # file must fall under a named path or glob in the UniProt entry.
    uni_start = notice.find("UniProt")
    uni_end = notice.find("\n\n", uni_start)
    uni_section = notice[uni_start:uni_end if uni_end > 0 else len(notice)]
    uni_globs = [g for g in re.findall(r"[\w./*-]*\*[\w./*-]*", uni_section) if "**" not in g]
    unnamed = []
    for f in yamls:
        rel = str(Path(f).relative_to(REPO))
        got = re.findall(r"sequence:\s*([A-Z]{40,})", Path(f).read_text())
        if not any(any(g in c for c in canon) for g in got):
            continue
        if rel in uni_section or any(fnmatch.fnmatch(rel, g) for g in uni_globs):
            continue
        unnamed.append(rel)
    check("every file the UniProt criterion selects is named in NOTICE",
          not unnamed, f"{len(unnamed)} unnamed, e.g. {unnamed[:3]}")


def test_readme_cites_the_plan_each_study_actually_ran():
    """Every study section in the README must cite its artefact's CURRENT plan hash.

    Studies #9 and #10 were re-run as v3. The #10 section was rewritten and the #9 section was
    not, so the README kept citing plan 1609f77d8511 (v2) beside v2's construct column, v2's
    ipTM values, v2's means, and a "Holm p = 1.0" that cbc/inference.py had already abolished —
    while the artefact recorded candidate-screen-v3, 3e748519960b, and no p_holm key at all.
    The document contradicted itself: #10's table carried the correct v3 values for the same
    four candidates a hundred lines below. One section updated, one forgotten, is exactly the
    failure a hand-maintained summary makes, so it is checked mechanically now.
    """
    print("\n[readme] cited plan hashes match the artefacts")
    import glob
    rd = (REPO / "README.md").read_text()
    # Scoping by filename was fragile: study #2's analysis artefact is
    # study_inference_variance_analysis.json, whose stem appears nowhere in the README, so the
    # heuristic dropped it and the guard's coverage depended on a sibling file happening to
    # carry the same study_id. The criterion is now structural and has no heuristic in it: for
    # every study, if ANY of its registered plan hashes appears in the README, the one that
    # appears must be the hash its current artefact records.
    import glob as _g
    current: dict[str, str] = {}
    for f in _g.glob(str(REPO / "data" / "study_*.json")):
        body = json.loads(Path(f).read_text())
        a = body.get("analysis") or body
        h, sid = a.get("prespec_hash"), a.get("study_id")
        if h and sid:
            current[sid.rsplit("-v", 1)[0]] = h      # key on the study, not the version

    stale = []
    for f in _g.glob(str(REPO / "prespec" / "*.json")):
        plan = json.loads(Path(f).read_text())
        sid, h = plan["content"]["study_id"], plan["hash"]
        if h[:12] not in rd:
            continue                       # this version is not cited; nothing to check
        # Compare on the study, not the versioned id: a superseded plan's study_id is
        # candidate-screen-v4 while the artefact records candidate-screen-v5, so keying on the
        # full id made every superseded hash miss the lookup and skip silently — the exact
        # case this guard exists for.
        cur = current.get(sid.rsplit("-v", 1)[0])
        if not cur or h == cur:
            continue
        # A superseded hash may legitimately appear as a RETAINED RECORD — the retention
        # sentences name files like prespec/candidate-screen-v1.5a62fdf6d614.json, and that
        # citation is the point of keeping them. What must not happen is a superseded hash
        # standing in for the plan a study ran under. So it is a defect only where the hash
        # occurs somewhere other than inside its own prespec/ path.
        bare = [i for i in range(len(rd)) if rd.startswith(h[:12], i)
                and not rd[max(0, i - 60):i].rstrip().endswith(f"prespec/{sid}.")]
        if bare:
            ctx = rd[max(0, bare[0] - 50):bare[0] + 20].replace("\n", " ")
            stale.append(f"{sid}: {h[:12]} cited outside its prespec/ path — ...{ctx}...")
    check(f"{len(current)} studies cross-checked; none cited at a superseded hash",
          not stale, str(stale))
    uncited = sorted(sid for sid, h in current.items() if h[:12] not in rd)
    check("every study's current plan hash appears in the README", not uncited, str(uncited))

    # A retracted quantity must not survive as a live claim. Every "Holm p = X" quoted in the
    # README must correspond to a value some artefact actually emits; the fabricated 0/1
    # sentinels no longer exist anywhere, so quoting one is quoting a number nothing computed.
    emitted = set()
    for f in sorted(glob.glob(str(REPO / "data" / "study_*.json"))):
        _b = json.loads(Path(f).read_text())
        a = _b.get("analysis") or _b
        for v in (a.get("p_holm") or {}).values():
            emitted.add(round(float(v), 5))
    orphans = []
    for m in re.finditer(r"Holm p = (\d+(?:\.\d+)?)", rd):
        val = round(float(m.group(1)), 5)
        if any(abs(val - e) < 10 ** -min(5, len(m.group(1).split(".")[-1])) for e in emitted):
            continue
        line_start = rd.rfind("\n", 0, m.start()) + 1
        line = rd[line_start:rd.find("\n", m.end())]
        if any(w in line for w in ("Earlier version", "previously", "moved from", "used to")):
            continue                                   # explicit historical reference
        orphans.append(m.group(0))
    check("every 'Holm p' quoted in the README is a value some artefact emits",
          not orphans, str(orphans[:4]))


def test_published_pae_values_have_a_retained_array():
    """A published pae_min/pae_max must have the array it came from under custody.

    rescue_runs.PAE_KINDS was derived by grepping ONE module for .npz readers, so it kept
    pae matrices only for the variance study. Two other consumers read them —
    cbc/predictor.py and compare_real_vs_hardcoded.py — and the second produces the
    pae_min/pae_max published for 22 candidates in data/real_vs_hardcoded.json. Those 44
    numbers had no retained array behind them while the manifest asserted that everything a
    displayed value derives from is kept. A retention policy is a claim about provenance, so
    it is checked against the published values rather than against the comment that states it.
    """
    print("\n[custody] every published PAE value has its array retained")
    rvh = REPO / "data" / "real_vs_hardcoded.json"
    manifest = REPO / "runs" / "manifest.json"
    if not (rvh.exists() and manifest.exists()):
        check("real_vs_hardcoded.json and the manifest both exist", False)
        return
    rows = json.loads(rvh.read_text())["rows"]
    publishing = [r for r in rows if (r.get("real") or {}).get("pae_min") is not None]
    man = json.loads(manifest.read_text())
    pae_kinds = {r["kind"] for r in man["runs"]
                 for f in r["files"] if "_pae_" in f["file"]}
    n_pae_files = sum(1 for r in man["runs"] for f in r["files"] if "_pae_" in f["file"])
    check(f"{len(publishing)} candidates publish a PAE value", bool(publishing))
    check("the kind that produced them retains its pae arrays",
          "candidate-fold" in pae_kinds, str(sorted(pae_kinds)))
    # An inequality over the whole corpus is not a per-value guarantee: deleting the pae
    # entries from 21 of the 22 candidate-fold runs still satisfied it, because the variance
    # study's 150 arrays alone clear the bar. Each publishing candidate is now resolved to its
    # own run and that run must retain an array.
    by_job = {r["job"]: r for r in man["runs"]}
    orphaned = []
    for r in publishing:
        run = by_job.get(r.get("code"))
        if run is None or not any("_pae_" in f["file"] for f in run["files"]):
            orphaned.append(r.get("code"))
    check("every candidate publishing a PAE value has its own array retained",
          not orphaned, f"{len(orphaned)} without one: {orphaned[:4]}")

    # Every module that reads a pae array must have its kind covered, so the policy cannot be
    # narrowed again by surveying a single file.
    import glob
    readers = [f for f in glob.glob(str(REPO / "platform" / "**" / "*.py"), recursive=True)
               if "pae_" in Path(f).read_text() and ".npz" in Path(f).read_text()
               and "rescue_runs" not in f]
    check("more than one module reads pae arrays, as the policy comment now states",
          len(readers) >= 2, str([Path(f).name for f in readers]))


def test_registered_plans_are_hash_stable():
    """Re-registering an unchanged plan must reproduce its stored hash, for every study.

    Lineage fields (supersedes/supersedes_reason) were added after five plans had been
    registered, so their stored content has no such key. Including an empty one in the hash
    made those plans hash differently than they had: re-running --register would write a
    SECOND file for the study, and prespec.load() refuses to resolve a study with more than
    one plan — permanently, and by design. Measured before the fix, prodigy-discrimination-v1
    hashed to 585801dae8b2 against its stored b6b903d9ec37.
    """
    print("\n[prespec] registered plans are hash-stable")
    import glob
    import hashlib as _h
    mismatched = []
    for f in sorted(glob.glob(str(REPO / "prespec" / "*.json"))):
        d = json.loads(Path(f).read_text())
        blob = json.dumps(d["content"], sort_keys=True, separators=(",", ":"))
        if _h.sha256(blob.encode()).hexdigest() != d["hash"]:
            mismatched.append(Path(f).name)
    check(f"all {len(glob.glob(str(REPO / 'prespec' / '*.json')))} plans hash to their own content",
          not mismatched, str(mismatched))

    # The check above is a tautology about the JSON: it re-hashes a file's own content against
    # that file's own hash and can never see a change to the Prespecification dataclass, which
    # is the ONLY way this defect can recur. Probed by adding one defaulted field, it still
    # printed PASS while pose-accuracy-v1 had started hashing to a different value. So the
    # property is tested where it lives: build each study's plan FROM CODE and require it to
    # reproduce the hash stored on disk.
    import importlib.util as _ilu
    drift = []
    skipped = []
    for src in sorted(glob.glob(str(REPO / "platform" / "studies" / "*.py"))):
        spec = _ilu.spec_from_file_location(f"_p_{Path(src).stem}", src)
        mod = _ilu.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as exc:                                   # noqa: BLE001
            drift.append(f"{Path(src).name}: import failed: {type(exc).__name__}")
            continue
        if not hasattr(mod, "build_prespec"):
            continue
        hits = glob.glob(str(REPO / "prespec" / f"{mod.STUDY_ID}.*.json"))
        if not hits:
            continue
        if not hasattr(mod, "prespec_args"):
            skipped.append(mod.STUDY_ID)                            # single-arg n taken from data
            continue
        stored = json.loads(Path(hits[0]).read_text())
        try:
            built = mod.build_prespec(*mod.prespec_args())
        except Exception as exc:                                   # noqa: BLE001
            drift.append(f"{mod.STUDY_ID}: build failed: {type(exc).__name__}")
            continue
        if built.hash() != stored["hash"]:
            drift.append(f"{mod.STUDY_ID}: code {built.hash()[:12]} vs stored {stored['hash'][:12]}")
    # This used to be check(..., True, ...) — literally unable to fail — and its stated
    # justification was false: the "artefact check above" re-hashes a file against its own
    # hash and cannot see code drift at all. Probed by changing pose_accuracy's
    # primary_metric, the whole suite still printed 165 passed, 0 failed. Every study must be
    # covered, so an uncovered one is now a failure rather than a footnote.
    check("every study exposes prespec_args() so its plan can be rebuilt from code",
          not skipped, f"uncovered: {sorted(skipped)}")
    check("plans rebuilt from code reproduce their stored hash", not drift, str(drift[:3]))

    # An absent lineage and an empty lineage are the same statement and must hash alike.
    from cbc import prespec as ps
    base = dict(study_id="x", question="q", primary_metric="m",
                primary_metric_justification="j", decision_threshold="t", n_planned=5,
                n_comparisons=1, multiplicity_correction="holm", alpha=0.05,
                stopping_rule="s", analysis_plan="a",
                hypotheses=(ps.Hypothesis(name="H", statement="s", predicted_by="p",
                                          confirmed_if="c", falsified_if="f"),))
    check("an empty lineage hashes the same as no lineage at all",
          ps.Prespecification(**base).hash()
          == ps.Prespecification(**base, supersedes="", supersedes_reason="").hash())
    check("a real lineage changes the hash",
          ps.Prespecification(**base).hash()
          != ps.Prespecification(**base, supersedes="y", supersedes_reason="r").hash())

    # One plan per study: more than one is what load() refuses.
    from collections import Counter
    stems = Counter(Path(f).name.rsplit(".", 2)[0]
                    for f in glob.glob(str(REPO / "prespec" / "*.json")))
    dupes = [k for k, v in stems.items() if v > 1]
    check("no study has two registered plans", not dupes, str(dupes))


def test_readme_headline_metrics_match_the_artefacts():
    """Headline metrics quoted in the README must equal what the artefacts record.

    Three rounds running, the same defect: a study is re-run, its own section is regenerated,
    and a DERIVED sentence elsewhere keeps the old base. Round 6 found the worst instance —
    the variance section said study #10's MSA rise "sits essentially at the 0.149 noise floor,
    so the average is not resolvable", quoting +0.151, while the artefact recorded +0.1833,
    which is 1.23x the floor. The stale base inverted the conclusion, in the section whose job
    is to say what is and is not resolvable. Prose cannot be checked mechanically, but the
    NUMBERS in it can be.
    """
    print("\n[readme] headline metrics equal the artefacts")
    rd = (REPO / "README.md").read_text()

    def metric(path, *keys):
        body = json.loads((REPO / path).read_text())
        a = body.get("analysis") or body
        for k in keys:
            a = a.get(k) if isinstance(a, dict) else None
            if a is None:
                return None
        return a

    # (label, value, how it is written in prose)
    checks = [
        ("#10 MSA rise", metric("data/study_msa_specificity.json", "metrics", "delta_vs_study9"), 3),
        ("#10 mean native", metric("data/study_msa_specificity.json", "metrics", "mean_native_iptm"), 3),
        ("#10 mean decoy", metric("data/study_msa_specificity.json", "metrics", "mean_decoy_iptm"), 3),
        ("#9 mean native", metric("data/study_candidate_screen.json", "metrics", "mean_native_iptm"), 3),
        ("#9 mean decoy", metric("data/study_candidate_screen.json", "metrics", "mean_decoy_iptm"), 3),
        ("#2 ipTM floor", metric("data/study_inference_variance_analysis.json", "metrics",
                                 "across_seed_sd_iptm"), 3),
        ("#11 ratio", metric("data/study_prodigy.json", "metrics", "discrimination_ratio"), 2),
    ]
    # The AlphaFold section is prose over a derived artefact and has exactly the property that
    # made every earlier README section go stale: nothing recomputes it when #9 or #10 is
    # re-run. Its headline numbers are pinned here for the same reason theirs are.
    af = json.loads((REPO / "data" / "alphafold_db_comparison.json").read_text())
    for arm_name, arm in af["arms"].items():
        checks.append((f"AF {arm_name} median r", arm["pearson_r_median"], 3))
        checks.append((f"AF {arm_name} pLDDT offset", arm["mean_offset_afdb_minus_boltz"], 2))
    checks.append(("AF arm shift",
                   af["arm_agreement"]["median_shift_in_r_when_boltz_gets_an_msa"], 4))
    missing = []
    for label, val, nd in checks:
        if val is None:
            missing.append(f"{label}: absent from artefact")
            continue
        forms = {f"{val:.{nd}f}", f"{val:.{nd}f}".rstrip("0").rstrip(".")}
        if not any(f in rd for f in forms):
            missing.append(f"{label}={val} (looked for {sorted(forms)})")
    check(f"{len(checks)} headline metrics appear in the README at their artefact value",
          not missing, str(missing))

    # The screen's population, by molecule. "all 13 distinct candidates" was true of no
    # artefact in the repository: 13 is the construct count and 12 is the peptide count,
    # because de-duplication is applied on (peptide, target) and one 41-mer is declared
    # against two receptors. The README must state the second number wherever it states the
    # first, and must not call the first one distinct.
    import re as _re
    pop = []
    for rel in ("data/study_candidate_screen.json", "data/study_msa_specificity.json"):
        mult = metric(rel, "peptide_multiplicity")
        if not mult:
            pop.append(f"{rel}: no peptide_multiplicity block to source the count to")
            continue
        n_c, n_d = mult["n_constructs"], mult["n_distinct_peptides"]
        if n_d == n_c:
            continue
        if not _re.search(rf"\b{n_d}\b[^.]{{0,80}}distinct peptides", rd):
            pop.append(f"{rel}: README never states {n_d} distinct peptides")
        for word in ("distinct candidates", "distinct designs", "distinct peptides"):
            for m in _re.finditer(rf"\b{n_c}\b\s+{word}", rd):
                pop.append(f"{rel}: README calls {n_c} constructs '{m.group(0)}'")
        sens = metric(rel, "metrics", "shared_peptide_sensitivity")
        if not sens:
            pop.append(f"{rel}: no shared_peptide_sensitivity to source the disclosure to")
            continue
        key = ("paired_native_minus_decoy_mean" if "msa" in rel
               else "native_minus_decoy_mean")
        for label, v in sens["counted_once"].items():
            val = f"{v[key]:.4f}"
            if val not in rd and val.lstrip("0") not in rd:
                pop.append(f"{rel}: README omits the counted-once value {val} ({label})")
    check("the README states the screen's distinct-peptide count and what it moves",
          not pop, str(pop))

    # And the one derived comparison that inverted: the MSA rise against the ipTM noise floor.
    rise = metric("data/study_msa_specificity.json", "metrics", "delta_vs_study9")
    floor = metric("data/study_inference_variance_analysis.json", "metrics", "across_seed_sd_iptm")
    if rise is not None and floor is not None:
        says_below = ("sits essentially *at*" in rd or "rather\nthan above it" in rd
                      or "not resolvable against sampler noise" in rd)
        check("the README does not call the MSA rise unresolvable when it exceeds the floor",
              not (rise > floor and says_below),
              f"rise {rise} vs floor {floor}")


def test_screen_coverage_is_recorded_and_complete():
    """The screened population must be derived, recorded, and gap-free.

    The README claims coverage() "records why each candidate is in or out"; nothing wrote it
    anywhere, so the claim pointed at a function the reader would have to run. And an earlier
    coverage() short-circuited on the hand-written map, so the criterion governed exclusions
    only while the inclusion half stayed hand-listed — the defect it was written to remove,
    surviving in the half that matters.
    """
    print("\n[coverage] the screened population is derived and recorded")
    art = REPO / "data" / "study_candidate_screen.json"
    if not art.exists():
        check("the screen artefact exists", False)
        return
    a = json.loads(art.read_text())["analysis"]
    cov = a.get("coverage")
    check("the artefact records the coverage derivation", cov is not None)
    if not cov:
        return
    check("no candidate the criterion admits is left unscreened",
          cov["n_admissible_but_unscreened"] == 0, str(cov.get("admissible_but_unscreened")))
    scored = {p["code"] for p in a["per_candidate"]}
    screened = set(cov["screened"])
    # Duplicates collapse, so scored is a subset of screened; nothing scored may be outside it.
    check("every scored candidate is one the criterion admitted",
          scored <= screened, str(sorted(scored - screened)))
    check("every exclusion carries a reason",
          all(e.get("reasons") or e.get("reason") for e in cov["excluded"]),
          str([e["code"] for e in cov["excluded"] if not (e.get("reasons") or e.get("reason"))]))


def test_every_published_row_resolves_to_a_run_under_custody():
    """The repository's central promise, checked end to end.

    Every number in a study artefact is supposed to trace to bytes under `runs/`. Pieces of
    that were guarded -- no /tmp path survives in a published file, a published PAE value has
    a retained array -- but nothing asserted the whole chain: that for EVERY row a study
    reports, a run producing it is still in the manifest.

    It matters because run directories are content-addressed, so a directory's name changes
    whenever its file set changes. Adding a PAE array or dropping one under the retention
    policy moves a run to a new hash and deletes the old path; 24 directories tracked at the
    last commit are gone from the working tree for exactly that reason. All 24 turned out to
    be re-hashed rather than lost, and this test is what makes that difference detectable
    instead of something a person has to remember to check by hand.

    The job-naming convention differs per study and is written out rather than guessed. A
    hand-run of this check reported 256 missing rows purely because the key was built wrongly,
    which is the failure mode a named mapping prevents.

    A NAMED MAPPING ALSO NAMES WHAT IT LEAVES OUT, AND THIS ONE DID NOT. The docstring says
    "EVERY row a study reports" and the list below held six studies. Study #12 folds 176 rows
    and is not on it, and #12 is precisely the study that would fail: 160 of its rows name
    `runs/interface-null-positive-control/`, an uncommitted tree, so they resolve for nobody
    who clones this repository. The universal was republished into the written report --
    "A test asserts that every row any study reports resolves to a run still in the
    manifest" -- while the test it names had quietly stopped covering the counterexample.
    That is the whole shape of this audit in one list literal: the correction was made (the
    README says the tree is not here, in full) on a surface nobody checking custody was
    looking at. Two checks close it. The mapping must now account for every study in the
    slate rather than an unstated six, and a study left out must be left out because
    `slate.json` records its custody as incomplete or records that its rows name no folds --
    never by omission. And the shortfall itself is checked against the artefacts rather than
    trusted, so #12 is covered by this test in the only form that is true of it.
    """
    print("\n[custody] every published row has a retained run")
    manifest = json.loads((REPO / "runs" / "manifest.json").read_text())["runs"]
    idx = set()
    for r in manifest:
        for name in [r["job"], *(r.get("identical_jobs") or [])]:
            idx.add((r.get("kind"), name))

    def screen_job(row):
        k = row.get("kind", "native")
        return f"{row['code']}_{'native' if k == 'native' else k}"

    STUDIES = [
        ("study_candidate_screen.json", "candidate-screen", screen_job),
        ("study_msa_specificity.json", "msa-specificity", screen_job),
        ("study_inference_variance.json", "inference-variance",
         lambda r: f"{r['code']}_{r['arm']}_s{r['seed']}"),
        ("study_pose_accuracy.json", "pose-accuracy", lambda r: r.get("pdb_id")),
        ("study_peptide_interface.json", "peptide-interface", lambda r: r.get("pdb_id")),
        ("study_ache_affinity.json", "ache-affinity", lambda r: r.get("chembl")),
        # Study #8 re-analyses study #1's fifteen compounds against corrected references and
        # reuses their folds, so its rows resolve under the ache-affinity kind. It cites no
        # path of its own and was on no list, which left fifteen published rows with nothing
        # asserting their bytes at all -- found by the coverage check at the end of this
        # function, which is what that check exists for.
        ("study_affinity_corrected.json", "ache-affinity", lambda r: r.get("chembl")),
    ]
    total = 0
    for name, kind, job_of in STUDIES:
        path = REPO / "data" / name
        if not path.exists():
            check(f"data/{name} exists", False)
            continue
        rows = [r for r in (json.loads(path.read_text()).get("rows") or [])
                if r.get("ok") is not False]
        jobs = [job_of(r) for r in rows]
        unnamed = sum(1 for j in jobs if j is None)
        lost = [j for j in jobs if j is not None and (kind, j) not in idx]
        total += len(rows)
        check(f"{name}: all {len(rows)} reported rows have a retained run",
              not lost and not unnamed,
              f"{len(lost)} missing e.g. {lost[:3]}" if lost
              else f"{unnamed} rows yielded no job name")
    check(f"{total} published rows checked against the run manifest", total > 250,
          f"only {total} rows found; the mapping above may have gone stale")

    # -- the second mechanism: rows that name their own path --------------------------- #
    # Two conventions resolve a row to its bytes and both are real. The mapping above keys a
    # row to a run by NAME; studies #2, #6, #7, #11 and #12 write the run-relative path into
    # the row itself, so those resolve directly. slate.json's `custody` block counts the
    # second kind, and it is the one that exposes study #12. Recomputed here from the rows
    # and the manifest rather than read back out of the file being checked.
    slate = json.loads((REPO / "data" / "slate.json").read_text())
    held_files = {f"{r['path']}/{f['file']}"
                  for r in manifest for f in r.get("files", [])}
    wrong, declared = [], []
    for st in slate["studies"]:
        cu = st.get("custody") or {}
        n_held = n_short = 0
        for art in [st["artefact"], *(st.get("companion_artefacts") or [])]:
            for r in (json.loads((REPO / art).read_text()).get("rows") or []):
                ps = [v for v in r.values()
                      if isinstance(v, str) and v.startswith("runs/")]
                if not ps:
                    continue
                if all(q in held_files for q in ps):
                    n_held += 1
                else:
                    n_short += 1
        if (n_held, n_short) != (cu.get("rows_whose_bytes_this_repository_holds"),
                                 cu.get("rows_whose_bytes_this_repository_does_not_hold")):
            wrong.append(f"{st['study_id']}: rows say {n_held}/{n_short}, slate.json says "
                         f"{cu.get('rows_whose_bytes_this_repository_holds')}/"
                         f"{cu.get('rows_whose_bytes_this_repository_does_not_hold')}")
        if n_short:
            declared.append(f"{st['study_id']} ({n_short} of {n_held + n_short})")
    check("every study's path-resolved custody count matches the rows and the manifest",
          not wrong, str(wrong))
    check("the studies missing fold bytes are declared, not discovered",
          declared == ["interface-null-positive-control-v1 (160 of 176)"], str(declared))

    # -- nothing is checked by neither mechanism --------------------------------------- #
    # A study absent from the mapping AND citing no paths has nothing asserted about its
    # bytes at all, and this test's docstring would still say "EVERY row a study reports".
    mapped = {n for n, _, _ in STUDIES}
    silent = [st["study_id"] for st in slate["studies"]
              if not any(Path(x).name in mapped
                         for x in [st["artefact"], *(st.get("companion_artefacts") or [])])
              and not (st.get("custody") or {}).get("rows_citing_a_fold_output")]
    check("no study's rows are outside both custody mechanisms", not silent, str(silent))


# --------------------------------------------------------------------------- #
# Every study's analysis, recomputed from that study's own rows
# --------------------------------------------------------------------------- #
# A study artefact carries two things: the rows a run produced, and an analysis block
# summarising them. Nothing until now checked that the second follows from the first. Every
# other guard in this file checks provenance (a row resolves to a run) or currency (an index
# matches its generator); none of them would notice a mean computed over the wrong subset, a
# metric left behind when its rows were re-run, or a p-value carried over from an earlier
# version of a study. The published summary could disagree with the rows printed directly
# above it and the suite would pass.
#
# The manuscript run that added study #12 checked this by hand and deposited a 48 KB
# transcript of the arithmetic. A transcript records that someone once agreed; it does not
# object when the artefact changes. This does.
#
# One recompute function per artefact, written from the pre-registered definition rather than
# by importing the analyser -- importing it would only prove the analyser is deterministic.
# Tolerance is derived from the precision each value was PUBLISHED at: a value stored as
# 0.0895 must agree to within half of the last decimal it shows. Two kinds of quantity are
# out of reach and are named rather than skipped silently:
#
#   * study #6's per-entry RMSD is symmetry-corrected against coordinate files with RDKit, so
#     it is not a function of rows[] at all. Its per-entry values are taken as given and
#     everything the analysis derives FROM them -- the fractions, the strata, the Wilson
#     intervals, Fisher's exact p -- is recomputed.
#   * study #11's variance decomposition needs the six fitted PRODIGY coefficients, which are
#     external constants and appear nowhere in the artefact.

def _decimals(x: float) -> int:
    """How many decimals a stored value shows -- i.e. the precision it was published at."""
    s = repr(float(x))
    if "e" in s or "E" in s:
        return 12
    frac = s.split(".")[1].rstrip("0")
    return len(frac)


def _pct(vals: list[float], q: float) -> float:
    """numpy's default percentile, on a sorted list, without importing numpy."""
    k = (len(vals) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return vals[lo] if lo == hi else vals[lo] * (hi - k) + vals[hi] * (k - lo)


def _wilson95(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _fisher2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p, computed exactly."""
    n = a + b + c + d
    row1, col1 = a + b, a + c
    obs = math.comb(row1, a) * math.comb(n - row1, c) / math.comb(n, col1)
    total = 0.0
    for i in range(max(0, col1 - (n - row1)), min(row1, col1) + 1):
        pr = math.comb(row1, i) * math.comb(n - row1, col1 - i) / math.comb(n, col1)
        if pr <= obs * (1 + 1e-9):
            total += pr
    return min(1.0, total)


def _native_vs_decoys(rows: list[dict], key: str = "code") -> dict:
    """The shape shared by #9, #10 and #12: one native per item, the rest its own null."""
    by: dict[str, dict] = {}
    for r in rows:
        if not r.get("ok"):
            continue
        d = by.setdefault(r[key], {"native": None, "decoys": []})
        if r["kind"] == "native":
            d["native"] = r["iptm"]
        else:
            d["decoys"].append(r["iptm"])
    return by


def _rc_ache_affinity(d: dict, add) -> None:
    import numpy as np
    from scipy import stats

    a, m = d["analysis"], d["analysis"]["metrics"]
    ok = [r for r in d["rows"] if r.get("ok")]
    pred = [r["pred_pic50"] for r in ok]
    meas = [r["meas_pic50"] for r in ok]
    err = [abs(p - q) for p, q in zip(pred, meas)]
    nrec = [r["n_records"] for r in ok]
    rr = stats.spearmanr(pred, meas)
    add("n_observed", len(ok), a["n_observed"])
    add("spearman rho", float(rr.statistic), m["spearman_rho_predicted_vs_measured_pIC50"])
    add("H1 p", float(rr.pvalue), a["p_raw"]["H1_ranking_ability"])
    add("mean absolute error", statistics.fmean(err), m["mean_absolute_error_log10"])
    add("rmse", math.sqrt(statistics.fmean([(p - q) ** 2 for p, q in zip(pred, meas)])),
        m["rmse_log10"])
    add("pearson r", float(stats.pearsonr(pred, meas).statistic), m["pearson_r_pIC50"])
    add("kendall tau", float(stats.kendalltau(pred, meas).statistic), m["kendall_tau"])
    add("fraction within 1 log", statistics.fmean([float(e <= 1) for e in err]),
        m["fraction_within_1_log"])
    mem = stats.spearmanr(err, nrec)
    add("memorization rho", float(mem.statistic), a["memorization_rho"])
    add("H2 p", float(mem.pvalue), a["p_raw"]["H2_memorization_signature"])
    hup = next(r for r in ok if "HUPERZINE" in r["name"].upper())
    hup_err = abs(hup["error_log10"])
    add("huperzine error", hup_err, m["huperzine_absolute_error_log10"])
    z = (hup_err - statistics.fmean(err)) / statistics.stdev(err)
    add("huperzine z", z, a["huperzine_z"])
    add("H3 p", float(2 * (1 - stats.norm.cdf(abs(z)))),
        a["p_raw"]["H3_huperzine_representative"])
    # The bootstrap interval is seeded, so it is reproducible arithmetic like any other.
    rng = np.random.default_rng(0)
    p_arr, m_arr = np.array(pred), np.array(meas)
    boot = sorted(b for b in
                  (stats.spearmanr(p_arr[s], m_arr[s]).statistic
                   for s in (rng.integers(0, len(ok), len(ok)) for _ in range(10000)))
                  if not math.isnan(b))
    add("spearman CI lo", _pct(boot, 2.5), a["spearman_ci95"][0])
    add("spearman CI hi", _pct(boot, 97.5), a["spearman_ci95"][1])


def _rc_affinity_corrected(d: dict, add) -> None:
    import numpy as np
    from scipy import stats

    a, m = d["analysis"], d["analysis"]["metrics"]
    ok = [r for r in d["rows"] if r.get("corrected")]
    pred = [r["pred_pic50"] for r in ok]
    meas = [r["meas_pic50_corrected"] for r in ok]
    err = [abs(p - q) for p, q in zip(pred, meas)]
    rr = stats.spearmanr(pred, meas)
    add("n_observed", len(ok), a["n_observed"])
    add("spearman rho", float(rr.statistic), m["spearman_rho_corrected"])
    add("spearman p", float(rr.pvalue), a["spearman_p"])
    # rho_v1 is the superseded study's published rho, not a quantity these rows can produce;
    # the delta the artefact reports must still be the difference of the two.
    add("delta rho", float(rr.statistic) - m["rho_v1"], m["delta_rho"])
    add("median absolute error", statistics.median(err), m["median_absolute_error_log10"])
    disp = [r["reference"]["log10_sd"] for r in ok
            if r["reference"].get("log10_sd") is not None]
    add("median reference sd", statistics.median(disp), m["median_reference_log10_sd"])
    add("median records", statistics.median([r["reference"]["n"] for r in ok]),
        m["median_records_per_compound"])
    add("single-record compounds", sum(1 for r in ok if r["reference"]["n"] == 1),
        m["n_compounds_with_single_record"])
    add("max reference spread", max(r["reference"]["log10_spread"] for r in ok),
        m["max_reference_log10_spread"])
    add("pearson r", float(stats.pearsonr(pred, meas).statistic), m["pearson_r"])
    add("kendall tau", float(stats.kendalltau(pred, meas).statistic), m["kendall_tau"])
    rng = np.random.default_rng(0)
    p_arr, m_arr = np.array(pred), np.array(meas)
    boot = sorted(b for b in
                  (stats.spearmanr(p_arr[s], m_arr[s]).statistic
                   for s in (rng.integers(0, len(ok), len(ok)) for _ in range(10000)))
                  if not math.isnan(b))
    add("spearman CI lo", _pct(boot, 2.5), a["spearman_ci95"][0])
    add("spearman CI hi", _pct(boot, 97.5), a["spearman_ci95"][1])


def _rc_shared_peptide(d: dict, add, *, paired: bool) -> None:
    """Recompute the shared-peptide multiplicity and sensitivity from the rows.

    The screen de-duplicates on (peptide, target), which does not collapse one peptide
    declared against two receptors, so a thirteen-construct screen can be twelve molecules.
    Nothing here reads the generator: the peptide strings come off the stored rows and the
    grouping is redone, so a change to the de-duplication key that quietly re-inflated the
    count would fail here rather than reappear as "13 distinct candidates" in prose.
    """
    a = d["analysis"]
    mult = a.get("peptide_multiplicity")
    if not mult:
        add("peptide multiplicity recorded", True, False)
        return
    codes = {c["code"] for c in a["per_candidate"]}
    seq = {r["code"]: r["peptide"] for r in d["rows"]
           if r["kind"] == "native" and r.get("ok") and r["code"] in codes}
    add("constructs", len(seq), mult["n_constructs"])
    add("distinct peptides", len(set(seq.values())), mult["n_distinct_peptides"])
    shared = sorted(sorted(c for c in seq if seq[c] == s)
                    for s in set(seq.values())
                    if sum(1 for c in seq if seq[c] == s) > 1)
    add("shared groups", len(shared), len(mult["shared_sequence_groups"]))
    for want, got in zip(shared, mult["shared_sequence_groups"]):
        add("shared group members",
            ", ".join(want), ", ".join(sorted(x["code"] for x in got["codes"])))
        # The two constructs share their whole decoy arm, not only the native.
        arms = [sorted((r["kind"], r["peptide_used"]) for r in d["rows"]
                       if r["code"] == c and r.get("ok")) for c in want]
        add("shared group decoy arms identical",
            all(x == arms[0] for x in arms), got["decoy_arms_identical"])

    sens = a["metrics"].get("shared_peptide_sensitivity")
    if not shared:
        add("no sensitivity block when nothing is shared", sens is None, True)
        return
    if sens is None:
        add("sensitivity block present", True, False)
        return
    by = {c["code"]: c for c in a["per_candidate"]}
    drops = [c for g in shared for c in g]
    for label, stored in sens["counted_once"].items():
        kept = [c for c in by if c not in label[len("drop "):].split(", ")]
        add(f"{label}: n", len(kept), stored["n_constructs"])
        diffs = [by[c]["native_iptm"] - by[c]["decoy_mean"] for c in kept]
        nat = [by[c]["native_iptm"] for c in kept]
        if paired:
            add(f"{label}: paired mean", statistics.fmean(diffs),
                stored["paired_native_minus_decoy_mean"])
            add(f"{label}: dz", statistics.fmean(diffs) / statistics.stdev(diffs),
                stored["cohens_dz"])
            add(f"{label}: df", len(kept) - 1, stored["paired_t_df"])
        else:
            dec = [x for c in kept for x in by[c]["decoy_iptm"]]
            add(f"{label}: native minus decoy",
                statistics.fmean(nat) - statistics.fmean(dec),
                stored["native_minus_decoy_mean"])
            add(f"{label}: below 0.6", sum(1 for v in nat if v < 0.6),
                stored["n_candidates_below_0.6"])
    add("every shared construct is dropped in some variant",
        len(sens["counted_once"]), len(drops))
    # The point of the block: it must say whether a verdict moved, and it must be right.
    add("verdicts that move", "", ", ".join(sens["verdicts_that_move"]))


def _rc_candidate_screen(d: dict, add) -> None:
    a, m = d["analysis"], d["analysis"]["metrics"]
    by = _native_vs_decoys(d["rows"])
    stored = {p["code"]: p for p in a["per_candidate"]}
    add("n_observed", sum(1 for r in d["rows"] if r.get("ok")), a["n_observed"])
    add("candidates", len(by), len(stored))
    natives, decoys, sweeps = [], [], 0
    for code, v in by.items():
        s = stored[code]
        n_ge = sum(1 for x in v["decoys"] if x >= v["native"])
        add(f"{code} native", v["native"], s["native_iptm"])
        add(f"{code} decoy mean", statistics.fmean(v["decoys"]), s["decoy_mean"])
        add(f"{code} decoy max", max(v["decoys"]), s["decoy_max"])
        add(f"{code} beats all decoys", all(v["native"] > x for x in v["decoys"]),
            s["beats_all_decoys"])
        add(f"{code} empirical p", (1 + n_ge) / (len(v["decoys"]) + 1), s["empirical_p"])
        natives.append(v["native"])
        decoys += v["decoys"]
        sweeps += bool(all(v["native"] > x for x in v["decoys"]))
    add("mean native", statistics.fmean(natives), m["mean_native_iptm"])
    add("mean decoy", statistics.fmean(decoys), m["mean_decoy_iptm"])
    add("native minus decoy", statistics.fmean(natives) - statistics.fmean(decoys),
        m["native_minus_decoy_mean"])
    add("fraction beating the null", sweeps / len(by), m["fraction_candidates_beating_null"])
    add("candidates above 0.8", sum(1 for v in natives if v > 0.8),
        m["n_candidates_above_0.8"])
    add("candidates below 0.6", sum(1 for v in natives if v < 0.6),
        m["n_candidates_below_0.6"])
    _rc_shared_peptide(d, add, paired=False)


def _rc_msa_specificity(d: dict, add) -> None:
    from scipy import stats

    a, m = d["analysis"], d["analysis"]["metrics"]
    stored = {p["code"]: p for p in a["per_candidate"]}
    diffs, natives, decoy_means = [], [], []
    for code, v in _native_vs_decoys(d["rows"]).items():
        # The plan admits a candidate only with at least five decoys; a candidate the
        # analyser dropped for that reason must not reappear here.
        if v["native"] is None or len(v["decoys"]) < 5:
            continue
        s = stored[code]
        dm = statistics.fmean(v["decoys"])
        n_ge = sum(1 for x in v["decoys"] if x >= v["native"])
        add(f"{code} native", v["native"], s["native_iptm"])
        add(f"{code} n decoys", len(v["decoys"]), s["n_decoys"])
        add(f"{code} decoy mean", dm, s["decoy_mean"])
        add(f"{code} decoy max", max(v["decoys"]), s["decoy_max"])
        add(f"{code} difference", v["native"] - dm, s["difference"])
        add(f"{code} beats all decoys", all(v["native"] > x for x in v["decoys"]),
            s["beats_all_decoys"])
        add(f"{code} empirical p", (1 + n_ge) / (len(v["decoys"]) + 1), s["empirical_p"])
        diffs.append(v["native"] - dm)
        natives.append(v["native"])
        decoy_means.append(dm)
    add("candidates", len(diffs), len(stored))
    add("paired mean difference", statistics.fmean(diffs),
        m["paired_native_minus_decoy_mean"])
    add("mean native", statistics.fmean(natives), m["mean_native_iptm"])
    add("mean decoy", statistics.fmean(decoy_means), m["mean_decoy_iptm"])
    add("cohens dz", statistics.fmean(diffs) / statistics.stdev(diffs), m["cohens_dz"])
    add("paired t p", float(stats.ttest_1samp(diffs, 0.0).pvalue), a["paired_t_p"])
    _rc_shared_peptide(d, add, paired=True)
    nul = m["beats_all_decoys_null"]
    sweeps = sum(1 for s in stored.values() if s["beats_all_decoys"])
    n_dec = max(s["n_decoys"] for s in stored.values())
    p0 = 1 / (n_dec + 1)
    add("sweeps", sweeps, nul["observed"])
    add("sweeps expected", len(stored) * p0, nul["expected_under_null"])
    add("P(X >= observed)", float(stats.binom.sf(sweeps - 1, len(stored), p0)),
        nul["p_at_least_observed"])


def _rc_peptide_interface(d: dict, add) -> None:
    from scipy import stats

    a, m = d["analysis"], d["analysis"]["metrics"]
    ok = [r for r in d["rows"] if r.get("ok")]
    dockq = [r["dockq"] for r in ok]
    iptm = [r["iptm"] for r in ok if r.get("iptm") is not None]
    paired = [(r["iptm"], r["dockq"]) for r in ok if r.get("iptm") is not None]
    add("n_observed", len(ok), a["n_observed"])
    add("fraction DockQ acceptable", statistics.fmean([float(v >= 0.23) for v in dockq]),
        m["fraction_dockq_acceptable"])
    add("median DockQ", statistics.median(dockq), m["median_dockq"])
    add("mean ipTM", statistics.fmean(iptm), m["mean_iptm"])
    rr = stats.spearmanr([x for x, _ in paired], [y for _, y in paired])
    add("spearman ipTM/DockQ", float(rr.statistic), m["spearman_iptm_dockq"])
    add("spearman p", float(rr.pvalue), a["spearman_p"])
    add("fraction ipTM > 0.8", statistics.fmean([float(v > 0.8) for v in iptm]),
        m["fraction_iptm_above_0.8"])
    band = {k: 0 for k in m["iptm_band_confusion"]}
    for x, y in paired:
        good = y >= 0.23
        if x > 0.8:
            band["confident_and_acceptable" if good else "confident_but_wrong"] += 1
        elif x < 0.6:
            band["failed_band_but_acceptable" if good else "failed_band_and_wrong"] += 1
        else:
            band["grey_and_acceptable" if good else "grey_and_wrong"] += 1
    for k, v in band.items():
        add(f"band {k}", v, m["iptm_band_confusion"][k])
    add("median iRMSD", statistics.median([r["irmsd"] for r in ok if "irmsd" in r]),
        m["median_irmsd"])
    add("median fnat", statistics.median([r["fnat"] for r in ok if "fnat" in r]),
        m["median_fnat"])
    # The pre-cutoff fraction is the gate for study #9, so it is the one number in this
    # artefact another study's admissibility depends on.
    for name in ("pre_cutoff", "post_cutoff"):
        rs = [r for r in ok if r["split"] == name]
        k = sum(1 for r in rs if r["dockq"] >= 0.23)
        add(f"{name} k", k, a["strata"][name]["k"])
        add(f"{name} n", len(rs), a["strata"][name]["n"])
        add(f"{name} fraction", k / len(rs), a["strata"][name]["fraction"])
        add(f"{name} median DockQ", statistics.median([r["dockq"] for r in rs]),
            a["strata"][name]["median_dockq"])
        lo, hi = _wilson95(k, len(rs))
        add(f"{name} Wilson lo", lo, a["strata"][name]["wilson95"][0])
        add(f"{name} Wilson hi", hi, a["strata"][name]["wilson95"][1])


def _rc_pose_accuracy(d: dict, add) -> None:
    a, m = d["analysis"], d["analysis"]["metrics"]
    rmsd = m["per_entry_rmsd"]
    stratum = {r["pdb_id"]: r.get("stratum") for r in d["rows"]}
    vals = list(rmsd.values())
    # Every scored entry must still be a row of this study, even though its RMSD was
    # produced from coordinate files rather than from the row.
    add("every scored entry is a row of this study",
        all(pid in stratum for pid in rmsd), True)
    add("n_observed", len(vals), a["n_observed"])
    add("fraction under 2A", statistics.fmean([float(v <= 2.0) for v in vals]),
        m["fraction_rmsd_under_2A"])
    add("fraction under 5A", statistics.fmean([float(v <= 5.0) for v in vals]),
        m["fraction_rmsd_under_5A"])
    add("median RMSD", statistics.median(vals), m["median_rmsd"])
    add("mean RMSD", statistics.fmean(vals), m["mean_rmsd"])
    tally: dict[str, list[int]] = {}
    for pid, v in rmsd.items():
        t = tally.setdefault(stratum[pid], [0, 0])
        t[0] += v <= 2.0
        t[1] += 1
    for name in ("recall", "congeneric_extension"):
        k, n = tally[name]
        add(f"{name} k", k, a["strata"][name]["k"])
        add(f"{name} n", n, a["strata"][name]["n"])
        add(f"{name} fraction", k / n, a["strata"][name]["fraction"])
        lo, hi = _wilson95(k, n)
        add(f"{name} Wilson lo", lo, a["strata"][name]["wilson95"][0])
        add(f"{name} Wilson hi", hi, a["strata"][name]["wilson95"][1])
    (k1, n1), (k2, n2) = tally["recall"], tally["congeneric_extension"]
    add("interpolation premium", k1 / n1 - k2 / n2, a["interpolation_premium"])
    add("Fisher p", _fisher2x2(k1, n1 - k1, k2, n2 - k2),
        a["fisher_p_recall_vs_congeneric"])


def _rc_prodigy(d: dict, add) -> None:
    import random
    from scipy import stats

    a, m = d["analysis"], d["analysis"]["metrics"]
    by: dict[str, list[dict]] = {}
    for r in d["rows"]:
        if r.get("ok"):
            by.setdefault(r["code"], []).append(r)
    means = {c: statistics.fmean(x["dg"] for x in rs) for c, rs in by.items()}
    between = statistics.stdev(means.values())
    within = statistics.fmean([statistics.variance([x["dg"] for x in rs])
                               for rs in by.values() if len(rs) > 1]) ** 0.5
    add("n_observed", sum(1 for r in d["rows"] if r.get("ok")), a["n_observed"])
    add("between-candidate SD", between, m["between_candidate_sd"])
    add("within-candidate SD", within, m["within_candidate_sd"])
    add("discrimination ratio", between / within, m["discrimination_ratio"])
    add("between-candidate range", max(means.values()) - min(means.values()),
        m["between_candidate_range"])
    add("mean predicted dG",
        statistics.fmean([r["dg"] for r in d["rows"] if r.get("ok")]), m["mean_predicted_dg"])
    add("fraction of fit range",
        (max(means.values()) - min(means.values())) / 14.3,
        m["fraction_of_fit_range_occupied"])
    for code, v in a["per_candidate_mean_dg"].items():
        add(f"{code} mean dG", means[code], v)
    for code, ic in m["ic_counts_per_candidate"].items():
        for k, v in ic.items():
            add(f"{code} {k}", statistics.fmean(x[k] for x in by[code]), v)
    groups = [[x["dg"] for x in rs] for rs in by.values() if len(rs) > 1]
    F, p = stats.f_oneway(*groups)
    add("ANOVA F", float(F), m["anova_candidate_identity_F"])
    add("ANOVA p", float(p), m["anova_candidate_identity_p"])
    # Seeded bootstrap, so the published interval is reproducible arithmetic.
    rng = random.Random(m["bootstrap_seed"])
    boot = []
    for _ in range(m["bootstrap_resamples"]):
        gs = [[rng.choice([x["dg"] for x in by[c]]) for _ in by[c]] for c in by]
        try:
            b = statistics.stdev([statistics.fmean(g) for g in gs])
            w = statistics.fmean([statistics.variance(g) for g in gs if len(g) > 1]) ** 0.5
        except statistics.StatisticsError:
            continue
        if w > 0:
            boot.append(b / w)
    boot.sort()
    add("ratio CI lo", boot[int(.025 * len(boot))],
        m["discrimination_ratio_ci95_bootstrap"][0])
    add("ratio CI hi", boot[int(.975 * len(boot))],
        m["discrimination_ratio_ci95_bootstrap"][1])


def _rc_inference_variance(d: dict, add) -> None:
    """#2 is the one study whose rows and analysis are in different files."""
    rows = json.loads((REPO / "data" / "study_inference_variance.json").read_text())["rows"]
    m = d["metrics"]

    def arm(letter):
        out: dict[str, list[dict]] = {}
        for r in rows:
            if r.get("arm", "").startswith(letter) and r.get("returncode") == 0:
                out.setdefault(r["code"], []).append(r)
        return out

    def pooled(per: dict[str, list[float]]):
        """sqrt(mean of within-candidate variances) -- NOT the SD of the pooled values."""
        sds = {c: statistics.stdev(v) for c, v in per.items() if len(v) > 1}
        return math.sqrt(statistics.fmean([s ** 2 for s in sds.values()])), sds

    armA = arm("A")
    for code, rs in armA.items():
        vals = [r["complex_plddt"] for r in rs if r.get("complex_plddt") is not None]
        add(f"{code} same-seed distinct values", len(set(vals)),
            m["same_seed_distinct_values"][code])
    plddt: dict[str, list[float]] = {}
    ptm: dict[str, list[float]] = {}
    for code, rs in armA.items():
        plddt.setdefault(code, []).append(rs[0]["complex_plddt"])
        if rs[0].get("ptm") is not None:
            ptm.setdefault(code, []).append(rs[0]["ptm"])
    for code, rs in arm("B").items():
        for r in rs:
            if r.get("complex_plddt") is not None:
                plddt.setdefault(code, []).append(r["complex_plddt"])
            if r.get("ptm") is not None:
                ptm.setdefault(code, []).append(r["ptm"])
    sd_plddt, sds = pooled(plddt)
    add("across-seed SD pLDDT", sd_plddt * 100, m["across_seed_sd_complex_plddt"])
    add("across-seed SD pTM", pooled(ptm)[0], m["across_seed_sd_ptm"])
    for code, v in d["per_candidate_sd_plddt"].items():
        add(f"{code} SD pLDDT", sds[code] * 100, v)
    iptm: dict[str, list[float]] = {}
    ipae: dict[str, list[float]] = {}
    for code, rs in arm("D").items():
        for r in rs:
            if r.get("iptm") is not None:
                iptm.setdefault(code, []).append(r["iptm"])
            if r.get("interface_pae_min") is not None:
                ipae.setdefault(code, []).append(r["interface_pae_min"])
    add("across-seed SD ipTM", pooled(iptm)[0], m["across_seed_sd_iptm"])
    if ipae:
        add("across-seed SD interface PAE", pooled(ipae)[0],
            m["across_seed_sd_interface_pae_min"])
    paired = []
    for code, rs in arm("C").items():
        with_msa = [r["complex_plddt"] for r in rs if r.get("complex_plddt") is not None]
        without = plddt.get(code, [])
        if with_msa and without:
            paired.append((statistics.fmean(without), statistics.fmean(with_msa)))
    add("MSA mean shift", statistics.fmean([(w - o) * 100 for o, w in paired]),
        m["msa_mean_shift"])


def _rc_interface_null_positive_control(d: dict, add) -> None:
    from scipy import stats

    a, m = d["analysis"], d["analysis"]["metrics"]
    pt = a["primary_test"]
    stored = {c["pdb_id"]: c for c in m["per_complex"]}
    n_perm = max(c["n_permutations"] for c in stored.values())
    by = _native_vs_decoys(d["rows"], key="pdb_id")
    natives, perms_all, diffs, sweeps = [], [], [], 0
    rows_by_id = {r["pdb_id"]: r for r in d["rows"] if r["kind"] == "native"}
    for pid, v in by.items():
        s = stored[pid]
        pm = statistics.fmean(v["decoys"])
        n_ge = sum(1 for x in v["decoys"] if x >= v["native"])
        add(f"{pid} native", v["native"], s["native_iptm"])
        add(f"{pid} permutations", len(v["decoys"]), s["n_permutations"])
        add(f"{pid} permutation mean", pm, s["permutation_mean"])
        add(f"{pid} permutation max", max(v["decoys"]), s["permutation_max"])
        add(f"{pid} difference", v["native"] - pm, s["difference"])
        add(f"{pid} beats all permutations", all(v["native"] > x for x in v["decoys"]),
            s["beats_all_permutations"])
        add(f"{pid} empirical p", (1 + n_ge) / (len(v["decoys"]) + 1), s["empirical_p"])
        natives.append(v["native"])
        perms_all += v["decoys"]
        diffs.append(v["native"] - pm)
        sweeps += bool(all(v["native"] > x for x in v["decoys"]))
    n = len(diffs)
    mean, sd = statistics.fmean(diffs), statistics.stdev(diffs)
    se = sd / math.sqrt(n)
    t, p = stats.ttest_1samp(diffs, 0.0)
    tcrit = float(stats.t.ppf(0.975, n - 1))
    add("n pairs", n, pt["n_pairs"])
    add("mean difference", mean, pt["mean_difference"])
    add("SD of differences", sd, pt["sd_of_differences"])
    add("SE of the mean", se, pt["se_of_mean"])
    add("t", float(t), pt["t"])
    add("df", n - 1, pt["df"])
    add("p two-sided", float(p), pt["p_exact_two_sided"])
    add("CI lo", mean - tcrit * se, pt["ci95_mean_difference"][0])
    add("CI hi", mean + tcrit * se, pt["ci95_mean_difference"][1])
    add("cohens dz", mean / sd, pt["cohens_dz"])
    add("differences positive", sum(1 for x in diffs if x > 0),
        pt["n_differences_positive"])
    add("paired mean metric", mean, m["paired_native_minus_permutation_mean"])
    add("dz metric", mean / sd, m["cohens_dz"])
    add("mean native ipTM", statistics.fmean(natives), m["mean_native_iptm"])
    add("mean permutation ipTM", statistics.fmean(perms_all), m["mean_permutation_iptm"])
    add("paired t p", float(p), a["paired_t_p"])
    sw = stats.shapiro(diffs)
    add("Shapiro-Wilk W", float(sw.statistic), a["assumption_checks"]["shapiro_wilk_W"])
    add("Shapiro-Wilk p", float(sw.pvalue), a["assumption_checks"]["shapiro_wilk_p"])
    # H2: the criterion the study registered in advance and did not meet.
    h2 = a["secondary_tests"]["H2_binomial_reference"]
    p0 = 1 / (n_perm + 1)
    add("sweeps observed", sweeps, h2["observed_sweeps"])
    add("sweeps metric", sweeps, m["n_complexes_beating_all_permutations"])
    add("complexes", n, h2["n_complexes"])
    add("sweeps expected", n * p0, h2["expected_under_null"])
    add("P(X >= observed)", float(stats.binom.sf(sweeps - 1, n, p0)),
        h2["p_at_least_observed"])
    add("P(X >= registered threshold)",
        float(stats.binom.sf(h2["registered_threshold"] - 1, n, p0)), h2["p_at_threshold"])
    # H3 is a contrast against another study, and the registered comparator is named in the
    # plan: candidate-screen-v8, the single-sequence arm. Its differences come from ITS
    # artefact, already rounded to four decimals there, which is why this one check is given
    # an explicit tolerance rather than the published-precision one.
    h3 = a["secondary_tests"]["H3_welch_contrast"]
    v8 = json.loads((REPO / "data" / "study_candidate_screen.json").read_text())
    d8 = [c["native_iptm"] - c["decoy_mean"] for c in v8["analysis"]["per_candidate"]]
    add("comparator n", len(d8), h3["n_designed"])
    add("comparator mean", statistics.fmean(d8), h3["designed_mean"])
    add("contrast", mean - statistics.fmean(d8), h3["contrast"])
    add("Welch p", float(stats.ttest_ind(diffs, d8, equal_var=False).pvalue),
        h3["p_exact_two_sided"], 1e-4)
    # The two stratifications were registered before the folds were scored, which is the only
    # thing that keeps them from being a subgroup chosen after the fact.
    for block, name_of in (
            (m["paired_difference_by_dockq_stratum"],
             lambda r: ("gate_dockq_acceptable" if r["gate_dockq"] >= 0.23
                        else "gate_dockq_incorrect")),
            (m["paired_difference_by_split"], lambda r: r["split"])):
        groups: dict[str, list[float]] = {}
        for pid, v in by.items():
            groups.setdefault(name_of(rows_by_id[pid]), []).append(
                v["native"] - statistics.fmean(v["decoys"]))
        for name, vals in groups.items():
            add(f"{name} n", len(vals), block[name]["n"])
            add(f"{name} mean difference", statistics.fmean(vals),
                block[name]["mean_difference"])


#: Every study artefact in data/, and the function that rebuilds its analysis from its rows.
#: A study with no entry here fails the test rather than being skipped, so a new artefact
#: cannot arrive unchecked -- which is the whole point of writing this as a test of the
#: repository rather than a test of one commit.
RECOMPUTE = {
    "study_ache_affinity.json": _rc_ache_affinity,
    "study_affinity_corrected.json": _rc_affinity_corrected,
    "study_candidate_screen.json": _rc_candidate_screen,
    "study_msa_specificity.json": _rc_msa_specificity,
    "study_peptide_interface.json": _rc_peptide_interface,
    "study_pose_accuracy.json": _rc_pose_accuracy,
    "study_prodigy.json": _rc_prodigy,
    "study_inference_variance_analysis.json": _rc_inference_variance,
    "study_interface_null_positive_control.json": _rc_interface_null_positive_control,
    # Rows only: this file carries the folds, and its analysis lives in the file above.
    "study_inference_variance.json": None,
}


def test_every_analysis_block_recomputes_from_its_own_rows():
    """Every published statistic must follow from the rows published beside it."""
    print("\n[recompute] every analysis block follows from its own rows")
    found = sorted(p.name for p in (REPO / "data").glob("study_*.json"))
    unregistered = [n for n in found if n not in RECOMPUTE]
    check(f"all {len(found)} study artefacts in data/ have a recompute", not unregistered,
          f"no recompute for {unregistered}; add one rather than exempting the artefact"
          if unregistered else "")
    total = 0
    for name in found:
        fn = RECOMPUTE.get(name)
        if fn is None:
            continue
        payload = json.loads((REPO / "data" / name).read_text())
        checks: list[tuple] = []

        def add(label, got, want, tol=None, _c=checks):
            _c.append((label, got, want, tol))

        try:
            fn(payload, add)
        except Exception as exc:  # noqa: BLE001
            check(f"{name}: the analysis recomputes from rows[]", False,
                  f"recompute raised {exc!r}")
            continue
        bad = []
        for label, got, want, tol in checks:
            if want is None:
                bad.append(f"{label}: nothing published to compare against")
                continue
            if isinstance(got, bool) or isinstance(got, str):
                ok = got == want
            else:
                # Agreement to the precision the value was PUBLISHED at: a stored 0.0895
                # must be reproduced to within half of its last decimal.
                t = tol if tol is not None else 0.5 * 10 ** -_decimals(want) + 1e-9
                ok = abs(float(got) - float(want)) <= t
            if not ok:
                bad.append(f"{label}: rows give {got!r}, artefact says {want!r}")
        total += len(checks)
        check(f"{name}: all {len(checks)} published statistics recompute from its rows",
              not bad, "; ".join(bad[:3]) + (f" (+{len(bad) - 3} more)" if len(bad) > 3 else ""))
    check(f"{total} published statistics recomputed across the slate", total > 350,
          "" if total > 350 else "a recompute above has probably gone empty")


def test_generated_indices_are_current():
    """data/slate.json and data/structures.json must be what their generators produce now.

    Both are derived files that the page reads directly. Nothing forces a rebuild after a
    study is re-run, so the page could keep showing study #10 v8's verdicts beside a v9
    artefact indefinitely -- the same one-section-updated-one-forgotten failure the README
    checks already exist for, moved into a file nobody reads by eye. The generators are pure
    functions of files under custody, so the test is simply: run them into a scratch copy and
    compare. A difference means the shipped index is stale, not that the generator is wrong.
    """
    print("\n[indices] the generated indices match their generators")
    import shutil
    import tempfile
    # The AlphaFold comparison belongs here for the same reason the indices do: its arms read
    # study #9 and #10, so re-running either silently invalidates it, and it is cheap enough
    # to regenerate that there is no excuse for finding out later.
    for script, name in (("build_slate.py", "slate.json"),
                         ("build_structures.py", "structures.json"),
                         ("studies/alphafold_db_compare.py --analyse",
                          "alphafold_db_comparison.json")):
        shipped = REPO / "data" / name
        if not shipped.exists():
            check(f"data/{name} exists", False)
            continue
        before = shipped.read_text()
        backup = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        backup.write(before)
        backup.close()
        js = REPO / "data" / name.replace(".json", ".js")
        js_before = js.read_text() if js.exists() else None
        pae_dir = REPO / "data" / "pae"
        pae_before = ({f.name: f.read_bytes() for f in pae_dir.iterdir() if f.is_file()}
                      if pae_dir.is_dir() else None)
        try:
            script_path, *extra = script.split()
            r = subprocess.run([sys.executable, str(REPO / "platform" / script_path), *extra],
                               capture_output=True, text=True, cwd=REPO)
            ok = r.returncode == 0
            check(f"platform/{script_path} runs clean", ok, r.stderr.strip()[-200:])
            rebuilt = shipped.read_text()
            same = _same_index(before, rebuilt)
            # Order matters and so does the conjunction: a generator that dies before writing
            # leaves the shipped file untouched, so `rebuilt == before` and this reported the
            # file as current. Currency is only meaningful if something was actually produced.
            check(f"data/{name} is current with platform/{script_path}", ok and same,
                  "generator failed, so currency was not established" if not ok
                  else "" if same else "regenerating it changes the file; rebuild and commit")
        finally:
            # Restore whatever was shipped, so a failing test never silently "fixes" the
            # repository by leaving the rebuilt file in place.
            shutil.copyfile(backup.name, shipped)
            if js_before is not None:
                js.write_text(js_before)
            else:
                js.unlink(missing_ok=True)      # do not leave a twin the repo did not have
            if pae_before is not None and pae_dir.is_dir():
                for f in list(pae_dir.iterdir()):
                    if f.name not in pae_before:
                        f.unlink()
                    elif f.read_bytes() != pae_before[f.name]:
                        f.write_bytes(pae_before[f.name])
                for n, b in pae_before.items():
                    if not (pae_dir / n).exists():
                        (pae_dir / n).write_bytes(b)
            Path(backup.name).unlink()


def test_release_notes_are_generated_and_published_ones_are_frozen():
    """The note VERSION points at is a rebuild of the artefacts; older notes are records.

    The defect this encodes. `docs/RELEASE_NOTES_v1.0.0.md` said "**8 pre-registered
    studies**, 25 hypotheses, 13 confirmed and 11 falsified... **Not one study is
    confirmatory**" and "313 automated checks across six suites". All of it was true on
    2026-08-20. Study #12 was registered on 2026-08-22 with an empty deviation list -- the
    first confirmatory study in the slate -- and `VERSION` still read `1.0.0`, so the file
    asserting that no study had ever cleared its plan WAS the repository's description of
    itself. It was hand-written prose; `release.sh` only checked the file existed.

    Two properties, and neither is sufficient alone:

    * The note for `VERSION` must be byte-identical to what
      `platform/build_release_notes.py` produces from `data/`, `prespec/` and
      `verify_all.SUITES`. A count in it cannot go stale unless the generator does.
    * Every OTHER note must be frozen. A published release note is the body of a GitHub
      release and the description behind a minted version DOI; a rebuild must not be able to
      rewrite what a release contained, for the same reason `prespec/` is never rewritten.
      The refusal is exercised here, not merely asserted: the generator is pointed at a
      published note and must decline to write it.

    The first property holds only while `VERSION` is UNPUBLISHED, and this test used to
    assert it unconditionally. That is wrong for the window every release passes through:
    between the moment the release is closed -- its note frozen, which is what
    `check_version_stamps.py` reads as "published" -- and the moment `VERSION` is bumped for
    the next cycle, `VERSION` names a release that has been deposited, and its note is a
    record like any other. Asserting "the note for VERSION is never frozen" there would
    demand that the just-published release be left rewritable, which is the exact property
    freezing exists to remove. So the state is read from the marker, the same source
    `build_release_notes.py` and `check_version_stamps.py` both read, and each state gets
    the assertion that belongs to it.
    """
    print("\n[release notes] the note for VERSION is generated; published notes are frozen")
    gen = REPO / "platform" / "build_release_notes.py"
    version_file = REPO / "VERSION"
    version = version_file.read_text().strip()
    current = REPO / "docs" / f"RELEASE_NOTES_v{version}.md"
    frozen_re = re.compile(r"<!--\s*RELEASE-NOTE-FROZEN")

    check(f"docs/{current.name} exists for VERSION {version}", current.exists(),
          "" if current.exists() else "release.sh refuses to tag without it")
    if not current.exists():
        return

    current_is_frozen = bool(frozen_re.search(current.read_text()[:4096]))
    if current_is_frozen:
        # VERSION is published: the release has been cut and its note frozen, and VERSION has
        # not yet been bumped for the next cycle. The note is now a record, so the generator
        # must refuse it rather than track it -- the same rule every older note is held to.
        r = subprocess.run([sys.executable, str(gen)],
                           capture_output=True, text=True, cwd=REPO)
        refused = r.returncode != 0 and "REFUSED" in r.stdout
        check(f"docs/{current.name} is frozen, so VERSION {version} is a published release "
              f"and the generator refuses to rewrite it", refused,
              "" if refused else (r.stdout + r.stderr).strip()[-200:])
    else:
        # VERSION is in preparation: its note is not frozen (this branch's condition), so it
        # must track the artefacts byte-for-byte.
        r = subprocess.run([sys.executable, str(gen), "--check"],
                           capture_output=True, text=True, cwd=REPO)
        check(f"docs/{current.name} is not frozen, so it follows VERSION and is current "
              f"with platform/build_release_notes.py", r.returncode == 0,
              "" if r.returncode == 0 else (r.stdout + r.stderr).strip()[-200:])

    published = [n for n in sorted((REPO / "docs").glob("RELEASE_NOTES_v*.md"))
                 if n != current]
    for note in published:
        is_frozen = bool(frozen_re.search(note.read_text()[:4096]))
        check(f"docs/{note.name} is frozen to the release it describes", is_frozen,
              "" if is_frozen else "a published note is a record of that release; "
                                   "mark it RELEASE-NOTE-FROZEN")

    # The refusal, executed. VERSION is moved back to a published version so the generator
    # resolves to a frozen file, and must exit non-zero without touching it. Restored in
    # `finally` -- a test that leaves VERSION pointing at an old release would be worse than
    # the defect it guards.
    if published:
        target = published[-1]
        old_version = version
        before = target.read_bytes()
        try:
            version_file.write_text(target.stem.removeprefix("RELEASE_NOTES_v") + "\n")
            r = subprocess.run([sys.executable, str(gen)],
                               capture_output=True, text=True, cwd=REPO)
            refused = r.returncode != 0 and "REFUSED" in r.stdout
            check(f"the generator refuses to rewrite docs/{target.name}", refused,
                  "" if refused else (r.stdout + r.stderr).strip()[-200:])
            check(f"docs/{target.name} is byte-identical after the refusal",
                  target.read_bytes() == before)
        finally:
            version_file.write_text(old_version + "\n")
            target.write_bytes(before)


# --------------------------------------------------------------------------- #
# The retraction ledger and its guard
# --------------------------------------------------------------------------- #

def _retraction_fixture(tmp: Path) -> Path:
    """A miniature repository: the real ledger, plus one file of every surface class.

    The ledger is the real one on purpose. A fixture ledger would let the guard pass while
    the shipped records were malformed, which is the failure this whole mechanism exists to
    make impossible one level up.
    """
    root = tmp / "repo"
    for d in ("data", "data/superseded", "prespec", "memory/ledger", "memory/views",
              "platform"):
        (root / d).mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "retractions.jsonl", root / "retractions.jsonl")
    # check_ledger resolves every cited plan and artefact against the root it is given, so
    # the fixture has to carry one file per citation. That list used to be typed here --
    # two plans and two artefacts, correct for ret_0001..ret_0003 -- and ret_0005 was filed
    # against msa-specificity-v9 without it. The fixture then failed to resolve a plan that
    # is sitting in prespec/, and BOTH retraction tests raised LedgerError on a ledger the
    # standalone guard passes. A hand-typed list of what the data contains is the same
    # defect this round is closing everywhere else, so it is derived now: whatever the
    # ledger cites, the fixture holds. The plans are copied rather than stubbed because a
    # `plan_field` anchor is checked against the plan's real `content`.
    for _line in (REPO / "retractions.jsonl").read_text().splitlines():
        if not _line.strip() or _line.lstrip().startswith("//"):
            continue
        _rec = json.loads(_line)
        _by = _rec.get("retracted_by") or {}
        for _glob in ([f"*.{_by['prespec']}.json"] if _by.get("prespec") else []) + [
                f"{a['study']}.*.json" for a in (_rec.get("anchors") or []) if a.get("study")]:
            for _src in (REPO / "prespec").glob(_glob):
                shutil.copy(_src, root / "prespec" / _src.name)
        if _by.get("artefact"):
            _dst = root / _by["artefact"]
            _dst.parent.mkdir(parents=True, exist_ok=True)
            _dst.write_text("{}\n")
    (root / "README.md").write_text("# Fixture\n\nNothing withdrawn here.\n")
    (root / "data" / "slate.json").write_text(json.dumps(
        {"studies": [{"study_id": "peptide-interface-v1",
                      "hypotheses": [{"name": "H2_iptm_calibration",
                                      "statement": "a harmless sentence",
                                      "verdict": "CONFIRMED"}]}]}, indent=2))
    return root


#: The sentence study #12 falsified, exactly as prespec/peptide-interface-v1 registers it.
_RETRACTED_SENTENCE = ("ipTM predicts whether the interface is right, "
                       "so it can be used as a screening filter.")


def test_retraction_ledger_is_well_formed():
    """Every way a retraction record can be wrong that a machine can see.

    The last two are the ones with teeth. A fingerprint that does not match its own claim
    catches nothing and says nothing; a fingerprint that ALSO matches the replacement makes
    the corrected reading trip the guard forever, which is how a guard teaches people to
    write exemptions instead of corrections.
    """
    print("\n[retractions] the ledger itself")
    sys.path.insert(0, str(REPO / "platform"))
    import retractions as R

    recs = R.load()
    check("retractions.jsonl parses and validates", len(recs) > 0, f"{len(recs)} records")
    check("every record cites a replacement reading",
          all(r.replacement.strip() for r in recs))
    check("every record cites who withdrew the claim and when",
          all(r.retracted_by.get("date") and
              (r.retracted_by.get("study") or r.retracted_by.get("agent")) for r in recs))
    check("no two records hold the same claim",
          len({r.id for r in recs}) == len(recs))

    def problems(mutate) -> list[str]:
        import copy
        raw = [copy.deepcopy(r.rec) for r in recs]
        mutate(raw)
        return R.check_ledger([R.Retraction(x, i) for i, x in enumerate(raw, 1)], repo=REPO)

    check("a duplicate id is refused",
          any("duplicate id" in p for p in problems(lambda r: r.append(dict(r[0])))))
    check("a fingerprint that does not match its own claim is refused",
          any("does not match its own claim" in p
              for p in problems(lambda r: r[0].__setitem__("fingerprints", ["zzz_nomatch"]))))
    def _overlap(r):
        token = re.escape(recs[0].replacement[:24])
        r[0]["claim"] = r[0]["claim"] + " " + recs[0].replacement[:24]
        r[0]["fingerprints"] = [token]
    check("a fingerprint that also matches the replacement is refused",
          any("matches the replacement" in p for p in problems(_overlap)))
    check("a null citation with no stated reason is refused",
          any("absent_reason" in p for p in problems(
              lambda r: (r[0]["retracted_by"].__setitem__("prespec", None),
                         r[0]["retracted_by"].pop("prespec_absent_reason", None)))))


def test_retraction_guard_fails_on_the_defect_it_names():
    """Inject the retracted sentence and assert the guard finds it, on every surface class.

    The audit finding this closes: the front page rendered study #7's registered statement
    -- "ipTM ... can be used as a screening filter" -- verbatim beside a green CONFIRMED,
    for a use study #12 falsified with 4 of 16 established binders beating all ten
    permutations of themselves against a threshold of 5 registered in advance. The plan is
    hash-locked and is never edited. What must be impossible is the statement rendering
    ALONE.
    """
    print("\n[retractions] the guard, proven by making it fail")
    sys.path.insert(0, str(REPO / "platform"))
    import check_retractions as CR

    with tempfile.TemporaryDirectory() as td:
        root = _retraction_fixture(Path(td))
        hits, scanned, _, _ = CR.run(root)
        check("a clean fixture passes", not hits, str([h.path for h in hits]))
        check("the fixture is actually being read", len(scanned) >= 3, f"{len(scanned)}")

        # (a) prose, no withdrawal anywhere near it
        readme = root / "README.md"
        readme.write_text(f"# Fixture\n\nOur screen is sound: {_RETRACTED_SENTENCE}\n")
        hits, _, _, _ = CR.run(root)
        check("FAILS when the retracted sentence is injected into README.md",
              any(h.path == "README.md" and h.rec.id == "ret_0002" for h in hits))
        check("and names the surface and line",
              any(h.path == "README.md" and h.line > 0 for h in hits))

        # (b) same sentence, withdrawn in the same paragraph -> not an assertion
        readme.write_text(f"# Fixture\n\nThis section used to say: {_RETRACTED_SENTENCE}\n"
                          "That clause is retracted; study #12 falsified it.\n")
        hits, _, _, _ = CR.run(root)
        check("PASSES when the same sentence carries its withdrawal in the same block",
              not any(h.path == "README.md" for h in hits))
        readme.write_text("# Fixture\n")

        # (c) structured: the generated slate, which is where the real defect lived
        slate = root / "data" / "slate.json"
        doc = json.loads(slate.read_text())
        hyp = doc["studies"][0]["hypotheses"][0]
        hyp["statement"] = _RETRACTED_SENTENCE
        slate.write_text(json.dumps(doc, indent=2))
        hits, _, _, _ = CR.run(root)
        check("FAILS when data/slate.json republishes the registered statement alone",
              any(h.path == "data/slate.json" and h.rec.id == "ret_0002" for h in hits))

        # (d) ... and stops failing the moment build_slate.py's join is present
        hyp["retraction"] = {"id": "ret_0002", "replacement": "discrimination, not a filter"}
        slate.write_text(json.dumps(doc, indent=2))
        hits, _, _, _ = CR.run(root)
        check("PASSES once the withdrawal is attached to the same object",
              not any(h.path == "data/slate.json" for h in hits))

        # (e) delete the join back out: the guard is independent of the generator
        hyp.pop("retraction")
        slate.write_text(json.dumps(doc, indent=2))
        hits, _, _, _ = CR.run(root)
        check("FAILS again if the generator's join is removed",
              any(h.path == "data/slate.json" for h in hits))

        # (f) the exemption is by PATH, and the same bytes in an exempt record are silent
        for rel in ("data/superseded/study_candidate_screen.v2.json",
                    "prespec/peptide-interface-v1.515be79a7d12.json",
                    "memory/ledger/study-peptide-interface.jsonl"):
            (root / rel).write_text(json.dumps({"statement": _RETRACTED_SENTENCE}) + "\n")
        hits, _, _, _ = CR.run(root)
        offenders = sorted({h.path for h in hits})
        check("SILENT on data/superseded/, prespec/ and memory/ledger/ with the same bytes",
              offenders == ["data/slate.json"], str(offenders))

        # (g) but a rendering of an exempt record is not exempt
        (root / "memory" / "views" / "claims.md").write_text(
            f"- **[measurement]** {_RETRACTED_SENTENCE}\n")
        hits, _, _, _ = CR.run(root)
        check("NOT silent on memory/views/, which renders the exempt ledger",
              any(h.path == "memory/views/claims.md" for h in hits))

        # (h) a neighbouring claim's withdrawal must not clear this one. memory/views/
        # renders 860 claims as consecutive list items and a plain line window let one
        # item's marker clear another six lines away -- which is how audit finding 4
        # survived the first version of this guard.
        (root / "memory" / "views" / "claims.md").write_text(
            "- **[decision]** Some other claim entirely. RETRACTED.\n"
            "  `clm_0000000000000000` conf 0.90\n"
            f"- **[measurement]** {_RETRACTED_SENTENCE}\n"
            "  `clm_1111111111111111` conf 0.90\n")
        hits, _, _, _ = CR.run(root)
        check("a neighbouring item's withdrawal does not clear this claim",
              any(h.path == "memory/views/claims.md" for h in hits))

        # (i) a nested bullet IS covered by its parent item's withdrawal
        (root / "memory" / "views" / "claims.md").write_text(
            "- \u274c **[decision]** refuted by a later study\n"
            f"  - rationale: the claim was {_RETRACTED_SENTENCE}\n")
        hits, _, _, _ = CR.run(root)
        check("a nested bullet inherits its parent item's withdrawal",
              not any(h.path == "memory/views/claims.md" for h in hits))

        # (j) a skipped surface is reported, never counted as passing
        _, _, notes, _ = CR.run(root, remote=False)
        check("the GitHub About field is reported as not read, not as passing",
              any("github:About" in n for n in notes), str(notes))


def test_the_front_page_cannot_publish_a_withdrawn_statement():
    """The real artefact, not a fixture: study #7's H2 carries its withdrawal.

    build_slate.py joins retractions.jsonl on (study_id, hypothesis name) -- both keys the
    frozen plan already has -- so the ledger points at the plan and the plan never points
    back. The plan stays byte-identical; the rendering cannot appear without the withdrawal.
    """
    print("\n[retractions] the shipped slate")
    sys.path.insert(0, str(REPO / "platform"))
    import retractions as R

    slate = json.loads((REPO / "data" / "slate.json").read_text())
    recs = R.load()
    live = []
    for st in slate["studies"]:
        for h in st["hypotheses"]:
            for r in R.for_text(recs, h.get("statement") or ""):
                if "retraction" not in h:
                    live.append(f"{st['study_id']}/{h['name']} -> {r.id}")
    check("no hypothesis statement on the page asserts a retracted claim alone",
          not live, str(live))

    h7 = next(h for st in slate["studies"] if st["study_id"] == "peptide-interface-v1"
              for h in st["hypotheses"] if h["name"] == "H2_iptm_calibration")
    check("study #7's H2 carries its withdrawal", h7.get("retraction", {}).get("id")
          == "ret_0002", str(h7.get("retraction", {}).get("id")))
    check("the withdrawal names the study that falsified it",
          h7["retraction"]["retracted_by"]["study"] == "interface-null-positive-control-v1")
    check("the withdrawal carries the falsifying study's plan hash",
          h7["retraction"]["retracted_by"]["prespec"] == "69a5009d6f62")
    check("the withdrawal carries a replacement reading",
          bool(h7["retraction"]["replacement"].strip()))
    check("the CONFIRMED verdict is untouched -- the threshold really was met",
          h7["verdict"] == "CONFIRMED")
    check("the registered statement is reproduced exactly as registered",
          h7["statement"] == json.loads((REPO / "prespec" /
              "peptide-interface-v1.515be79a7d12.json").read_text()
              )["content"]["hypotheses"][1]["statement"])
    check("app.js renders it", "renderRetraction" in (REPO / "app.js").read_text())


def test_a_verdict_built_on_a_withdrawn_reading_carries_its_limit():
    """The second shape the page had, which is NOT a withdrawn statement and must not render
    as one.

    Study #10's H2 -- "at least one candidate is both better than its null and confident in
    absolute terms" -- rendered a green CONFIRMED with nothing beside it. Two of thirteen
    candidates cleared the registered conjunction, so the verdict is a true record of a
    threshold firing and the statement was never withdrawn; striking either would publish a
    falsehood. What is withdrawn is the READING the rule rests on. The rule asks whether one
    candidate beat one set of shuffles of itself, and study #12 measured that comparison on
    sixteen deposited X-ray complexes -- every one an established binder -- and found only 4
    of 16 beating all of theirs. The study's own artefact also records that 1.18 of 13 are
    expected to sweep by chance and that observing 2 has probability 0.334.

    So the ledger anchors a `decision_rule` limit rather than a retraction, and the last two
    checks here are the ones with teeth: the limit must NOT strike the statement, and the
    guard must fail when the join is deleted. A withdrawn statement enforces itself, because
    the statement carries the fingerprint; a withdrawn reading does not, because the
    statement contains none of its words. Without the landing check, deleting this join
    removes the only string a scan could see and every scan goes green.
    """
    print("\n[retractions] a verdict whose rule rests on a withdrawn reading")
    sys.path.insert(0, str(REPO / "platform"))
    import retractions as R
    import check_retractions as CR

    slate = json.loads((REPO / "data" / "slate.json").read_text())
    recs = R.load()

    def hyp(study_id, name):
        return next(h for st in slate["studies"] if st["study_id"] == study_id
                    for h in st["hypotheses"] if h["name"] == name)

    h10 = hyp("msa-specificity-v9", "H2_a_candidate_is_confident_and_specific")
    h9 = hyp("candidate-screen-v8", "H1_any_candidate_binds")
    check("the CONFIRMED chip carries a reading limit",
          (h10.get("reading_limit") or {}).get("retraction") == "ret_0001",
          str((h10.get("reading_limit") or {}).get("retraction")))
    check("so does the FALSIFIED one -- an absent binder is the same overclaim inverted",
          (h9.get("reading_limit") or {}).get("retraction") == "ret_0001")
    check("the verdict is untouched -- the registered threshold really did fire",
          h10["verdict"] == "CONFIRMED")
    check("the statement is NOT marked withdrawn, because it was not withdrawn",
          "retraction" not in h10 and "retraction" not in h9)
    check("the limit names what the verdict does not license",
          "no" in h10["reading_limit"]["limit"].lower()
          and bool(h10["reading_limit"]["read_instead"].strip()))
    check("it quotes the withdrawn reading so the two can be told apart",
          h10["reading_limit"]["withdrawn_reading"]
          == next(r for r in recs if r.id == "ret_0001").claim)
    check("app.js renders it, and separately from a withdrawal",
          all(s in (REPO / "app.js").read_text()
              for s in ("renderReadingLimit", "h.reading_limit")))

    # The landing check, proven by removing the join. A fingerprint scan cannot see this
    # defect: study #10's statement matches no retraction, which is why the anchor exists.
    with tempfile.TemporaryDirectory() as td:
        root = _retraction_fixture(Path(td))
        shutil.copy(REPO / "data" / "slate.json", root / "data" / "slate.json")
        check("the shipped slate lands every reading limit the ledger requires",
              not CR.check_anchors_landed(root, recs),
              str(CR.check_anchors_landed(root, recs)))

        doc = json.loads((root / "data" / "slate.json").read_text())
        for st in doc["studies"]:
            for h in st["hypotheses"]:
                h.pop("reading_limit", None)
        (root / "data" / "slate.json").write_text(json.dumps(doc, indent=2))
        problems = CR.check_anchors_landed(root, recs)
        check("FAILS when build_slate.py's reading-limit join is deleted",
              len(problems) == 2, str(problems))
        check("and it names the verdict left standing alone",
              any("msa-specificity-v9/H2_a_candidate_is_confident_and_specific" in p
                  for p in problems), str(problems))
        check("a plain fingerprint scan cannot see it, which is why this check exists",
              not any(h.path == "data/slate.json" and h.rec.id == "ret_0001"
                      for h in CR.run(root)[0]))



def _same_index(a: str, b: str) -> bool:
    """Equal ignoring the two stamps that change without the content changing.

    `built` moves at midnight and `git_sha` moves at every commit -- so as written, this test
    would have started failing the moment the repository was committed, on a checkout where
    nothing was actually stale. Both record WHEN a derived file was produced, not what it
    claims, so neither belongs in a comparison about staleness. Everything else must match.
    """
    ja, jb = json.loads(a), json.loads(b)
    for d in (ja, jb):
        d.pop("built", None)
        d.pop("git_sha", None)
    return ja == jb


def main() -> int:
    print("=" * 76)
    print("CognitionBioChem platform regression suite")
    print("=" * 76)
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            import traceback
            FAIL.append(t.__name__)
            print(f"  FAIL  {t.__name__} raised {exc!r}")
            traceback.print_exc()
    print("\n" + "=" * 76)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  -", f)
    print("=" * 76)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
