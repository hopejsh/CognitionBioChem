#!/usr/bin/env python3
"""Take custody of prediction artefacts: copy them out of /tmp and content-address them.

The panel ranked this first, and it is the cheapest item on the slate. Every Boltz-2 run
performed in this project lives under /tmp, which macOS is entitled to delete on reboot, and
data/real_vs_hardcoded.json records no path for any structure — so no displayed pLDDT can be
traced back to the coordinate file that produced it.

This copies each run into runs/<sha256[:12]>/ and writes a manifest mapping candidate code ->
content hash -> files, so a number can be traced to bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEST = REPO / "runs"
MANIFEST = DEST / "manifest.json"

#: Every directory this project's Boltz-2 invocations write to.
#:
#: This list covered only the first three roots for a long time, while each new study added
#: its own /tmp constant and never appeared here. The result was that runs/ held 24 runs while
#: data/study_*.json published 148 absolute /tmp paths as the sole provenance for every DockQ,
#: RMSD, ipTM and PRODIGY number in studies #2, #6, #7, #9, #10 and #11 — paths that resolve to
#: nothing in a fresh clone and that macOS may clear on reboot. A repository whose central claim
#: is that a displayed number traces to the bytes that produced it cannot leave that gap open.
#:
#: Keep this list in step with the WORK/REFS constants in platform/studies/*.py. The check in
#: platform/tests/test_platform.py fails if a study names a root that is missing here, so the
#: two cannot drift apart silently again.
SOURCES = [
    ("candidate-fold", Path("/tmp/cbc_boltz")),
    ("single-peptide", Path("/tmp/boltz2")),
    ("affinity", Path("/tmp/aff")),
    ("pose-accuracy", Path("/tmp/cbc_pose")),
    ("pose-accuracy-reference", Path("/tmp/cbc_pose_refs")),
    ("peptide-interface", Path("/tmp/cbc_pep")),
    ("peptide-interface-reference", Path("/tmp/cbc_pep_refs")),
    ("candidate-screen", Path("/tmp/cbc_screen")),
    ("inference-variance", Path("/tmp/cbc_variance")),
    ("msa-specificity", Path("/tmp/cbc_msa10")),
    ("ache-affinity", Path("/tmp/ache_affinity")),
]

#: What custody means here, and what it deliberately does not cover.
#:
#: Coordinates (.cif), confidence summaries (.json) and the exact input (.yaml) are always
#: kept: every number this repository publishes is derived from those three, so keeping them
#: is what makes the provenance claim true rather than decorative.
#:
#: The matrix outputs are treated by what actually reads them, measured rather than assumed:
#:   pae_*.npz    read by Prediction.interface_pae, which produces the interface-PAE numbers
#:                published by the variance study. KEPT — but only for the study that
#:                publishes a PAE-derived quantity, because keeping it everywhere adds 108 MB
#:                that nothing in this repository ever opens.
#:   pde_*.npz    predicted DISTANCE error. Nothing in this repository reads it; the only
#:                globs in compute/structure.py are pae_* and plddt_*. 127 MB, DROPPED.
#:   plddt_*.npz  redundant with the mmCIF: Boltz writes per-residue pLDDT into the
#:                B_iso_or_equiv column, and the two agree to 5e-4 over 583 residues (the
#:                residual is the mmCIF's 3-decimal rounding). Tiny, so kept anyway.
#:
#: Retaining all matrices for all 247 runs would put 320 MB into a public repository to
#: preserve files no code path opens. Retaining none of them would break the traceability of a
#: number the README quotes. The split is stated here so a reader can see it is a decision
#: with a reason, not an oversight — and DROPPED_KINDS records it in the manifest too.
KEEP = {".cif", ".json", ".npz", ".yaml", ".pdb"}

#: pae matrices are kept only for kinds whose published numbers depend on them.
#:
#: This set was derived from a survey of ONE module (cbc/compute/structure.py) and was wrong
#: for that reason. Two other consumers read pae_*.npz: cbc/predictor.py:390 and
#: compare_real_vs_hardcoded.py:68 — and the latter produces the pae_min / pae_max published
#: for 22 candidates in data/real_vs_hardcoded.json, i.e. 44 numbers whose backing array the
#: policy had discarded. Anything added here must be justified by a grep over EVERY .npz
#: consumer in the repository, not one file; platform/tests/test_platform.py fails if a
#: published pae value has no retained array behind it.
PAE_KINDS = {"inference-variance", "candidate-fold"}

#: ...and for the NATIVE fold of a two-chain study, whose interface PAE is the one quantity
#: that says whether the peptide is confidently PLACED against the receptor rather than
#: merely folded. Study #7 showed interface PAE tracks DockQ, so discarding it left the
#: workbench able to show a 0.81 ipTM with nothing beside it that speaks to placement. Decoy
#: folds stay excluded: there are ten per candidate, they are read only through their ipTM,
#: and retaining 130 matrices to display none of them is storage without a consumer.
#:
#: This is forward-looking. The runs already under custody were rescued under the older
#: policy and their /tmp sources are gone, so the 13 complexes in data/structures.json have
#: no PAE and the page says so explicitly rather than leaving a blank panel.
PAE_NATIVE_KINDS = {"msa-specificity", "candidate-screen", "peptide-interface"}

SKIP_DIRS = {"processed", "__pycache__", "lightning_logs", "msa"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_hash(files: list[Path]) -> str:
    """Hash of the run = hash over each file's (relative name, content hash), sorted.

    Content-addressing the run rather than a single file means the identifier changes if any
    output changes, which is what makes it usable as a provenance key.
    """
    h = hashlib.sha256()
    for name, digest in sorted((f.name, sha256_file(f)) for f in files):
        h.update(name.encode())
        h.update(digest.encode())
    return h.hexdigest()


def collect(root: Path, kind: str) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in KEEP:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.name.startswith("pde_"):
            continue                                  # nothing reads it; see KEEP above
        if p.name.startswith("pae_") and kind not in PAE_KINDS:
            if not (kind in PAE_NATIVE_KINDS and root.name.endswith("_native")):
                continue
        out.append(p)
    return out


def main() -> int:
    DEST.mkdir(exist_ok=True)
    manifest: dict = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("Prediction artefacts rescued from /tmp and content-addressed. Each run "
                 "directory is named for the sha256 over its outputs, so a displayed value "
                 "can be traced to the exact bytes that produced it."),
        "retention_policy": {
            "always": [".cif", ".json", ".yaml", "plddt_*.npz"],
            "pae_npz_kept_for": sorted(PAE_KINDS),
            "dropped": {
                "pde_*.npz": "predicted distance error; no code path reads it",
                "pae_*.npz outside pae_npz_kept_for":
                    "no published number derives from it for those studies",
                "processed/, msa/, lightning_logs/":
                    "tokenised input cache, re-fetchable alignments, trainer logs"},
        },
        "runs": [],
    }
    if MANIFEST.exists():
        manifest["runs"] = json.loads(MANIFEST.read_text()).get("runs", [])
    known = {r["run_hash"] for r in manifest["runs"]}

    total_files = total_bytes = 0
    for kind, src in SOURCES:
        if not src.is_dir():
            print(f"  skip {src} (absent)")
            continue
        # Each immediate child of the source is one prediction job.
        jobs = [d for d in sorted(src.iterdir()) if d.is_dir()] or [src]
        for job in jobs:
            files = collect(job, kind)
            if not files:
                continue
            rh = run_hash(files)
            if rh in known:
                # Not a skip: a second job whose outputs hash identically is EVIDENCE. These
                # are the same-seed replicates, and their colliding content hash is the
                # determinism claim demonstrated rather than asserted. Record the alias so the
                # replicate's own /tmp path still resolves to bytes under custody, instead of
                # being dropped and leaving a dangling absolute path in the published study.
                held = next(r for r in manifest["runs"] if r["run_hash"] == rh)
                aliases = held.setdefault("identical_jobs", [])
                if job.name not in aliases and job.name != held["job"]:
                    aliases.append(job.name)
                for f in files:
                    rel = f.relative_to(job)
                    name = rel.name if len(rel.parts) == 1 else "_".join(rel.parts)
                    held.setdefault("alias_sources", {})[str(f)] = name
                print(f"  identical to {held['job'][:28]:30s} {job.name}  {rh[:12]}")
                continue
            target = DEST / rh[:12]
            target.mkdir(exist_ok=True)
            recorded = []
            for f in files:
                rel = f.relative_to(job)
                out = target / rel.name if len(rel.parts) == 1 else target / "_".join(rel.parts)
                shutil.copy2(f, out)
                size = out.stat().st_size
                recorded.append({"file": out.name, "sha256": sha256_file(out),
                                 "bytes": size, "source": str(f)})
                total_files += 1
                total_bytes += size
            manifest["runs"].append({
                "run_hash": rh,
                "short": rh[:12],
                "kind": kind,
                "job": job.name,
                "path": str(target.relative_to(REPO)),
                "n_files": len(recorded),
                "files": recorded,
            })
            known.add(rh)
            print(f"  rescued {job.name:34s} -> runs/{rh[:12]}  ({len(recorded)} files)")

    MANIFEST.write_text(json.dumps(manifest, indent=1))

    # Rewrite every published artefact's absolute /tmp path to the repo-relative custody path.
    # This was being done by hand after each run, which meant the custody guard's green state
    # was produced by an out-of-band edit rather than by the pipeline: a third party running
    # the studies and then rescue_runs would still be left with dangling absolute paths, and
    # the property the repository sells -- a displayed number traces to the bytes that made
    # it -- would hold only for whoever remembered the extra step.
    src2dst: dict[str, str] = {}
    for r in manifest["runs"]:
        for f in r["files"]:
            src2dst[f["source"]] = f"{r['path']}/{f['file']}"
        for src, name in (r.get("alias_sources") or {}).items():
            src2dst[src] = f"{r['path']}/{name}"

    rewritten = unresolved = 0
    for art in sorted((REPO / "data").glob("study_*.json")):
        body = art.read_text()
        new_body = re.sub(
            r'"(/tmp/[^"]*)"',
            lambda m: f'"{src2dst[m.group(1)]}"' if m.group(1) in src2dst else m.group(0),
            body)
        left = len(re.findall(r'"/tmp/[^"]*"', new_body))
        unresolved += left
        if new_body != body:
            art.write_text(new_body)
            rewritten += 1
    print(f"  rewrote absolute paths in {rewritten} study artefacts; "
          f"{unresolved} unresolved remain")
    print(f"\n{len(manifest['runs'])} runs under custody, "
          f"{total_files} new files, {total_bytes/1e6:.1f} MB copied")
    print(f"manifest: {MANIFEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
