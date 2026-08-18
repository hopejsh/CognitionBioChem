#!/usr/bin/env python3
"""Record the public-database curation and its independent verification."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
cur = json.loads((REPO / "data" / "curated.json").read_text())
aud = json.loads((REPO / "data" / "residue_audit.json").read_text())

with mem.Ledger("curator", task="public database curation") as L:
    art = L.artifact(REPO / "data" / "curated.json", kind="data",
                     desc="verified chemistry, motif provenance and target records")
    for c in cur["chemistry"]["compounds"]:
        if not c.get("pubchem_cid"):
            continue
        L.claim(
            f"{c['name']}: verified structure is PubChem CID {c['pubchem_cid']}, formula "
            f"{c['molecular_formula']}, MW {c['molecular_weight']}, InChIKey "
            f"{c['inchikey']}, {c['stereocenters_defined']} defined stereocentres. "
            f"{c['notes'][:400]}",
            kind="evidence", source_type="database",
            source_ref=f"PubChem CID {c['pubchem_cid']}", confidence=0.9,
            tags=["chemistry", "curated"])

with mem.Ledger("residue-verifier", task="residue identity audit") as L:
    for f in aud["fabricated"]:
        L.claim(
            f"The dataset asserts {f['asserted']} for {f['target']}, but {f['uniprot']} "
            f"position {f['asserted'][3:]} is {f['actual']}. {f['note']}",
            kind="finding", source_type="database", source_ref=f["uniprot"],
            confidence=0.9, tags=["residues", "fabricated-data", f["target"].lower()])
    n = aud["numbering_convention_errors"][0]
    L.claim(f"{n['problem'].capitalize()}. {n['resolution']}", kind="finding",
            source_type="database", source_ref=n["uniprot"], confidence=0.9,
            tags=["residues", "scientific-error", "ache"])
    for v in aud["verified_correct"]:
        L.claim(
            f"Verified CORRECT against {v['uniprot']}: {v['target']} "
            f"{', '.join(v['residues'])}"
            + (f" ({v['convention']})" if v.get("convention") else ""),
            kind="evidence", source_type="database", source_ref=v["uniprot"],
            confidence=0.9, tags=["residues", "verified"])

with mem.Ledger("curation-verifier", task="verify the curation") as L:
    for name, v in zip(("chemistry", "motifs", "targets"), cur["verification"]):
        c = L.claim(
            f"Independent re-check of the {name} curation: {v['checked']} identifiers "
            f"retrieved and confirmed, {len(v['errors_found'])} errors found, "
            f"{len(v['unverifiable'])} claims unverifiable. Verdict {v['verdict']}.",
            kind="verdict", source_type="review", source_ref=f"curation:{name}",
            confidence=0.85, tags=["curation", "verification"])
        for e in v["errors_found"]:
            L.claim(f"[{e['severity']}] {e['item']} — claimed: {e['claimed'][:200]} / "
                    f"actual: {e['actual'][:300]}",
                    kind="finding", source_type="review", source_ref=f"curation:{name}",
                    confidence=0.85, tags=["curation", "correction", e["severity"]])

idx = mem.Index(); idx.sync(); mem.write_views(idx)
print(json.dumps(idx.stats(), indent=1)); idx.close()
