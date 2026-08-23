#!/usr/bin/env python3
"""CBC-Memory: a provenance ledger for the CognitionBioChem multi-agent system.

Authority lives in append-only JSONL files under memory/ledger/, one per agent.
memory/index/ is a disposable derived index (SQLite FTS5 + sparse TF-IDF) rebuilt
incrementally from the ledger. Reading never writes to the ledger.

See DESIGN.md for the rationale and for the v1 flaws each mechanism defends against.

Dependencies: Python 3.11+ stdlib and numpy. Nothing else.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parent
LEDGER_DIR = ROOT / "ledger"
INDEX_DIR = ROOT / "index"
VIEWS_DIR = ROOT / "views"

REC_TYPES = ("CLAIM", "EDGE", "STATUS", "ARTIFACT", "RUN")
REL_TYPES = ("SUPPORTS", "REFUTES", "CITES", "SUPERSEDES", "DERIVES_FROM", "RELATES_TO")
STATUS_TYPES = ("ASSERTED", "VERIFIED", "REFUTED", "SUPERSEDED", "WITHDRAWN")
CLAIM_KINDS = (
    "finding", "verdict", "evidence", "decision", "requirement",
    "measurement", "summary", "question", "plan", "note",
)

# Retrieval constants. RRF k=60 is Cormack et al., SIGIR 2009 -- the one constant here
# with a published justification. See DESIGN.md on why nothing else is tunable.
RRF_K = 60
VEC_DIM = 1 << 20
CAND_LEX = 200
CAND_VEC = 200
EXPANSION_DECAY = 0.5
EXPANSION_FANOUT = 8

F_FULLFSYNC = 51  # <sys/fcntl.h> on Darwin


# --------------------------------------------------------------------------- #
# Normalization and identity
# --------------------------------------------------------------------------- #

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC + casefold + whitespace collapse. Used for identity and for indexing."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _digest(prefix: str, parts: Any) -> str:
    return prefix + hashlib.blake2b(_canonical(parts), digest_size=8).hexdigest()


def claim_id(agent: str, kind: str, text: str, src_type: str, src_ref: str) -> str:
    """Identity excludes ts, run, confidence and tags, so a retry is byte-identical."""
    return _digest("clm_", [agent, kind, normalize(text), src_type, src_ref])


def edge_id(src: str, rel: str, dst: str, agent: str) -> str:
    return _digest("edg_", [src, rel, dst, agent])


def status_id(target: str, status: str, agent: str, rationale: str) -> str:
    return _digest("sts_", [target, status, agent, normalize(rationale)])


def artifact_id(path: str, sha256: str) -> str:
    return _digest("art_", [path, sha256])


def run_id(agent: str, task: str, nonce: str) -> str:
    return _digest("run_", [agent, task, nonce])


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Write path
# --------------------------------------------------------------------------- #

class LedgerError(RuntimeError):
    pass


class Ledger:
    """Append-only writer for one agent.

    Owns exactly one file. The lock fd is retained on the instance so CPython
    refcounting cannot silently release it. If the agent's primary file is locked by
    another live process, this instance takes the next free suffix rather than failing:
    two processes never share a descriptor, and a human running `mem search` is never
    blocked by a running agent (search opens no Ledger at all).
    """

    def __init__(self, agent: str, task: str = "", ledger_dir: Path | None = None,
                 fsync_every: int = 64):
        if not agent or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", agent):
            raise LedgerError(f"invalid agent id: {agent!r}")
        self.agent = agent
        self.dir = Path(ledger_dir or LEDGER_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.fsync_every = fsync_every

        self._lock = threading.Lock()  # one agent may parallelize its own writes
        self._fd = -1
        self._since_sync = 0
        self._last_ts = 0
        self._seen: set[str] = set()
        self._closed = False

        self.path = self._acquire()
        self._size = os.lseek(self._fd, 0, os.SEEK_END)
        self._seen = {r["id"] for r in read_file(self.path) if "id" in r}

        self.run = run_id(agent, task, f"{os.getpid()}:{time.time_ns()}")
        self._write({"rec": "RUN", "id": self.run, "event": "OPEN", "task": task,
                     "meta": {"pid": os.getpid(), "host": os.uname().nodename,
                              "python": sys.version.split()[0]}})

    # -- file acquisition ---------------------------------------------------- #

    def _acquire(self) -> Path:
        for n in range(1, 100):
            path = self.dir / (f"{self.agent}.jsonl" if n == 1 else f"{self.agent}.{n}.jsonl")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                continue
            self._fd = fd
            return path
        raise LedgerError(f"no free ledger file for agent {self.agent!r}")

    # -- durability ---------------------------------------------------------- #

    def _sync(self) -> None:
        """Real durability. On Darwin os.fsync returns before data reaches storage;
        measured 0.031 ms/rec vs 3.81 ms/rec for F_FULLFSYNC."""
        if sys.platform == "darwin":
            try:
                fcntl.fcntl(self._fd, F_FULLFSYNC)
                self._since_sync = 0
                return
            except OSError:
                pass
        os.fsync(self._fd)
        self._since_sync = 0

    # -- the single append primitive ---------------------------------------- #

    def _write(self, body: dict, *, sync: bool = False) -> dict:
        if self._closed:
            raise LedgerError("ledger is closed")
        with self._lock:
            now = time.time_ns()
            ts = max(now, self._last_ts + 1)  # monotonic clamp; NTP steps must not reorder
            self._last_ts = ts
            rec = {**body, "agent": self.agent, "run": self.run, "ts": ts}
            if rec["rec"] not in REC_TYPES:
                raise LedgerError(f"unknown rec type {rec['rec']!r}")

            if rec["id"] in self._seen:
                return rec  # idempotent retry: already durable in this file
            data = (json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n").encode()

            written = os.write(self._fd, data)
            if written != len(data):
                # ENOSPC / RLIMIT_FSIZE. Repair rather than assert: an assert vanishes
                # under -O and would leave a corrupt line in the middle of the file.
                os.ftruncate(self._fd, self._size)
                os.lseek(self._fd, 0, os.SEEK_END)
                raise LedgerError(f"short write ({written}/{len(data)}); rolled back")

            self._size += written
            self._seen.add(rec["id"])
            self._since_sync += 1
            if sync or self._since_sync >= self.fsync_every:
                self._sync()
            return rec

    # -- public API ---------------------------------------------------------- #

    def claim(self, text: str, *, kind: str = "finding", source_type: str = "reasoning",
              source_ref: str = "", locator: str = "", confidence: float = 0.5,
              tags: Sequence[str] = ()) -> str:
        if kind not in CLAIM_KINDS:
            raise LedgerError(f"unknown claim kind {kind!r}; expected one of {CLAIM_KINDS}")
        if not 0.0 <= confidence <= 1.0:
            raise LedgerError(f"confidence out of range: {confidence}")
        if not text.strip():
            raise LedgerError("claim text is empty")
        cid = claim_id(self.agent, kind, text, source_type, source_ref)
        self._write({
            "rec": "CLAIM", "id": cid, "text": text, "kind": kind,
            "source": {"type": source_type, "ref": source_ref, "locator": locator},
            "confidence": round(float(confidence), 4), "tags": sorted(set(tags)),
        })
        return cid

    def edge(self, src: str, rel: str, dst: str, note: str = "") -> str:
        if rel not in REL_TYPES:
            raise LedgerError(f"unknown relation {rel!r}; expected one of {REL_TYPES}")
        eid = edge_id(src, rel, dst, self.agent)
        # Same file as the claim it references, so a claim written earlier in this
        # process is durable-ordered ahead of the edge without cross-file fsync games.
        self._write({"rec": "EDGE", "id": eid, "src": src, "rel": rel, "dst": dst,
                     "note": note}, sync=True)
        return eid

    def status(self, target: str, status: str, *, rationale: str = "",
               evidence: Sequence[str] = ()) -> str:
        if status not in STATUS_TYPES:
            raise LedgerError(f"unknown status {status!r}; expected one of {STATUS_TYPES}")
        sid = status_id(target, status, self.agent, rationale)
        self._write({"rec": "STATUS", "id": sid, "target": target, "status": status,
                     "rationale": rationale, "evidence": list(evidence)}, sync=True)
        return sid

    def verify(self, target: str, rationale: str, evidence: Sequence[str] = ()) -> str:
        return self.status(target, "VERIFIED", rationale=rationale, evidence=evidence)

    def refute(self, target: str, rationale: str, evidence: Sequence[str] = (),
               refuting_claim: str | None = None) -> str:
        if refuting_claim:
            self.edge(refuting_claim, "REFUTES", target, note=rationale[:200])
        return self.status(target, "REFUTED", rationale=rationale, evidence=evidence)

    def artifact(self, path: str | Path, *, kind: str = "file", desc: str = "") -> str:
        p = Path(path)
        digest = sha256_file(p)
        rel = str(p.resolve()).replace(str(ROOT.parent) + os.sep, "")
        aid = artifact_id(rel, digest)
        self._write({"rec": "ARTIFACT", "id": aid, "path": rel, "sha256": digest,
                     "kind": kind, "desc": desc})
        return aid

    def close(self, status: str = "OK", note: str = "") -> None:
        if self._closed:
            return
        try:
            self._write({"rec": "RUN", "id": _digest("run_", [self.run, "CLOSE"]),
                         "event": "CLOSE", "task": "", "meta": {"status": status, "note": note}},
                        sync=True)
        finally:
            self._closed = True
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = -1

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close("ERROR" if exc_type else "OK", note=repr(exc) if exc else "")


# --------------------------------------------------------------------------- #
# Reading the ledger
# --------------------------------------------------------------------------- #

def read_file(path: Path, start: int = 0) -> list[dict]:
    """Parse complete lines from `start`. A trailing partial line is ignored."""
    return [r for r, _ in _scan(path, start)]


def _scan(path: Path, start: int = 0) -> Iterator[tuple[dict, int]]:
    """Yield (record, end_offset) for each complete line. end_offset is the byte offset
    just past the record's newline, so the caller can persist exactly what it consumed."""
    if not path.exists():
        return
    with open(path, "rb") as fh:
        fh.seek(start)
        buf = fh.read()
    cut = buf.rfind(b"\n")
    if cut < 0:
        return
    offset = start
    for raw in buf[: cut + 1].splitlines(keepends=True):
        offset += len(raw)
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # a malformed line is skipped, never fatal: the file is immutable
        if isinstance(rec, dict) and rec.get("rec") in REC_TYPES and "id" in rec:
            yield rec, offset


def ledger_files(ledger_dir: Path | None = None) -> list[Path]:
    d = Path(ledger_dir or LEDGER_DIR)
    return sorted(d.glob("*.jsonl")) if d.exists() else []


# --------------------------------------------------------------------------- #
# Sparse hashed TF-IDF (SMART lnc.ltc)
# --------------------------------------------------------------------------- #

_WORD = re.compile(r"[a-z0-9][a-z0-9._+-]*")


def features(text: str) -> dict[int, float]:
    """Word tokens plus character 3/4/5-grams, hashed into VEC_DIM buckets.

    D = 2**20 is affordable only because storage is sparse; a dense matrix at this D
    would need 1.3 GB for 10^4 docs, which is what pushed v1 to a colliding D = 2048.
    """
    norm = normalize(text)
    counts: dict[int, int] = {}

    def add(token: str) -> None:
        h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "little")
        slot = h % VEC_DIM
        counts[slot] = counts.get(slot, 0) + 1

    for m in _WORD.finditer(norm):
        add("w:" + m.group())
    packed = norm.replace(" ", "_")
    for n in (3, 4, 5):
        for i in range(len(packed) - n + 1):
            add("c:" + packed[i : i + n])
    # lnc: sublinear tf, no idf on the document side, L2 normalized.
    vec = {slot: 1.0 + math.log(c) for slot, c in counts.items()}
    norm_l2 = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {slot: v / norm_l2 for slot, v in vec.items()}


@dataclass
class VectorIndex:
    """Column-compressed sparse matrix: feats[f] owns rows[indptr[f]:indptr[f+1]]."""

    feats: np.ndarray      # int64[F], sorted unique feature slots
    indptr: np.ndarray     # int64[F+1]
    rows: np.ndarray       # int32[NNZ] -> item row
    vals: np.ndarray       # float32[NNZ]
    df: np.ndarray         # int32[F], document frequency per feature
    n_items: int

    @classmethod
    def build(cls, docs: Sequence[str]) -> "VectorIndex":
        per_doc = [features(d) for d in docs]
        by_feat: dict[int, list[tuple[int, float]]] = {}
        for row, vec in enumerate(per_doc):
            for slot, val in vec.items():
                by_feat.setdefault(slot, []).append((row, val))
        feats = np.array(sorted(by_feat), dtype=np.int64)
        indptr = np.zeros(len(feats) + 1, dtype=np.int64)
        rows_l: list[int] = []
        vals_l: list[float] = []
        df = np.zeros(len(feats), dtype=np.int32)
        for i, slot in enumerate(feats):
            entries = by_feat[int(slot)]
            df[i] = len(entries)
            for row, val in entries:
                rows_l.append(row)
                vals_l.append(val)
            indptr[i + 1] = len(rows_l)
        return cls(feats, indptr,
                   np.array(rows_l, dtype=np.int32), np.array(vals_l, dtype=np.float32),
                   df, len(docs))

    def score(self, query: str, mask: np.ndarray | None = None) -> np.ndarray:
        """Cosine against the ltc query vector. Returns float32[n_items]."""
        qvec = features(query)
        if not qvec or self.n_items == 0:
            return np.zeros(self.n_items, dtype=np.float32)
        slots = np.fromiter(qvec, dtype=np.int64, count=len(qvec))
        pos = np.searchsorted(self.feats, slots)
        pos = np.clip(pos, 0, max(len(self.feats) - 1, 0))
        hit = (len(self.feats) > 0) & (self.feats[pos] == slots)
        if not hit.any():
            return np.zeros(self.n_items, dtype=np.float32)

        slots, pos = slots[hit], pos[hit]
        # ltc: sublinear tf * idf on the query side only. This is SMART lnc.ltc, not a
        # symmetric IDF-weighted cosine -- stated plainly rather than claimed as exact.
        idf = np.log(self.n_items / np.maximum(self.df[pos], 1)) + 1.0
        qw = np.array([qvec[int(s)] for s in slots], dtype=np.float64) * idf
        qn = math.sqrt(float(np.dot(qw, qw))) or 1.0
        qw = (qw / qn).astype(np.float32)

        starts, ends = self.indptr[pos], self.indptr[pos + 1]
        widths = (ends - starts).astype(np.int64)
        if widths.sum() == 0:
            return np.zeros(self.n_items, dtype=np.float32)
        idx = np.concatenate([np.arange(s, e) for s, e in zip(starts, ends)])
        weights = self.vals[idx] * np.repeat(qw, widths)
        scores = np.bincount(self.rows[idx], weights=weights,
                             minlength=self.n_items).astype(np.float32)
        if mask is not None:
            scores = np.where(mask, scores, 0.0).astype(np.float32)
        return scores

    def save(self, path: Path) -> None:
        np.savez(path, feats=self.feats, indptr=self.indptr, rows=self.rows,
                 vals=self.vals, df=self.df, n_items=np.array([self.n_items]))

    @classmethod
    def load(cls, path: Path) -> "VectorIndex":
        z = np.load(path)
        return cls(z["feats"], z["indptr"], z["rows"], z["vals"], z["df"],
                   int(z["n_items"][0]))


# --------------------------------------------------------------------------- #
# Derived index
# --------------------------------------------------------------------------- #

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS offsets (
    path      TEXT PRIMARY KEY,
    consumed  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS item (
    row         INTEGER PRIMARY KEY AUTOINCREMENT,
    id          TEXT NOT NULL UNIQUE,
    agent       TEXT NOT NULL,
    run         TEXT NOT NULL,
    ts          INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    text        TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    locator     TEXT NOT NULL DEFAULT '',
    confidence  REAL NOT NULL,
    tags        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'ASSERTED',
    status_ts   INTEGER
);
CREATE INDEX IF NOT EXISTS ix_item_agent  ON item(agent);
CREATE INDEX IF NOT EXISTS ix_item_kind   ON item(kind);
CREATE INDEX IF NOT EXISTS ix_item_status ON item(status);
CREATE INDEX IF NOT EXISTS ix_item_ts     ON item(ts);

CREATE TABLE IF NOT EXISTS edge (
    id    TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    ts    INTEGER NOT NULL,
    src   TEXT NOT NULL,
    rel   TEXT NOT NULL,
    dst   TEXT NOT NULL,
    note  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_edge_src ON edge(src);
CREATE INDEX IF NOT EXISTS ix_edge_dst ON edge(dst);
CREATE INDEX IF NOT EXISTS ix_edge_rel ON edge(rel);

CREATE TABLE IF NOT EXISTS status_rec (
    id        TEXT PRIMARY KEY,
    agent     TEXT NOT NULL,
    ts        INTEGER NOT NULL,
    target    TEXT NOT NULL,
    status    TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    evidence  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_status_target ON status_rec(target);

CREATE TABLE IF NOT EXISTS artifact (
    id     TEXT PRIMARY KEY,
    agent  TEXT NOT NULL,
    ts     INTEGER NOT NULL,
    path   TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    kind   TEXT NOT NULL DEFAULT 'file',
    desc   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS run (
    id     TEXT PRIMARY KEY,
    agent  TEXT NOT NULL,
    ts     INTEGER NOT NULL,
    event  TEXT NOT NULL,
    task   TEXT NOT NULL DEFAULT '',
    meta   TEXT NOT NULL DEFAULT '{}'
);

-- text and tags only. claim_type and source_ref are filters, not FTS columns:
-- indexing a closed enum as text made a two-word query match a third of the corpus.
CREATE VIRTUAL TABLE IF NOT EXISTS item_fts USING fts5(
    text, tags, content='item', content_rowid='row', tokenize="unicode61"
);
"""

VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_refuted AS
SELECT i.id AS claim_id, i.agent AS claim_agent, i.text AS claim_text,
       s.agent AS refuted_by, s.rationale, s.ts AS refuted_ts,
       (SELECT group_concat(e.src, ' ') FROM edge e
         WHERE e.dst = i.id AND e.rel = 'REFUTES') AS refuting_claims
FROM item i JOIN status_rec s ON s.target = i.id
WHERE i.status = 'REFUTED' AND s.status = 'REFUTED';

CREATE VIEW IF NOT EXISTS v_dispute AS
SELECT target,
       sum(status = 'VERIFIED') AS n_verified,
       sum(status = 'REFUTED')  AS n_refuted,
       count(DISTINCT agent)    AS n_agents
FROM status_rec
WHERE status IN ('VERIFIED', 'REFUTED')
GROUP BY target
HAVING n_verified > 0 AND n_refuted > 0;
"""

# Later status wins; ties broken deterministically by rank so a fold is reproducible.
STATUS_RANK = {"ASSERTED": 0, "SUPERSEDED": 1, "VERIFIED": 2, "REFUTED": 3, "WITHDRAWN": 4}


class Index:
    """Derived, disposable. Rebuilt incrementally from consumed byte offsets."""

    def __init__(self, index_dir: Path | None = None, ledger_dir: Path | None = None):
        self.dir = Path(index_dir or INDEX_DIR)
        self.ledger_dir = Path(ledger_dir or LEDGER_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "derived.sqlite3"
        self.vec_path = self.dir / "vectors.npz"
        self.db = sqlite3.connect(self.db_path, timeout=30.0)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.executescript(VIEW_SQL)
        self._vec: VectorIndex | None = None
        self.stale = False

    # -- ingest -------------------------------------------------------------- #

    def sync(self, force: bool = False) -> dict[str, int]:
        """Ingest new bytes from every ledger file. Returns per-record-type counts.

        Guarded by a non-blocking lock. On contention the caller proceeds with a
        slightly stale index and `self.stale` is set -- staleness is a normal condition
        in a concurrent system, and crashing is not an acceptable response to it.
        """
        lock_path = self.dir / ".sync.lock"
        lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.stale = True
                return {}
            return self._sync_locked(force)
        finally:
            os.close(lock_fd)

    def _sync_locked(self, force: bool) -> dict[str, int]:
        if force:
            self.db.executescript(
                "DELETE FROM item; DELETE FROM edge; DELETE FROM status_rec;"
                "DELETE FROM artifact; DELETE FROM run; DELETE FROM offsets;"
                "DELETE FROM item_fts;"
            )
        offsets = {r["path"]: r["consumed"] for r in self.db.execute("SELECT * FROM offsets")}
        seen = {r["id"] for r in self.db.execute("SELECT id FROM item")}
        seen |= {r["id"] for r in self.db.execute("SELECT id FROM edge")}
        seen |= {r["id"] for r in self.db.execute("SELECT id FROM status_rec")}
        seen |= {r["id"] for r in self.db.execute("SELECT id FROM artifact")}
        seen |= {r["id"] for r in self.db.execute("SELECT id FROM run")}

        counts: dict[str, int] = {}
        touched_items = False
        for path in ledger_files(self.ledger_dir):
            key = path.name
            start = offsets.get(key, 0)
            size = path.stat().st_size
            if size < start:  # a ledger file must only grow; if it shrank, distrust it
                start = 0
            if size == start:
                continue
            consumed = start
            for rec, end in _scan(path, start):
                consumed = end
                rid = rec["id"]
                if rid in seen:  # global first-occurrence-wins; never a hard error
                    continue
                seen.add(rid)
                self._insert(rec)
                counts[rec["rec"]] = counts.get(rec["rec"], 0) + 1
                if rec["rec"] in ("CLAIM", "STATUS"):
                    touched_items = True
            self.db.execute(
                "INSERT INTO offsets(path, consumed) VALUES(?,?) "
                "ON CONFLICT(path) DO UPDATE SET consumed=excluded.consumed",
                (key, consumed),
            )
        if touched_items or force:
            self._fold_status()
        self.db.commit()
        if counts.get("CLAIM") or force:
            self._rebuild_vectors()
        return counts

    def _insert(self, rec: dict) -> None:
        t = rec["rec"]
        if t == "CLAIM":
            src = rec.get("source") or {}
            cur = self.db.execute(
                "INSERT INTO item(id,agent,run,ts,kind,text,source_type,source_ref,"
                "locator,confidence,tags) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rec["id"], rec["agent"], rec.get("run", ""), rec["ts"],
                 rec.get("kind", "note"), rec.get("text", ""),
                 src.get("type", ""), src.get("ref", ""), src.get("locator", ""),
                 float(rec.get("confidence", 0.5)), " ".join(rec.get("tags") or [])),
            )
            self.db.execute("INSERT INTO item_fts(rowid, text, tags) VALUES(?,?,?)",
                            (cur.lastrowid, rec.get("text", ""),
                             " ".join(rec.get("tags") or [])))
        elif t == "EDGE":
            self.db.execute(
                "INSERT INTO edge(id,agent,ts,src,rel,dst,note) VALUES(?,?,?,?,?,?,?)",
                (rec["id"], rec["agent"], rec["ts"], rec["src"], rec["rel"], rec["dst"],
                 rec.get("note", "")))
        elif t == "STATUS":
            self.db.execute(
                "INSERT INTO status_rec(id,agent,ts,target,status,rationale,evidence) "
                "VALUES(?,?,?,?,?,?,?)",
                (rec["id"], rec["agent"], rec["ts"], rec["target"], rec["status"],
                 rec.get("rationale", ""), " ".join(rec.get("evidence") or [])))
        elif t == "ARTIFACT":
            self.db.execute(
                "INSERT INTO artifact(id,agent,ts,path,sha256,kind,desc) VALUES(?,?,?,?,?,?,?)",
                (rec["id"], rec["agent"], rec["ts"], rec["path"], rec["sha256"],
                 rec.get("kind", "file"), rec.get("desc", "")))
        elif t == "RUN":
            self.db.execute(
                "INSERT INTO run(id,agent,ts,event,task,meta) VALUES(?,?,?,?,?,?)",
                (rec["id"], rec["agent"], rec["ts"], rec.get("event", "OPEN"),
                 rec.get("task", ""), json.dumps(rec.get("meta") or {}, sort_keys=True)))

    def _fold_status(self) -> None:
        """Latest status per target wins, ordered by (ts, rank, id) so it is reproducible."""
        self.db.execute("UPDATE item SET status='ASSERTED', status_ts=NULL")
        rows = self.db.execute(
            "SELECT target, status, ts, id FROM status_rec ORDER BY target, ts, id"
        ).fetchall()
        best: dict[str, tuple[int, int, str, str]] = {}
        for r in rows:
            key = (r["ts"], STATUS_RANK.get(r["status"], 0), r["id"])
            cur = best.get(r["target"])
            if cur is None or key > (cur[0], cur[1], cur[2]):
                best[r["target"]] = (r["ts"], STATUS_RANK.get(r["status"], 0), r["id"],
                                     r["status"])
        for target, (ts, _rank, _sid, status) in best.items():
            self.db.execute("UPDATE item SET status=?, status_ts=? WHERE id=?",
                            (status, ts, target))

    def _rebuild_vectors(self) -> None:
        rows = self.db.execute("SELECT row, text, tags FROM item ORDER BY row").fetchall()
        self._row_ids = [r["row"] for r in rows]
        docs = [f"{r['text']} {r['tags']}" for r in rows]
        vec = VectorIndex.build(docs)
        # np.savez appends '.npz' to any path that lacks it, so the temp name must
        # already end in '.npz' or the rename target will not be the file just written.
        tmp = self.vec_path.with_name(self.vec_path.stem + ".tmp.npz")
        vec.save(tmp)
        os.replace(tmp, self.vec_path)
        self._vec = vec
        self.db.execute(
            "INSERT INTO meta(key,value) VALUES('vec_rows',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(self._row_ids),))
        self.db.commit()

    @property
    def vectors(self) -> VectorIndex | None:
        if self._vec is None and self.vec_path.exists():
            self._vec = VectorIndex.load(self.vec_path)
            r = self.db.execute("SELECT value FROM meta WHERE key='vec_rows'").fetchone()
            self._row_ids = json.loads(r["value"]) if r else []
        return self._vec

    # -- search -------------------------------------------------------------- #

    def search(self, query: str, *, limit: int = 10, agent: str | None = None,
               kind: str | None = None, status: str | None = None,
               tag: str | None = None, as_of: int | None = None,
               expand: bool = False, boost: bool = False) -> list[dict]:
        """Hybrid BM25 + sparse cosine, fused by pure RRF.

        Priors do not multiply RRF. In v1 the prior product spanned 27.8x against RRF's
        4.3x, so the worst-relevance document outranked the best by 6.5x and ranking
        became a metadata sort. `boost` is an explicit, capped, off-by-default opt-in.
        """
        where, params = ["1=1"], []
        if agent:
            where.append("agent = ?"); params.append(agent)
        if kind:
            where.append("kind = ?"); params.append(kind)
        if status:
            where.append("status = ?"); params.append(status)
        if tag:
            where.append("(' ' || tags || ' ') LIKE ?"); params.append(f"% {tag} %")
        if as_of is not None:
            where.append("ts <= ?"); params.append(as_of)
        clause = " AND ".join(where)

        allowed = {r["row"]: dict(r) for r in self.db.execute(
            f"SELECT * FROM item WHERE {clause}", params)}
        if not allowed:
            return []

        lex_rank = self._lexical_ranks(query, clause, params)
        vec_rank = self._vector_ranks(query, set(allowed))

        fused: dict[int, float] = {}
        for ranks in (lex_rank, vec_rank):
            for row, rank in ranks.items():
                if row in allowed:
                    fused[row] = fused.get(row, 0.0) + 1.0 / (RRF_K + rank)
        if not fused:
            return []

        if boost:
            # Capped additive nudge: it can reorder within a relevance band, never across
            # one. max bonus is 12% of the best achievable RRF contribution.
            cap = 0.12 * (2.0 / (RRF_K + 1))
            for row in fused:
                it = allowed[row]
                b = {"VERIFIED": 1.0, "ASSERTED": 0.5, "SUPERSEDED": 0.1,
                     "REFUTED": 0.0, "WITHDRAWN": 0.0}.get(it["status"], 0.5)
                fused[row] += cap * (0.7 * b + 0.3 * float(it["confidence"]))

        out = [{**allowed[row], "score": s, "via": "direct"}
               for row, s in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))]

        if expand:
            out.extend(self._expand(out[:limit], allowed, {d["row"] for d in out}))
            out.sort(key=lambda d: (-d["score"], d["row"]))
        return out[:limit]

    def _lexical_ranks(self, query: str, clause: str, params: list) -> dict[int, int]:
        match = self._fts_query(query)
        if not match:
            return {}
        try:
            rows = self.db.execute(
                f"SELECT i.row FROM item_fts f JOIN item i ON i.row = f.rowid "
                f"WHERE item_fts MATCH ? AND {clause} ORDER BY bm25(item_fts, 1.0, 0.5) "
                f"LIMIT ?", [match, *params, CAND_LEX]).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {r["row"]: i + 1 for i, r in enumerate(rows)}

    @staticmethod
    def _fts_query(query: str) -> str:
        toks = [t for t in _WORD.findall(normalize(query)) if len(t) > 1]
        return " OR ".join(f'"{t}"' for t in toks)

    def _vector_ranks(self, query: str, allowed_rows: set[int]) -> dict[int, int]:
        vec = self.vectors
        if vec is None or vec.n_items == 0:
            return {}
        scores = vec.score(query)
        n = scores.shape[0]
        if n == 0:
            return {}
        # kth must be in range: v1 crashed on every corpus of <= 200 items.
        k = min(CAND_VEC, n - 1) if n > 1 else 0
        top = np.argpartition(-scores, k)[: k + 1] if n > 1 else np.array([0])
        top = top[np.argsort(-scores[top], kind="stable")]
        out: dict[int, int] = {}
        for i, idx in enumerate(top):
            if scores[idx] <= 0.0:
                continue  # masked/zero rows are dropped, not left to acquire ranks
            row = self._row_ids[int(idx)]
            if row in allowed_rows:
                out[row] = len(out) + 1
        return out

    def _expand(self, seeds: list[dict], allowed: dict[int, dict],
                already: set[int]) -> list[dict]:
        """One hop. Every Stage-A filter still applies, fan-out is capped, and an
        expanded node scores at half its seed so it can never outrank a direct hit."""
        by_id = {it["id"]: row for row, it in allowed.items()}
        out: list[dict] = []
        for seed in seeds:
            neighbours = self.db.execute(
                "SELECT dst AS other, rel FROM edge WHERE src = ? "
                "UNION ALL SELECT src AS other, rel FROM edge WHERE dst = ? LIMIT ?",
                (seed["id"], seed["id"], EXPANSION_FANOUT)).fetchall()
            for nb in neighbours:
                row = by_id.get(nb["other"])
                if row is None or row in already:
                    continue
                already.add(row)
                out.append({**allowed[row],
                            "score": seed["score"] * EXPANSION_DECAY,
                            "via": f"{seed['id']}-{nb['rel']}"})
        return out

    # -- provenance ---------------------------------------------------------- #

    def trace(self, claim: str) -> dict:
        item = self.db.execute("SELECT * FROM item WHERE id = ?", (claim,)).fetchone()
        if item is None:
            return {}
        return {
            "claim": dict(item),
            "status_history": [dict(r) for r in self.db.execute(
                "SELECT * FROM status_rec WHERE target = ? ORDER BY ts", (claim,))],
            "edges_out": [dict(r) for r in self.db.execute(
                "SELECT * FROM edge WHERE src = ? ORDER BY ts", (claim,))],
            "edges_in": [dict(r) for r in self.db.execute(
                "SELECT * FROM edge WHERE dst = ? ORDER BY ts", (claim,))],
        }

    def decided_status(self) -> dict[str, dict]:
        """The status record that DECIDED each claim's status, keyed by claim id.

        Folded by the identical key `sync` uses, so what a view prints can never disagree
        with the badge `item.status` produced. Read-only: this reports a decision somebody
        else filed, it never makes one.

        `write_views` needs the deciding record, not just the resulting word, because a
        badge is not a correction. A claim rendered with a glyph and nothing else tells a
        reader that something happened to it and not what -- and the reader who most needs
        to know is the one who arrived at that line from a search and will quote it.
        """
        best: dict[str, tuple] = {}
        for r in self.db.execute(
                "SELECT target, status, agent, rationale, evidence, ts, id "
                "FROM status_rec ORDER BY target, ts, id"):
            key = (r["ts"], STATUS_RANK.get(r["status"], 0), r["id"])
            cur = best.get(r["target"])
            if cur is None or key > cur[0]:
                best[r["target"]] = (key, dict(r))
        return {target: rec for target, (_key, rec) in best.items()}

    def refuted_with_evidence(self, tag: str | None = None) -> list[dict]:
        """R3: the multi-hop query, as a join over edges that were born structured."""
        sql = """
        SELECT i.id, i.text, i.agent AS claimed_by, i.tags,
               s.agent AS refuted_by, s.rationale,
               ref.text AS refuting_claim, ref.source_ref AS refuting_source,
               cited.source_ref AS cited_source
        FROM item i
        JOIN status_rec s ON s.target = i.id AND s.status = 'REFUTED'
        LEFT JOIN edge e   ON e.dst = i.id AND e.rel = 'REFUTES'
        LEFT JOIN item ref ON ref.id = e.src
        LEFT JOIN edge ce  ON ce.src = ref.id AND ce.rel = 'CITES'
        LEFT JOIN item cited ON cited.id = ce.dst
        WHERE i.status = 'REFUTED'
        """
        params: list = []
        if tag:
            sql += " AND (' ' || i.tags || ' ') LIKE ?"
            params.append(f"% {tag} %")
        return [dict(r) for r in self.db.execute(sql + " ORDER BY i.ts", params)]

    def stats(self) -> dict:
        q = lambda s: self.db.execute(s).fetchone()[0]
        return {
            "claims": q("SELECT count(*) FROM item"),
            "edges": q("SELECT count(*) FROM edge"),
            "status_records": q("SELECT count(*) FROM status_rec"),
            "artifacts": q("SELECT count(*) FROM artifact"),
            "runs": q("SELECT count(*) FROM run WHERE event='OPEN'"),
            "agents": q("SELECT count(DISTINCT agent) FROM item"),
            "verified": q("SELECT count(*) FROM item WHERE status='VERIFIED'"),
            "refuted": q("SELECT count(*) FROM item WHERE status='REFUTED'"),
            "withdrawn": q("SELECT count(*) FROM item WHERE status='WITHDRAWN'"),
            "superseded": q("SELECT count(*) FROM item WHERE status='SUPERSEDED'"),
            "disputed": q("SELECT count(*) FROM v_dispute"),
            "ledger_bytes": sum(p.stat().st_size for p in ledger_files(self.ledger_dir)),
            "vec_features": int(self.vectors.feats.shape[0]) if self.vectors else 0,
            "stale": self.stale,
        }

    def close(self) -> None:
        self.db.close()


# --------------------------------------------------------------------------- #
# Generated views
# --------------------------------------------------------------------------- #

BANNER = ("<!-- GENERATED FILE - do not edit. Source of truth: memory/ledger/*.jsonl\n"
          "     Regenerate: python3 memory/mem.py views -->\n")


def _decision_line(rec: dict | None) -> str:
    """The one line that travels with a claim whose status is no longer ASSERTED.

    Rendered as a CONTINUATION of the claim's own list item -- indented, no bullet -- and
    that is load-bearing rather than cosmetic. `memory/views/claims.md` renders 860 claims
    as consecutive list items with no blank line between them, so a withdrawal written as a
    nested bullet would start a new authored block and read as a separate entry: attached to
    the claim for a human skimming, detached for anything that parses blocks
    (`platform/retractions.py:block_around` is one such reader, and an earlier version of
    this file is the example in its docstring). A continuation line stays inside the item it
    corrects.

    Whitespace is collapsed because a rationale is free text and a newline inside it would
    break the item in exactly the way described above.
    """
    if not rec or rec["status"] == "ASSERTED":
        return ""
    why = " ".join((rec["rationale"] or "").split())
    return f"  **{rec['status']}** by `{rec['agent']}`" + (f": {why}" if why else "") + "  \n"


def write_views(idx: Index, views_dir: Path | None = None) -> list[Path]:
    """Byte-stable markdown mirror: no timestamps, no mtime-derived hashes, so a
    CI byte-comparison can actually pass (v1's banner made that impossible)."""
    d = Path(views_dir or VIEWS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    written = []

    s = idx.stats()
    lines = [BANNER, "# Memory index\n",
             f"- Claims: **{s['claims']}** across {s['agents']} agents",
             f"- Verified: **{s['verified']}** | Refuted: **{s['refuted']}** "
             f"| Withdrawn: **{s['withdrawn']}** | Superseded: **{s['superseded']}** "
             f"| Disputed: **{s['disputed']}**",
             f"- Edges: {s['edges']} | Status records: {s['status_records']} "
             f"| Artifacts: {s['artifacts']}", ""]
    for kind in CLAIM_KINDS:
        n = idx.db.execute("SELECT count(*) FROM item WHERE kind=?", (kind,)).fetchone()[0]
        if n:
            lines.append(f"  - `{kind}`: {n}")
    p = d / "INDEX.md"; p.write_text("\n".join(lines) + "\n"); written.append(p)

    rows = idx.db.execute(
        "SELECT * FROM item ORDER BY agent, kind, id").fetchall()
    decided = idx.decided_status()
    out = [BANNER, "# Claims\n"]
    cur = None
    for r in rows:
        if r["agent"] != cur:
            cur = r["agent"]; out.append(f"\n## {cur}\n")
        badge = {"VERIFIED": "✅", "REFUTED": "❌", "SUPERSEDED": "⤴️",
                 "WITHDRAWN": "🚫"}.get(r["status"], "•")
        src = f"{r['source_type']}:{r['source_ref']}" if r["source_ref"] else r["source_type"]
        out.append(f"- {badge} **[{r['kind']}]** {r['text']}  \n"
                   + _decision_line(decided.get(r["id"]))
                   + f"  `{r['id']}` · conf {r['confidence']:.2f} · source `{src}`"
                   + (f" · tags {r['tags']}" if r["tags"] else ""))
    p = d / "claims.md"; p.write_text("\n".join(out) + "\n"); written.append(p)

    dis = idx.db.execute("SELECT * FROM v_dispute").fetchall()
    out = [BANNER, "# Disputes\n",
           "Claims where independent agents disagree. Never auto-resolved: in a\n"
           "critical-review system the record of disagreement is the deliverable.\n"]
    if not dis:
        out.append("_No disputes._")
    for r in dis:
        it = idx.db.execute("SELECT * FROM item WHERE id=?", (r["target"],)).fetchone()
        out.append(f"\n## {r['target']}\n")
        if it:
            out.append(f"> {it['text']}\n")
        out.append(f"- verified by {r['n_verified']}, refuted by {r['n_refuted']}, "
                   f"{r['n_agents']} agents")
        for s in idx.db.execute("SELECT * FROM status_rec WHERE target=? ORDER BY ts",
                                (r["target"],)):
            out.append(f"  - **{s['status']}** by `{s['agent']}`: {s['rationale']}")
    p = d / "disputes.md"; p.write_text("\n".join(out) + "\n"); written.append(p)

    ref = idx.refuted_with_evidence()
    out = [BANNER, "# Refuted claims and their evidence\n"]
    if not ref:
        out.append("_Nothing refuted._")
    for r in ref:
        out.append(f"\n- ❌ **{r['text']}**  \n  `{r['id']}` claimed by `{r['claimed_by']}`, "
                   f"refuted by `{r['refuted_by']}`")
        if r["rationale"]:
            out.append(f"  - rationale: {r['rationale']}")
        if r["refuting_claim"]:
            out.append(f"  - refuting claim: {r['refuting_claim']}")
        if r["cited_source"]:
            out.append(f"  - cited evidence: `{r['cited_source']}`")
    p = d / "refuted.md"; p.write_text("\n".join(out) + "\n"); written.append(p)
    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _open_index() -> Index:
    idx = Index()
    idx.sync()
    return idx


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="mem", description="CBC-Memory provenance ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="append a claim")
    w.add_argument("--agent", required=True)
    w.add_argument("--text", required=True)
    w.add_argument("--kind", default="finding", choices=CLAIM_KINDS)
    w.add_argument("--source-type", default="reasoning")
    w.add_argument("--source-ref", default="")
    w.add_argument("--confidence", type=float, default=0.5)
    w.add_argument("--tags", default="")

    v = sub.add_parser("verify", help="mark a claim VERIFIED or REFUTED")
    v.add_argument("--agent", required=True)
    v.add_argument("--target", required=True)
    v.add_argument("--status", required=True, choices=STATUS_TYPES)
    v.add_argument("--rationale", default="")

    e = sub.add_parser("edge", help="append a typed edge")
    e.add_argument("--agent", required=True)
    e.add_argument("--src", required=True)
    e.add_argument("--rel", required=True, choices=REL_TYPES)
    e.add_argument("--dst", required=True)
    e.add_argument("--note", default="")

    s = sub.add_parser("search", help="hybrid BM25 + cosine search")
    s.add_argument("query")
    s.add_argument("-n", "--limit", type=int, default=10)
    s.add_argument("--agent"); s.add_argument("--kind", choices=CLAIM_KINDS)
    s.add_argument("--status", choices=STATUS_TYPES); s.add_argument("--tag")
    s.add_argument("--expand", action="store_true")
    s.add_argument("--boost", action="store_true")
    s.add_argument("--json", action="store_true")

    t = sub.add_parser("trace", help="full provenance for one claim")
    t.add_argument("claim")

    sub.add_parser("refuted", help="refuted claims with their refuting evidence")
    sub.add_parser("stats", help="index statistics")
    sub.add_parser("views", help="regenerate the markdown mirror")
    r = sub.add_parser("rebuild", help="rebuild the derived index")
    r.add_argument("--force", action="store_true")

    a = ap.parse_args(argv)

    if a.cmd in ("write", "verify", "edge"):
        with Ledger(a.agent, task=f"cli {a.cmd}") as led:
            if a.cmd == "write":
                cid = led.claim(a.text, kind=a.kind, source_type=a.source_type,
                                source_ref=a.source_ref, confidence=a.confidence,
                                tags=[x for x in a.tags.split(",") if x])
                print(cid)
            elif a.cmd == "verify":
                print(led.status(a.target, a.status, rationale=a.rationale))
            else:
                print(led.edge(a.src, a.rel, a.dst, note=a.note))
        return 0

    idx = _open_index()
    try:
        if a.cmd == "search":
            hits = idx.search(a.query, limit=a.limit, agent=a.agent, kind=a.kind,
                              status=a.status, tag=a.tag, expand=a.expand, boost=a.boost)
            if a.json:
                print(json.dumps(hits, indent=1, default=str)); return 0
            if not hits:
                print("no results"); return 0
            for i, h in enumerate(hits, 1):
                mark = {"VERIFIED": "✅", "REFUTED": "❌"}.get(h["status"], "•")
                print(f"{i:2d}. {mark} [{h['score']:.5f}] ({h['kind']}/{h['agent']}) "
                      f"{h['text'][:150]}")
                print(f"      {h['id']}  via={h['via']}  status={h['status']}")
        elif a.cmd == "trace":
            print(json.dumps(idx.trace(a.claim), indent=1, default=str))
        elif a.cmd == "refuted":
            print(json.dumps(idx.refuted_with_evidence(), indent=1, default=str))
        elif a.cmd == "stats":
            print(json.dumps(idx.stats(), indent=1))
        elif a.cmd == "views":
            for p in write_views(idx):
                print(p)
        elif a.cmd == "rebuild":
            print(json.dumps(idx.sync(force=a.force), indent=1))
    finally:
        idx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
