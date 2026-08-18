#!/usr/bin/env python3
"""Parse REAL structure-predictor output.

This is the module CognitionBioChem was missing: it reads actual files produced by a
structure predictor and surfaces the actual confidence metrics, instead of synthesizing
them. It computes nothing it cannot read from the file.

Supported inputs
----------------
AlphaFold Server / AlphaFold 3
    <job>_model_<n>.cif                  coordinates; B-factor column carries pLDDT
    <job>_full_data_<n>.json             atom_plddts, pae, token_chain_ids, token_res_ids
    <job>_summary_confidences_<n>.json   ptm, iptm, ranking_score, has_clash, ...
AlphaFold Protein Structure Database
    AF-<ACC>-F1-model_v*.cif
    AF-<ACC>-F1-predicted_aligned_error_v*.json
Boltz-1 / Boltz-2
    confidence_<name>_model_<n>.json     confidence_score, ptm, iptm, complex_plddt
    plddt_<name>_model_<n>.npz / pae_<name>_model_<n>.npz
Chai-1
    scores.model_idx_<n>.npz             aggregate_score, ptm, iptm, per_chain_pae, plddt

Nothing here requires a GPU, model weights, or a licence: it reads output somebody else
produced. That is deliberate -- it decouples "can display real results" from "can generate
real results", which is the only way this platform becomes honest before a GPU exists.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# AlphaFold's four published confidence bands (same cut points AFDB uses).
PLDDT_BANDS = [
    (90.0, 100.0, "Very high", "#0053D6"),
    (70.0, 90.0, "Confident", "#65CBF3"),
    (50.0, 70.0, "Low", "#FFDB13"),
    (0.0, 50.0, "Very low", "#FF7D45"),
]

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
    "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
    "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "MSE": "M", "SEC": "U", "PYL": "O",
}

CA_CA_IDEAL = 3.80  # Angstrom, virtual bond length between consecutive C-alpha atoms


class PredictorError(RuntimeError):
    pass


@dataclass
class Residue:
    chain: str
    seq_id: int
    name3: str
    aa: str
    x: float
    y: float
    z: float
    plddt: float | None = None


@dataclass
class LigandAtom:
    """A non-polymer atom. Kept separately from `residues` because a ligand has no
    C-alpha and no residue index, so folding it into the polymer list would corrupt
    both the sequence and the Ca-Ca geometry audit."""

    chain: str
    comp: str
    atom: str
    element: str
    x: float
    y: float
    z: float
    plddt: float | None = None


@dataclass
class Prediction:
    """Everything read from a real prediction. Every field traces to a file."""

    source: str                       # which format was detected
    files: dict[str, str] = field(default_factory=dict)
    residues: list[Residue] = field(default_factory=list)
    ligands: list[LigandAtom] = field(default_factory=list)
    chains: list[str] = field(default_factory=list)
    plddt: list[float] = field(default_factory=list)       # per residue
    pae: list[list[float]] | None = None                   # token x token, Angstrom
    pae_max: float | None = None
    ptm: float | None = None
    iptm: float | None = None
    ranking_score: float | None = None
    has_clash: bool | None = None
    fraction_disordered: float | None = None
    chain_pair_pae_min: list[list[float]] | None = None
    warnings: list[str] = field(default_factory=list)

    # -- derived, clearly labelled as derived ------------------------------------ #
    @property
    def sequence(self) -> str:
        return "".join(r.aa for r in self.residues)

    @property
    def mean_plddt(self) -> float | None:
        return round(statistics.fmean(self.plddt), 2) if self.plddt else None

    def band_fractions(self) -> dict[str, float]:
        if not self.plddt:
            return {}
        out: dict[str, float] = {}
        for lo, hi, label, _ in PLDDT_BANDS:
            n = sum(1 for v in self.plddt if lo <= v < hi or (hi == 100.0 and v == 100.0))
            out[label] = round(n / len(self.plddt), 4)
        return out

    def low_confidence_regions(self, threshold: float = 70.0, min_len: int = 3
                               ) -> list[dict[str, Any]]:
        """Contiguous runs below `threshold` -- typically linkers and disordered tails."""
        runs, start = [], None
        for i, v in enumerate(self.plddt):
            if v < threshold and start is None:
                start = i
            elif v >= threshold and start is not None:
                if i - start >= min_len:
                    runs.append((start, i - 1))
                start = None
        if start is not None and len(self.plddt) - start >= min_len:
            runs.append((start, len(self.plddt) - 1))
        return [{"start_index": a, "end_index": b, "length": b - a + 1,
                 "sequence": self.sequence[a:b + 1],
                 "mean_plddt": round(statistics.fmean(self.plddt[a:b + 1]), 2)}
                for a, b in runs]

    def interface_pae(self, chain_a: str, chain_b: str) -> dict[str, Any] | None:
        """Mean and minimum PAE across a chain pair -- the metric that actually matters
        for a binder, and the one the original platform never had."""
        if self.pae is None:
            return None
        ia = [i for i, r in enumerate(self.residues) if r.chain == chain_a]
        ib = [i for i, r in enumerate(self.residues) if r.chain == chain_b]
        if not ia or not ib or max(ia + ib) >= len(self.pae):
            return None
        vals = [self.pae[i][j] for i in ia for j in ib] + \
               [self.pae[j][i] for i in ia for j in ib]
        return {"chain_pair": f"{chain_a}-{chain_b}",
                "mean_pae": round(statistics.fmean(vals), 2),
                "min_pae": round(min(vals), 2),
                "n_pairs": len(vals)}

    def geometry_check(self) -> dict[str, Any]:
        """Are consecutive C-alpha atoms ~3.8 A apart? A real structure passes; a
        synthetic curve does not. This is the check that distinguishes the two."""
        d: list[float] = []
        for a, b in zip(self.residues, self.residues[1:]):
            if a.chain != b.chain:
                continue
            d.append(math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)))
        if not d:
            return {"checked": False}
        outliers = [v for v in d if abs(v - CA_CA_IDEAL) > 0.5]
        return {
            "checked": True, "n_bonds": len(d),
            "mean_ca_ca": round(statistics.fmean(d), 3),
            "stdev_ca_ca": round(statistics.pstdev(d), 3) if len(d) > 1 else 0.0,
            "min": round(min(d), 3), "max": round(max(d), 3),
            "outliers_beyond_0.5A": len(outliers),
            "plausible_protein": len(outliers) / len(d) < 0.05,
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["residues"] = len(self.residues)
        d["ligand_atoms"] = len(self.ligands)
        d["ligand_comps"] = sorted({l.comp for l in self.ligands})
        d["sequence"] = self.sequence
        d["mean_plddt"] = self.mean_plddt
        d["band_fractions"] = self.band_fractions()
        d["geometry"] = self.geometry_check()
        if self.pae is not None:
            d["pae"] = f"<{len(self.pae)}x{len(self.pae[0])} matrix>"
        return d


# --------------------------------------------------------------------------- #
# mmCIF
# --------------------------------------------------------------------------- #

def parse_mmcif(path: str | Path) -> tuple[list[Residue], list[str], list[LigandAtom]]:
    """Minimal mmCIF atom_site reader. Takes one CA atom per residue and reads pLDDT
    from the B-factor column, which is where AlphaFold writes it."""
    path = Path(path)
    text = path.read_text()
    lines = text.splitlines()

    cols: list[str] = []
    rows: list[str] = []
    in_loop = False
    for line in lines:
        s = line.strip()
        if s.startswith("loop_"):
            cols, in_loop = [], True
            continue
        if in_loop and s.startswith("_atom_site."):
            cols.append(s.split(".", 1)[1].split()[0])
            continue
        if cols and s and not s.startswith("_") and not s.startswith("#"):
            if s.startswith(("ATOM", "HETATM")):
                rows.append(s)
                continue
            if rows:
                break
        if s.startswith("#") and rows:
            break
        if in_loop and s.startswith("_") and not s.startswith("_atom_site."):
            if not rows:
                cols, in_loop = [], False

    if not cols or not rows:
        raise PredictorError(f"no _atom_site loop found in {path.name}")

    idx = {c: i for i, c in enumerate(cols)}
    need = ["group_PDB", "label_atom_id", "label_comp_id", "Cartn_x", "Cartn_y", "Cartn_z"]
    missing = [c for c in need if c not in idx]
    if missing:
        raise PredictorError(f"mmCIF missing required columns: {missing}")

    chain_key = next((k for k in ("auth_asym_id", "label_asym_id") if k in idx), None)
    seq_key = next((k for k in ("auth_seq_id", "label_seq_id") if k in idx), None)
    b_key = next((k for k in ("B_iso_or_equiv", "pLDDT") if k in idx), None)

    residues: list[Residue] = []
    ligands: list[LigandAtom] = []
    seen: set[tuple[str, int]] = set()
    for row in rows:
        f = row.split()
        if len(f) < len(cols):
            continue

        # Ligand atoms are HETATM rows and have no CA, so a CA-only filter discards them
        # entirely. That silently dropped all 18 atoms of the huperzine model before any
        # check could run, which made every ligand pose invisible to the platform.
        if f[idx["group_PDB"]] == "HETATM" and f[idx["label_comp_id"]] != "HOH":
            try:
                ligands.append(LigandAtom(
                    chain=f[idx[chain_key]] if chain_key else "L",
                    comp=f[idx["label_comp_id"]],
                    atom=f[idx["label_atom_id"]].strip('"'),
                    element=f[idx["type_symbol"]] if "type_symbol" in idx else "",
                    x=float(f[idx["Cartn_x"]]), y=float(f[idx["Cartn_y"]]),
                    z=float(f[idx["Cartn_z"]]),
                    plddt=float(f[idx[b_key]]) if b_key else None))
            except ValueError:
                pass
            continue

        if f[idx["label_atom_id"]].strip('"') != "CA":
            continue
        comp = f[idx["label_comp_id"]]
        chain = f[idx[chain_key]] if chain_key else "A"
        try:
            seq_id = int(f[idx[seq_key]]) if seq_key else len(residues) + 1
        except ValueError:
            seq_id = len(residues) + 1
        if (chain, seq_id) in seen:
            continue
        seen.add((chain, seq_id))
        try:
            plddt = float(f[idx[b_key]]) if b_key else None
        except ValueError:
            plddt = None
        residues.append(Residue(
            chain=chain, seq_id=seq_id, name3=comp,
            aa=THREE_TO_ONE.get(comp.upper(), "X"),
            x=float(f[idx["Cartn_x"]]), y=float(f[idx["Cartn_y"]]),
            z=float(f[idx["Cartn_z"]]), plddt=plddt))

    chains = sorted({r.chain for r in residues})
    return residues, chains, ligands


# --------------------------------------------------------------------------- #
# Format detection and loading
# --------------------------------------------------------------------------- #

def load(directory: str | Path) -> Prediction:
    """Detect the predictor format in `directory` and load it."""
    d = Path(directory)
    if not d.is_dir():
        raise PredictorError(f"{d} is not a directory")

    cifs = sorted(list(d.glob("*.cif")) + list(d.glob("*.mmcif")))
    if not cifs:
        raise PredictorError(
            f"no .cif file in {d}. Expected output from AlphaFold Server, AlphaFold DB, "
            "Boltz or Chai. Nothing can be displayed without real coordinates.")
    cif = cifs[0]

    full = sorted(d.glob("*full_data*.json"))
    summary = sorted(d.glob("*summary_confidences*.json"))
    afdb_pae = sorted(d.glob("*predicted_aligned_error*.json"))
    boltz_conf = sorted(d.glob("confidence_*.json"))

    if full or summary:
        source = "alphafold3"
    elif afdb_pae:
        source = "alphafold_db"
    elif boltz_conf:
        source = "boltz"
    else:
        source = "mmcif_only"

    residues, chains, ligands = parse_mmcif(cif)
    pred = Prediction(source=source, residues=residues, chains=chains,
                      ligands=ligands, files={"model": str(cif)})
    pred.plddt = [r.plddt if r.plddt is not None else float("nan") for r in residues]

    if full:
        _load_af3_full(pred, full[0])
    if summary:
        _load_af3_summary(pred, summary[0])
    if afdb_pae:
        _load_afdb_pae(pred, afdb_pae[0])
    if boltz_conf:
        _load_boltz(pred, boltz_conf[0], d)

    _sanity(pred)
    return pred


def _load_af3_full(pred: Prediction, path: Path) -> None:
    data = json.loads(path.read_text())
    pred.files["full_data"] = str(path)
    if "pae" in data:
        pred.pae = data["pae"]
        pred.pae_max = max(max(row) for row in pred.pae) if pred.pae else None
    atom_plddts = data.get("atom_plddts")
    token_res = data.get("token_res_ids")
    token_chain = data.get("token_chain_ids")
    if atom_plddts and token_res and len(atom_plddts) == len(token_res):
        # Aggregate per-atom pLDDT to per-residue by mean, which is what AFDB's
        # B-factor column already contains -- do it only if the cif lacked values.
        if all(math.isnan(v) for v in pred.plddt):
            buckets: dict[tuple[Any, Any], list[float]] = {}
            for v, rid, ch in zip(atom_plddts, token_res,
                                  token_chain or ["A"] * len(token_res)):
                buckets.setdefault((ch, rid), []).append(v)
            pred.plddt = [round(statistics.fmean(buckets[(r.chain, r.seq_id)]), 2)
                          if (r.chain, r.seq_id) in buckets else float("nan")
                          for r in pred.residues]


def _load_af3_summary(pred: Prediction, path: Path) -> None:
    data = json.loads(path.read_text())
    pred.files["summary"] = str(path)
    pred.ptm = data.get("ptm")
    pred.iptm = data.get("iptm")
    pred.ranking_score = data.get("ranking_score")
    pred.has_clash = bool(data["has_clash"]) if "has_clash" in data else None
    pred.fraction_disordered = data.get("fraction_disordered")
    pred.chain_pair_pae_min = data.get("chain_pair_pae_min")


def _load_afdb_pae(pred: Prediction, path: Path) -> None:
    data = json.loads(path.read_text())
    pred.files["pae"] = str(path)
    entry = data[0] if isinstance(data, list) else data
    if "predicted_aligned_error" in entry:
        pred.pae = entry["predicted_aligned_error"]
        pred.pae_max = entry.get("max_predicted_aligned_error") or (
            max(max(r) for r in pred.pae) if pred.pae else None)


def _load_boltz(pred: Prediction, path: Path, d: Path) -> None:
    data = json.loads(path.read_text())
    pred.files["confidence"] = str(path)
    pred.ptm = data.get("ptm")
    pred.iptm = data.get("iptm")
    pred.ranking_score = data.get("confidence_score")
    try:
        import numpy as np
        for p in d.glob("pae_*.npz"):
            pred.pae = np.load(p)["pae"].tolist()
            pred.pae_max = float(max(max(r) for r in pred.pae))
            pred.files["pae"] = str(p)
            break
        if all(math.isnan(v) for v in pred.plddt):
            for p in d.glob("plddt_*.npz"):
                arr = np.load(p)["plddt"]
                vals = (arr * 100.0) if float(arr.max()) <= 1.0 else arr
                pred.plddt = [round(float(v), 2) for v in vals]
                pred.files["plddt"] = str(p)
                break
    except ImportError:
        pred.warnings.append("numpy unavailable; Boltz .npz arrays not loaded")


def _sanity(pred: Prediction) -> None:
    """Flag anything that does not look like genuine predictor output."""
    if not pred.residues:
        pred.warnings.append("no residues parsed from the coordinate file")
        return
    if all(math.isnan(v) for v in pred.plddt):
        pred.warnings.append(
            "no pLDDT found: the B-factor column is empty and no confidence file was "
            "supplied. Confidence cannot be displayed for this prediction.")
        pred.plddt = []
    else:
        pred.plddt = [v for v in pred.plddt if not math.isnan(v)]
        if max(pred.plddt) <= 1.0:
            pred.plddt = [round(v * 100, 2) for v in pred.plddt]
            pred.warnings.append("pLDDT appeared to be on a 0-1 scale; rescaled to 0-100")
        if min(pred.plddt) > 85.0:
            pred.warnings.append(
                f"minimum pLDDT is {min(pred.plddt):.1f}. Genuine predictions almost "
                "always show low-confidence termini and linkers; a floor this high is "
                "worth checking against the source file.")
    if pred.pae is not None:
        n = len(pred.pae)
        if any(len(row) != n for row in pred.pae):
            pred.warnings.append("PAE matrix is not square")
        # Asymmetry is only diagnostic for a SINGLE chain. The original 12.0 A threshold was
        # derived from single-chain output and flags every genuine complex as synthetic:
        # measured 16.8 A on a real 1YCR two-chain prediction and 19.2 A on AChE + peptide.
        # Across a chain boundary, large |PAE_ij - PAE_ji| is the expected signature of a
        # small chain docked against a large one, not evidence of fabrication.
        #
        # So the check now runs only within a chain, where the original reasoning holds, and
        # reports inter-chain asymmetry separately as information rather than as a warning.
        chain_of = [r.chain for r in pred.residues]
        lim = min(n, 60, len(chain_of))
        intra = [abs(pred.pae[i][j] - pred.pae[j][i])
                 for i in range(lim) for j in range(lim)
                 if chain_of[i] == chain_of[j]]
        asym = max(intra, default=0.0)
        if asym > 12.0:
            pred.warnings.append(
                f"PAE is strongly asymmetric WITHIN a chain (max |PAE_ij - PAE_ji| = "
                f"{asym:.1f} A). Within a single chain real PAE is only mildly asymmetric, "
                "so this suggests the matrix was not produced by a predictor.")
    geo = pred.geometry_check()
    if geo.get("checked") and not geo["plausible_protein"]:
        pred.warnings.append(
            f"C-alpha geometry is not protein-like: mean Ca-Ca {geo['mean_ca_ca']} A "
            f"(expected {CA_CA_IDEAL}), {geo['outliers_beyond_0.5A']}/{geo['n_bonds']} "
            "bonds outside +/-0.5 A. These coordinates are not a folded polypeptide.")


def fetch_alphafold_db(accession: str, out_dir: str | Path) -> Path:
    """Download a real AlphaFold DB entry (coordinates + PAE) for end-to-end testing.

    Requires network but no GPU, no weights and no licence key, which makes it the
    cheapest way to prove the parser works against genuine output.
    """
    import urllib.request
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    api = f"https://alphafold.ebi.ac.uk/api/prediction/{accession}"
    with urllib.request.urlopen(api, timeout=60) as fh:
        meta = json.loads(fh.read())
    if not meta:
        raise PredictorError(f"no AlphaFold DB entry for {accession}")
    entry = meta[0]
    for key, suffix in (("cifUrl", ".cif"), ("paeDocUrl", "_pae.json")):
        url = entry.get(key)
        if not url:
            continue
        dest = out / f"AF-{accession}{suffix}"
        if suffix == "_pae.json":
            dest = out / f"AF-{accession}-predicted_aligned_error.json"
        with urllib.request.urlopen(url, timeout=120) as fh:
            dest.write_bytes(fh.read())
    return out
