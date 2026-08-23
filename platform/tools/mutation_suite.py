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

Both print green today. So did `platform/check_paper.py`, which reported 10 passed / 0 failed
on a manuscript stating "8 pre-registered studies and 25 hypotheses" while `data/` held 9 and
28 -- because every one of those numerals really was somewhere in `data/`. A green line is
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


def _pinned_mutation(rel: str, scratch: Path) -> str | None:
    """The naive repair: relabel a frozen deposit to follow VERSION."""
    cur = _cur(scratch)
    pub = CVS.published_versions(scratch)
    if not pub:
        return None
    pin = pub[-1]
    if rel in ("CITATION.cff", "README.md"):
        return _sub_file(scratch, rel, f"fixed to v{pin}", f"fixed to v{cur}")
    if rel == "biotools.json":
        def edit(d):
            for dl in d.get("download") or []:
                dl["url"] = dl["url"].replace(f"v{pin}", f"v{cur}")
                dl["version"] = cur
            for o in d.get("otherID") or []:
                if isinstance(o.get("version"), str):
                    o["version"] = o["version"].replace(f"v{pin}", f"v{cur}")
            return f"download and otherID relabelled v{pin} -> v{cur}"
        return _json_at(scratch, rel, edit)
    if rel.startswith("data/dataset."):
        def edit(d):
            for i in d["citation"].get("identifiers") or []:
                if isinstance(i.get("description"), str):
                    i["description"] = i["description"].replace(f"v{pin}", f"v{cur}")
            return f"version-DOI description relabelled v{pin} -> v{cur}"
        return _json_at(scratch, rel, edit)
    return None


def _drop_disclosure(rel: str, scratch: Path) -> str | None:
    """Break the sentence's shape without deleting a line, which is how a real edit loses it.

    Reworded rather than removed: a guard that only notices a missing paragraph would pass on
    a surface where someone softened the wording and left the version number behind.
    """
    return _sub_file(scratch, rel, "is not yet deposited", "is the current version")


def _bump_version(scratch: Path) -> str | None:
    cur = _cur(scratch)
    major, minor, patch = (int(x) for x in cur.split("."))
    p = materialise(scratch, "VERSION")
    p.write_text(f"{major}.{minor + 1}.{patch}\n", encoding="utf-8")
    return f"VERSION {cur} -> {major}.{minor + 1}.{patch}, touching no metadata surface"


def _freeze_current_note(scratch: Path) -> str | None:
    """Mark this version's note frozen and change nothing else.

    That single edit says the version has been published, so the disclosure sentence on six
    surfaces becomes false. It is the binding test for the published set: if the guard read a
    hand-written release list instead of the notes, nothing here would move.
    """
    cur = _cur(scratch)
    return _sub_file(scratch, f"docs/RELEASE_NOTES_v{cur}.md",
                     "<!-- RELEASE-NOTE-GENERATED", "<!-- RELEASE-NOTE-FROZEN")


def _cut_the_release(scratch: Path) -> str | None:
    """The whole release path, executed: freeze the note AND drop the disclosure everywhere.

    Must stay SILENT. Without this the suite would only ever have shown the guard failing,
    and a guard that cannot go green after the work is done is a guard the author routes
    around. The pinned stamps still read v1.0.0 here and must still be accepted: 1.0.0 is
    published, and that is the whole rule.
    """
    if _freeze_current_note(scratch) is None:
        return None
    done = [rel for rel in CVS.DISCLOSURE_SURFACES
            if _sub_file(scratch, rel, "is not yet deposited", "is the current version")]
    return f"froze this version's note and reworded the disclosure on {len(done)} surface(s)"


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
                            plant=lambda s, rel=rel: _drop_disclosure(rel, s),
                            expect_in_output=rel))
    out += [
        Mutation(Slot("check_version_stamps", "binding", "VERSION",
                      "the identity half is bound to the file, not to a number in this guard"),
                 "ver-bind:version-file", plant=_bump_version,
                 expect_in_output="VERSION says"),
        Mutation(Slot("check_version_stamps", "binding", "RELEASE-NOTE-FROZEN markers",
                      "the published set is read from docs/, so freezing a note moves it"),
                 "ver-bind:frozen-notes", plant=_freeze_current_note,
                 expect_in_output="Remove the sentence"),
        Mutation(Slot("check_version_stamps", "rule", "the release path goes green",
                      "a guard that cannot be satisfied is a guard that gets routed around"),
                 "ver-rule:cut-the-release", plant=_cut_the_release, must="stay-silent"),
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


ORDER = ["SURVIVED", "FALSE-FIRE", "UNCOVERED", "BASELINE-RED", "ANCHOR-LOST", "UNPROVABLE",
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
                    "UNCOVERED": " UNCV ", "ANCHOR-LOST": " LOST ", "BASELINE-RED": " RED  ",
                    "UNPROVABLE": " n/a  "}[r.status]
            print(f"  [{mark}] {r.slot.kind:<9} {r.slot.name}")
            if r.status != "CAUGHT" or verbose:
                print(f"            {r.detail}")

    counts = {s: sum(1 for r in results if r.status == s) for s in ORDER}
    print("\n" + "=" * 78)
    print(f"{counts['CAUGHT']} caught, {counts['SURVIVED']} survived, "
          f"{counts['FALSE-FIRE']} false-fire, {counts['UNCOVERED']} uncovered, "
          f"{counts['ANCHOR-LOST']} anchor-lost, {counts['BASELINE-RED']} baseline-red, "
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
            + version_stamp_mutations())


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
            results += rule_coverage() + github_about_proof(base)
        return report(results, a.verbose)
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
