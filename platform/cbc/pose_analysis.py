#!/usr/bin/env python3
"""Score the pose-accuracy study: symmetry-corrected RMSD and physical validity.

Two details decide whether the numbers mean anything.

RMSD must be computed with RDKit `CalcRMS`, which is symmetry-corrected and computed IN
PLACE. PoseBusters' paper states it uses `GetBestRMS`; its code never has, and the difference
is not cosmetic — a pose translated 3.0 A scores 3.0 under CalcRMS and 0.0 under GetBestRMS,
because GetBestRMS re-superimposes and discards exactly the placement error being measured.

Bond orders must be assigned from the ligand's SMILES template before RMSD. Coordinates read
from a coordinate file carry no bond orders, and without them the molecular graph is wrong,
so the automorphism group used for symmetry correction is wrong too.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

from . import inference as inf, prespec as ps

RMSD_SUCCESS = 2.0


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval: correct near 0 and 1, where the normal interval is not."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for a 2x2 table, computed exactly."""
    from math import comb
    n = a + b + c + d
    row1, col1 = a + b, a + c
    obs = comb(row1, a) * comb(n - row1, c) / comb(n, col1)
    total = 0.0
    for i in range(max(0, col1 - (n - row1)), min(row1, col1) + 1):
        pr = comb(row1, i) * comb(n - row1, col1 - i) / comb(n, col1)
        if pr <= obs * (1 + 1e-9):
            total += pr
    return min(1.0, total)


def _ligand_copies(atoms, ligand_code: str) -> list[list]:
    """Group ligand atoms into separate copies.

    A crystal often contains the same ligand bound at several sites, or several copies in
    the asymmetric unit. Treating them as one molecule inflates the atom count — measured
    here as ref counts that were exact multiples of the prediction (56 vs 14, 60 vs 30,
    74 vs 37) — and makes any RMSD meaningless. Each copy is scored separately and the best
    match is taken, which is the standard convention for redocking against a multi-copy
    reference.
    """
    groups: dict = {}
    for a in atoms:
        if a.element == "H":
            continue
        if a.resn == ligand_code or a.resn.startswith("LIG"):
            groups.setdefault((a.chain, a.resi), []).append(a)
    return [v for v in groups.values() if len(v) >= 5]


def _mol_from_atoms(atoms, coords, smiles: str):
    """Build an RDKit molecule from atoms + coordinates, with bond orders from SMILES.

    A PDB block is used rather than a hand-written molblock: the molblock counts line is
    fixed-width and unforgiving, and an earlier hand-rolled version emitted a malformed
    header that RDKit rejected on every entry. PDB is tolerant and RDKit infers connectivity
    from geometry, after which the SMILES template supplies the true bond orders.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    lines = []
    for i, (a, xyz) in enumerate(zip(atoms, coords), 1):
        el = (a.element or a.name[:1]).capitalize()
        lines.append(
            f"HETATM{i:5d} {a.name[:4]:<4s} LIG A 900    "
            f"{xyz[0]:8.3f}{xyz[1]:8.3f}{xyz[2]:8.3f}  1.00  0.00          {el:>2s}")
    lines.append("END")
    raw = Chem.MolFromPDBBlock("\n".join(lines), sanitize=False, removeHs=False)
    if raw is None:
        return None
    template = Chem.MolFromSmiles(smiles)
    if template is None:
        return None
    template = Chem.RemoveHs(template)
    if template.GetNumAtoms() != raw.GetNumAtoms():
        return None
    try:
        return AllChem.AssignBondOrdersFromTemplate(template, raw)
    except Exception:  # noqa: BLE001
        return None


def score_entry(row: dict) -> dict:
    """Symmetry-corrected in-place RMSD between the aligned prediction and the crystal."""
    import numpy as np
    from rdkit.Chem.rdMolAlign import CalcRMS
    from . import physics

    aln = row.get("alignment") or {}
    if not aln.get("ok"):
        return {"scored": False, "reason": aln.get("reason", "no alignment")}

    pred_atoms_all = physics.parse_all_atoms(row["pred_cif"])
    ref_atoms_all = physics.parse_all_atoms(row["ref_cif"])
    pred_copies = _ligand_copies(pred_atoms_all, row["ligand"])
    ref_copies = _ligand_copies(ref_atoms_all, row["ligand"])
    if not pred_copies or not ref_copies:
        return {"scored": False,
                "reason": f"ligand copies: pred {len(pred_copies)}, ref {len(ref_copies)}"}

    # The alignment transform was fitted on the pocket; apply it to predicted coordinates.
    pred_all_xyz = np.array(aln["pred_ligand_xyz"])
    flat_pred = [a for grp in pred_copies for a in grp]
    if len(flat_pred) != len(pred_all_xyz):
        return {"scored": False,
                "reason": f"aligned coords {len(pred_all_xyz)} != ligand atoms {len(flat_pred)}"}
    xyz_of = {id(a): pred_all_xyz[i] for i, a in enumerate(flat_pred)}

    smiles = row["ligand_smiles"]
    best = None
    for pc in pred_copies:
        pm = _mol_from_atoms(pc, [xyz_of[id(a)] for a in pc], smiles)
        if pm is None:
            continue
        for rc in ref_copies:
            if len(rc) != len(pc):
                continue
            rm = _mol_from_atoms(rc, [[a.x, a.y, a.z] for a in rc], smiles)
            if rm is None:
                continue
            try:
                v = float(CalcRMS(pm, rm, symmetrizeConjugatedTerminalGroups=True,
                                  maxMatches=1000000))
            except Exception:  # noqa: BLE001
                continue
            if best is None or v < best:
                best = v
    if best is None:
        return {"scored": False,
                "reason": (f"no scorable copy pair (pred copies "
                           f"{[len(c) for c in pred_copies]}, ref copies "
                           f"{[len(c) for c in ref_copies]}, template "
                           f"{smiles[:40]})")}
    return {"scored": True, "rmsd": round(best, 3), "success": best <= RMSD_SUCCESS,
            "n_pred_copies": len(pred_copies), "n_ref_copies": len(ref_copies),
            "pocket_backbone_rmsd": aln.get("pocket_backbone_rmsd")}


def main(path: Path, study_id: str) -> int:
    payload = json.loads(Path(path).read_text())
    rows = payload["rows"]

    scored = []
    for r in rows:
        if not r.get("ok"):
            continue
        s = score_entry(r)
        scored.append({**{k: r[k] for k in
                          ("pdb_id", "stratum", "ligand", "ligand_heavy_atoms",
                           "chain_length", "seconds")}, **s})

    usable = [s for s in scored if s.get("scored")]
    strata: dict[str, list[dict]] = {}
    for s in usable:
        strata.setdefault(s["stratum"], []).append(s)

    def frac(rs):
        k = sum(1 for r in rs if r["success"])
        return k, len(rs), (k / len(rs) if rs else 0.0), _wilson(k, len(rs))

    rec = strata.get("recall", [])
    con = strata.get("congeneric_extension", [])
    k1, n1, f1, ci1 = frac(rec)
    k2, n2, f2, ci2 = frac(con)

    p_fisher = _fisher(k1, n1 - k1, k2, n2 - k2) if (n1 and n2) else None

    # H1 and H2 are threshold criteria on fractions; H3 is not evaluated at all when
    # PoseBusters is unavailable. The Fisher test comparing the two strata IS a real test, and
    # it was previously computed and reported beside a `p_holm` block built from 0/1 sentinels
    # that did not include it. It is now the family, and the family has one member.
    ruling = inf.decide(criteria={
        "H1_recall_accuracy": inf.Criterion(
            f1 > 0.5, round(f1, 4), "recall-stratum accuracy > 0.5"),
        "H2_interpolation_premium": inf.Criterion(
            (f1 - f2) >= 0.2, round(f1 - f2, 4),
            "recall minus congeneric-extension accuracy >= 0.2"),
    }, tests=({"H2_interpolation_premium_fisher": p_fisher}
              if (p_fisher is not None and 0.0 < p_fisher <= 1.0) else {}))
    ruling["verdicts"]["H3_physical_validity"] = "NOT_TESTED"

    all_rmsd = [s["rmsd"] for s in usable]
    report = {
        "study_id": study_id, "prespec_hash": payload["prespec_hash"],
        "n_observed": len(usable), "primary_metric": "fraction_rmsd_under_2A",
        "metrics": {
            "fraction_rmsd_under_2A": round(len([r for r in all_rmsd if r <= 2.0])
                                            / len(all_rmsd), 4) if all_rmsd else None,
            "median_rmsd": round(statistics.median(all_rmsd), 3) if all_rmsd else None,
            "mean_rmsd": round(statistics.fmean(all_rmsd), 3) if all_rmsd else None,
            "fraction_rmsd_under_5A": round(len([r for r in all_rmsd if r <= 5.0])
                                            / len(all_rmsd), 4) if all_rmsd else None,
            "pocket_backbone_rmsd": round(statistics.median(
                [s["pocket_backbone_rmsd"] for s in usable
                 if s.get("pocket_backbone_rmsd") is not None]), 3) if usable else None,
            "posebusters_pass_rate": None,
            "per_entry_rmsd": {s["pdb_id"]: s["rmsd"] for s in usable},
            "wall_clock_seconds_per_complex": inf.wall_clock(usable),
        },
        "strata": {
            "recall": {"k": k1, "n": n1, "fraction": round(f1, 4),
                       "wilson95": [round(c, 4) for c in ci1]},
            "congeneric_extension": {"k": k2, "n": n2, "fraction": round(f2, 4),
                                     "wilson95": [round(c, 4) for c in ci2]},
            "receptor_disjoint": {"k": 0, "n": 0,
                                  "note": "NOT CONSTRUCTIBLE — every post-cutoff receptor "
                                          "checked already had pre-cutoff PDB entries "
                                          "(13 to 1172)."},
        },
        "interpolation_premium": round(f1 - f2, 4),
        "fisher_p_recall_vs_congeneric": (round(p_fisher, 5)
                                          if p_fisher is not None else None),
        **ruling,
        "failures": [{k: r.get(k) for k in ("pdb_id", "stratum", "error")}
                     for r in rows if not r.get("ok")]
                    + [{"pdb_id": s["pdb_id"], "stratum": s["stratum"],
                        "error": s.get("reason")} for s in scored if not s.get("scored")],
    }
    report["prespec_audit"] = ps.verify_result(study_id, report)
    Path(path).write_text(json.dumps({**payload, "analysis": report}, indent=1))

    m = report["metrics"]
    print("=" * 92)
    print(f"STUDY {study_id}   prespec {payload['prespec_hash'][:12]}   n = {len(usable)} scored")
    print("=" * 92)
    print(f"\nPRIMARY  fraction within {RMSD_SUCCESS} A (all strata) = "
          f"{m['fraction_rmsd_under_2A']}")
    print(f"         median RMSD {m['median_rmsd']} A, mean {m['mean_rmsd']} A")
    print(f"         median pocket backbone RMSD {m['pocket_backbone_rmsd']} A")
    print("\nBY STRATUM")
    for name in ("recall", "congeneric_extension"):
        st = report["strata"][name]
        print(f"  {name:22s} {st['k']}/{st['n']} = {st['fraction']:.2f}   "
              f"Wilson 95% [{st['wilson95'][0]:.2f}, {st['wilson95'][1]:.2f}]")
    print(f"  {'receptor_disjoint':22s} — {report['strata']['receptor_disjoint']['note']}")
    print(f"\ninterpolation premium (recall - congeneric) = {report['interpolation_premium']}")
    print(f"Fisher exact p = {report['fisher_p_recall_vs_congeneric']}")
    print("\nPER-ENTRY RMSD")
    for s in sorted(usable, key=lambda x: x["rmsd"]):
        mark = "hit " if s["success"] else "MISS"
        print(f"  {s['pdb_id']:6s} {s['stratum']:22s} {s['rmsd']:8.3f} A  {mark}")
    if report["failures"]:
        print("\nFAILURES (recorded, excluded as pre-registered)")
        for f in report["failures"]:
            print(f"  {f['pdb_id']:6s} {str(f.get('stratum'))[:20]:22s} "
                  f"{str(f.get('error'))[:70]}")
    print("\nPRE-SPECIFIED VERDICTS")
    print(inf.format_verdicts(report))
    a = report["prespec_audit"]
    print(f"\nprespec audit: {'CONFIRMATORY' if a['confirmatory'] else 'DEVIATIONS'}")
    for d in a["deviations"]:
        print("  -", d)
    print("=" * 92)
    return 0
