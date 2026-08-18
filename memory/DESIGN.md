# CBC-Memory: Provenance Ledger

Local, durable, git-diffable memory for the CognitionBioChem multi-agent system.

## Status of this document

This is **v2**. Version 1 (`SPEC_draft.md`, retained for the record) was produced by a
specification agent and then **rejected by three independent adversarial critics**
(concurrency/durability, retrieval, simplicity) — 18 fatal flaws with measured evidence.
It is not implemented. This document is the corrected design, and every section below
names the v1 flaw it defends against.

**Root cause of the v1 failure:** the spec-writing prompt demanded ten mandatory sections
and "complete, unambiguous" coverage. That rewarded machinery over minimality, and produced
seven file streams, ~30 free parameters, an ACT-R activation model, an auto-merge daemon,
and a rebuild-on-every-read loop — for a corpus of 10³–10⁴ items. v2 optimizes for the
smallest thing that satisfies the requirements and survives every critic finding.

## Requirements

| # | Requirement |
|---|---|
| R1 | ~16 parallel agents write concurrently without corruption or lost writes |
| R2 | Every item carries provenance: author, source, confidence, verification status |
| R3 | Multi-hop retrieval ("which findings were refuted, and by what evidence?") |
| R4 | 100% local: Python stdlib + numpy, no service, no key, no network |
| R5 | Human-readable and git-diffable |
| R6 | Cheap at 10³–10⁴ items — no machinery a linear scan would beat |
| R7 | Survives across sessions; a fresh agent can reload with no context |

## Architecture

```
memory/
  ledger/<agent>.jsonl      AUTHORITY. Append-only. Git-tracked. One file per agent.
  index/                    DERIVED. Disposable. Gitignored. Rebuilt from ledger.
  views/*.md                GENERATED. Git-tracked. Human/LLM-readable mirror.
  mem.py                    Library + CLI.
```

The ledger has all authority; the index has none. Coupling is strictly one-directional,
which is the only reason a hybrid is simpler here than either pure design.

### One file per agent, one stream per file

v1 used 7 streams × 2000 shards = 14,000 files, costing a measured 30 ms `stat` storm per
read. v2 uses one file per agent, discriminated by a `rec` field. This also makes the
claim-before-edge durability dependency automatic: same file descriptor, same fsync.

*Defends: v1 overengineering #3, design error #2, fatal flaw #6 (cross-file fsync ordering).*

## Record types

All records share `{rec, id, agent, run, ts, ...}`. `ts` is ingest wall-clock, monotonically
clamped per process (`ts = max(now, last+1)`).

| `rec` | Payload |
|---|---|
| `CLAIM` | `text, kind, source{type,ref,locator}, confidence, tags[]` |
| `EDGE` | `src, rel, dst, note` — rel ∈ SUPPORTS, REFUTES, CITES, SUPERSEDES, DERIVES_FROM, RELATES_TO |
| `STATUS` | `target, status, rationale, evidence[]` — status ∈ ASSERTED, VERIFIED, REFUTED, SUPERSEDED, WITHDRAWN |
| `ARTIFACT` | `path, sha256, kind, desc` |
| `RUN` | `event ∈ OPEN\|CLOSE, task, meta` |

### Identity is a pure function of semantics

`id = blake2b(canonical_json(semantic_fields))`, and **no timestamp, run id, or confidence
is a semantic field**.

| Record | Semantic key |
|---|---|
| CLAIM | `agent, kind, normalize(text), source.type, source.ref` |
| EDGE | `src, rel, dst, agent` |
| STATUS | `target, status, agent, normalize(rationale)` |

A crashed-and-retried write therefore produces a byte-identical id, and dedupe works
globally rather than per-shard. Duplicate ids are **skipped, first-occurrence-wins by
`(ts, file, lineno)`** — never a hard error, because in an append-only file a hard error
would be permanent.

*Defends: v1 fatal flaws #1 (key embeds write time) and #2 (dedupe scope vs uniqueness scope,
permanent unbuildable index).*

## Write path

One `O_APPEND` file descriptor per process, retained on the instance so refcounting cannot
silently drop the `flock`. If the agent's file is already locked, the process takes
`<agent>.2.jsonl` rather than failing — two live processes never share a descriptor.

- Records are serialized with `json.dumps(sort_keys=True)` + `\n` and written with one
  `os.write`. A short write (ENOSPC, RLIMIT_FSIZE) is repaired by `ftruncate` back to the
  pre-write size — safe because there is exactly one writer — rather than by an `assert`,
  which vanishes under `python -O` and would otherwise glue a partial line mid-file.
- `threading.Lock` guards the sequence/size/dedupe state, so one agent may parallelize its
  own writes.
- Durability on macOS uses `fcntl(fd, F_FULLFSYNC)`, not `os.fsync`. Measured on this
  machine: `os.fsync` 0.031 ms/rec vs `F_FULLFSYNC` 3.81 ms/rec — a 125× gap that proves
  plain `fsync` returns before data reaches stable storage on APFS.

*Defends: v1 fatal flaws #4, #5, #9; design errors #6, #8, #12.*

## Read path

**Reading never writes to the ledger.** No READ events, no access counters in the ledger.
Usage statistics, if ever wanted, belong in the disposable index.

*Defends: v1 fatal flaw #3 — the read/rebuild deadlock that made exit 4 the steady state.*

### Freshness by consumed byte offset

The index records, per ledger file, the **byte offset actually consumed** — not
`(size, mtime, inode)`. Ledger files only grow, so ingest is incremental from that offset.
A trailing partial line is not consumed and its bytes are not counted, so it is picked up
on the next pass instead of being lost behind a "fresh" stamp.

*Defends: v1 fatal flaw #8 — a dead shard's last record invisible forever.*

Concurrent ingest is guarded by a non-blocking lock on the index. On contention the reader
proceeds with a slightly stale index and says so, rather than raising `IndexStale`. Staleness
is a normal condition in a concurrent system; a crash is not an acceptable response to it.

### Ranking

Two channels over the same filtered candidate set:

1. **Lexical** — SQLite FTS5, BM25, over `text` and `tags` only. `claim_type` and
   `source_ref` are *filters*, not FTS columns; indexing a closed enum as text made a
   two-word query match 33% of the corpus in v1.
2. **Vector** — sparse hashed TF-IDF cosine, SMART `lnc.ltc` (IDF on the query side only —
   stated honestly, since `lnc.ltc` is not a symmetric IDF-weighted cosine). Features are
   word tokens plus character 3/4/5-grams, hashed into **D = 2²⁰**. Stored **sparse (CSC)**,
   so a large D costs nothing: ~24 MB at 10⁴ docs, versus the 1.3 GB a dense D=2²⁰ matrix
   would need. v1 chose D=2048 on a dense-storage budget and lost 3× of its IDF
   discrimination to collisions.

   Known limitation, found while testing: because character n-grams dominate the feature
   count, this channel scores weak matches on shared morphology — "quantiz**ation**"
   retrieves against "gener**ation**" at roughly half the score of a true match. That is
   the channel behaving as designed (it is what makes it robust to `CYP3A4` vs `CYP 3A4`),
   but it is a lexical-orthographic signal, not a semantic one, and is documented as such
   rather than described as an embedding.

Fusion is **pure RRF**, `score = Σ 1/(60 + rank)` (Cormack et al., SIGIR 2009). Priors do
not multiply it. In v1 the prior product spanned 27.8× against RRF's 4.3×, so the
worst-relevance document beat the best-relevance one by 6.5× and ranking degenerated into a
metadata sort. Status/recency weighting is available behind an explicit `--boost` flag,
capped so it can only reorder within a relevance band, and **off by default**.

*Defends: v1 fatal flaw #2, design errors #1, #2, #5, #6, #9, #10.*

`np.argpartition` is called with `kth = min(k, N-1)`, so search works on a 1-item corpus.
Masked rows are dropped, not set to `-inf` and left to acquire ranks.

*Defends: v1 design error #7 — crash on every corpus of ≤200 items.*

### Graph hop

Multi-hop (R3) is a **SQL join over typed edges**, because the edges are born structured: a
verifier that refutes a claim writes the `REFUTES` and `CITES` edges at that moment. Nothing
needs to be inferred, so no entity-extraction error term is introduced.

Optional 1-hop expansion in search obeys three rules v1 violated: every Stage-A filter is
re-applied to expanded nodes; fan-out per seed is capped; and an expanded node is scored at
`0.5 ×` its seed so it can never outrank a direct hit. v1's expansion could exceed the
maximum possible direct score, which meant every query surfacing a superseding claim also
resurfaced the invalidated one it replaced.

*Defends: v1 fatal flaw #3 (retrieval).*

## What was deliberately removed

| Removed | Why |
|---|---|
| Automatic `SAME_AS` merging | Merged semantic opposites. Measured: "is a potent inhibitor" vs "is **not** a potent inhibitor" → cos 0.940, Jaccard 0.917, merged. Both gates are lexical and both are *maximized* by minimal-edit contradictions, so they are the same mistake twice. In a critical-review MAS the record of disagreement is the deliverable. |
| Automatic contradiction detector writing STATUS | Its regex was a silent no-op against normalized text; once fixed it compared `900 nM` against `1 uM` numerically and would auto-invalidate correct claims. No unattended process may write a verification status. |
| ACT-R base-level activation | Misstated formula, double-counted recency, and counted *impressions* rather than *use*, closing a rich-get-richer loop with no damping. |
| Embedding cached in the ledger record | A pure function of text stored beside that text, and it froze `D` into an append-only file. |
| Second SQLite cache database | Caching a pure function in a system that rebuilds in milliseconds. |
| Per-relation decay tables, 6-term salience, ~30 tunables | No evaluation set exists to fit them. The one constant kept (`rrf_k = 60`) is the one with published justification. |

## Consolidation and forgetting

Nothing is ever deleted. Consolidation only *appends* summary CLAIMs that cite their
sources via `DERIVES_FROM` edges, and is manual (`mem consolidate`). Redaction writes a
`WITHDRAWN` status; it never rewrites a ledger line, so a withdrawal can never silently
un-refute a claim that depended on it.

## Views

`memory/views/*.md` are generated and byte-stable: no timestamps, no mtime-derived hashes
in the banner. v1's banner embedded both, so its own `mirror --check` CI step could never
pass. Regenerate with `python3 memory/mem.py views`.

## Verification

Every critic finding above is encoded as a regression test in `memory/tests/test_mem.py`.
The design is considered validated only when that suite passes, not when this document reads
convincingly.
