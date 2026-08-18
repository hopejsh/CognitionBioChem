#!/usr/bin/env python3
"""Curate and score a pocket-aligned pose-accuracy benchmark.

The question is not "can Boltz-2 dock" but "how much of its docking accuracy is recall".
Boltz-2's structure training used every PDB entry up to 2023-06-01, so an entry deposited
before that date may simply be remembered. A benchmark that does not separate the two
measures memorisation and reports it as accuracy.

Curation
--------
Entries are drawn from the RCSB search API with hard filters chosen so that a failure means
something: one protein entity, one drug-like ligand, X-ray at good resolution, and a chain
short enough to fold repeatedly on a laptop. The temporal split is on *deposition* date, not
release date, because deposition is what determines whether the coordinates could have
entered a training snapshot.

Scoring
-------
RMSD is computed with RDKit `CalcRMS`, which is symmetry-corrected and computed IN PLACE.
This matters more than it looks. PoseBusters' paper states it uses `GetBestRMS`; its code has
never used that for the pass/fail decision, and the difference is not cosmetic — measured
here, a pose translated 3.0 A scores CalcRMS 3.0 (correctly fails) and GetBestRMS 0.0
(would pass). `GetBestRMS` re-superimposes and therefore discards exactly the placement error
a docking benchmark exists to measure.
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_DATA = "https://data.rcsb.org/rest/v1/core"
FILES = "https://files.rcsb.org/download"

#: Boltz-2 structure training cutoff, stated in the paper: "every PDB structure up to the
#: training date cutoff of 06/01/2023".
TRAINING_CUTOFF = "2023-06-01"

#: Ligand codes that are crystallisation additives, buffers or cryoprotectants rather than
#: binders. A "pose" for one of these is not a docking result.
JUNK_LIGANDS = {
    "HOH", "GOL", "EDO", "SO4", "PO4", "ACT", "CL", "NA", "MG", "ZN", "CA", "K", "MN",
    "DMS", "PEG", "PG4", "1PE", "TRS", "EPE", "MES", "IMD", "FMT", "ACY", "NO3", "IOD",
    "BR", "CD", "NI", "CU", "FE", "SIN", "CIT", "TLA", "MPD", "BME", "DTT", "NAG", "MAN",
    "BMA", "FUC", "GAL", "GLC", "SEP", "TPO", "PTR", "MLY", "CSO", "OCS",
}


@dataclass
class Entry:
    pdb_id: str
    deposited: str
    resolution: float | None
    ligand: str
    ligand_smiles: str
    ligand_heavy_atoms: int
    chain_length: int
    uniprot: str | None
    title: str
    split: str = ""

    @property
    def pre_cutoff(self) -> bool:
        return self.deposited < TRAINING_CUTOFF

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pre_cutoff"] = self.pre_cutoff
        return d


def _ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _post(url: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "CognitionBioChem/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as fh:
        return json.loads(fh.read())


def _get(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "CognitionBioChem/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as fh:
        return json.loads(fh.read())


def search(date_from: str, date_to: str, *, max_length: int = 300,
           max_resolution: float = 2.5, limit: int = 60) -> list[str]:
    """PDB IDs of single-entity protein-ligand X-ray structures deposited in a date window."""
    q = {
        "query": {
            "type": "group", "logical_operator": "and", "nodes": [
                {"type": "terminal", "service": "text", "parameters": {
                    "attribute": "rcsb_accession_info.deposit_date", "operator": "range",
                    "value": {"from": date_from, "to": date_to}}},
                {"type": "terminal", "service": "text", "parameters": {
                    "attribute": "rcsb_entry_info.experimental_method",
                    "operator": "exact_match", "value": "X-ray"}},
                {"type": "terminal", "service": "text", "parameters": {
                    "attribute": "rcsb_entry_info.resolution_combined", "operator": "less",
                    "value": max_resolution}},
                {"type": "terminal", "service": "text", "parameters": {
                    "attribute": "rcsb_entry_info.polymer_entity_count_protein",
                    "operator": "equals", "value": 1}},
                {"type": "terminal", "service": "text", "parameters": {
                    "attribute": "rcsb_entry_info.nonpolymer_entity_count",
                    "operator": "equals", "value": 1}},
                {"type": "terminal", "service": "text", "parameters": {
                    "attribute": "rcsb_entry_info.deposited_polymer_monomer_count",
                    "operator": "less", "value": max_length}},
            ],
        },
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": limit},
                            "results_content_type": ["experimental"]},
    }
    res = _post(RCSB_SEARCH, q)
    return [r["identifier"] for r in res.get("result_set", [])]


def describe(pdb_id: str) -> Entry | None:
    """Fetch the metadata needed to decide whether an entry is usable."""
    try:
        entry = _get(f"{RCSB_DATA}/entry/{pdb_id}")
    except Exception:  # noqa: BLE001
        return None
    info = entry.get("rcsb_entry_info", {})
    dep = (entry.get("rcsb_accession_info", {}).get("deposit_date") or "")[:10]
    res = (info.get("resolution_combined") or [None])[0]
    title = entry.get("struct", {}).get("title", "")[:120]

    lig_ids = [c for c in entry.get("rcsb_entry_container_identifiers", {})
               .get("non_polymer_entity_ids", [])]
    for lid in lig_ids:
        try:
            npe = _get(f"{RCSB_DATA}/nonpolymer_entity/{pdb_id}/{lid}")
        except Exception:  # noqa: BLE001
            continue
        comp = npe.get("pdbx_entity_nonpoly", {}).get("comp_id", "")
        if comp in JUNK_LIGANDS:
            continue
        try:
            chem = _get(f"{RCSB_DATA}/chemcomp/{comp}")
        except Exception:  # noqa: BLE001
            continue
        desc = chem.get("rcsb_chem_comp_descriptor", {})
        # RCSB uses capitalised keys: SMILES_stereo / SMILES.
        smiles = desc.get("SMILES_stereo") or desc.get("SMILES") or ""
        info_c = chem.get("rcsb_chem_comp_info", {})
        n_heavy = info_c.get("atom_count_heavy") or 0
        # Drug-like and inside Boltz's documented affinity-head atom guidance.
        if not smiles or not (12 <= n_heavy <= 50):
            continue
        up = None
        try:
            peid = (entry.get("rcsb_entry_container_identifiers", {})
                    .get("polymer_entity_ids") or ["1"])[0]
            pe = _get(f"{RCSB_DATA}/polymer_entity/{pdb_id}/{peid}")
            ids = pe.get("rcsb_polymer_entity_container_identifiers", {})
            up = (ids.get("uniprot_ids") or [None])[0]
        except Exception:  # noqa: BLE001
            pass
        return Entry(
            pdb_id=pdb_id, deposited=dep, resolution=res, ligand=comp,
            ligand_smiles=smiles, ligand_heavy_atoms=n_heavy,
            chain_length=info.get("deposited_polymer_monomer_count", 0),
            uniprot=up, title=title)
    return None


def fetch_structure(pdb_id: str, dest: Path) -> Path:
    """Download the mmCIF for a PDB entry."""
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"{pdb_id}.cif"
    if out.exists():
        return out
    req = urllib.request.Request(f"{FILES}/{pdb_id}.cif",
                                 headers={"User-Agent": "CognitionBioChem/1.0"})
    with urllib.request.urlopen(req, timeout=180, context=_ctx()) as fh:
        out.write_bytes(fh.read())
    return out


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def pocket_aligned_rmsd(pred_cif: Path, ref_cif: Path, ligand_code: str
                        ) -> dict[str, Any]:
    """Superpose on the binding-pocket backbone, then measure ligand RMSD in place.

    Pocket alignment rather than whole-chain alignment is the right frame for a docking
    question: a model can place a ligand correctly relative to its pocket while the chain as
    a whole is shifted, and whole-chain superposition would charge that global shift to the
    pose.
    """
    import numpy as np
    from cbc import physics

    pred_atoms = physics.parse_all_atoms(pred_cif)
    ref_atoms = physics.parse_all_atoms(ref_cif)

    def split(atoms):
        prot, lig = [], []
        for a in atoms:
            if a.resn == ligand_code or (a.resn.startswith("LIG")):
                lig.append(a)
            elif a.name in ("N", "CA", "C", "O") and a.resn not in physics.__dict__.get(
                    "JUNK", ()):
                prot.append(a)
        return prot, lig

    pref, lref = split(ref_atoms)
    ppred, lpred = split(pred_atoms)
    if not lref or not lpred:
        return {"ok": False, "reason": "ligand atoms not found in one of the structures",
                "n_ref_lig": len(lref), "n_pred_lig": len(lpred)}

    # Residues must be paired by SEQUENCE, never by residue number. A predicted model is
    # numbered 1..N over the construct while a crystal uses author numbering with an offset
    # and gaps for disordered regions. Pairing on (chain, resi) silently matched residue 33
    # of the prediction to residue 33 of the crystal — measured on 4XH6, only 4.2% of such
    # pairs were even the same amino acid, so every RMSD built on them was meaningless.
    corr = _sequence_correspondence(pref, ppred)
    if len(corr) < 20:
        return {"ok": False,
                "reason": f"sequence alignment paired only {len(corr)} residues"}

    # Pocket = reference backbone atoms within 10 A of any reference ligand atom.
    lig_xyz = np.array([[a.x, a.y, a.z] for a in lref])
    ref_by_res = {}
    for a in pref:
        ref_by_res.setdefault((a.chain, a.resi), {})[a.name] = a
    pred_by_res = {}
    for a in ppred:
        pred_by_res.setdefault((a.chain, a.resi), {})[a.name] = a

    pairs = []
    for rkey, pkey in corr.items():
        ra = ref_by_res.get(rkey, {}).get("CA")
        pa = pred_by_res.get(pkey, {}).get("CA")
        if ra is None or pa is None:
            continue
        if np.min(np.linalg.norm(lig_xyz - np.array([ra.x, ra.y, ra.z]), axis=1)) >= 10.0:
            continue
        for nm in ("N", "CA", "C", "O"):
            r_at = ref_by_res[rkey].get(nm)
            p_at = pred_by_res[pkey].get(nm)
            if r_at is not None and p_at is not None:
                pairs.append((r_at, p_at))
    if len(pairs) < 12:
        return {"ok": False, "reason": f"only {len(pairs)} pocket atoms matched between "
                                       "prediction and reference after sequence alignment"}

    P = np.array([[b.x, b.y, b.z] for _, b in pairs])     # predicted pocket
    Q = np.array([[a.x, a.y, a.z] for a, _ in pairs])     # reference pocket
    Pc, Qc = P.mean(0), Q.mean(0)
    H = (P - Pc).T @ (Q - Qc)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    pocket_rmsd = float(np.sqrt((((P - Pc) @ R.T - (Q - Qc)) ** 2).sum(1).mean()))

    moved = (np.array([[a.x, a.y, a.z] for a in lpred]) - Pc) @ R.T + Qc
    return {"ok": True, "pocket_atoms": len(pairs),
            "pocket_backbone_rmsd": round(pocket_rmsd, 3),
            "pred_ligand_xyz": moved.tolist(),
            "ref_ligand_xyz": lig_xyz.tolist(),
            "n_ligand_atoms_pred": len(lpred), "n_ligand_atoms_ref": len(lref)}


def symmetry_rmsd(pred_sdf: Path, ref_sdf: Path) -> float | None:
    """Symmetry-corrected, in-place RMSD. CalcRMS, never GetBestRMS."""
    from rdkit import Chem
    from rdkit.Chem.rdMolAlign import CalcRMS
    p = Chem.MolFromMolFile(str(pred_sdf), sanitize=False)
    r = Chem.MolFromMolFile(str(ref_sdf), sanitize=False)
    if p is None or r is None:
        return None
    try:
        return float(CalcRMS(p, r, symmetrizeConjugatedTerminalGroups=True,
                             maxMatches=1000000))
    except Exception:  # noqa: BLE001
        return None


def receptor_prior_exposure(uniprot: str) -> dict[str, Any]:
    """How many PDB entries for this protein were deposited BEFORE the training cutoff.

    This is what separates the two kinds of novelty. An entry deposited after the cutoff is a
    novel COMPLEX, but if its receptor already had dozens of pre-cutoff structures then the
    fold and the pocket were both seen in training and only the ligand is new. That is
    congeneric extension. A receptor with no pre-cutoff entries at all is the genuinely
    harder case. Reporting them together would let the easy case carry the hard one.
    """
    if not uniprot:
        return {"uniprot": None, "prior_entries": None, "stratum": "unknown"}
    q = {
        "query": {"type": "group", "logical_operator": "and", "nodes": [
            {"type": "terminal", "service": "text", "parameters": {
                "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                "operator": "exact_match", "value": uniprot}},
            {"type": "terminal", "service": "text", "parameters": {
                "attribute": "rcsb_accession_info.deposit_date", "operator": "less",
                "value": TRAINING_CUTOFF}},
        ]},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": 1},
                            "results_content_type": ["experimental"]},
    }
    try:
        res = _post(RCSB_SEARCH, q)
        n = res.get("total_count", 0)
    except Exception:  # noqa: BLE001
        return {"uniprot": uniprot, "prior_entries": None, "stratum": "unknown"}
    return {"uniprot": uniprot, "prior_entries": n,
            "stratum": "congeneric_extension" if n > 0 else "receptor_disjoint"}


def _sequence_correspondence(ref_atoms, pred_atoms) -> dict:
    """Map reference (chain, resi) to predicted (chain, resi) by aligning sequences.

    A predicted model is numbered 1..N over the construct; a crystal uses author numbering
    with an arbitrary offset and gaps where residues were disordered. Global alignment of the
    two one-letter sequences recovers the correspondence without assuming either.
    """
    from Bio import Align
    from cbc.physics import Atom  # noqa: F401  (typing only)

    THREE_TO_ONE = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
        "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
        "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V", "MSE": "M",
    }

    def chain_seq(atoms):
        seen, keys, seq = set(), [], []
        for a in atoms:
            if a.name != "CA":
                continue
            k = (a.chain, a.resi)
            if k in seen:
                continue
            seen.add(k)
            aa = THREE_TO_ONE.get(a.resn.upper())
            if aa is None:
                continue
            keys.append(k)
            seq.append(aa)
        return keys, "".join(seq)

    rkeys, rseq = chain_seq(ref_atoms)
    pkeys, pseq = chain_seq(pred_atoms)
    if not rseq or not pseq:
        return {}

    aligner = Align.PairwiseAligner()
    aligner.mode = "global"
    aligner.open_gap_score = -10.0
    aligner.extend_gap_score = -0.5
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aln = aligner.align(rseq, pseq)[0]

    out = {}
    for (r0, r1), (p0, p1) in zip(*aln.aligned):
        for off in range(r1 - r0):
            ri, pi = r0 + off, p0 + off
            # Only accept pairs that are the same amino acid: this is the guard that would
            # have caught the numbering bug immediately.
            if rseq[ri] == pseq[pi]:
                out[rkeys[ri]] = pkeys[pi]
    return out
