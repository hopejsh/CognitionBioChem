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
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEST = REPO / "runs"
MANIFEST = DEST / "manifest.json"

#: Directories written by this project's Boltz-2 invocations.
SOURCES = [
    ("candidate-fold", Path("/tmp/cbc_boltz")),
    ("single-peptide", Path("/tmp/boltz2")),
    ("affinity", Path("/tmp/aff")),
]

#: Only the scientifically meaningful outputs. Boltz also writes a `processed/` tree of
#: tokenized inputs that is large, machine-specific and reconstructible from the YAML.
KEEP = {".cif", ".json", ".npz", ".yaml", ".pdb"}
SKIP_DIRS = {"processed", "__pycache__", "lightning_logs"}


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


def collect(root: Path) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in KEEP:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
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
            files = collect(job)
            if not files:
                continue
            rh = run_hash(files)
            if rh in known:
                print(f"  already held  {job.name}  {rh[:12]}")
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
    print(f"\n{len(manifest['runs'])} runs under custody, "
          f"{total_files} new files, {total_bytes/1e6:.1f} MB copied")
    print(f"manifest: {MANIFEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
