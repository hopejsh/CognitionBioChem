#!/usr/bin/env python3
"""All-atom physical validity checks for predicted structures.

The existing geometry check inspects only consecutive C-alpha distances. That is enough to
separate a real backbone from a parametric curve, but it never looks at a side chain, so it
will certify a structure with interpenetrating atoms, inverted stereocentres or impossible
disulfides as "plausible_protein: true". This module adds the checks that actually decide
whether coordinates are physically possible.

Every threshold here is either a literature value with its source named, or a project
convention explicitly labelled as such. Nothing is a remembered number.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Constants, with sources
# --------------------------------------------------------------------------- #

#: Bondi van der Waals radii, Angstrom. Bondi, J Phys Chem 68:441 (1964); the H value is the
#: 1.20 A from that paper rather than the later 1.09 A revision, matching MolProbity usage.
VDW = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80,
       "SE": 1.90, "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98}

#: A contact is a clash when the overlap exceeds this. MolProbity defines a serious clash as
#: >= 0.4 A overlap of van der Waals surfaces (Word et al., J Mol Biol 285:1735 (1999);
#: Chen et al., Acta Cryst D66:12 (2010)).
CLASH_OVERLAP = 0.4

#: Overlap at which two heavy atoms are genuinely interpenetrating rather than merely
#: crowded. Project convention, set from the measured reference below: the AlphaFold DB
#: model of human TrkB has 105 overlaps >= 0.4 A but its worst is far smaller than this,
#: so this threshold separates "imperfect but real" from "impossible".
SEVERE_OVERLAP = 0.9

#: Engh & Huber ideal geometry, Acta Cryst A47:392 (1991) / revised 2001. Mean +- sd.
IDEAL_BONDS = {
    ("N", "CA"): (1.459, 0.020),
    ("CA", "C"): (1.525, 0.021),
    ("C", "O"): (1.229, 0.019),
    ("C", "N"): (1.336, 0.023),   # peptide bond, inter-residue
}

#: Disulfide S-S distance. Surveys of protein structures give 2.03-2.05 A;
#: 2.05 +- 0.03 is the value used by validation tools.
SS_BOND = (2.05, 0.03)
#: Above this, two cysteine sulfurs are simply not bonded.
SS_MAX = 3.0

#: CA-CA across a cis peptide bond is ~2.9 A; trans is ~3.8 A. Cis peptide bonds are rare
#: (~0.03% for non-proline, ~5% for X-Pro; Weiss et al., Nat Struct Biol 5:676 (1998)).
CIS_CA_CA = 3.0


@dataclass
class Atom:
    chain: str
    resi: int
    resn: str
    name: str
    element: str
    x: float
    y: float
    z: float
    b: float | None = None

    def dist(self, o: "Atom") -> float:
        return math.dist((self.x, self.y, self.z), (o.x, o.y, o.z))


@dataclass
class ValidityReport:
    n_atoms: int = 0
    n_residues: int = 0
    clashes: list[dict] = field(default_factory=list)
    clashscore: float | None = None
    bond_outliers: list[dict] = field(default_factory=list)
    cis_peptides: list[dict] = field(default_factory=list)
    d_amino_acids: list[dict] = field(default_factory=list)
    disulfides: list[dict] = field(default_factory=list)
    free_cysteines: list[dict] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)

    @property
    def severe_clashes(self) -> list[dict]:
        """Overlaps beyond SEVERE_OVERLAP: atoms genuinely interpenetrating."""
        return [c for c in self.clashes if c["overlap"] >= SEVERE_OVERLAP]

    @property
    def physically_valid(self) -> bool:
        """Reject only for defects that are unambiguously impossible.

        The clash threshold here is CALIBRATED, not asserted. An earlier version failed a
        structure for having any clash at all, which rejected the genuine AlphaFold DB model
        of human TrkB (clashscore 16.24, 105 heavy-atom overlaps at the 0.4 A MolProbity
        criterion). Real deposited and predicted structures carry clashes at that criterion,
        especially when scored without hydrogens as here, so "any clash" is not a validity
        test — it is a quality metric. Only interpenetration beyond SEVERE_OVERLAP, wrong
        backbone bond lengths, and D-amino acids in a model built from an L sequence are
        treated as impossibilities.

        Cis peptides and free cysteines are reported but never fail a structure: both occur
        in real proteins.
        """
        return not (self.severe_clashes or self.bond_outliers or self.d_amino_acids)

    def quality_band(self) -> str:
        """Where the clashscore sits relative to measured references.

        Anchors measured in this project rather than recalled: the AlphaFold DB model of
        human TrkB (Q16620) scores 16.24 under this implementation, and Boltz-2 single-chain
        peptide models score 32-77. MolProbity's own guidance for experimental structures is
        that a clashscore under 2 is good at high resolution, but that scale is computed with
        hydrogens present and does not transfer directly to this heavy-atom-only measure.
        """
        c = self.clashscore
        if c is None:
            return "not measured"
        if c <= 5:
            return "clean"
        if c <= 20:
            return "comparable to a released AlphaFold DB model (TrkB scores 16.2 here)"
        if c <= 50:
            return "poor: more crowded than a released AlphaFold model"
        return "very poor"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["physically_valid"] = self.physically_valid
        for k in ("clashes", "bond_outliers", "cis_peptides", "d_amino_acids",
                  "disulfides", "free_cysteines"):
            d[f"n_{k}"] = len(getattr(self, k))
            d[k] = getattr(self, k)[:20]
        return d


# --------------------------------------------------------------------------- #
# Parsing: all atoms, not just C-alpha
# --------------------------------------------------------------------------- #

def parse_all_atoms(path: str | Path) -> list[Atom]:
    """Read every atom from an mmCIF or PDB file."""
    p = Path(path)
    text = p.read_text()
    if p.suffix.lower() in (".pdb", ".ent"):
        return _parse_pdb(text)
    return _parse_cif(text)


def _parse_pdb(text: str) -> list[Atom]:
    out: list[Atom] = []
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        try:
            out.append(Atom(
                chain=line[21].strip() or "A", resi=int(line[22:26]),
                resn=line[17:20].strip(), name=line[12:16].strip(),
                element=(line[76:78].strip() or line[12:16].strip()[:1]).upper(),
                x=float(line[30:38]), y=float(line[38:46]), z=float(line[46:54]),
                b=float(line[60:66]) if line[60:66].strip() else None))
        except (ValueError, IndexError):
            continue
    return out


def _parse_cif(text: str) -> list[Atom]:
    lines = text.splitlines()
    cols: list[str] = []
    rows: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("_atom_site."):
            cols.append(s.split(".", 1)[1].split()[0])
        elif cols and s.startswith(("ATOM", "HETATM")):
            rows.append(s)
        elif rows and (s.startswith("#") or s.startswith("loop_")):
            break
    if not cols or not rows:
        return []
    idx = {c: i for i, c in enumerate(cols)}

    def col(f: list[str], *names: str, default: str = "") -> str:
        for n in names:
            if n in idx and idx[n] < len(f):
                return f[idx[n]]
        return default

    out: list[Atom] = []
    for row in rows:
        f = row.split()
        if len(f) < len(cols):
            continue
        try:
            resi_raw = col(f, "auth_seq_id", "label_seq_id", default="0")
            out.append(Atom(
                chain=col(f, "auth_asym_id", "label_asym_id", default="A"),
                resi=int(resi_raw) if resi_raw not in (".", "?") else 0,
                resn=col(f, "label_comp_id", "auth_comp_id"),
                name=col(f, "label_atom_id").strip('"'),
                element=col(f, "type_symbol").upper(),
                x=float(col(f, "Cartn_x")), y=float(col(f, "Cartn_y")),
                z=float(col(f, "Cartn_z")),
                b=float(col(f, "B_iso_or_equiv", default="nan"))))
        except (ValueError, IndexError):
            continue
    return out


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

def _bonded(a: Atom, b: Atom) -> bool:
    """Exclude pairs that are bonded or 1-3 related, which are legitimately close."""
    if a.chain == b.chain:
        if a.resi == b.resi:
            return True
        if abs(a.resi - b.resi) == 1:
            first, second = (a, b) if a.resi < b.resi else (b, a)
            # Atoms bonded or 1-3 related across the peptide bond C(i)-N(i+1).
            if first.name in ("C", "O", "CA") and second.name in ("N", "CA"):
                return True
            # Proline: CD is bonded to the ring nitrogen, so C(i) and CD(i+1) are 1-3
            # related and sit ~2.4 A apart legitimately. Without this the gate reports a
            # clash at every X-Pro junction.
            if second.resn == "PRO" and second.name == "CD" and first.name in ("C", "O"):
                return True
    return False


def find_clashes(atoms: list[Atom], overlap: float = CLASH_OVERLAP) -> list[dict]:
    """Steric clashes by van der Waals overlap, using a uniform grid for O(n) neighbours."""
    heavy = [a for a in atoms if a.element and a.element != "H"]
    if not heavy:
        return []
    cell = 4.0
    grid: dict[tuple[int, int, int], list[Atom]] = {}
    for a in heavy:
        grid.setdefault((int(a.x // cell), int(a.y // cell), int(a.z // cell)), []).append(a)

    seen: set[tuple[int, int]] = set()
    out: list[dict] = []
    for (cx, cy, cz), bucket in grid.items():
        neigh: list[Atom] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neigh.extend(grid.get((cx + dx, cy + dy, cz + dz), []))
        for a in bucket:
            for b in neigh:
                if a is b:
                    continue
                key = (id(a), id(b)) if id(a) < id(b) else (id(b), id(a))
                if key in seen:
                    continue
                seen.add(key)
                if _bonded(a, b):
                    continue
                d = a.dist(b)
                lim = VDW.get(a.element, 1.7) + VDW.get(b.element, 1.7) - overlap
                # A genuine disulfide is not a clash.
                if a.element == "S" and b.element == "S" and d < SS_MAX:
                    continue
                if d < lim:
                    out.append({
                        "atom_1": f"{a.chain}/{a.resn}{a.resi}/{a.name}",
                        "atom_2": f"{b.chain}/{b.resn}{b.resi}/{b.name}",
                        "distance": round(d, 3),
                        "overlap": round(lim + overlap - d, 3)})
    return sorted(out, key=lambda c: -c["overlap"])


def check_bonds(atoms: list[Atom], sigma: float = 4.0) -> list[dict]:
    """Backbone bond lengths against Engh & Huber ideals, flagged beyond `sigma` sd."""
    by_res: dict[tuple[str, int], dict[str, Atom]] = {}
    for a in atoms:
        by_res.setdefault((a.chain, a.resi), {})[a.name] = a

    out: list[dict] = []
    keys = sorted(by_res)
    for i, k in enumerate(keys):
        r = by_res[k]
        for (n1, n2), (mu, sd) in IDEAL_BONDS.items():
            if (n1, n2) == ("C", "N"):
                continue
            if n1 in r and n2 in r:
                d = r[n1].dist(r[n2])
                if abs(d - mu) > sigma * sd:
                    out.append({"residue": f"{k[0]}/{r[n1].resn}{k[1]}", "bond": f"{n1}-{n2}",
                                "length": round(d, 3), "ideal": mu,
                                "deviation_sigma": round((d - mu) / sd, 1)})
        if i + 1 < len(keys):
            nxt = keys[i + 1]
            if nxt[0] == k[0] and nxt[1] == k[1] + 1:
                if "C" in r and "N" in by_res[nxt]:
                    mu, sd = IDEAL_BONDS[("C", "N")]
                    d = r["C"].dist(by_res[nxt]["N"])
                    if abs(d - mu) > sigma * sd:
                        out.append({"residue": f"{k[0]}/{k[1]}-{nxt[1]}", "bond": "C-N",
                                    "length": round(d, 3), "ideal": mu,
                                    "deviation_sigma": round((d - mu) / sd, 1)})
    return out


def check_chirality(atoms: list[Atom]) -> list[dict]:
    """Detect D-amino acids by the sign of the CA chiral volume.

    The signed volume (N-CA) . [(C-CA) x (CB-CA)] is POSITIVE for an L-amino acid and
    NEGATIVE for a D-amino acid. Glycine has no CB and is skipped.

    The sign was established empirically rather than asserted: the AlphaFold DB structure of
    human TrkB (Q16620), which is necessarily all-L, gives a positive volume for 769 of its
    822 residues. An earlier version of this function had the sign inverted and therefore
    reported 93.6% of a real protein as D-amino acids.
    """
    by_res: dict[tuple[str, int], dict[str, Atom]] = {}
    for a in atoms:
        by_res.setdefault((a.chain, a.resi), {})[a.name] = a
    out: list[dict] = []
    for (ch, ri), r in sorted(by_res.items()):
        if not {"N", "CA", "C", "CB"} <= set(r):
            continue
        ca = r["CA"]
        v = []
        for nm in ("N", "C", "CB"):
            a = r[nm]
            v.append((a.x - ca.x, a.y - ca.y, a.z - ca.z))
        cross = (v[1][1] * v[2][2] - v[1][2] * v[2][1],
                 v[1][2] * v[2][0] - v[1][0] * v[2][2],
                 v[1][0] * v[2][1] - v[1][1] * v[2][0])
        vol = sum(v[0][i] * cross[i] for i in range(3))
        if vol < 0:
            out.append({"residue": f"{ch}/{r['CA'].resn}{ri}",
                        "chiral_volume": round(vol, 3),
                        "note": "negative chiral volume: D-amino acid"})
    return out


def check_disulfides(atoms: list[Atom]) -> tuple[list[dict], list[dict]]:
    """Pair cysteine sulfurs and report both bonds and unpaired thiols."""
    sg = [a for a in atoms if a.name == "SG" and a.resn in ("CYS", "CYX")]
    bonds: list[dict] = []
    paired: set[int] = set()
    for i, a in enumerate(sg):
        for b in sg[i + 1:]:
            d = a.dist(b)
            if d < SS_MAX:
                mu, sd = SS_BOND
                bonds.append({
                    "cys_1": f"{a.chain}/{a.resi}", "cys_2": f"{b.chain}/{b.resi}",
                    "distance": round(d, 3),
                    "deviation_sigma": round((d - mu) / sd, 1),
                    "geometry_ok": abs(d - mu) <= 4 * sd})
                paired.add(id(a))
                paired.add(id(b))
    free = [{"residue": f"{a.chain}/{a.resi}"} for a in sg if id(a) not in paired]
    return bonds, free


def check_cis_peptides(atoms: list[Atom]) -> list[dict]:
    ca = {}
    for a in atoms:
        if a.name == "CA":
            ca[(a.chain, a.resi)] = a
    out = []
    for (ch, ri), a in sorted(ca.items()):
        b = ca.get((ch, ri + 1))
        if b and a.dist(b) < CIS_CA_CA:
            out.append({"residues": f"{ch}/{ri}-{ri+1}", "ca_ca": round(a.dist(b), 3),
                        "residue_2": b.resn,
                        "expected": "X-Pro cis is uncommon but real; non-Pro cis is rare"})
    return out


def validate(path: str | Path) -> ValidityReport:
    atoms = parse_all_atoms(path)
    rep = ValidityReport(n_atoms=len(atoms),
                         n_residues=len({(a.chain, a.resi) for a in atoms}))
    if not atoms:
        rep.checks_skipped.append("no atoms parsed")
        return rep

    has_sidechains = any(a.name not in ("N", "CA", "C", "O") for a in atoms)
    rep.clashes = find_clashes(atoms)
    rep.checks_run.append("steric clashes (Bondi vdW, MolProbity 0.4 A overlap)")
    heavy = sum(1 for a in atoms if a.element != "H")
    rep.clashscore = round(1000 * len(rep.clashes) / heavy, 2) if heavy else None

    rep.bond_outliers = check_bonds(atoms)
    rep.checks_run.append("backbone bond lengths (Engh & Huber, 4 sigma)")
    rep.cis_peptides = check_cis_peptides(atoms)
    rep.checks_run.append("cis peptide bonds")

    if has_sidechains:
        rep.d_amino_acids = check_chirality(atoms)
        rep.checks_run.append("CA chirality (signed chiral volume)")
        rep.disulfides, rep.free_cysteines = check_disulfides(atoms)
        rep.checks_run.append("disulfide pairing and S-S geometry")
    else:
        rep.checks_skipped.append(
            "chirality and disulfide checks: this file contains backbone atoms only, so "
            "side-chain stereochemistry cannot be assessed")
    return rep
