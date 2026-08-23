#!/usr/bin/env python3
"""Plant, in a scratch copy, the defect each guard exists to catch -- and fail the guard that shrugs.

    ./.venv/bin/python platform/tools/mutation_suite.py [--only <substring>] [--list] [-v]

WHY THIS FILE EXISTS
--------------------
Two guards were added to this repository to close one mechanism: a claim is minted once, fans
out across dozens of surfaces, is later withdrawn by a measurement made inside this same
repository, and survives on every surface the person making the correction was not looking at.

    platform/check_retractions.py      no surface may assert a withdrawn claim without its
                                       withdrawal travelling beside it
    platform/check_metadata_counts.py  no hand-typed slate count may disagree with the
                                       artefacts it summarises

Both print green today. So did the prose guard that used to run beside them, which reported
10 passed / 0 failed on a manuscript stating "8 pre-registered studies and 25 hypotheses"
while `data/` held 9 and 28 -- because every one of those numerals really was somewhere in
`data/`. That guard watched writing this repository no longer publishes and is no longer part
of it; the lesson it taught is why this file exists. A green line is
indistinguishable from a green line: the reader cannot tell whether the check examined the
surface and found nothing, or examined nothing.

This suite makes that distinction mechanical. For every slot below it plants the defect the
guard exists to catch in a scratch copy of the repository, runs the guard against that copy,
and requires the guard to FAIL and to name the file it failed on. A guard that passes its own
mutation is reported by name and fails this suite.

WHAT THE REAL PRODUCT IS
------------------------
The COVERAGE TABLE, not the mutations. The slots are enumerated FROM THE GUARDS' OWN CODE --
every entry of `check_retractions.SURFACES`, every entry of `check_metadata_counts.SURFACES`
and `.SURFACE_GLOBS`, every record in `retractions.jsonl`, and every count key in
`check_metadata_counts.RULES` and `.WORDED`. A surface added to a guard's watch list without a
mutation aimed at it is therefore reported UNCOVERED rather than silently omitted, which is the
only property that stops the next vacuous check: a mutation list written from memory goes
exactly as stale as the memory that wrote it.

STATUSES, and what each one means
---------------------------------
    CAUGHT       the guard was green on the clean copy and failed on the mutant, naming it.
                 Proven. This is the only status that counts as coverage.
    SURVIVED     the defect was planted and the guard still passed. The defect class.
    FALSE-FIRE   a mutation that must stay SILENT (an exemption, an escape hatch) made the
                 guard fail. Also the defect class, from the other side.
    UNCOVERED    the guard declares this slot and no mutation targets it.
    ANCHOR-LOST  the mutation could not be planted -- the file or text it edits is gone.
                 Proves nothing, and never counts as coverage.
    BASELINE-RED the guard was already failing on the clean copy, so its failure on the mutant
                 says nothing. Reported, never counted.
    UNPROVABLE   the slot cannot be reached from outside the guard, and the reason is stated.
                 Never counted as coverage, never hidden either.

WHAT IT NEVER DOES
------------------
It never writes to the repository. Every mutation goes to a scratch tree of real directories
and symlinks-to-files; the one file a mutation edits is materialised as a real copy first, so
the repository cannot be touched even by a mutation with a bug in it. Nothing here is run with
the repository as its root.

WHAT IT CANNOT REACH, STATED RATHER THAN PASSED OVER
----------------------------------------------------
* The CONTENT of the live GitHub About field. What that field says today is a fact about a
  server, and no offline check can decide it -- which is what `--remote` is for. This suite
  used to report the whole surface UNPROVABLE on those grounds, and that was one step too
  far: `gh` is resolved from PATH, so the suite supplies its own stub and proves the four
  things that ARE local -- a clean read is legible, an asserted retraction fails naming the
  surface, an empty field says it is empty, and a missing `gh` is still a SKIP rather than a
  pass. Nothing here touches the network.
* The three exempt directories are unreachable BY THE CURRENT SURFACE LISTS -- no glob in
  `check_retractions.SURFACES` descends into `prespec/`, `data/superseded/` or
  `memory/ledger/`, so planting a retracted sentence there is silent whether the exemption
  exists or not, and a mutation asserting that silence would prove nothing. They are proven
  differentially instead: the guard is run in-process with the surface list widened to reach
  the directory, once with the exemption in place and once with it removed. The exemption
  counts as proven only when the sentence is silent with it and caught without it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[1]
PY = str(REPO / ".venv" / "bin" / "python") if (REPO / ".venv" / "bin" / "python").exists() \
    else sys.executable

sys.path.insert(0, str(REPO / "platform"))
import check_metadata_counts as CM                                        # noqa: E402
import check_retractions as CR                                            # noqa: E402
import check_version_stamps as CVS                                        # noqa: E402
import retractions as R                                                   # noqa: E402

#: Never copied into a scratch tree: no guard reads them, and 507 run trees would make every
#: mutation cost a second.
SKIP_NAMES = {".git", ".venv", ".venv312", ".venvdockq", "runs", "__pycache__",
              "node_modules", ".DS_Store"}
SKIP_RELS = {"data/pae", "data/targets", "data/alphafold_db", "data/study_inputs"}


# --------------------------------------------------------------------------- #
# The scratch tree
# --------------------------------------------------------------------------- #

def shadow(dest: Path) -> Path:
    """A tree of real directories whose files are symlinks back to the repository.

    Real directories rather than symlinked ones, because `Path.glob` does not recurse
    through a symlinked directory -- `platform/**/*.py` would silently match nothing and
    every mutation aimed at a docstring would report CAUGHT-by-accident, or worse, SURVIVED
    for a reason that has nothing to do with the guard.
    """
    dest.mkdir(parents=True, exist_ok=True)

    def walk(src: Path, out: Path, rel: str) -> None:
        for child in sorted(src.iterdir()):
            r = f"{rel}/{child.name}".lstrip("/")
            if child.name in SKIP_NAMES or r in SKIP_RELS:
                continue
            target = out / child.name
            if child.is_dir() and not child.is_symlink():
                target.mkdir(exist_ok=True)
                walk(child, target, r)
            else:
                target.symlink_to(child.resolve())
    walk(REPO, dest, "")
    return dest


def materialise(scratch: Path, rel: str) -> Path:
    """Turn one symlinked file in the scratch tree into a real, writable copy."""
    p = scratch / rel
    if p.is_symlink():
        data = p.resolve().read_bytes()
        p.unlink()
        p.write_bytes(data)
    return p


# --------------------------------------------------------------------------- #
# Injectors -- one per shape of surface
# --------------------------------------------------------------------------- #

_COMMENT = {".py": "# {}", ".js": "// {}", ".css": "/* {} */", ".html": "<p>{}</p>",
            ".md": "\n{}\n", ".cff": "# {}"}


def inject(scratch: Path, rel: str, sentence: str) -> str | None:
    """Plant `sentence` in `rel`, in whatever shape that surface holds prose.

    Returns a note describing how, or None when the surface cannot carry it.
    """
    p = materialise(scratch, rel)
    suffix = p.suffix.lower()
    if suffix in (".docx", ".pptx"):
        return _inject_office(p, sentence)
    if suffix == ".json" or (suffix == ".js" and p.parent.name == "data"):
        return _inject_json(p, sentence)
    if suffix == ".jsonl":
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"mutation_suite_note": sentence}, ensure_ascii=False) + "\n")
        return f"appended a record to {rel}"
    text = p.read_text(encoding="utf-8", errors="replace")
    shape = _COMMENT.get(suffix, "{}")
    p.write_text(text.rstrip("\n") + "\n\n" + shape.format(sentence) + "\n", encoding="utf-8")
    return f"appended to {rel}"


def _inject_json(p: Path, sentence: str) -> str | None:
    """A new string field on the root object -- which carries no `retraction` key.

    That is the shape the defect actually had: `build_slate.py` copied a registered
    hypothesis statement into an object that had nowhere to put a withdrawal.
    """
    raw = p.read_text(encoding="utf-8")
    prefix = ""
    body = raw
    if p.suffix == ".js":
        m = CR._JS_ASSIGN.match(raw)
        if not m:
            return None
        prefix, body = raw[:m.end()], raw[m.end():].strip().rstrip(";").strip()
    try:
        doc = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(doc, dict):
        doc["mutation_suite_note"] = sentence
    elif isinstance(doc, list):
        doc.append({"mutation_suite_note": sentence})
    else:
        return None
    out = prefix + json.dumps(doc, indent=1, ensure_ascii=False) + (";\n" if prefix else "\n")
    p.write_text(out, encoding="utf-8")
    return f"added a string field to {p.name}"


def _inject_office(p: Path, sentence: str) -> str | None:
    """Into a real text run, so it survives the guard's tag-stripping the way authored text does."""
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            items = [(n, z.read(n)) for n in names]
    except (zipfile.BadZipFile, OSError):
        return None
    done = False
    out_items = []
    for n, data in items:
        carries_text = n == "word/document.xml" or (
            n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        if carries_text and not done:
            text = data.decode("utf-8", "replace")
            for close in ("</w:t>", "</a:t>"):
                if close in text:
                    text = text.replace(close, " " + sentence + close, 1)
                    done = True
                    break
            data = text.encode("utf-8")
        out_items.append((n, data))
    if not done:
        return None
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in out_items:
            z.writestr(n, data)
    return f"added a text run to {p.name}"


# --------------------------------------------------------------------------- #
# Running a guard against a scratch tree
# --------------------------------------------------------------------------- #

GUARDS = {
    "check_retractions": [PY, str(REPO / "platform" / "check_retractions.py"), "--quiet"],
    "check_metadata_counts": [PY, str(REPO / "platform" / "check_metadata_counts.py")],
    "check_version_stamps": [PY, str(REPO / "platform" / "check_version_stamps.py")],
}


def run_guard(guard: str, root: Path) -> tuple[int, str]:
    cmd = GUARDS[guard] + ["--root", str(root)]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


# --------------------------------------------------------------------------- #
# Slots and mutations
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Slot:
    """One thing a guard claims to be able to catch."""
    guard: str
    kind: str          # "surface" | "record" | "rule" | "join" | "exemption" | "binding"
    name: str
    detail: str = ""

    @property
    def key(self) -> str:
        return f"{self.guard}::{self.kind}::{self.name}"


@dataclass
class Mutation:
    slot: Slot
    ident: str
    plant: object                      # (scratch) -> note | None
    must: str = "fail"                 # "fail" | "stay-silent"
    expect_in_output: str = ""
    note: str = ""


@dataclass
class Result:
    slot: Slot
    ident: str
    status: str
    detail: str = ""
    seconds: float = 0.0
    collateral: list[str] = field(default_factory=list)


#: The claim used for every surface-reachability mutation. Short, unambiguous, and the exact
#: sentence that is registered in `prespec/peptide-interface-v1.515be79a7d12.json` and was
#: rendered as a live green CONFIRMED on the front page.
RETRACTED_SENTENCE = "ipTM predicts whether the interface is right, " \
                     "so it can be used as a screening filter."

#: The stale count, in the word form that let it survive a repository full of numeric guards.
STALE_COUNT_SENTENCE = "Eight studies were pre-registered under content hashes before any " \
                       "data was seen."


def first_match(pattern: str) -> str | None:
    for p in sorted(REPO.glob(pattern)):
        if not p.is_file():
            continue
        rel = str(p.relative_to(REPO))
        if CR.is_exempt(rel) or rel in CR.EXEMPT_FILES:
            continue
        return rel
    return None


def retraction_surface_mutations() -> list[Mutation]:
    """One per entry of `check_retractions.SURFACES`. The list is the guard's promise."""
    out: list[Mutation] = []
    for pattern in CR.SURFACES:
        slot = Slot("check_retractions", "surface", pattern,
                    "a withdrawn claim published here must be caught")
        rel = first_match(pattern)
        if rel is None:
            out.append(Mutation(slot, f"ret-surface:{pattern}",
                                plant=lambda _s: None,
                                note="no file in the repository matches this pattern"))
            continue
        out.append(Mutation(
            slot, f"ret-surface:{rel}",
            plant=lambda s, rel=rel: inject(s, rel, RETRACTED_SENTENCE),
            expect_in_output=rel))
    return out


def retraction_record_mutations() -> list[Mutation]:
    """One per record in `retractions.jsonl`: a record that cannot recognise its own claim
    is a dead letter, and would leave the claim it names free to be republished."""
    out: list[Mutation] = []
    for rec in R.load(REPO / "retractions.jsonl"):
        slot = Slot("check_retractions", "record", rec.id, rec.claim[:80])
        matched = list(rec.search(rec.claim))
        if not matched:
            out.append(Mutation(slot, f"ret-record:{rec.id}", plant=lambda _s: None,
                                note="this record's fingerprints do not match its own claim "
                                     "text, so no mutation can be derived from it"))
            continue
        text = matched[0].group(0)
        out.append(Mutation(
            slot, f"ret-record:{rec.id}",
            plant=lambda s, t=text: inject(s, "README.md", t),
            expect_in_output=rec.id))
    return out


def _slate_hypothesis_without_fingerprint(root: Path) -> tuple[str, str] | None:
    """A (study, hypothesis) whose reading limit is the ONLY thing a scan could see.

    Study #7's H2 statement carries `ret_0002`'s fingerprint, so deleting its reading limit
    is caught by the text scan and proves nothing about the anchor check. The anchors that
    matter are the ones whose statement matches nothing -- study #10's H2 says "at least one
    candidate is both better than its null and confident in absolute terms", which is not the
    withdrawn sentence. Delete that join and every scan passes.
    """
    slate = json.loads((root / "data" / "slate.json").read_text())
    recs = R.load(root / "retractions.jsonl")
    by_study = {s.get("study_id"): s for s in slate.get("studies", [])}
    for rec in recs:
        for a in rec.anchors:
            if a.get("kind") != "decision_rule":
                continue
            st = by_study.get(a.get("study"))
            if not st:
                continue
            for h in st.get("hypotheses", []):
                if h.get("name") != a.get("hypothesis"):
                    continue
                blob = json.dumps({k: v for k, v in h.items()
                                   if k not in ("reading_limit",)}, ensure_ascii=False)
                if not any(r.search(blob) for r in recs):
                    return a["study"], a["hypothesis"]
    return None


def drop_reading_limit(scratch: Path) -> str | None:
    found = _slate_hypothesis_without_fingerprint(scratch)
    if not found:
        return None
    study, hyp = found
    p = materialise(scratch, "data/slate.json")
    doc = json.loads(p.read_text())
    for s in doc.get("studies", []):
        if s.get("study_id") != study:
            continue
        for h in s.get("hypotheses", []):
            if h.get("name") == hyp:
                h.pop("reading_limit", None)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return f"deleted the reading limit on {study}/{hyp}"


def drop_plan_field_correction(scratch: Path) -> str | None:
    """The half-drop the text scan cannot see.

    A republished plan field carries the withdrawn wording, so deleting the join outright
    fails on the text. This deletes only the RENDERING -- the correction block beside the
    field -- and leaves the record id in the study's `retractions` list, which is exactly
    what a generator refactor would do by accident. Every scan passes; the page prints the
    stale count alone. Only check_plan_fields_landed can fail on it.
    """
    recs = R.load(scratch / "retractions.jsonl")
    wanted = [(r, a) for r in recs for a in r.anchors if a.get("kind") == "plan_field"]
    if not wanted:
        return None
    r, a = wanted[0]
    p = materialise(scratch, "data/slate.json")
    doc = json.loads(p.read_text())
    hit = False
    for st in doc.get("studies", []):
        if st.get("study_id") == a["study"]:
            hit = st.pop(f"{a['field']}_correction", None) is not None
    if not hit:
        return None
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return f"deleted the correction beside {a['study']}/{a['field']}, leaving {r.id} " \
           "in the study's retractions list"


def drop_withdrawal_line(scratch: Path) -> str | None:
    """Remove the withdrawal that travels with a claim in the generated ledger view."""
    p = materialise(scratch, "memory/views/claims.md")
    lines = p.read_text().splitlines()
    for i, line in enumerate(lines):
        if "biotin, biocytin and HABA binding" in line:
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j].lstrip().startswith("**WITHDRAWN**"):
                    del lines[j]
                    p.write_text("\n".join(lines) + "\n")
                    return "deleted the WITHDRAWN continuation line from claims.md"
    return None


def acknowledge_in_place(scratch: Path) -> str | None:
    """The other direction: a retracted sentence WITH its withdrawal must stay silent."""
    p = materialise(scratch, "data/slate.json")
    doc = json.loads(p.read_text())
    doc["mutation_suite_note"] = RETRACTED_SENTENCE
    doc["retraction"] = {"id": "ret_0002", "why": "planted by the mutation suite to prove "
                                                  "that an acknowledged claim is not a hit"}
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return "planted the sentence beside a `retraction` field naming ret_0002"


def corrupt_ledger(scratch: Path) -> str | None:
    """A malformed retraction record must stop the guard, not be skipped past."""
    p = materialise(scratch, "retractions.jsonl")
    out = []
    dropped = False
    for line in p.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not dropped:
            rec = json.loads(s)
            rec.pop("replacement", None)
            line = json.dumps(rec, ensure_ascii=False)
            dropped = True
        out.append(line)
    if not dropped:
        return None
    p.write_text("\n".join(out) + "\n")
    return "removed the `replacement` field from the first record"


def exemption_mutations() -> list[Mutation]:
    """Differential, because these directories are not reachable from the surface lists.

    Planting a retracted sentence in `prespec/` is silent whether or not the exemption
    exists, so silence alone proves nothing. Each of these runs the guard IN PROCESS with the
    surface list widened to reach the directory: once with the exemption in place, where the
    sentence must be silent, and once with it removed, where it must be caught. Only both
    together prove the exemption is what produced the silence.
    """
    out: list[Mutation] = []
    for directory, _why in CR.EXEMPT_DIRS:
        slot = Slot("check_retractions", "exemption", directory,
                    "a record of what was registered or believed is never rewritten")
        out.append(Mutation(slot, f"ret-exempt:{directory}", plant=lambda _s: None,
                            note="differential, run in process"))
    return out


def run_exemption(directory: str, scratch: Path) -> tuple[str, str]:
    """(status, detail) for one exemption, proven differentially."""
    target = None
    for pat in (f"{directory}/*.json", f"{directory}/*.jsonl", f"{directory}/*.md"):
        hits = sorted(scratch.glob(pat))
        if hits:
            target = str(hits[0].relative_to(scratch))
            break
    if target is None:
        return "ANCHOR-LOST", f"no file under {directory}/ to plant in"
    note = inject(scratch, target, RETRACTED_SENTENCE)
    if note is None:
        return "ANCHOR-LOST", f"could not plant a sentence in {target}"

    widened = CR.SURFACES + (f"{directory}/*.json", f"{directory}/*.jsonl",
                             f"{directory}/*.md")
    saved_surfaces, saved_exempt = CR.SURFACES, CR.EXEMPT_DIRS
    try:
        CR.SURFACES = widened
        with_exemption, _, _, _ = CR.run(scratch)
        CR.EXEMPT_DIRS = tuple(d for d in saved_exempt if d[0] != directory)
        without, _, _, _ = CR.run(scratch)
    finally:
        CR.SURFACES, CR.EXEMPT_DIRS = saved_surfaces, saved_exempt

    silent = [h for h in with_exemption if h.path.startswith(directory)]
    caught = [h for h in without if h.path.startswith(directory)]
    if silent:
        return "FALSE-FIRE", (f"{target} was reported even though {directory}/ is exempt")
    if not caught:
        return "SURVIVED", (f"removing the {directory}/ exemption did not surface the "
                            f"sentence planted in {target}, so the exemption is not what "
                            "produces the silence -- the surface list never reaches it")
    return "CAUGHT", (f"silent with the exemption, {len(caught)} hit(s) without it "
                      f"({target})")


def metadata_surface_mutations() -> list[Mutation]:
    """One per surface family the count guard watches."""
    out: list[Mutation] = []
    families = [(s, s) for s in CM.SURFACES]
    for pattern in CM.SURFACE_GLOBS:
        head, _, tail = pattern.partition("/")
        hits = sorted((REPO / head).glob(tail))
        families.append((pattern, str(hits[0].relative_to(REPO)) if hits else None))
    for name, rel in families:
        slot = Slot("check_metadata_counts", "surface", name,
                    "a stale slate count typed here must be caught")
        if rel is None or not (REPO / rel).is_file():
            out.append(Mutation(slot, f"cnt-surface:{name}", plant=lambda _s: None,
                                note="no file in the repository matches this surface"))
            continue
        out.append(Mutation(
            slot, f"cnt-surface:{rel}",
            plant=lambda s, rel=rel: inject(s, rel, STALE_COUNT_SENTENCE),
            expect_in_output=rel))
    return out


def bump_slate_count(scratch: Path) -> str | None:
    p = materialise(scratch, "data/slate.json")
    doc = json.loads(p.read_text())
    doc["counts"]["studies"] = doc["counts"]["studies"] + 1
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return "moved slate.json counts.studies by one without touching any surface"


def add_plan(scratch: Path) -> str | None:
    (scratch / "prespec").mkdir(exist_ok=True)
    (scratch / "prespec" / "zz-mutation-suite.json").write_text(
        json.dumps({"note": "planted by the mutation suite"}, indent=1) + "\n")
    return "added a 28th file to prespec/ without touching any surface"


def add_suite(scratch: Path) -> str | None:
    """A tenth suite makes every 'N suites' sentence stale in the same commit that adds it."""
    p = materialise(scratch, "verify_all.py")
    text = p.read_text()
    marker = "\n]\n"
    if marker not in text:
        return None
    entry = ('    ("Mutation-suite placeholder", [PY, "platform/tools/mutation_suite.py"], 0,\n'
             '     "planted by the mutation suite"),\n')
    text = text.replace(marker, "\n" + entry + "]\n", 1)
    p.write_text(text)
    return "appended a suite to verify_all.SUITES without correcting the surfaces that count them"


def historical_marker(scratch: Path) -> str | None:
    p = materialise(scratch, "docs/REGISTRATION.md")
    text = p.read_text()
    p.write_text(text.rstrip("\n") + "\n\n" + STALE_COUNT_SENTENCE
                 + f" <!-- {CM.EXEMPT_TOKEN}: planted by the mutation suite -->\n")
    return "planted the same stale sentence behind the one escape hatch"


def numeral_form(scratch: Path) -> str | None:
    return inject(scratch, ".zenodo.json", "8 pre-registered studies, 25 hypotheses")


def nominalised_form(scratch: Path) -> str | None:
    """The noun, not the participle. `README.md` said "including the eleven falsifications"
    while every rule in the guard was matching "N falsified", and the count was two out of
    date. The whole nominalised half of the vocabulary was added after that; this plants the
    shape rather than the one instance, so the family is proven and not the example."""
    return inject(scratch, "CITATION.cff",
                  "The slate records 11 confirmations, 9 falsifications and 3 untested "
                  "hypotheses across 7 pre-registrations.")


def roster_form(scratch: Path) -> str | None:
    """README.md line 90 -- the first quantitative sentence a visitor reads -- states the
    hypothesis count and the decided count in the same breath as the study count, and neither
    was bound: the loose `hypotheses` rule is excluded on README because three real sentences
    in that file count ONE study's three. This is the phrasing that cannot be per-study."""
    return inject(scratch, "README.md",
                  "| Study reporting | 8 pre-registered studies, 25 hypotheses of which "
                  "22 are decided | planted by the mutation suite |")


def unclassified_file(scratch: Path) -> str | None:
    """A new text file that is neither on a surface list nor in UNWATCHED.

    This is the derived half of the guard, and the only slot here that is not about what a
    file SAYS. `app.js`, `index.html` and `verify_all.py` each carried a stale count for
    months on a surface nobody had decided about; the content rules could not have caught any
    of them, because the files were never opened. The file planted below says nothing at all.
    It must fail the guard anyway."""
    (scratch / "docs").mkdir(exist_ok=True)
    (scratch / "docs" / "ZZ_MUTATION_NOTES.md").write_text(
        "# A new document\n\nIt states no count. That is not the point.\n")
    return "added docs/ZZ_MUTATION_NOTES.md, which no surface list and no exemption covers"


def exempted_file(scratch: Path) -> str | None:
    """The other side of the same rule: a file under a stated exemption must stay silent.

    Without this, the coverage check could be satisfied by failing on everything, which is
    the same as failing on nothing."""
    (scratch / "reviews").mkdir(exist_ok=True)
    (scratch / "reviews" / "zz_mutation_review.json").write_text(
        '{"finding": "the slate holds 8 pre-registered studies", "verdict": "stale"}\n')
    return ("added reviews/zz_mutation_review.json, quoting a stale count, under the "
            "`reviews/*` exemption")


def special_mutations() -> list[Mutation]:
    return [
        Mutation(Slot("check_retractions", "join", "reading_limit lands on the page",
                      "a withdrawn READING has no text to scan; only the join can be checked"),
                 "ret-join:drop-reading-limit", plant=drop_reading_limit,
                 expect_in_output="reading limit"),
        Mutation(Slot("check_retractions", "join", "plan-field correction lands on the page",
                      "the wording is quoted as registered, so only the join carries the "
                      "corrected count"),
                 "ret-join:drop-plan-field-correction", plant=drop_plan_field_correction,
                 expect_in_output="correction"),
        Mutation(Slot("check_retractions", "rule", "withdrawal must travel with the claim",
                      "the generated ledger view is a rendering, and a rendering is never exempt"),
                 "ret-rule:drop-withdrawal-line", plant=drop_withdrawal_line,
                 expect_in_output="memory/views/claims.md"),
        Mutation(Slot("check_retractions", "rule", "an acknowledged claim is not a hit",
                      "the guard must not force a withdrawn sentence out of existence"),
                 "ret-rule:acknowledged-in-place", plant=acknowledge_in_place,
                 must="stay-silent"),
        Mutation(Slot("check_retractions", "rule", "a malformed ledger stops the guard",
                      "a record the loader cannot read must never be skipped past"),
                 "ret-rule:corrupt-ledger", plant=corrupt_ledger,
                 expect_in_output="replacement"),
        Mutation(Slot("check_metadata_counts", "binding", "data/slate.json counts",
                      "the expected values are read from the artefacts, never typed"),
                 "cnt-bind:slate-counts", plant=bump_slate_count,
                 expect_in_output="artefacts say"),
        Mutation(Slot("check_metadata_counts", "binding", "len(glob('prespec/*.json'))",
                      "the plan count is the directory, not a number in a sentence"),
                 "cnt-bind:prespec-count", plant=add_plan,
                 expect_in_output="plans"),
        Mutation(Slot("check_metadata_counts", "binding", "len(verify_all.SUITES)",
                      "adding a suite makes every sentence that counts them stale"),
                 "cnt-bind:suite-count", plant=add_suite,
                 expect_in_output="suites"),
        Mutation(Slot("check_metadata_counts", "rule", "the number-word half",
                      "three of the four metadata files spelled it 'Eight'"),
                 "cnt-rule:numeral-form", plant=numeral_form,
                 expect_in_output=".zenodo.json"),
        Mutation(Slot("check_metadata_counts", "rule", CM.EXEMPT_TOKEN,
                      "exactly one escape hatch, and it must work"),
                 "cnt-rule:historical-marker", plant=historical_marker,
                 must="stay-silent"),
    ]


# --------------------------------------------------------------------------- #
# check_version_stamps: the two kinds of stamp, and the state that separates them
# --------------------------------------------------------------------------- #
#
# The slots are enumerated from `CVS.stamps(REPO)` -- the guard's own reading of the tree --
# so a surface it starts watching without a mutation aimed at it reports UNCOVERED. The
# mutations come in matched pairs, because this guard is the first one here whose two rules
# pull in opposite directions and a suite that only proved one of them would license exactly
# the wrong repair:
#
#   identity  a stamp that describes THIS TREE is moved off VERSION            -> must fail
#   pinned    a stamp frozen to a PUBLISHED deposit is relabelled to VERSION   -> must fail
#
# The second is the naive fix for the first. `sed -i s/1.0.0/1.1.0/` on the six metadata
# files would have made the identity half green and made the repository assert that Zenodo
# DOI 10.5281/zenodo.22032685 names bytes it will never name.

BOGUS = "9.9.9"


def _cur(root: Path) -> str:
    return (root / "VERSION").read_text().strip()


def _sub_file(scratch: Path, rel: str, old: str, new: str) -> str | None:
    p = materialise(scratch, rel)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        return None
    p.write_text(text.replace(old, new), encoding="utf-8")
    return f"{rel}: {old!r} -> {new!r}"


def _json_at(scratch: Path, rel: str, edit) -> str | None:
    """Edit a JSON (or `const x = {...};` JS) surface in place, keeping its wrapper."""
    p = materialise(scratch, rel)
    raw = p.read_text(encoding="utf-8")
    prefix, body, suffix = "", raw, ""
    if rel.endswith(".js"):
        i = raw.find("{")
        prefix, body = raw[:i], raw[i:].rstrip()
        if body.endswith(";"):
            body, suffix = body[:-1], ";"
    doc = json.loads(body)
    note = edit(doc)
    if note is None:
        return None
    p.write_text(prefix + json.dumps(doc, indent=1, ensure_ascii=False) + suffix + "\n",
                 encoding="utf-8")
    return f"{rel}: {note}"


def _identity_mutation(rel: str, scratch: Path) -> str | None:
    """Move every stamp on `rel` that describes this tree off VERSION."""
    cur = _cur(scratch)
    if rel == "CITATION.cff":
        return _sub_file(scratch, rel, f"\nversion: {cur}\n", f"\nversion: {BOGUS}\n")
    if rel == "README.md":
        return _sub_file(scratch, rel, f"(Version {cur})", f"(Version {BOGUS})")
    if rel == "docs/REGISTRATION.md":
        return _sub_file(scratch, rel, f"./release.sh {cur}", f"./release.sh {BOGUS}")
    if rel in ("codemeta.json", ".zenodo.json"):
        def edit(d):
            d["version"] = BOGUS
            if "releaseNotes" in d:
                d["releaseNotes"] = d["releaseNotes"].replace(f"v{cur}", f"v{BOGUS}")
            return f"version -> {BOGUS}"
        return _json_at(scratch, rel, edit)
    if rel == "biotools.json":
        return _json_at(scratch, rel, lambda d: (d.__setitem__("version", [BOGUS]),
                                                 f"version[] -> {BOGUS}")[1])
    if rel.startswith("data/dataset."):
        def edit(d):
            d["citation"]["version"] = BOGUS
            return f"citation.version -> {BOGUS}"
        return _json_at(scratch, rel, edit)
    return None


def _is_published(scratch: Path) -> bool:
    """Is VERSION itself a published release?

    The repository is legitimately in one of two states and the mutations below are not the
    same in each. IN PREPARATION, `VERSION` names a version with no tag and no DOI: the
    disclosure sentence is required, and the pinned stamps name the PREVIOUS release.
    PUBLISHED, `VERSION` names the release that was just cut: the disclosure must be gone,
    and the pinned stamps name `VERSION` itself -- not because anyone relabelled them, but
    because Zenodo minted that DOI for that release.

    This suite used to assume the first state only, so closing a release silently disarmed
    fourteen of its own slots: five pinned mutations became no-ops (`v1.1.0` -> `v1.1.0`) and
    nine anchors vanished with the sentence they edited. A mutation suite that stops biting
    the moment the release procedure is followed is a mutation suite that proves nothing at
    exactly the moment the citation surfaces change.
    """
    return _cur(scratch) in CVS.published_versions(scratch)


def _pinned_mutation(rel: str, scratch: Path) -> str | None:
    """Point a pinned reference at a version it cannot name.

    IN PREPARATION that is the naive repair -- relabel the frozen deposit to follow VERSION.
    PUBLISHED, the naive repair is not expressible: the pin already equals VERSION, so the
    substitution is the identity and mutates nothing. The rule underneath is the same either
    way -- a pinned reference must name a release that exists -- so in that state the pin is
    moved to a version that was never published.
    """
    cur = _cur(scratch)
    pub = CVS.published_versions(scratch)
    if not pub:
        return None
    pin = pub[-1]
    target = BOGUS if pin == cur else cur
    why = ("relabelled to follow VERSION" if target == cur
           else "moved to a version that was never published")
    if rel in ("CITATION.cff", "README.md"):
        return _sub_file(scratch, rel, f"fixed to v{pin}", f"fixed to v{target}")
    if rel == "biotools.json":
        def edit(d):
            for dl in d.get("download") or []:
                dl["url"] = dl["url"].replace(f"v{pin}", f"v{target}")
                dl["version"] = target
            for o in d.get("otherID") or []:
                if isinstance(o.get("version"), str):
                    o["version"] = o["version"].replace(f"v{pin}", f"v{target}")
            return f"download and otherID v{pin} -> v{target} ({why})"
        return _json_at(scratch, rel, edit)
    if rel.startswith("data/dataset."):
        def edit(d):
            for i in d["citation"].get("identifiers") or []:
                if isinstance(i.get("description"), str):
                    i["description"] = i["description"].replace(f"v{pin}", f"v{target}")
            return f"version-DOI description v{pin} -> v{target} ({why})"
        return _json_at(scratch, rel, edit)
    return None


def _plant_stale_disclosure(rel: str, scratch: Path) -> str | None:
    """Leave the undeposited-version sentence behind on a surface after the deposit exists.

    This is the defect the release procedure actually produces. `release.sh` ends by telling
    the author to delete the sentence from seven surfaces by hand, which is six chances to
    delete it from six. The sentence planted is the one that was true yesterday, so the
    surface reads "not yet deposited" about a version that now has a DOI.
    """
    cur = _cur(scratch)
    pub = [v for v in CVS.published_versions(scratch) if v != cur]
    sentence = CVS.disclosure(cur, pub[-1] if pub else "0.0.0")
    if rel.endswith((".md", ".cff")):
        p = materialise(scratch, rel)
        marker = "# " if rel.endswith(".cff") else ""
        p.write_text(p.read_text(encoding="utf-8").rstrip("\n")
                     + f"\n\n{marker}{sentence}\n", encoding="utf-8")
        return f"{rel}: stale disclosure appended"

    # JSON and the JS shim carry prose in string fields; appending raw text would break the
    # parse and report as a crash rather than as the guard catching anything.
    def edit(d):
        if "citation" in d and isinstance(d["citation"].get("note"), str):
            d["citation"]["note"] += " " + sentence
        elif isinstance(d.get("description"), str):
            d["description"] += " " + sentence
        else:
            return None
        return "stale disclosure appended to a prose field"
    return _json_at(scratch, rel, edit)


def _disclosure_mutation(rel: str, scratch: Path) -> str | None:
    """Break the disclosure rule on `rel`, in whichever direction this state admits.

    IN PREPARATION the sentence is required, so it is REWORDED rather than removed: a guard
    that only noticed a missing paragraph would pass on a surface where someone softened the
    wording and left the version number behind. PUBLISHED there is no sentence to lose, and
    the rule runs the other way -- the sentence must be ABSENT -- so one is planted.
    """
    if _is_published(scratch):
        return _plant_stale_disclosure(rel, scratch)
    return _sub_file(scratch, rel, "is not yet deposited", "is the current version")


def _bump_version(scratch: Path) -> str | None:
    cur = _cur(scratch)
    major, minor, patch = (int(x) for x in cur.split("."))
    p = materialise(scratch, "VERSION")
    p.write_text(f"{major}.{minor + 1}.{patch}\n", encoding="utf-8")
    return f"VERSION {cur} -> {major}.{minor + 1}.{patch}, touching no metadata surface"


def _toggle_current_note(scratch: Path) -> str | None:
    """Flip this version's note between GENERATED and FROZEN, and change nothing else.

    That single edit is what decides whether `VERSION` counts as published, so it must move
    the disclosure rule in whichever direction the tree is currently sitting: freezing an
    unpublished version's note makes the sentence on seven surfaces false, and unfreezing a
    published version's note makes its absence a defect. It is the binding test for the
    published set -- if the guard read a hand-written release list instead of the notes,
    nothing here would move in either direction.
    """
    cur = _cur(scratch)
    rel = f"docs/RELEASE_NOTES_v{cur}.md"
    if _is_published(scratch):
        return _sub_file(scratch, rel, "<!-- RELEASE-NOTE-FROZEN", "<!-- RELEASE-NOTE-GENERATED")
    return _sub_file(scratch, rel, "<!-- RELEASE-NOTE-GENERATED", "<!-- RELEASE-NOTE-FROZEN")


def _walk_the_release_path(scratch: Path) -> str | None:
    """The whole release path, executed, in whichever direction this state admits.

    Must stay SILENT. Without this the suite would only ever have shown the guard failing,
    and a guard that cannot go green after the work is done is a guard the author routes
    around. Both endpoints of the path are legitimate states and both must be accepted:

    IN PREPARATION -> PUBLISHED: freeze the note and remove the disclosure everywhere. The
    pinned stamps still name the previous release here and must still be accepted -- they
    name a release that exists, and that is the whole rule.

    PUBLISHED -> IN PREPARATION: the same tree one step earlier, rebuilt. Unfreezing the note
    alone does NOT produce it and must not be mistaken for it -- that leaves a version DOI
    saying "fixed to v1.1.0" in a tree claiming v1.1.0 was never released, which is
    incoherent, and the guard is right to reject it. The pre-release state is the whole
    triple: the note unfrozen, the pinned stamps naming the PREVIOUS release, and the
    disclosure back on every surface. Reconstructing it proves the guard accepts the state a
    release starts from as well as the one it ends in.
    """
    cur = _cur(scratch)
    if _is_published(scratch):
        pub = CVS.published_versions(scratch)
        if len(pub) < 2:
            return None       # no earlier release to pin to; the state is not constructible
        prev = pub[-2]
        if _toggle_current_note(scratch) is None:
            return None
        for rel in ("CITATION.cff", "README.md"):
            _sub_file(scratch, rel, f"fixed to v{cur}", f"fixed to v{prev}")

        def rewind(d):
            for dl in d.get("download") or []:
                dl["url"] = dl["url"].replace(f"v{cur}", f"v{prev}")
                dl["version"] = prev
            for o in d.get("otherID") or []:
                if isinstance(o.get("version"), str):
                    o["version"] = o["version"].replace(f"v{cur}", f"v{prev}")
            return "rewound"
        _json_at(scratch, "biotools.json", rewind)

        def rewind_ds(d):
            for i in d["citation"].get("identifiers") or []:
                if isinstance(i.get("description"), str):
                    i["description"] = i["description"].replace(f"v{cur}", f"v{prev}")
            return "rewound"
        for rel in ("data/dataset.json", "data/dataset.js"):
            _json_at(scratch, rel, rewind_ds)

        # The DOI half of the same state. Before v1.1.0 was deposited there was no v1.1.0
        # version DOI to name -- the webhook mints it only after the tag is pushed -- so the
        # citation slots named the v1.0.0 deposit and the declaration had no row for 1.1.0.
        # Rewinding the version strings alone produces a tree that says 1.1.0 was never
        # released while four surfaces send the reader to a DOI minted for it, which is not
        # a state this repository was ever in and not one the guard should accept.
        decl = CVS.declaration(scratch)
        here, there = decl.by_version(cur), decl.by_version(prev)
        moved = 0
        if here is not None and there is not None:
            moved = _repoint_slots(scratch, here.doi, there.doi)
            _drop_declared(scratch, cur)

        sentence = CVS.disclosure(cur, prev)
        done = [rel for rel in CVS.DISCLOSURE_SURFACES
                if _plant_disclosure_verbatim(scratch, rel, sentence)]
        return (f"rewound to the pre-release state: note unfrozen, pinned stamps back to "
                f"v{prev}, {moved} citation slot(s) back to the v{prev} DOI, the v{cur} row "
                f"removed from {CVS.DECLARATION}, disclosure restored on {len(done)} "
                f"surface(s)")
    if _toggle_current_note(scratch) is None:
        return None
    # Freezing the note is the moment VERSION becomes published, and a published version
    # must have a version DOI written down: the release is not closed until the DOI the
    # webhook minted is in the declaration and on every citation surface. The DOI here is
    # synthetic -- no deposit exists for an unreleased version, which is the whole reason
    # this step cannot be automated -- but the *shape* of the finished release is what this
    # mutation has to produce, and a release that stops at the note is a half-cut release.
    decl = CVS.declaration(scratch)
    pub = [v for v in CVS.published_versions(scratch) if v != cur]
    prev = decl.by_version(pub[-1]) if pub else None
    minted = f"10.5281/zenodo.{int(decl.concept_record) + 90000000}"
    _add_declared(scratch, cur, minted, "2026-01-01")
    moved = _repoint_slots(scratch, prev.doi, minted) if prev else 0
    done = [rel for rel in CVS.DISCLOSURE_SURFACES
            if _sub_file(scratch, rel, "is not yet deposited", "is the current version")]
    return (f"froze this version's note, wrote the minted DOI {minted} into "
            f"{CVS.DECLARATION} and {moved} citation slot(s), and reworded the disclosure "
            f"on {len(done)} surface(s)")


def _plant_disclosure_verbatim(scratch: Path, rel: str, sentence: str) -> str | None:
    """Put the disclosure on `rel` in the shape that surface holds prose.

    The guard finds the sentence through `_flatten`, which strips `>` quote markers, `#` YAML
    comments and `//` JS comments -- so a comment is a legitimate carrier and is what the
    real surfaces use.
    """
    if rel.endswith((".md", ".cff")):
        p = materialise(scratch, rel)
        marker = "# " if rel.endswith(".cff") else ""
        p.write_text(p.read_text(encoding="utf-8").rstrip("\n")
                     + f"\n\n{marker}{sentence}\n", encoding="utf-8")
        return rel

    def edit(d):
        if "citation" in d and isinstance(d["citation"].get("note"), str):
            d["citation"]["note"] += " " + sentence
        elif isinstance(d.get("description"), str):
            d["description"] += " " + sentence
        else:
            return None
        return "disclosure restored"
    return _json_at(scratch, rel, edit)


def version_stamp_mutations() -> list[Mutation]:
    out: list[Mutation] = []
    kinds: dict[tuple[str, str], str] = {}
    for st in CVS.stamps(REPO):
        kinds.setdefault((st.path, st.kind), st.where)
    for (rel, kind), where in sorted(kinds.items()):
        slot = Slot("check_version_stamps", "surface", f"{rel} [{kind}]",
                    f"e.g. {where} -- a {kind} stamp here must be catchable")
        plant = _identity_mutation if kind == "identity" else _pinned_mutation
        out.append(Mutation(slot, f"ver-{kind}:{rel}",
                            plant=lambda s, rel=rel, f=plant: f(rel, s),
                            expect_in_output=rel))
    for rel in CVS.DISCLOSURE_SURFACES:
        slot = Slot("check_version_stamps", "surface", f"{rel} [disclosure]",
                    "the undeposited-version disclosure must be required here")
        out.append(Mutation(slot, f"ver-disclosure:{rel}",
                            plant=lambda s, rel=rel: _disclosure_mutation(rel, s),
                            expect_in_output=rel))
    out += [
        Mutation(Slot("check_version_stamps", "binding", "VERSION",
                      "the identity half is bound to the file, not to a number in this guard"),
                 "ver-bind:version-file", plant=_bump_version,
                 expect_in_output="VERSION says"),
        # The expected output is a surface name rather than one verdict's wording: this slot
        # is proved in whichever direction the tree currently sits, and the two directions
        # produce opposite complaints ("Remove the sentence" vs "does not carry the
        # undeposited-version disclosure"). What both must do is name the surface.
        Mutation(Slot("check_version_stamps", "binding", "RELEASE-NOTE-FROZEN markers",
                      "the published set is read from docs/, so moving a marker moves it"),
                 "ver-bind:frozen-notes", plant=_toggle_current_note,
                 expect_in_output="CITATION.cff"),
        Mutation(Slot("check_version_stamps", "rule", "the release path goes green",
                      "a guard that cannot be satisfied is a guard that gets routed around"),
                 "ver-rule:cut-the-release", plant=_walk_the_release_path,
                 must="stay-silent"),
        Mutation(Slot("check_metadata_counts", "rule", "the nominalised forms",
                      "a count stated as a noun is the same claim as the participle"),
                 "cnt-rule:nominalised", plant=nominalised_form,
                 expect_in_output="CITATION.cff"),
        Mutation(Slot("check_metadata_counts", "rule", "the roster line",
                      "the hypothesis and decided counts stated beside the study count, "
                      "which is the one phrasing on README that cannot be per-study"),
                 "cnt-rule:roster", plant=roster_form, expect_in_output="README.md"),
        Mutation(Slot("check_metadata_counts", "rule",
                      "every text file is a decision somebody made",
                      "the derived half: an unwatched, unexempted file is the defect, "
                      "whatever it says"),
                 "cnt-rule:unclassified-file", plant=unclassified_file,
                 expect_in_output="ZZ_MUTATION_NOTES.md"),
        Mutation(Slot("check_metadata_counts", "rule",
                      "a stated exemption stays silent",
                      "coverage satisfied by failing on everything is coverage of nothing"),
                 "cnt-rule:exempted-file", plant=exempted_file, must="stay-silent"),
    ]
    return out


# --------------------------------------------------------------------------- #
# check_version_stamps: which DEPOSIT a version DOI names
# --------------------------------------------------------------------------- #
#
# The mutations above move version NUMBERS. Every one of them passed on 2026-08-23 while four
# citation surfaces still carried the DOI Zenodo minted for the v1.0.0 deposit -- because a
# guard that reads the numeral typed beside an identifier and never the identifier cannot see
# that. These mutations move the IDENTIFIER and leave every numeral correct, which is the
# exact state the tree was in.
#
# The slots are enumerated from `CVS.doi_slots(REPO)` -- the guard's own reading -- so a
# citation surface it starts watching without a mutation aimed at it reports UNCOVERED.
#
# Two directions again, and they are not symmetrical:
#
#   slot     a field a reader cites FROM is pointed at the superseded deposit  -> must fail
#   prose    a deliberate historical mention loses the version beside it       -> must fail
#   prose    a deliberate historical mention that keeps it                     -> must be SILENT
#
# The third is the one that makes the first two worth anything. This repository keeps true
# statements about the superseded v1.0.0 DOI on purpose -- README.md holds one of those and a
# live citation instruction five lines apart -- so a guard that fired on every mention of an
# old DOI would be satisfied only by deleting the history, and would be turned off.


def _decl(scratch: Path):
    """(declaration, the deposit surfaces must name, the newest superseded deposit)."""
    decl = CVS.declaration(scratch)
    tgt = CVS.target_deposit(decl, _cur(scratch), CVS.published_versions(scratch))
    older = [d for d in decl.deposits if tgt is not None and d.doi != tgt.doi]
    return decl, tgt, (older[-1] if older else None)


def _doi_slot_mutation(rel: str, scratch: Path) -> str | None:
    """Point one citation slot on `rel` at the previous release's version DOI.

    THE DEFECT, EXACTLY. Nothing else changes: `VERSION` still reads 1.1.0, every identity
    stamp still equals it, and the description beside the DOI still says "permanently fixed
    to v1.1.0". Only the identifier moves -- which is what a release does to a repository
    when the author forgets that the webhook mints a new DOI and the old one is still sitting
    in four files.

    The slot is located through `CVS.doi_slots`, so the mutation lands where the guard
    actually looks rather than on the first textual match, which in README.md and
    CITATION.cff is prose several hundred lines away from the field a reader copies.
    """
    decl, tgt, old = _decl(scratch)
    if tgt is None or old is None:
        return None
    slots = [s for s in CVS.doi_slots(scratch) if s.path == rel and s.line]
    pick = (next((s for s in slots if s.doi == tgt.doi), None)
            or next((s for s in slots if s.doi == decl.concept), None))
    if pick is None:
        return None
    p = materialise(scratch, rel)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    if pick.doi not in lines[pick.line - 1]:
        return None
    lines[pick.line - 1] = lines[pick.line - 1].replace(pick.doi, old.doi, 1)
    p.write_text("".join(lines), encoding="utf-8")
    return (f"{rel}:{pick.line} {pick.where}: {pick.doi} -> {old.doi}, the deposit for "
            f"v{old.version}")


def _repoint_slots(scratch: Path, frm: str, to: str) -> int:
    """Move every citation slot naming `frm` to `to`. Returns how many moved.

    Located through `CVS.doi_slots` so it touches the fields a reader cites from and not the
    prose that talks about them -- README.md names both DOIs in running text a thousand lines
    from the blocks anyone copies.
    """
    moved = 0
    for rel in sorted({s.path for s in CVS.doi_slots(scratch)}):
        picks = [s for s in CVS.doi_slots(scratch)
                 if s.path == rel and s.doi == frm and s.line]
        if not picks:
            continue
        p = materialise(scratch, rel)
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        for s in picks:
            if frm in lines[s.line - 1]:
                lines[s.line - 1] = lines[s.line - 1].replace(frm, to, 1)
                moved += 1
        p.write_text("".join(lines), encoding="utf-8")
    return moved


def _drop_declared(scratch: Path, version: str) -> None:
    """Remove one release's row from the declaration -- what the file looked like before the
    webhook minted that DOI, since nothing can write the row before the tag is pushed."""
    def edit(d):
        rows = [r for r in (d.get("versions") or []) if r.get("version") != version]
        if len(rows) == len(d.get("versions") or []):
            return None
        d["versions"] = rows
        return "row removed"
    _json_at(scratch, CVS.DECLARATION, edit)


def _add_declared(scratch: Path, version: str, doi: str, deposited: str) -> None:
    """Append the row a release adds by hand once the webhook has answered."""
    def edit(d):
        d.setdefault("versions", []).append(
            {"version": version, "doi": doi, "deposited": deposited,
             "note": "written down at the release, from the DOI the webhook minted"})
        return "row appended"
    _json_at(scratch, CVS.DECLARATION, edit)


def _drop_version_doi(scratch: Path) -> str | None:
    """Delete the version-DOI entry from biotools.json instead of pointing it wrong.

    A surface that stops answering "which deposit is this release" has not become correct by
    going quiet, and a rule written only as "the DOI you name must be the right one" is
    silent on a file that names none.
    """
    _decl_, tgt, _old = _decl(scratch)
    if tgt is None:
        return None

    def edit(d):
        before = d.get("otherID") or []
        after = [o for o in before if tgt.doi not in str(o.get("value") or "")]
        if len(after) == len(before):
            return None
        d["otherID"] = after
        return f"otherID entry naming {tgt.doi} removed"
    return _json_at(scratch, "biotools.json", edit)


def _unqualify_historical(scratch: Path) -> str | None:
    """Take the version away from README's deliberate mention of the superseded DOI.

    The paragraph stays; only "the v1.0.0 deposit of 2026-08-20" becomes "the earlier
    deposit". That is the sentence a reader meets after being told not to cite the old DOI,
    and stripped of the version it names nothing -- an unqualified DOI in running prose reads
    as the one to cite, which is how this repository's citation instruction went wrong the
    first time.
    """
    _decl_, _tgt, old = _decl(scratch)
    if old is None:
        return None
    return (_sub_file(scratch, "README.md", f"the v{old.version} deposit of {old.deposited}",
                      "the earlier deposit")
            or _sub_file(scratch, "README.md", f"v{old.version} deposit", "earlier deposit"))


def _qualified_historical(scratch: Path) -> str | None:
    """Add a NEW, correctly qualified mention of the superseded DOI. Must stay silent.

    Without this the suite would only ever have shown the prose rule firing, and a rule that
    fires on every mention of an old DOI is a rule whose only green state is a repository
    with no history in it.
    """
    _decl_, _tgt, old = _decl(scratch)
    if old is None:
        return None
    p = materialise(scratch, "docs/REGISTRATION.md")
    p.write_text(p.read_text(encoding="utf-8").rstrip("\n")
                 + f"\n\nFor the record: {old.doi} is the v{old.version} deposit of "
                   f"{old.deposited}, and it is not this tree.\n", encoding="utf-8")
    return f"a qualified historical mention of {old.doi} appended to docs/REGISTRATION.md"


def _retarget_declaration(scratch: Path) -> str | None:
    """Move the declared DOI for this version and change no surface.

    The binding test. If the mapping were typed into the guard instead of read from
    `zenodo_dois.json`, this would change nothing and every surface would still pass -- and
    the declaration would be decoration.
    """
    _decl_, tgt, _old = _decl(scratch)
    if tgt is None:
        return None
    fake = "10.5281/zenodo.99999999"

    def edit(d):
        for row in d.get("versions") or []:
            if row.get("doi") == tgt.doi:
                row["doi"] = fake
                return f"the declared DOI for v{tgt.version}: {tgt.doi} -> {fake}"
        return None
    return _json_at(scratch, CVS.DECLARATION, edit)


def _undeclared_doi(scratch: Path) -> str | None:
    """Put a Zenodo DOI nobody declared into a citation slot -- one digit dropped."""
    decl, tgt, _old = _decl(scratch)
    if tgt is None:
        return None
    typo = decl.concept[:-1]
    slots = [s for s in CVS.doi_slots(scratch)
             if s.path == "codemeta.json" and s.doi == decl.concept and s.line]
    if not slots:
        return None
    pick = slots[0]
    p = materialise(scratch, "codemeta.json")
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[pick.line - 1] = lines[pick.line - 1].replace(pick.doi, typo, 1)
    p.write_text("".join(lines), encoding="utf-8")
    return f"codemeta.json:{pick.line} {pick.doi} -> {typo}, a record id one digit short"


def _remove_declaration(scratch: Path) -> str | None:
    """Delete the declaration. The guard must refuse, not fall back to reading a surface."""
    p = scratch / CVS.DECLARATION
    if not p.exists():
        return None
    p.unlink()
    return f"{CVS.DECLARATION} deleted"


def doi_mutations() -> list[Mutation]:
    out: list[Mutation] = []
    try:
        decl = CVS.declaration(REPO)
        tgt = CVS.target_deposit(decl, _cur(REPO), CVS.published_versions(REPO))
        older = [d for d in decl.deposits if tgt is not None and d.doi != tgt.doi]
        old = older[-1] if older else None
    except SystemExit:
        return out
    for rel in sorted({s.path for s in CVS.doi_slots(REPO)}):
        slot = Slot("check_version_stamps", "surface", f"{rel} [citation-doi]",
                    "a field a reader is sent to cite from; it must name the deposit for "
                    "this version, whatever the numeral beside it says")
        out.append(Mutation(slot, f"ver-doi:{rel}",
                            plant=lambda s, rel=rel: _doi_slot_mutation(rel, s),
                            expect_in_output=rel))
    out += [
        # The requirement is not only that the guard fails. It is that the failure says which
        # release the DOI it found belongs to -- "CITATION.cff names 10.5281/zenodo.22032685,
        # which belongs to v1.0.0" is a fix, and "the DOI is wrong" is a puzzle. Derived from
        # the declaration, so it cannot be satisfied by a hardcoded sentence.
        Mutation(Slot("check_version_stamps", "rule",
                      "the failure names the version the DOI belongs to",
                      "the sentence that turns a wrong identifier into an obvious defect"),
                 "ver-doi-rule:names-the-owning-version",
                 plant=lambda s: _doi_slot_mutation("CITATION.cff", s),
                 expect_in_output=f"belongs to v{old.version}" if old else "belongs to v"),
        Mutation(Slot("check_version_stamps", "rule",
                      "a citation surface must name this version's DOI at all",
                      "going quiet is not the same as being right"),
                 "ver-doi-rule:drop-version-doi", plant=_drop_version_doi,
                 expect_in_output="biotools.json"),
        Mutation(Slot("check_version_stamps", "rule",
                      "a superseded DOI in prose needs the version beside it",
                      "unqualified, it reads as the one to cite"),
                 "ver-doi-rule:unqualified-historical", plant=_unqualify_historical,
                 expect_in_output="README.md"),
        Mutation(Slot("check_version_stamps", "rule",
                      "a qualified historical mention stays silent",
                      "the repository keeps true statements about the old deposit on "
                      "purpose; a rule that forbids them would be turned off"),
                 "ver-doi-rule:qualified-historical", plant=_qualified_historical,
                 must="stay-silent"),
        Mutation(Slot("check_version_stamps", "binding", CVS.DECLARATION,
                      "the version-to-DOI mapping is read from the declaration, not typed "
                      "into the guard"),
                 "ver-doi-bind:retarget-declaration", plant=_retarget_declaration,
                 expect_in_output="CITATION.cff"),
        Mutation(Slot("check_version_stamps", "binding", f"{CVS.DECLARATION} must exist",
                      "with no declaration there is nothing to hold a surface to, and the "
                      "guard must say so rather than pass"),
                 "ver-doi-bind:no-declaration", plant=_remove_declaration,
                 expect_in_output=CVS.DECLARATION),
        Mutation(Slot("check_version_stamps", "rule",
                      "a DOI declared for nothing",
                      "a dropped digit names a record that belongs to someone else"),
                 "ver-doi-rule:undeclared-doi", plant=_undeclared_doi,
                 expect_in_output="does not declare"),
    ]
    return out


# --------------------------------------------------------------------------- #
# The Zenodo API, proven with a stubbed response instead of declared UNPROVABLE
# --------------------------------------------------------------------------- #

#: Listed for `--list` so a branch added below and not here shows up as a listing that
#: disagrees with the run -- the same arrangement GITHUB_ABOUT_IDENTS has.
ZENODO_REMOTE_IDENTS: tuple[str, ...] = (
    "ver-remote:zenodo-latest[agrees-and-says-so]",
    "ver-remote:zenodo-latest[disagrees]",
    "ver-remote:zenodo-latest[unreachable-is-a-skip]",
    "ver-remote:zenodo-latest[no-flag-is-a-skip]",
)


def zenodo_remote_proof(scratch_root: Path) -> list[Result]:
    """`--remote` against a `file://` copy of a Zenodo response.

    `check_retractions`'s GitHub surface stopped being UNPROVABLE the moment someone noticed
    `gh` is resolved from PATH and the suite could supply its own. The same move works here
    for a different reason: the guard fetches through `urllib`, which speaks `file://`, so
    `CBC_ZENODO_RECORD_URL` points it at a response on disk and both answers -- the one that
    agrees with the declaration and the one that does not -- can be produced without a
    network and without a Zenodo account.

    Four branches, and two of them are about the OUTPUT rather than the verdict. A remote
    check that succeeds silently is indistinguishable from one that never ran, which is the
    failure this whole file exists to make impossible.
    """
    clean = shadow(scratch_root / "zenodo")
    decl = CVS.declaration(clean)
    tgt = CVS.target_deposit(decl, _cur(clean), CVS.published_versions(clean))
    older = [d for d in decl.deposits if tgt is not None and d.doi != tgt.doi]
    if tgt is None or not older:
        return []
    old = older[-1]

    def stub(name: str, doi: str, version: str) -> str:
        p = scratch_root / f"zenodo-{name}.json"
        p.write_text(json.dumps({
            "id": int(doi.rsplit(".", 1)[-1]),
            "doi": doi,
            "conceptdoi": decl.concept,
            "conceptrecid": decl.concept_record,
            "metadata": {"version": version, "publication_date": "2026-08-23"},
        }), encoding="utf-8")
        return p.as_uri()

    def slot_for(branch: str) -> Slot:
        return Slot("check_version_stamps", "surface", f"zenodo:latest [{branch}]",
                    "the archive itself -- the only authority on which deposit a version "
                    "DOI names")

    def go(url: str | None, flag: bool) -> tuple[int, str]:
        env = dict(os.environ)
        if url is not None:
            env[CVS.ZENODO_API_ENV] = url
        cmd = GUARDS["check_version_stamps"] + ["--root", str(clean)]
        if flag:
            cmd = cmd + ["--remote"]
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr

    out: list[Result] = []

    code, text = go(stub("agrees", tgt.doi, tgt.version), True)
    ok = code == 0 and "remote   zenodo:latest" in text and "Zenodo agrees" in text
    out.append(Result(slot_for("agrees-and-says-so"), ZENODO_REMOTE_IDENTS[0],
                      "CAUGHT" if ok else "SURVIVED",
                      "a successful resolve prints the address, the record, the DOI and the "
                      "version it found" if ok else
                      f"exit {code} with no `remote` line; a silent success cannot be told "
                      "apart from a check that never ran"))

    # Zenodo answering that the newest version is the PREVIOUS deposit: what the API would
    # have said on 2026-08-23 if the v1.1.0 release had minted nothing, which is the failure
    # mode docs/REGISTRATION.md §1 step 2 records happening once already.
    code, text = go(stub("stale", old.doi, old.version), True)
    ok = code != 0 and CVS.DECLARATION in text and old.doi in text
    out.append(Result(slot_for("disagrees"), ZENODO_REMOTE_IDENTS[1],
                      "CAUGHT" if ok else "SURVIVED",
                      f"the guard failed and named {CVS.DECLARATION} and the DOI Zenodo "
                      "actually returned" if ok else
                      f"the concept DOI resolved to the v{old.version} deposit and the "
                      f"guard exited {code}"))

    code, text = go((scratch_root / "no-such-response.json").as_uri(), True)
    ok = code == 0 and "SKIP" in text and "zenodo:latest" in text
    out.append(Result(slot_for("unreachable-is-a-skip"), ZENODO_REMOTE_IDENTS[2],
                      "CAUGHT" if ok else "FALSE-FIRE",
                      "an unreachable archive is a loud SKIP: it is a fact about the "
                      "machine, not about the repository" if ok else
                      f"an unreachable archive produced exit {code} without a SKIP line"))

    code, text = go(None, False)
    ok = code == 0 and "SKIP" in text and "pass --remote" in text
    out.append(Result(slot_for("no-flag-is-a-skip"), ZENODO_REMOTE_IDENTS[3],
                      "CAUGHT" if ok else "FALSE-FIRE",
                      "without the flag the surface is named as unread, with the address "
                      "that would have been read" if ok else
                      f"a run without --remote produced exit {code} and no SKIP line naming "
                      "the surface"))
    return out


def rule_coverage() -> list[Result]:
    """Every count key the guard binds must have a unit case in its own --self-test.

    Not a mutation: the guard's `--self-test` already asserts each pattern fires on the exact
    sentence that went stale and stays silent on the five false positives a numeral scan
    produces. What this adds is the enumeration -- a rule added later without a case shows up
    here as UNCOVERED instead of being trusted because the file is called a self-test.
    """
    covered: set[str] = set()
    for text, key, _v in CM.SELF_TEST:
        covered.add(key)
    for text, key, _v in CM.SELF_TEST_WORDED:
        covered.add(key)
    keys = {k for k, _p, _c in CM.RULES} | {k for k, _i, _p, _c in CM.WORDED}
    out = []
    for key in sorted(keys):
        slot = Slot("check_metadata_counts", "rule", key, "a count key the guard binds")
        out.append(Result(slot, f"cnt-rule-unit:{key}",
                          "CAUGHT" if key in covered else "UNCOVERED",
                          "asserted by --self-test" if key in covered
                          else "no case in SELF_TEST or SELF_TEST_WORDED fires this key"))
    return out


#: The four branches proven below, named here so `--list` can enumerate them without running
#: them. Kept beside the function so a branch added there and not here shows up as a listing
#: that disagrees with the run -- which is the same defect class this whole file is about.
GITHUB_ABOUT_IDENTS: tuple[str, ...] = (
    "ret-surface:github-about[clean-read-is-legible]",
    "ret-surface:github-about[asserted]",
    "ret-surface:github-about[empty-says-so]",
    "ret-surface:github-about[no-gh-is-a-skip]",
)


def github_about_proof(scratch_root: Path) -> list[Result]:
    """The remote surface, proven with a stub `gh` instead of declared UNPROVABLE.

    THIS SLOT USED TO READ "UNPROVABLE", and the stated reason was true but incomplete: the
    guard reports the field as SKIP unless `--remote` and `gh` are both present, and a skip
    is neither a pass nor a failure. What that reasoning missed is that `gh` is resolved from
    PATH, so the suite can supply its own -- and once it can, the surface behaves like every
    other one here: plant the retracted sentence on it and require the guard to fail naming
    it.

    Four branches, because the failure this closes was in the OUTPUT and not in the scan. A
    clean read used to print nothing at all, so a run that read the public About field and a
    run that never looked produced identical text. Each branch below asserts what the reader
    is told, not only what the guard returns:

        clean      exit 0, and a `remote` line naming the surface, the address, the size of
                   the field and how many withdrawn claims were tested against it
        asserted   exit 1, naming github:About and the record
        empty      exit 0, and a line saying the field is EMPTY -- distinct from clean prose,
                   because "nothing was asserted" and "there is nothing there" are different
                   facts and only one is evidence
        no gh      exit 0 and the SKIP, unchanged: a missing tool must never read as a pass

    The stub is a two-line shell script in the scratch tree. It never touches the network, so
    this proves the guard's handling of the surface and NOT the content of the live About
    field -- which no offline check can decide, and which is why `--remote` still exists.
    """
    bindir = scratch_root / "fakebin"
    bindir.mkdir(parents=True, exist_ok=True)
    stub = bindir / "gh"
    stub.write_text('#!/bin/sh\nprintf \'%s\\n\' "$GH_FAKE_DESCRIPTION"\n')
    stub.chmod(0o755)
    clean = shadow(scratch_root / "about")

    def slot_for(branch: str) -> Slot:
        # The branch is in the NAME, not only in the ident, because `report()` groups by name
        # and four rows reading "github:About" tell a reader nothing about what was proven.
        return Slot("check_retractions", "surface", f"github:About [{branch}]",
                    "a public surface that lives outside the tree, read through `gh`")

    def go(description: str | None, with_stub: bool) -> tuple[int, str]:
        env = dict(os.environ)
        if with_stub:
            env["PATH"] = f"{bindir}{os.pathsep}" + env.get("PATH", "")
            env["GH_FAKE_DESCRIPTION"] = description or ""
        else:
            # A PATH with no `gh` on it. `sys.executable` is absolute, so the guard still runs.
            env["PATH"] = "/nonexistent"
        cmd = GUARDS["check_retractions"] + ["--root", str(clean), "--remote"]
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, env=env)
        return r.returncode, r.stdout + r.stderr

    out: list[Result] = []

    code, text = go("Pre-registered computational study slate, artefacts and guards.", True)
    ok = code == 0 and "remote   github:About" in text and "tested against it" in text
    out.append(Result(slot_for("clean-read-is-legible"), "ret-surface:github-about[clean-read-is-legible]",
                      "CAUGHT" if ok else "SURVIVED",
                      "a clean read prints the surface, the address and the claim count"
                      if ok else
                      f"a clean read printed no `remote` line (exit {code}); silence is "
                      "indistinguishable from never having looked"))

    code, text = go(f"AlphaFold3 peptide design: {RETRACTED_SENTENCE}", True)
    ok = code != 0 and "github:About" in text
    out.append(Result(slot_for("asserted"), "ret-surface:github-about[asserted]",
                      "CAUGHT" if ok else "SURVIVED",
                      "the guard failed and named github:About" if ok else
                      f"the retracted sentence sat on the About field and the guard exited "
                      f"{code}"))

    code, text = go("null", True)
    ok = code == 0 and "the field is EMPTY" in text
    out.append(Result(slot_for("empty-says-so"), "ret-surface:github-about[empty-says-so]",
                      "CAUGHT" if ok else "SURVIVED",
                      "an empty field is reported as empty, not as clean prose" if ok else
                      "an empty About field was reported the same way as a field that was "
                      "read and found clean"))

    code, text = go(None, False)
    ok = code == 0 and "SKIP" in text and "github:About" in text
    out.append(Result(slot_for("no-gh-is-a-skip"), "ret-surface:github-about[no-gh-is-a-skip]",
                      "CAUGHT" if ok else "FALSE-FIRE",
                      "a missing `gh` is a loud SKIP, never a pass and never a failure"
                      if ok else
                      f"a missing `gh` produced exit {code} without a SKIP line"))
    return out


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #

def baseline(scratch_root: Path, verbose: bool) -> dict[str, bool]:
    clean = shadow(scratch_root / "baseline")
    out = {}
    for guard in GUARDS:
        code, text = run_guard(guard, clean)
        out[guard] = code == 0
        if verbose or code != 0:
            print(f"  baseline {guard}: exit {code}")
            if code != 0:
                print("\n".join("    | " + l for l in text.strip().splitlines()[-12:]))
    return out


def run_mutation(m: Mutation, base: Path, i: int, verbose: bool) -> Result:
    t0 = time.time()
    scratch = shadow(base / f"m{i:03d}")
    try:
        if m.slot.kind == "exemption":
            status, detail = run_exemption(m.slot.name, scratch)
            return Result(m.slot, m.ident, status, detail, time.time() - t0)
        note = m.plant(scratch)
        if note is None:
            if _absent_by_design(str(getattr(m.slot, "name", ""))):
                return Result(m.slot, m.ident, "NOT-IN-CLONE",
                              "deliberately not published, so a clone has nothing to plant "
                              "in; it is mutated in a tree that has it", time.time() - t0)
            return Result(m.slot, m.ident, "ANCHOR-LOST",
                          m.note or "the mutation could not be planted", time.time() - t0)
        code, text = run_guard(m.slot.guard, scratch)
        if m.must == "stay-silent":
            if code == 0:
                return Result(m.slot, m.ident, "CAUGHT", f"{note}; guard stayed silent",
                              time.time() - t0)
            return Result(m.slot, m.ident, "FALSE-FIRE",
                          f"{note}; guard failed where it must not:\n"
                          + "\n".join("      | " + l for l in text.strip().splitlines()[-6:]),
                          time.time() - t0)
        if code == 0:
            return Result(m.slot, m.ident, "SURVIVED", f"{note}; guard still exited 0",
                          time.time() - t0)
        if m.expect_in_output and m.expect_in_output not in text:
            return Result(m.slot, m.ident, "SURVIVED",
                          f"{note}; the guard failed but never named "
                          f"{m.expect_in_output!r}, so it failed for another reason",
                          time.time() - t0)
        return Result(m.slot, m.ident, "CAUGHT", note, time.time() - t0)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)




#: Surfaces the repository deliberately does not publish. paper/ is the author's manuscript
#: prose, untracked and ignored; docs/*.docx|pptx|pdf|html are generated documents, ignored for
#: the same reason. Both exist in the author's working tree and ARE mutated there. In a clone
#: they are absent, and a mutation that cannot be planted because its subject was never
#: published has not lost its anchor -- it has nothing to say. Reporting that as a defect made
#: verify_all.py red on every clone while green for the author, which is the exact asymmetry
#: this repository has already had to fix once.
_ABSENT_BY_DESIGN = ("paper/", "docs/CognitionBioChem_")
_ABSENT_SUFFIXES = (".docx", ".pptx", ".pdf", ".html")


def _absent_by_design(name: str) -> bool:
    if any(name.startswith(pfx) for pfx in _ABSENT_BY_DESIGN):
        return True
    return name.startswith("docs/") and any(name.endswith(sfx) for sfx in _ABSENT_SUFFIXES)

ORDER = ["SURVIVED", "FALSE-FIRE", "UNCOVERED", "BASELINE-RED", "ANCHOR-LOST",
         "NOT-IN-CLONE", "UNPROVABLE",
         "CAUGHT"]


def report(results: list[Result], verbose: bool) -> int:
    by_guard: dict[str, list[Result]] = {}
    for r in results:
        by_guard.setdefault(r.slot.guard, []).append(r)

    for guard in sorted(by_guard):
        print(f"\n{guard}")
        print("-" * len(guard))
        for r in sorted(by_guard[guard], key=lambda x: (x.slot.kind, x.slot.name)):
            mark = {"CAUGHT": "  ok  ", "SURVIVED": " SURV ", "FALSE-FIRE": " FIRE ",
                    "UNCOVERED": " UNCV ", "ANCHOR-LOST": " LOST ",
                    "NOT-IN-CLONE": " N/A  ", "BASELINE-RED": " RED  ",
                    "UNPROVABLE": " n/a  "}[r.status]
            print(f"  [{mark}] {r.slot.kind:<9} {r.slot.name}")
            if r.status != "CAUGHT" or verbose:
                print(f"            {r.detail}")

    counts = {s: sum(1 for r in results if r.status == s) for s in ORDER}
    print("\n" + "=" * 78)
    print(f"{counts['CAUGHT']} caught, {counts['SURVIVED']} survived, "
          f"{counts['FALSE-FIRE']} false-fire, {counts['UNCOVERED']} uncovered, "
          f"{counts['ANCHOR-LOST']} anchor-lost, "
          f"{counts['NOT-IN-CLONE']} absent-by-design, {counts['BASELINE-RED']} baseline-red, "
          f"{counts['UNPROVABLE']} unprovable")
    bad = counts["SURVIVED"] + counts["FALSE-FIRE"] + counts["UNCOVERED"] \
        + counts["ANCHOR-LOST"] + counts["BASELINE-RED"]
    if bad:
        print("=" * 78)
        print("Every slot above that is not `ok` is either a guard that cannot fail on "
              "something it\nclaims to watch, or a mutation that no longer reaches its "
              "target. Both are defects.")
        return 1
    print("every slot either failed the defect it exists to catch, or is named above as "
          "unreachable\nwith the reason stated. None passed vacuously.")
    print("=" * 78)
    return 0


def all_mutations() -> list[Mutation]:
    return (retraction_surface_mutations() + retraction_record_mutations()
            + exemption_mutations() + metadata_surface_mutations() + special_mutations()
            + version_stamp_mutations() + doi_mutations())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="run only mutations whose id contains this")
    ap.add_argument("--list", action="store_true", help="print the enumeration and stop")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    muts = all_mutations()
    if a.list:
        for m in muts:
            print(f"  {m.slot.guard:<22} {m.slot.kind:<10} {m.ident}")
        for r in rule_coverage():
            print(f"  {r.slot.guard:<22} {r.slot.kind:<10} {r.ident}")
        # Listed without running. `--list` is the enumeration, and running the About proof
        # to print its own names would make a listing cost four guard invocations.
        for ident in GITHUB_ABOUT_IDENTS:
            print(f"  {'check_retractions':<22} {'surface':<10} {ident}")
        for ident in ZENODO_REMOTE_IDENTS:
            print(f"  {'check_version_stamps':<22} {'surface':<10} {ident}")
        return 0

    print("=" * 78)
    print("mutation suite — every guard must be able to fail, on every surface it watches")
    print("=" * 78)

    base = Path(tempfile.mkdtemp(prefix="cbc-mutation-"))
    try:
        green = baseline(base, a.verbose)
        results: list[Result] = []
        selected = [m for m in muts if not a.only or a.only in m.ident]
        for i, m in enumerate(selected):
            if not green.get(m.slot.guard, False):
                results.append(Result(m.slot, m.ident, "BASELINE-RED",
                                      f"{m.slot.guard} was already failing on the clean copy"))
                continue
            results.append(run_mutation(m, base, i, a.verbose))
        if not a.only:
            results += (rule_coverage() + github_about_proof(base)
                        + zenodo_remote_proof(base))
        return report(results, a.verbose)
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
