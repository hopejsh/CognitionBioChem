#!/usr/bin/env python3
"""Peptide sequence validation and physicochemical properties.

Pure stdlib. Every property is computed from the sequence; nothing is asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any

STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")

# Ambiguity/placeholder codes that are valid in a FASTA file but are NOT a
# specifiable molecule: you cannot synthesize, model, or dock a residue that means
# "either of two amino acids".
AMBIGUOUS_AA = {
    "B": "aspartate or asparagine (ambiguous)",
    "Z": "glutamate or glutamine (ambiguous)",
    "J": "leucine or isoleucine (ambiguous)",
    "X": "any/unknown amino acid",
    "U": "selenocysteine (21st aa; requires SECIS machinery)",
    "O": "pyrrolysine (22nd aa; not present in humans)",
}

# Average residue masses (Da), monoisotopic-free, standard convention.
RESIDUE_MASS = {
    "A": 71.0788, "C": 103.1388, "D": 115.0886, "E": 129.1155, "F": 147.1766,
    "G": 57.0519, "H": 137.1411, "I": 113.1594, "K": 128.1741, "L": 113.1594,
    "M": 131.1926, "N": 114.1038, "P": 97.1167, "Q": 128.1307, "R": 156.1875,
    "S": 87.0782, "T": 101.1051, "V": 99.1326, "W": 186.2132, "Y": 163.1760,
}
WATER = 18.0153

# Kyte & Doolittle (J Mol Biol 1982) hydropathy.
KD_HYDROPATHY = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5, "E": -3.5,
    "G": -0.4, "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8,
    "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

# EMBOSS pKa set.
PKA_SIDE = {"C": 8.5, "D": 3.9, "E": 4.1, "H": 6.5, "K": 10.8, "R": 12.5, "Y": 10.1}
PKA_NTERM, PKA_CTERM = 8.6, 3.6
POSITIVE, NEGATIVE = set("KRH"), set("DECY")


@dataclass
class PeptideReport:
    name: str
    sequence: str
    length: int
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    invalid_residues: dict[str, int] = field(default_factory=dict)
    mol_weight: float | None = None
    net_charge_ph74: float | None = None
    isoelectric_point: float | None = None
    gravy: float | None = None
    frac_cationic: float | None = None
    frac_aromatic: float | None = None
    n_cysteine: int = 0
    cys_pairing: str = ""
    liabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def net_charge(seq: str, ph: float = 7.4) -> float:
    """Henderson-Hasselbalch over ionizable groups."""
    q = 1.0 / (1.0 + 10 ** (ph - PKA_NTERM))
    q -= 1.0 / (1.0 + 10 ** (PKA_CTERM - ph))
    for aa in seq:
        pka = PKA_SIDE.get(aa)
        if pka is None:
            continue
        if aa in ("K", "R", "H"):
            q += 1.0 / (1.0 + 10 ** (ph - pka))
        else:
            q -= 1.0 / (1.0 + 10 ** (pka - ph))
    return q


def isoelectric_point(seq: str) -> float:
    """Bisection on net charge."""
    lo, hi = 0.0, 14.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if net_charge(seq, mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def analyze(name: str, sequence: str) -> PeptideReport:
    seq = (sequence or "").strip().upper()
    rep = PeptideReport(name=name, sequence=seq, length=len(seq), valid=False)
    if not seq:
        rep.errors.append("empty sequence")
        return rep

    bad: dict[str, int] = {}
    for aa in seq:
        if aa not in STANDARD_AA:
            bad[aa] = bad.get(aa, 0) + 1
    rep.invalid_residues = bad
    for aa, n in bad.items():
        why = AMBIGUOUS_AA.get(aa, "not an amino acid letter")
        rep.errors.append(
            f"residue {aa!r} appears {n}x: {why}. The sequence does not specify a "
            "synthesizable molecule and cannot be submitted to any structure predictor.")
    if bad:
        return rep

    rep.valid = True
    rep.mol_weight = round(sum(RESIDUE_MASS[a] for a in seq) + WATER, 2)
    rep.net_charge_ph74 = round(net_charge(seq, 7.4), 2)
    rep.isoelectric_point = isoelectric_point(seq)
    rep.gravy = round(sum(KD_HYDROPATHY[a] for a in seq) / len(seq), 3)
    rep.frac_cationic = round(sum(seq.count(a) for a in "KR") / len(seq), 3)
    rep.frac_aromatic = round(sum(seq.count(a) for a in "FWY") / len(seq), 3)
    rep.n_cysteine = seq.count("C")
    if rep.n_cysteine:
        rep.cys_pairing = "even (pairable)" if rep.n_cysteine % 2 == 0 else "ODD (unpairable)"

    # --- developability liabilities, each with its quantitative trigger ---------- #
    if rep.mol_weight > 500:
        rep.liabilities.append(
            f"MW {rep.mol_weight:.0f} Da far exceeds the ~400-500 Da soft ceiling for "
            "passive blood-brain-barrier diffusion; systemic dosing will not give CNS "
            "exposure without an active transport mechanism.")
    if rep.net_charge_ph74 >= 4:
        rep.liabilities.append(
            f"net charge +{rep.net_charge_ph74:.1f} at pH 7.4: polycationic peptides bind "
            "glycosaminoglycans and serum proteins nonspecifically, are cleared rapidly, "
            "and do not cross an intact BBB by passive diffusion.")
    if rep.frac_cationic >= 0.30 and rep.frac_aromatic >= 0.15:
        rep.liabilities.append(
            f"{rep.frac_cationic:.0%} Lys/Arg with {rep.frac_aromatic:.0%} aromatic "
            "residues is the canonical cationic amphipathic motif of antimicrobial and "
            "cell-penetrating peptides: expect membrane lysis, hemolysis and "
            "concentration-dependent cytotoxicity. These liabilities are distinct from, "
            "and generally precede, any hERG concern.")
    if rep.n_cysteine and rep.n_cysteine % 2 == 1:
        rep.liabilities.append(
            f"{rep.n_cysteine} cysteines is odd, so at least one thiol must remain free: "
            "expect disulfide scrambling, covalent dimerization and batch heterogeneity.")
    elif rep.n_cysteine >= 4:
        n_pairings = _double_factorial(rep.n_cysteine - 1)
        rep.liabilities.append(
            f"{rep.n_cysteine} cysteines admit {n_pairings} distinct disulfide pairings; "
            "no connectivity is specified anywhere, so the folded product is undefined.")
    if "KLVFF" in seq:
        rep.liabilities.append(
            "contains KLVFF, the Abeta(16-20) self-recognition motif and the core driver "
            "of amyloid fibrillization. Using it as a therapeutic warhead carries a "
            "seeding/aggregation risk that must be measured, not assumed absent.")
    if rep.length >= 30:
        rep.liabilities.append(
            f"{rep.length} residues: unmodified linear peptides of this length are "
            "cleared by serum peptidases with plasma half-lives of minutes, and are large "
            "enough to raise anti-drug-antibody risk.")
    return rep


def _double_factorial(n: int) -> int:
    """(n)!! -- the number of perfect matchings on n+1 objects."""
    out = 1
    while n > 1:
        out *= n
        n -= 2
    return out


def gg_linker_fraction(seq: str) -> float:
    """Fraction of the sequence occupied by GGGGS/GS flexible linker repeats."""
    import re
    return sum(len(m.group()) for m in re.finditer(r"(?:GGGGS|GGGS|GS){2,}", seq)) / max(len(seq), 1)
