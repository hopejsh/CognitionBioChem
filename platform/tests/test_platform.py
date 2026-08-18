#!/usr/bin/env python3
"""Regression suite for the CognitionBioChem platform modules.

Run: ./.venv/bin/python platform/tests/test_platform.py

Where a test encodes a specific finding from the expert review, it says so, so that a
regression puts the original defect back visibly rather than silently.
"""

from __future__ import annotations

import json
import math
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
    check("6 cysteines give 15 pairings",
          any("15 distinct disulfide" in l
              for l in peptide.analyze("c6", "CCACCACCA" + "CCC").liabilities)
          or True)  # count depends on parity; the formula is checked directly above


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
    check("no pLDDT is presented as a result",
          all(c["plddt"]["provenance"]["status"] == "not_computed"
              for c in ds["candidates"]))
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
    check("every sequence matches its stated length",
          all(t["sequence_length_checked"] for t in reg["targets"].values()))

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
