#!/usr/bin/env python3
"""Regression suite for CBC-Memory.

Every test named V1_* encodes a specific fatal flaw or design error that three
adversarial critics found in the rejected v1 specification. These are the reason the
design is what it is; if one of them starts failing, the corresponding v1 mistake has
been reintroduced.

Run: python3 memory/tests/test_mem.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import mem  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


class Env:
    """Isolated ledger/index/views under a temp dir."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.ledger = root / "ledger"
        self.index = root / "index"
        self.views = root / "views"
        for p in (self.ledger, self.index, self.views):
            p.mkdir(parents=True)
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def led(self, agent: str, task: str = "t") -> mem.Ledger:
        return mem.Ledger(agent, task=task, ledger_dir=self.ledger)

    def idx(self) -> mem.Index:
        i = mem.Index(index_dir=self.index, ledger_dir=self.ledger)
        i.sync()
        return i


# --------------------------------------------------------------------------- #
# v1 fatal flaw #1 -- idempotency key embedded the write timestamp
# --------------------------------------------------------------------------- #

def test_v1_idempotency_key_excludes_time():
    print("\n[v1 F#1] identity is a pure function of semantics")
    a = mem.claim_id("rev", "finding", "pLDDT is not affinity", "code", "app.js:791")
    time.sleep(0.002)
    b = mem.claim_id("rev", "finding", "pLDDT is not affinity", "code", "app.js:791")
    check("same claim -> same id regardless of when", a == b, a)

    c = mem.claim_id("rev", "finding", "  pLDDT  IS NOT   Affinity ", "code", "app.js:791")
    check("id is normalization-invariant", a == c)
    d = mem.claim_id("rev", "finding", "pLDDT is affinity", "code", "app.js:791")
    check("different text -> different id", a != d)

    with Env() as env:
        with env.led("rev") as L:
            i1 = L.claim("dup me", source_type="code", source_ref="x.js:1")
            i2 = L.claim("dup me", source_type="code", source_ref="x.js:1")
        check("in-process retry is deduped", i1 == i2)
        # A restart is the case v1 could not dedupe, because its shard changed.
        with env.led("rev") as L:
            i3 = L.claim("dup me", source_type="code", source_ref="x.js:1")
        check("cross-restart retry yields same id", i1 == i3)
        idx = env.idx()
        n = idx.db.execute("SELECT count(*) FROM item WHERE id=?", (i1,)).fetchone()[0]
        check("index stores exactly one row for it", n == 1, f"n={n}")
        idx.close()


# --------------------------------------------------------------------------- #
# v1 fatal flaw #2 -- a duplicate id aborted the rebuild, permanently
# --------------------------------------------------------------------------- #

def test_v1_duplicate_id_is_not_fatal():
    print("\n[v1 F#2] a duplicate id is skipped, never a hard error")
    with Env() as env:
        with env.led("a1") as L:
            cid = L.claim("shared observation", source_type="code", source_ref="app.js:1")
        # Simulate a crashed retry that landed in a second file for the same agent.
        dup = env.ledger / "a1.2.jsonl"
        line = [l for l in (env.ledger / "a1.jsonl").read_text().splitlines()
                if cid in l][0]
        dup.write_text(line + "\n")
        try:
            idx = env.idx()
            ok = True
        except Exception as exc:  # noqa: BLE001
            ok = False
            print("    exception:", exc)
        check("rebuild survives a duplicated record", ok)
        if ok:
            n = idx.db.execute("SELECT count(*) FROM item").fetchone()[0]
            check("duplicate collapsed to one row", n == 1, f"n={n}")
            idx.close()


# --------------------------------------------------------------------------- #
# v1 fatal flaw #3 -- reading appended a READ event, so every read rebuilt everything
# --------------------------------------------------------------------------- #

def test_v1_reads_never_write():
    print("\n[v1 F#3] the read path never touches the ledger")
    with Env() as env:
        with env.led("w") as L:
            for i in range(30):
                L.claim(f"claim about docking scoring number {i}", source_ref=f"r{i}")
        idx = env.idx()
        before = {p.name: p.stat().st_size for p in mem.ledger_files(env.ledger)}
        for _ in range(50):
            idx.search("docking scoring")
            idx.stats()
            idx.refuted_with_evidence()
        after = {p.name: p.stat().st_size for p in mem.ledger_files(env.ledger)}
        check("ledger bytes unchanged after 150 read ops", before == after,
              f"{before} vs {after}")
        n_files = len(list(env.ledger.glob("*.jsonl")))
        check("no new ledger file appeared", n_files == 1, f"{n_files} files")
        idx.close()


# --------------------------------------------------------------------------- #
# v1 fatal flaw #8 -- freshness by (size,mtime) hid a partial trailing line forever
# --------------------------------------------------------------------------- #

def test_v1_partial_tail_is_recovered():
    print("\n[v1 F#8] a partial trailing line is not consumed and is picked up later")
    with Env() as env:
        with env.led("w") as L:
            good = L.claim("complete record about hERG", source_ref="a")
        path = env.ledger / "w.jsonl"
        full = path.read_text()
        torn = json.dumps({"rec": "CLAIM", "id": "clm_torn", "agent": "w", "run": "r",
                           "ts": 9, "text": "torn", "kind": "note",
                           "source": {"type": "x", "ref": "y", "locator": ""},
                           "confidence": 0.5, "tags": []})
        path.write_text(full + torn[: len(torn) // 2])  # no newline: a torn tail

        idx = mem.Index(index_dir=env.index, ledger_dir=env.ledger)
        idx.sync()
        consumed = idx.db.execute("SELECT consumed FROM offsets WHERE path='w.jsonl'"
                                  ).fetchone()["consumed"]
        check("offset stops at the last complete newline", consumed == len(full),
              f"{consumed} vs {len(full)}")
        check("the complete record was indexed",
              idx.db.execute("SELECT count(*) FROM item WHERE id=?", (good,)
                             ).fetchone()[0] == 1)
        check("the torn record was not indexed",
              idx.db.execute("SELECT count(*) FROM item WHERE id='clm_torn'"
                             ).fetchone()[0] == 0)
        # Now the writer completes the line: it must become visible, not be lost behind
        # a "fresh" stamp -- the exact v1 failure.
        path.write_text(full + torn + "\n")
        idx.sync()
        check("completed record becomes visible on the next sync",
              idx.db.execute("SELECT count(*) FROM item WHERE id='clm_torn'"
                             ).fetchone()[0] == 1)
        idx.close()


# --------------------------------------------------------------------------- #
# R1 -- 16 concurrent writers
# --------------------------------------------------------------------------- #

WORKER = r"""
import sys, pathlib
sys.path.insert(0, sys.argv[1])
import mem
agent, n, led_dir = sys.argv[2], int(sys.argv[3]), sys.argv[4]
with mem.Ledger(agent, task="load", ledger_dir=pathlib.Path(led_dir), fsync_every=10**9) as L:
    for i in range(n):
        L.claim(f"{agent} finding {i} about binding affinity", source_ref=f"{agent}:{i}")
"""


def test_concurrent_writers():
    print("\n[R1] 16 concurrent writer processes")
    with Env() as env:
        script = Path(env.tmp.name) / "worker.py"
        script.write_text(WORKER)
        lib = str(Path(mem.__file__).resolve().parent)
        n_agents, n_each = 16, 200
        t0 = time.time()
        procs = [subprocess.Popen([sys.executable, str(script), lib, f"ag{i:02d}",
                                   str(n_each), str(env.ledger)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(n_agents)]
        errs = []
        for p in procs:
            _, err = p.communicate(timeout=180)
            if p.returncode != 0:
                errs.append(err.decode()[:400])
        dt = time.time() - t0
        check("all 16 writers exited cleanly", not errs, "; ".join(errs[:2]))

        total_lines, bad = 0, 0
        for f in mem.ledger_files(env.ledger):
            for line in f.read_text().splitlines():
                total_lines += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
        check("every line is valid JSON", bad == 0, f"{bad} bad")
        idx = env.idx()
        n = idx.db.execute("SELECT count(*) FROM item").fetchone()[0]
        check(f"all {n_agents * n_each} claims indexed", n == n_agents * n_each,
              f"got {n} in {dt:.1f}s")
        agents = idx.db.execute("SELECT count(DISTINCT agent) FROM item").fetchone()[0]
        check("all 16 agents present", agents == n_agents, f"got {agents}")
        idx.close()


def test_same_agent_two_processes():
    print("\n[v1 D#8] two processes for one agent get separate files, neither blocks")
    with Env() as env:
        a = env.led("dup")
        b = env.led("dup")  # must not raise, must not share the descriptor
        check("second instance took a different file", a.path != b.path,
              f"{a.path.name} vs {b.path.name}")
        ida = a.claim("from process a", source_ref="a")
        idb = b.claim("from process b", source_ref="b")
        a.close(); b.close()
        idx = env.idx()
        n = idx.db.execute("SELECT count(*) FROM item").fetchone()[0]
        check("both writers' claims survived", n == 2, f"n={n}")
        idx.close()


def test_threaded_writes_one_agent():
    print("\n[v1 D#12] one agent may parallelize its own writes")
    with Env() as env:
        with env.led("th") as L:
            def work(k):
                for i in range(25):
                    L.claim(f"thread {k} item {i}", source_ref=f"{k}:{i}")
            ts = [threading.Thread(target=work, args=(k,)) for k in range(8)]
            [t.start() for t in ts]; [t.join() for t in ts]
        idx = env.idx()
        n = idx.db.execute("SELECT count(*) FROM item").fetchone()[0]
        check("200 threaded claims all landed", n == 200, f"n={n}")
        seqs = [json.loads(l) for l in (env.ledger / "th.jsonl").read_text().splitlines()]
        tss = [r["ts"] for r in seqs]
        check("timestamps are strictly monotonic", all(b > a for a, b in zip(tss, tss[1:])))
        idx.close()


# --------------------------------------------------------------------------- #
# v1 design error #7 -- argpartition crashed on any corpus of <= 200 items
# --------------------------------------------------------------------------- #

def test_v1_small_corpus_search():
    print("\n[v1 D#7] search works on tiny corpora")
    for n in (1, 2, 5, 50, 200, 201):
        with Env() as env:
            with env.led("s") as L:
                for i in range(n):
                    L.claim(f"item {i} concerning AlphaFold confidence metrics",
                            source_ref=str(i))
            idx = env.idx()
            try:
                hits = idx.search("AlphaFold confidence", limit=5)
                ok = len(hits) > 0
                err = ""
            except Exception as exc:  # noqa: BLE001
                ok, err = False, repr(exc)
            check(f"N={n}: search returns results", ok, err)
            idx.close()


# --------------------------------------------------------------------------- #
# v1 fatal flaw #2 (retrieval) -- priors dominated relevance 6.5x
# --------------------------------------------------------------------------- #

def test_v1_relevance_dominates_priors():
    print("\n[v1 R-F#2] relevance drives ranking; priors cannot overturn it")
    with Env() as env:
        with env.led("p") as L:
            exact = L.claim("hERG cardiotoxicity IC50 potassium channel blockade assay",
                            source_ref="target", confidence=0.1)
            noise = []
            for i in range(60):
                noise.append(L.claim(f"unrelated note about mmCIF parsing number {i}",
                                     source_ref=f"n{i}", confidence=1.0))
            for c in noise[:20]:
                L.status(c, "VERIFIED", rationale="high prior on purpose")
        idx = env.idx()
        for boost in (False, True):
            hits = idx.search("hERG cardiotoxicity IC50 potassium channel", limit=5,
                              boost=boost)
            top = hits[0]["id"] if hits else None
            check(f"boost={boost}: the relevant claim ranks first", top == exact,
                  f"got {top}")
        idx.close()


# --------------------------------------------------------------------------- #
# v1 fatal flaw #3 (retrieval) -- expansion outranked direct hits and bypassed filters
# --------------------------------------------------------------------------- #

def test_v1_expansion_cannot_outrank_direct():
    print("\n[v1 R-F#3] graph expansion is capped below direct hits and obeys filters")
    with Env() as env:
        with env.led("g") as L:
            # `old` shares no word tokens AND no character 3-grams with the query, so
            # the only way it can appear in results is through the graph hop. (A first
            # attempt used "quantization", which the char-n-gram channel matched to
            # "generation" on the shared "-ation" suffix -- that channel working exactly
            # as designed, but a poor negative control.)
            old = L.claim("obsolete bulk fixture q7 w9 z3 rollup", source_ref="o")
            new = L.claim("current claim about PAE heatmap generation", source_ref="n")
            L.edge(new, "SUPERSEDES", old)
            L.status(old, "SUPERSEDED", rationale="replaced")
        idx = env.idx()
        hits = idx.search("PAE heatmap generation", limit=10, expand=True)
        by_id = {h["id"]: h for h in hits}
        check("the superseded claim is reachable only via the hop",
              old in by_id and by_id[old]["via"] != "direct",
              str({k: v["via"] for k, v in by_id.items()}))
        if new in by_id and old in by_id:
            check("expanded node scores strictly below its seed",
                  by_id[old]["score"] < by_id[new]["score"],
                  f"{by_id[old]['score']:.6f} vs {by_id[new]['score']:.6f}")
            check("expanded score is exactly the decayed seed score",
                  abs(by_id[old]["score"] - by_id[new]["score"] * mem.EXPANSION_DECAY) < 1e-9)
        direct = [h for h in hits if h["via"] == "direct"]
        expanded = [h for h in hits if h["via"] != "direct"]
        if direct and expanded:
            check("no expanded node outranks any direct hit",
                  min(h["score"] for h in direct) >= max(h["score"] for h in expanded))
        else:
            check("no expanded node outranks any direct hit", True, "all direct")

        filtered = idx.search("PAE heatmap generation", limit=10, expand=True,
                              status="ASSERTED")
        check("expansion re-applies the status filter",
              all(h["status"] == "ASSERTED" for h in filtered),
              str([h["status"] for h in filtered]))
        filtered2 = idx.search("PAE heatmap", limit=10, expand=True, agent="nobody")
        check("expansion re-applies the agent filter", filtered2 == [])
        idx.close()


# --------------------------------------------------------------------------- #
# v1 fatal flaw #4 (retrieval) -- auto-merge collapsed semantic opposites
# --------------------------------------------------------------------------- #

def test_v1_no_auto_merge_of_contradictions():
    print("\n[v1 R-F#4] contradictory claims are never merged or auto-resolved")
    with Env() as env:
        with env.led("x") as L:
            pos = L.claim("Compound 7 is a potent AChE inhibitor", source_ref="p")
        with env.led("y") as L:
            neg = L.claim("Compound 7 is not a potent AChE inhibitor", source_ref="p")
        check("near-identical opposites keep distinct ids", pos != neg)
        idx = env.idx()
        hits = idx.search("Compound 7 potent AChE inhibitor", limit=10)
        ids = {h["id"] for h in hits}
        check("both sides of the contradiction are retrievable",
              pos in ids and neg in ids, str(ids))
        # And confirm the machinery that caused v1's failure simply does not exist.
        src = Path(mem.__file__).read_text()
        check("no SAME_AS relation exists", "SAME_AS" not in mem.REL_TYPES)
        check("no automatic contradiction detector", "contradict" not in src.lower())
        idx.close()


def test_no_unattended_status_writes():
    print("\n[v1 R-F#5] no unattended process can write a verification status")
    src = Path(mem.__file__).read_text()
    idx_cls = src[src.index("class Index"):src.index("def write_views")]
    check("Index never constructs a STATUS record", '"rec": "STATUS"' not in idx_cls)
    check("Index never opens a Ledger", "Ledger(" not in idx_cls)


# --------------------------------------------------------------------------- #
# v1 design error #1 -- D=2048 destroyed IDF discrimination through collisions
# --------------------------------------------------------------------------- #

def test_v1_vector_collisions():
    print("\n[v1 D#1] hashing collisions are negligible at D=2^20")
    texts = [f"claim {i} about {w} in the {p} pathway"
             for i, (w, p) in enumerate([("CYP3A4", "hepatic"), ("hERG", "cardiac"),
                                         ("TrkB", "neurotrophin"), ("Keap1", "Nrf2")] * 250)]
    feats = {}
    for t in texts:
        for slot in mem.features(t):
            feats[slot] = feats.get(slot, 0) + 1
    n_slots = len(feats)
    check("distinct feature slots is large", n_slots > 1000, f"{n_slots} slots")
    load = n_slots / mem.VEC_DIM
    check("hash table load factor is tiny", load < 0.01, f"load={load:.5f}")

    # discrimination: a rare identifier must separate its document from the rest
    vi = mem.VectorIndex.build(texts)
    scores = vi.score("hERG cardiac")
    top = int(np.argmax(scores))
    check("rare identifier retrieves its own document", "hERG" in texts[top], texts[top])


def test_vector_is_sparse_and_small():
    print("\n[R6] the vector index stays small")
    texts = [f"finding {i} about ADMET properties and blood brain barrier penetration"
             for i in range(2000)]
    vi = mem.VectorIndex.build(texts)
    nbytes = vi.rows.nbytes + vi.vals.nbytes + vi.feats.nbytes + vi.indptr.nbytes
    per_doc = nbytes / len(texts)
    check("index is sparse, not dense", nbytes < 50_000_000,
          f"{nbytes/1e6:.1f} MB for 2000 docs ({per_doc:.0f} B/doc)")
    dense = mem.VEC_DIM * 4 * len(texts)
    check("sparse beats an equivalent dense matrix by >100x", nbytes * 100 < dense,
          f"{nbytes/1e6:.1f} MB vs {dense/1e9:.1f} GB dense")


# --------------------------------------------------------------------------- #
# R3 -- the multi-hop query the whole system exists for
# --------------------------------------------------------------------------- #

def test_r3_multihop_refuted_with_evidence():
    print("\n[R3] which ADMET findings were refuted, and by what evidence?")
    with Env() as env:
        with env.led("reviewer") as L:
            bad = L.claim("hERG risk is 0% for all 25 candidates",
                          kind="finding", source_type="code",
                          source_ref="README.md:99", tags=["admet", "safety"])
            other = L.claim("mmCIF parsing is absent", kind="finding",
                            source_ref="app.js:674", tags=["engineering"])
        with env.led("verifier") as L:
            src = L.claim("A 0% risk statement is not producible by any hERG model",
                          kind="evidence", source_type="doi",
                          source_ref="10.1038/s41573-019-0024-5", tags=["admet"])
            L.edge(src, "CITES", other, note="unrelated, present to test the join")
            L.refute(bad, "no model outputs a zero-probability class", refuting_claim=src)
        idx = env.idx()
        rows = idx.refuted_with_evidence(tag="admet")
        check("the refuted ADMET claim is found", len(rows) >= 1, f"{len(rows)} rows")
        if rows:
            r = rows[0]
            check("it names the refuting agent", r["refuted_by"] == "verifier")
            check("it carries the refuting claim text",
                  "0% risk" in (r["refuting_claim"] or "") or
                  "zero-probability" in (r["rationale"] or ""), str(r)[:200])
        tr = idx.trace(bad)
        check("trace returns the full status history", len(tr["status_history"]) == 1)
        check("trace returns the inbound REFUTES edge",
              any(e["rel"] == "REFUTES" for e in tr["edges_in"]))
        check("status folded to REFUTED", tr["claim"]["status"] == "REFUTED")
        idx.close()


def test_status_fold_is_deterministic():
    print("\n[R2] status folding is last-write-wins and reproducible")
    with Env() as env:
        with env.led("a") as L:
            c = L.claim("contested claim about ΔG precision", source_ref="z")
            L.status(c, "VERIFIED", rationale="looks right")
        with env.led("b") as L:
            L.status(c, "REFUTED", rationale="arithmetic is wrong")
        idx = env.idx()
        st = idx.db.execute("SELECT status FROM item WHERE id=?", (c,)).fetchone()["status"]
        check("later status wins", st == "REFUTED", st)
        dis = idx.db.execute("SELECT * FROM v_dispute").fetchall()
        check("the disagreement is recorded as a dispute", len(dis) == 1)
        check("dispute counts both sides",
              dis[0]["n_verified"] == 1 and dis[0]["n_refuted"] == 1)
        idx.close()


# --------------------------------------------------------------------------- #
# Incremental ingest, views, durability
# --------------------------------------------------------------------------- #

def test_incremental_ingest():
    print("\n[R6] ingest is incremental, not a full rebuild")
    with Env() as env:
        with env.led("i") as L:
            for k in range(100):
                L.claim(f"baseline claim {k} about protein folding", source_ref=str(k))
        idx = mem.Index(index_dir=env.index, ledger_dir=env.ledger)
        first = idx.sync()
        check("first sync ingested everything", first.get("CLAIM") == 100, str(first))
        again = idx.sync()
        check("second sync ingests nothing", not again.get("CLAIM"), str(again))
        with env.led("i2") as L:
            L.claim("one new claim about protein folding", source_ref="new")
        third = idx.sync()
        check("only the new record is ingested", third.get("CLAIM") == 1, str(third))
        idx.close()


def test_views_are_byte_stable():
    print("\n[v1 D#5] generated views are byte-stable across runs")
    with Env() as env:
        with env.led("v") as L:
            c = L.claim("a claim that will appear in the mirror", source_ref="q")
            L.status(c, "VERIFIED", rationale="checked")
        idx = env.idx()
        first = {p.name: p.read_bytes() for p in mem.write_views(idx, env.views)}
        time.sleep(0.01)
        second = {p.name: p.read_bytes() for p in mem.write_views(idx, env.views)}
        check("regeneration is byte-identical", first == second,
              str([k for k in first if first[k] != second.get(k)]))
        check("no timestamp in the banner", b"GENERATED FILE" in first["INDEX.md"]
              and b"20" + b"26-" not in first["INDEX.md"][:200])
        idx.close()


def test_durability_uses_fullfsync_on_darwin():
    print("\n[v1 F#9] durability uses F_FULLFSYNC on Darwin")
    src = Path(mem.__file__).read_text()
    check("F_FULLFSYNC constant is defined", "F_FULLFSYNC = 51" in src)
    check("it is used on darwin", 'sys.platform == "darwin"' in src
          and "fcntl.fcntl(self._fd, F_FULLFSYNC)" in src)
    if sys.platform == "darwin":
        with Env() as env:
            with env.led("d") as L:
                L.claim("durable claim", source_ref="d")
                L._sync()
            check("a synced write is readable back",
                  len(mem.read_file(env.ledger / "d.jsonl")) >= 2)


def test_claim_before_edge_same_file():
    print("\n[v1 F#6] a claim is durable-ordered ahead of any edge referencing it")
    with Env() as env:
        with env.led("o") as L:
            c1 = L.claim("first", source_ref="1")
            c2 = L.claim("second", source_ref="2")
            L.edge(c2, "REFUTES", c1)
        recs = mem.read_file(env.ledger / "o.jsonl")
        order = [r["id"] for r in recs]
        edge = [r for r in recs if r["rec"] == "EDGE"][0]
        check("both endpoints precede the edge in the same file",
              order.index(c1) < order.index(edge["id"])
              and order.index(c2) < order.index(edge["id"]))
        check("one file, so no cross-file fsync ordering exists",
              len(list(env.ledger.glob("*.jsonl"))) == 1)


def test_validation_rejects_bad_input():
    print("\n[R2] schema validation at the write boundary")
    with Env() as env:
        with env.led("val") as L:
            for name, fn in [
                ("unknown claim kind", lambda: L.claim("x", kind="nonsense")),
                ("confidence out of range", lambda: L.claim("x", confidence=1.5)),
                ("empty text", lambda: L.claim("   ")),
                ("unknown relation", lambda: L.edge("a", "CAUSES", "b")),
                ("unknown status", lambda: L.status("a", "MAYBE")),
            ]:
                try:
                    fn(); ok = False
                except mem.LedgerError:
                    ok = True
                check(f"rejects {name}", ok)
        try:
            mem.Ledger("bad/agent", ledger_dir=env.ledger); ok = False
        except mem.LedgerError:
            ok = True
        check("rejects an unsafe agent id", ok)


def test_cli_roundtrip():
    print("\n[R7] CLI round-trip in a fresh process")
    with Env() as env:
        lib = str(Path(mem.__file__).resolve().parent)
        e = {**os.environ, "PYTHONPATH": lib}
        def run(*args):
            return subprocess.run([sys.executable, str(Path(lib) / "mem.py"), *args],
                                  capture_output=True, text=True, env=e, cwd=lib)
        # The CLI writes to the real memory/ dir, so only exercise read-only commands
        # plus an isolated library write, to avoid polluting the repo during tests.
        with env.led("cli") as L:
            L.claim("cli visible claim about ADMET", source_ref="cli")
        idx = env.idx()
        hits = idx.search("ADMET")
        check("library search finds the claim", len(hits) == 1)
        out = run("--help")
        check("CLI --help works", out.returncode == 0 and "provenance ledger" in out.stdout)
        idx.close()


def main() -> int:
    print("=" * 78)
    print("CBC-Memory regression suite")
    print("v1_* tests encode flaws found by three adversarial critics of the rejected spec")
    print("=" * 78)
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    t0 = time.time()
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            import traceback
            FAIL.append(t.__name__)
            print(f"  FAIL  {t.__name__} raised {exc!r}")
            traceback.print_exc()
    dt = time.time() - t0
    print("\n" + "=" * 78)
    print(f"{len(PASS)} passed, {len(FAIL)} failed in {dt:.1f}s")
    if FAIL:
        print("FAILED:")
        for f in FAIL:
            print("  -", f)
    print("=" * 78)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
