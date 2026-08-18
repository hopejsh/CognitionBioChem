#!/usr/bin/env python3
"""Seed CBC-Memory with what has been established so far in this engagement.

Only facts independently verified by reading the source or running code are written
here. Panel findings arrive separately, through the review ingest path, carrying their
own verification status.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    # ---- Architecture decisions for the memory system itself ----------------- #
    with mem.Ledger("architect", task="memory system design") as L:
        survey = L.claim(
            "A survey of 2015-2026 agent-memory literature (385 papers across 6 areas: "
            "LLM agent memory, retrieval indexing, graph/temporal memory, consolidation "
            "theory, storage systems, scientific provenance) scored 12 candidate "
            "architectures on concurrency, provenance, multi-hop recall, local cost and "
            "implementation risk.",
            kind="evidence", source_type="workflow", source_ref="wf_ef7b2339-a77",
            confidence=0.9, tags=["memory", "literature"])

        decision = L.claim(
            "Selected architecture: an append-only JSONL provenance ledger as the single "
            "source of truth, plus a fully derived, disposable SQLite index (FTS5 BM25 + "
            "sparse hashed TF-IDF cosine, fused by RRF k=60). Coupling is strictly "
            "one-directional: the ledger has all authority, the index has none.",
            kind="decision", source_type="reasoning", source_ref="memory/DESIGN.md",
            confidence=0.85, tags=["memory", "architecture"])
        L.edge(decision, "DERIVES_FROM", survey)

        rejected = L.claim(
            "The v1 memory specification was rejected by all three adversarial critics "
            "(concurrency, retrieval, simplicity) with 18 fatal flaws. Root cause: the "
            "spec-writing prompt demanded ten mandatory sections and 'complete, "
            "unambiguous' coverage, which rewarded machinery over minimality and produced "
            "7 file streams, ~30 free parameters and a rebuild-on-every-read loop for a "
            "corpus of 10^3-10^4 items.",
            kind="finding", source_type="workflow", source_ref="memory/SPEC_draft.md",
            confidence=0.95, tags=["memory", "process", "lesson"])
        L.edge(decision, "SUPERSEDES", rejected)

        for text, ref in [
            ("v1 idempotency was defeated by embedding t_valid/ts_author in the content "
             "key, so every retry produced a distinct id. v2 excludes all timestamps, run "
             "ids and confidence from identity.", "F#1"),
            ("v1 appended a READ event on every search while rebuilding whenever any "
             "ledger file changed, so reading was a write and every query rebuilt the "
             "whole index. v2's read path never touches the ledger.", "F#3"),
            ("v1 tracked freshness by (size, mtime, inode), so a process killed mid-write "
             "left its last record permanently invisible behind a 'fresh' stamp. v2 "
             "records the consumed byte offset and ignores a partial trailing line.", "F#8"),
            ("v1 multiplied RRF by four priors spanning 27.8x against RRF's own 4.3x, so "
             "the worst-relevance document outranked the best by 6.5x. v2 uses pure RRF "
             "with a capped, off-by-default boost.", "R-F#2"),
            ("v1's SAME_AS auto-merge collapsed semantic opposites: 'is a potent "
             "inhibitor' vs 'is not a potent inhibitor' scored cosine 0.940 and Jaccard "
             "0.917 and would be merged into fake consensus. v2 has no SAME_AS relation "
             "and no automatic merge.", "R-F#4"),
            ("On macOS/APFS os.fsync returns before data reaches stable storage: measured "
             "0.031 ms/rec versus 3.81 ms/rec for fcntl F_FULLFSYNC, a 125x gap. v2 uses "
             "F_FULLFSYNC on Darwin.", "F#9"),
        ]:
            c = L.claim(text, kind="requirement", source_type="review",
                        source_ref=f"critic:{ref}", confidence=0.9,
                        tags=["memory", "regression"])
            L.edge(c, "DERIVES_FROM", rejected)

    # ---- Independent verification of the memory implementation --------------- #
    with mem.Ledger("mem-verifier", task="verify memory implementation") as L:
        ev = L.claim(
            "memory/tests/test_mem.py passes 74/74 with exit code 0. It includes 16 "
            "concurrent writer processes writing 3200 claims with zero loss and zero "
            "malformed lines, incremental ingest, torn-tail recovery, byte-stable view "
            "generation, and a regression test for each v1 critic finding.",
            kind="measurement", source_type="test", source_ref="memory/tests/test_mem.py",
            confidence=0.95, tags=["memory", "verification"])
        idx = mem.Index()
        idx.sync()
        for row in idx.db.execute(
                "SELECT id FROM item WHERE agent='architect' AND kind='decision'"):
            L.verify(row["id"], "Implementation exists and its regression suite passes.",
                     evidence=[ev])
        idx.close()

    # ---- Facts about CognitionBioChem verified by reading the source --------- #
    with mem.Ledger("code-auditor", task="direct source inspection") as L:
        for text, ref, tags in [
            ("AlphaFold3 does not appear anywhere in the CognitionBioChem codebase: no "
             "inference call, no model weights, no API request, and no parser for any AF3 "
             "output format (mmCIF, ranking_scores.csv, confidences.json). The only "
             "AlphaFold presence is a hyperlink to alphafoldserver.com and a "
             "copy-FASTA-to-clipboard button.",
             "app.js", ["af3", "fabricated-data"]),
            ("The chart labelled 'AlphaFold3 pLDDT Score' is generated by the closed-form "
             "expression 93 + sin(i*0.4)*4 + (charCode % 5)*0.5. It is a sine wave "
             "parameterized by residue index and ASCII character code, not a confidence "
             "output.",
             "app.js:791", ["af3", "fabricated-data", "plddt"]),
            ("The PAE heatmap is generated by abs(i-j)*0.4 + (charCode % 4)*0.3, a linear "
             "ramp in distance from the diagonal. A real PAE matrix shows domain block "
             "structure and inter-chain blocks, which this cannot produce.",
             "app.js:850", ["af3", "fabricated-data", "pae"]),
            ("The 3D viewer builds a Catmull-Rom tube through points at "
             "radius = 6 + (charCode % 5) * 0.8 with angle from the residue index. The "
             "source comment above it reads 'REAL FASTA SEQUENCE PARSING & 3D BACKBONE "
             "TOPOLOGY GENERATION'. No protein geometry is involved: backbone conformation "
             "is set by phi/psi angles and hydrogen bonding, not by ASCII codes.",
             "app.js:707-732", ["af3", "fabricated-data", "structure"]),
            ("Residue colouring in the 3D viewer maps single amino-acid letters to pLDDT "
             "confidence bands (G/S rendered as high, P/D as low). Amino acid identity "
             "does not determine local prediction confidence.",
             "app.js:747-749", ["fabricated-data", "plddt"]),
            ("All binding affinities are hardcoded string literals inside UI data, e.g. "
             "'dG = -18.4 kcal/mol | Kd = 0.32 nM | AF3 pLDDT = 96.2 / 100' stored as one "
             "human-readable string. Numeric values embedded in prose cannot be validated, "
             "unit-checked, or recomputed programmatically.",
             "app.js:146", ["engineering", "data-model"]),
        ]:
            L.claim(text, kind="finding", source_type="code", source_ref=ref,
                    confidence=0.95, tags=tags)

    idx = mem.Index()
    idx.sync()
    for p in mem.write_views(idx):
        print("view:", p.relative_to(REPO))
    print("\nstats:", idx.stats())
    idx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
