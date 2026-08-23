#!/usr/bin/env python3
"""Guard: no public surface may assert a retracted claim without its withdrawal.

    ./.venv/bin/python platform/check_retractions.py [--remote] [--root DIR] [--quiet]

WHAT IT CHECKS
--------------
`retractions.jsonl` holds each withdrawn claim once, with the regexes that recognise it.
This walks every public surface in the repository, finds those claims, and fails naming the
file and the line unless the withdrawal travels with them.

Two ways to travel, matched to the two kinds of surface:

  STRUCTURED (`*.json`, and the `data/*.js` mirrors, which are one JSON object behind an
  assignment). The object that holds the retracted string must also hold a `retraction` or
  `retractions` field naming the record id -- or the string must carry the withdrawal itself,
  because one JSON string value is one authored unit, and `study_candidate_screen.json`'s
  `interpretation_key` is a paragraph that states its own retraction in place. No proximity
  beyond that. This is what makes the generator's join checkable: `build_slate.py` copies a
  registered hypothesis statement onto the front page, and the only thing that makes that
  legitimate is the retraction block sitting in the same object. Delete the join and this
  fails.

  PROSE (`*.md`, `*.py`, `*.js`, `*.html`, `*.css`, `*.cff`, `NOTICE`). A withdrawal marker
  must appear in the same authored block as the match
  -- the record id, or one of `retractions.WITHDRAWAL_MARKERS`. The README's Slate #7 gate
  paragraph is the shape this is calibrated on: it quotes the retracted clause and withdraws
  it four lines later, and that must pass. `memory/views/claims.md` is the shape that forced
  the block clipping: 860 claims rendered as consecutive list items, where a plain line
  window let one claim's `❌` clear a different claim six lines away.

THREE DIRECTORIES ARE EXEMPT, AS FILES
--------------------------------------
`prespec/`, `data/superseded/` and `memory/ledger/`. Each is an append-only or
content-hashed record of what was registered or believed at the time; each necessarily
contains the retracted sentence verbatim; and rewriting any of them to agree with a later
finding would destroy the property the project is built on.

Note the precise scope, because it is the difference between catching the defect that
started this and missing it. The exemption is by PATH. A `prespec` statement republished by
a generator into `data/slate.json` and rendered on the page is NOT exempt -- at that point it
is a live claim on a public surface. Neither is `memory/views/claims.md`, which is a
rendering of the exempt ledger. What is exempt is the record. Never the rendering.

WHAT IT DOES NOT SEE, STATED RATHER THAN PASSED OVER
----------------------------------------------------
* The GitHub About field, unless `--remote` is given and `gh` is installed. It is a public
  surface that lives outside the tree, and one audit survivor is sitting on it right now.
  Without the flag this prints a SKIP line naming the surface and the reason, the way the
  `node --check` prerequisite is already handled elsewhere. A skip is never a pass.
  WITH the flag it prints a `remote` line naming the surface, the address read, the size of
  the field, how many withdrawn claims were tested against it and the field's own text.
  Silence used to mean success here, which made a run that read the field indistinguishable
  from a run that never looked -- the same failure the whole guard exists to prevent, in the
  guard's own output.
* `reviews/` and `research/`. Those hold the raw review panel and adjudication transcripts,
  which are records of what was said, not claims the project is making today -- but unlike
  the three exempt directories they also contain live prose, so the right treatment is a
  judgement nobody has made yet. They are listed under NOT SCANNED rather than quietly
  omitted, so the gap is visible.
* `runs/`, `.venv*/`, `.git/`, `data/pae/`, `data/targets/`, `data/alphafold_db/`: machine
  output, no prose.
* Anything under `paper/` or any built `.docx`/`.pptx`/`.pdf`/`.html` under `docs/`. Those
  are not published by this repository and are absent from a clone, so they are not listed in
  SURFACES. The reader for Word and PowerPoint parts is retained for the day one of them is
  tracked again; see the note in SURFACES. Its known limit, recorded there rather than lost:
  text split across XML runs. Tags are stripped and whitespace collapsed before matching,
  which recovers most of it, but a fingerprint broken across a formatting boundary can still
  escape.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retractions as R                                              # noqa: E402

REPO = Path(__file__).resolve().parents[1]

#: Every surface a claim can be published on, named explicitly. The list is the point: an
#: unlisted surface is an unwatched one, so it is spelled out rather than inferred from a
#: recursive walk that would silently pick up whatever lands in the tree next.
SURFACES: tuple[str, ...] = (
    "README.md",
    "NOTICE",
    "VERSION",
    "CITATION.cff",
    "codemeta.json",
    "biotools.json",
    ".zenodo.json",
    "index.html",
    "app.js",
    "styles.css",
    "verify_all.py",
    "data/*.json",
    "data/*.js",
    "docs/*.md",
    # `docs/*.docx` and `docs/*.pptx` stood here. Nothing in this repository writes either
    # one any more: the six document generators are not published (see the block at the end
    # of .gitignore), so no tree a clone can reach produces a file those patterns would
    # match, and the surface slots the mutation suite derived from them were no-ops. The
    # Word/PowerPoint reader below is kept rather than deleted -- it is correct, the mutation
    # suite is what made it correct, and if a built document is ever tracked again the
    # pattern comes back here and the reader is already right. Until then it is unreachable,
    # which is stated rather than left to be discovered.
    #
    # `paper/*.md` STAYS. Unlike the two above it is hand-authored prose that still exists in
    # the author's working tree, where this guard still reads it; in a clone the pattern
    # matches nothing and the mutation suite already classes it absent-by-design. It is the
    # same treatment check_metadata_counts.py gives paper/, and the two lists agree on it.
    "paper/*.md",
    "platform/**/*.py",
    "memory/*.py",
    "memory/views/*.md",
    "memory/*.md",
)

#: Exempt AS FILES. See the module docstring: the record is exempt, the rendering never is.
EXEMPT_DIRS: tuple[tuple[str, str], ...] = (
    ("prespec", "hash-locked registered plans; a plan is a record of what was said in "
                "advance and is never rewritten after the fact"),
    ("data/superseded", "retained earlier artefacts; they record what was believed when "
                        "they were written, and README discloses the five that keep the "
                        "retracted clause"),
    ("memory/ledger", "the append-only provenance ledger; a retraction is filed there as a "
                      "NEW record, so the withdrawn text is present by construction. Its "
                      "generated views under memory/views/ are NOT exempt"),
)

#: These two hold the retracted sentences on purpose -- one is the ledger, one is the guard.
EXEMPT_FILES: tuple[str, ...] = (
    "retractions.jsonl",
    "platform/check_retractions.py",
    "platform/retractions.py",
    # Quotes a withdrawn sentence as the payload it plants in a scratch copy to prove this
    # guard can fail. Exempt for the same reason as the two above, and stated rather than
    # left to luck: it passed the scan before this line existed only because the constant is
    # spelled RETRACTED_SENTENCE and the word "retracted" reads as a withdrawal marker.
    "platform/tools/mutation_suite.py",
)

NOT_SCANNED: tuple[tuple[str, str], ...] = (
    ("reviews/", "raw review-panel transcripts and adjudications; they are records of what "
                 "reviewers said, but they also carry live prose, and which half they are "
                 "has not been decided"),
    ("research/", "same, for the research adjudication set"),
    ("runs/", "507 prediction run trees: coordinates and confidence JSON, no prose"),
    ("data/pae|targets|alphafold_db|study_inputs", "machine output"),
    ("mas/", "agent scaffolding, no published claim"),
)

_JS_ASSIGN = re.compile(r"^\s*(?://[^\n]*\n)*\s*(?:window\.)?[\w.$]+\s*=\s*", re.M)
_XML_TAG = re.compile(r"<[^>]+>")


class Hit:
    def __init__(self, path: str, line: int, rec: R.Retraction, text: str, why: str) -> None:
        self.path, self.line, self.rec, self.text, self.why = path, line, rec, text, why


# --------------------------------------------------------------------------- #
# Surface enumeration
# --------------------------------------------------------------------------- #

def is_exempt(rel: str) -> str | None:
    if rel in EXEMPT_FILES:
        return "the retraction ledger and its tooling quote withdrawn claims by construction"
    for d, why in EXEMPT_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return why
    return None


def surfaces(root: Path) -> list[Path]:
    out: list[Path] = []
    for pat in SURFACES:
        for p in sorted(root.glob(pat)):
            if not p.is_file():
                continue
            rel = str(p.relative_to(root))
            if is_exempt(rel):
                continue
            if p not in out:
                out.append(p)
    return out


# --------------------------------------------------------------------------- #
# Reading a surface
# --------------------------------------------------------------------------- #

def read_text(p: Path) -> str | None:
    if p.suffix in (".docx", ".pptx"):
        return _office_text(p)
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


#: What ends an authored unit inside a Word or PowerPoint part. Paragraph ends, line breaks
#: and table rows: the boundaries a person typing the document would recognise.
_OFFICE_BREAK = re.compile(r"</w:p>|</a:p>|</w:tr>|<w:br\s*/>|<a:br\s*/>")


def _office_text(p: Path) -> str:
    """Unzip, split into paragraphs, strip XML. One LINE PER PARAGRAPH, not one line per file.

    The line-per-paragraph part is load-bearing, and the mutation suite is what proved it.
    This function used to collapse every part of the document into a single line. Every
    acknowledgement rule downstream works on a block of lines, so a one-line document is one
    block, and a document is a block that contains the word "retracted" somewhere -- these
    are papers about a project whose central result was withdrawn, so of course it does. A
    A retracted claim planted anywhere in a forty-page manuscript was therefore acknowledged
    by a sentence forty pages away, and the guard reported the file clean.
    `platform/tools/mutation_suite.py` planted exactly that and required this to fail on it.
    Both the manuscript and the generators that rendered it are unpublished now, so nothing
    in a clone reaches this function; it is kept correct against the day one does.

    A line here is a paragraph, so a reported line number counts paragraphs rather than
    source lines -- there are no source lines in a zip. The withdrawal window is the same one
    prose files get, measured in paragraphs.

    Text is stored split across formatting runs, so a fingerprint that straddles a run
    boundary survives this. Stated in the summary rather than papered over.
    """
    parts: list[str] = []
    try:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith(".xml") and ("word/" in n or "ppt/slides/" in n
                                           or "ppt/notesSlides/" in n):
                    parts.append(z.read(n).decode("utf-8", "replace"))
    except (zipfile.BadZipFile, OSError):
        return ""
    lines: list[str] = []
    for part in parts:
        for para in _OFFICE_BREAK.split(part):
            text = re.sub(r"[ \t]+", " ", _XML_TAG.sub(" ", para)).strip()
            if text:
                lines.append(text)
        lines.append("")          # a part boundary is not an authored block boundary crossing
    return "\n".join(lines)


def as_json(p: Path, text: str) -> object | None:
    """The JSON object behind a `.json` file, or behind a `data/*.js` assignment."""
    if p.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    if p.suffix == ".js" and p.parent.name == "data":
        body = _JS_ASSIGN.sub("", text, count=1).strip().rstrip(";").strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None
    return None


# --------------------------------------------------------------------------- #
# The two acknowledgement rules
# --------------------------------------------------------------------------- #

def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_structured(rel: str, text: str, doc: object,
                    recs: list[R.Retraction]) -> list[Hit]:
    """A retracted string in JSON must sit in an object that names the retraction.

    Walking the parsed document rather than the raw bytes is what makes this exact: the
    "nearest enclosing object" is a real thing in a parse tree and a guess in a text file.
    """
    hits: list[Hit] = []

    def ack(obj: dict, rid: str) -> bool:
        for key in ("retraction", "retractions"):
            if key in obj and rid in json.dumps(obj[key]):
                return True
        return False

    def walk(node: object, owner: dict | None, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                # A `retraction` block quotes the claim it withdraws -- that is its job. It
                # is the withdrawal, not an assertion of the claim, so it is not walked.
                if k in ("retraction", "retractions"):
                    continue
                walk(v, node, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, owner, f"{path}[{i}]")
        elif isinstance(node, str):
            for r in recs:
                if not r.search(node):
                    continue
                if owner is not None and ack(owner, r.id):
                    continue
                # A JSON string value is one authored unit. If the author wrote the
                # withdrawal into the same field -- as study_candidate_screen.json's
                # interpretation_key does -- the claim is not being asserted live.
                if r.acknowledged_in(node):
                    continue
                where = text.find(node[:60]) if len(node) >= 20 else -1
                hits.append(Hit(rel, _line_of(text, where) if where >= 0 else 0, r, path,
                                "the object carrying this string has no `retraction` field "
                                f"naming {r.id}"))
    walk(doc, None, "")
    return hits


def scan_prose(rel: str, text: str, recs: list[R.Retraction]) -> list[Hit]:
    """A retracted claim in prose must have a withdrawal marker within the window."""
    lines = text.splitlines() or [text]
    hits: list[Hit] = []
    for r in recs:
        for m in r.search(text):
            ln = _line_of(text, m.start())
            if r.acknowledged_in("\n".join(R.block_around(lines, ln))):
                continue
            hits.append(Hit(rel, ln, r, lines[ln - 1].strip()[:140] if ln <= len(lines)
                            else m.group(0),
                            f"no withdrawal of {r.id} in the block that asserts it"))
    return hits


# --------------------------------------------------------------------------- #
# The surface outside the tree
# --------------------------------------------------------------------------- #

#: The repository whose About field is the one surface this guard cannot reach from the tree.
#: Named here rather than inline so the read line can print it: a reader who is told a remote
#: surface passed is owed the address that was read.
GITHUB_REPO = "hopejsh/CognitionBioChem"


def github_about(enabled: bool) -> tuple[list[Hit], str | None, str | None]:
    """The GitHub About field, as (hits, skip_reason, read_note). Exactly one note is set.

    WHY THE SUCCESS CASE HAS A NOTE AT ALL
    --------------------------------------
    It did not, and that was the defect. Without `--remote` this printed a loud SKIP naming
    the surface and the reason, which is right and which nobody has ever complained about.
    WITH `--remote` and a clean field it returned `(hits, None)` and printed nothing, so the
    run that actually read the public surface and the run that never looked produced the same
    output: a PASS line and no mention of GitHub. The flag's whole purpose is to let a reader
    tell those two runs apart, and the flag was the only thing that could -- which means the
    reader had to already know it was passed.

    So a successful read is now as legible as a skip: the surface, the address it was read
    from, how many characters came back, how many withdrawn claims were tested against them,
    and the field's own text. An EMPTY About field gets its own wording rather than being
    reported as clean prose, because "nothing was asserted" and "there is nothing there" are
    different facts and only one of them is evidence about the field.
    """
    if not enabled:
        return [], ("not fetched: pass --remote to read it. It is a public surface outside "
                    "the tree and no check can see it otherwise"), None
    try:
        r = subprocess.run(["gh", "api", f"repos/{GITHUB_REPO}", "--jq",
                            ".description"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return [], (f"not fetched: {exc.__class__.__name__}; `gh` must be installed and "
                    "authed"), None
    if r.returncode != 0:
        return [], f"not fetched: gh exited {r.returncode}: {r.stderr.strip()[:120]}", None

    recs = R.load()
    # Deduplicated here, not only in `run()`. Two fingerprints on one record match the same
    # sentence, and the read line reported "2 asserted without a withdrawal" above a FAIL
    # block listing 1 -- the guard contradicting itself in six lines, which is the shape of
    # the defect it exists to catch.
    seen: set[tuple[str, int, str]] = set()
    hits = []
    for h in scan_prose("github:About", r.stdout, recs):
        key = (h.path, h.line, h.rec.id)
        if key not in seen:
            seen.add(key)
            hits.append(h)
    # `gh api --jq .description` renders a null description as the literal "null".
    field = r.stdout.strip()
    if field in ("", "null"):
        note = (f"read from gh api repos/{GITHUB_REPO} — the field is EMPTY. Nothing is "
                f"asserted there, which is why nothing was found; {len(recs)} withdrawn "
                "claim(s) had nothing to match against")
    else:
        note = (f"read from gh api repos/{GITHUB_REPO} — {len(field)} char(s), "
                f"{len(recs)} withdrawn claim(s) tested against it, "
                f"{len(hits)} asserted without a withdrawal\n"
                f"             | {field[:150]}")
    return hits, None, note


# --------------------------------------------------------------------------- #

def check_plan_fields_landed(root: Path, recs: list[R.Retraction]) -> list[str]:
    """Every `plan_field` anchor must render its correction in `data/slate.json`.

    Weaker than the check below, and worth having anyway. A republished plan field DOES carry
    the withdrawn wording, so `scan_structured` catches the generator that drops the join
    outright -- the string arrives with no `retraction` beside it and the guard fails on the
    text. What it cannot catch is the half-drop: keep the record id in the study's
    `retractions` list, stop emitting the correction block, and every scan passes while the
    page prints "giving 13 distinct designs" under Supersedes with nothing next to it.

    So this asks the built artefact the question the text scan cannot: is the correction
    actually there, beside the field it corrects, naming the record that says so.
    """
    slate = root / "data" / "slate.json"
    wanted = [(r, a) for r in recs for a in r.anchors if a.get("kind") == "plan_field"]
    if not wanted:
        return []
    if not slate.exists():
        return [f"{len(wanted)} plan_field anchor(s) cannot be verified: data/slate.json is "
                "not built. Run platform/build_slate.py."]
    try:
        doc = json.loads(slate.read_text())
    except json.JSONDecodeError as exc:
        return [f"data/slate.json does not parse, so no anchor can be verified: {exc}"]
    by_study = {s.get("study_id"): s for s in doc.get("studies", [])}
    problems: list[str] = []
    for r, a in wanted:
        st = by_study.get(a["study"])
        if st is None:
            problems.append(f"{r.id} corrects a field of study {a['study']!r}, which is not "
                            "in data/slate.json")
            continue
        field = a["field"]
        block = st.get(f"{field}_correction") or {}
        if block.get("retraction") != r.id:
            problems.append(
                f"{a['study']}/{field} is republished on the page with no correction naming "
                f"{r.id} (found {block.get('retraction')!r}). The ledger says this field "
                "states a count the repository has since corrected; the page would print it "
                "alone. Re-run platform/build_slate.py, and if that does not fix it the "
                "plan_field join in build_slate.py is gone.")
            continue
        # The whole point of shipping the registered bytes is that they ARE the registered
        # bytes. A page that quotes a hash-locked plan inexactly is worse than one that does
        # not quote it, because it invites a comparison it would fail.
        if st.get(field) != block.get("registered_wording"):
            problems.append(
                f"{a['study']}/{field} on the page is not byte-identical to the "
                f"`registered_wording` {r.id} carries beside it; one of the two was edited "
                "in transit, and the plan is the one thing here that never changes")
    return problems


def check_anchors_landed(root: Path, recs: list[R.Retraction]) -> list[str]:
    """Every `decision_rule` anchor must be visible in `data/slate.json`.

    THIS IS NOT REDUNDANT WITH THE SCANS ABOVE, and the asymmetry is worth stating because
    it is easy to assume the opposite.

    A withdrawn STATEMENT enforces itself. `build_slate.py` copies study #7's H2 sentence
    onto the page; the sentence carries `ret_0002`'s fingerprint; delete the join and the
    sentence is still there and `scan_structured` fails on it. The generator cannot drop that
    retraction quietly.

    A withdrawn READING has no such property. Study #10's H2 says "at least one candidate is
    both better than its null and confident in absolute terms" and matches no fingerprint at
    all -- the withdrawn clause is not in it, which is precisely why the anchor had to be
    filed by hand. Delete that join and the `reading_limit` block vanishes along with the
    only string that could have been scanned, every scan passes, and the page goes back to
    rendering a green CONFIRMED with nothing beside it. The guard would report a clean bill
    of health on the exact defect it exists to catch.

    So a `decision_rule` anchor is checked by its LANDING rather than by its text: the ledger
    says this verdict must carry a limit, and the built artefact is asked whether it does.
    """
    slate = root / "data" / "slate.json"
    wanted = [(r, a) for r in recs for a in r.anchors
              if a.get("kind") == "decision_rule"]
    if not wanted:
        return []
    if not slate.exists():
        return [f"{len(wanted)} decision_rule anchor(s) cannot be verified: "
                "data/slate.json is not built. Run platform/build_slate.py."]
    try:
        doc = json.loads(slate.read_text())
    except json.JSONDecodeError as exc:
        return [f"data/slate.json does not parse, so no anchor can be verified: {exc}"]
    by_study = {s.get("study_id"): s for s in doc.get("studies", [])}
    problems: list[str] = []
    for r, a in wanted:
        st = by_study.get(a["study"])
        if st is None:
            problems.append(f"{r.id} anchors a reading limit to study {a['study']!r}, which "
                            "is not in data/slate.json")
            continue
        hyp = next((h for h in st.get("hypotheses", [])
                    if h.get("name") == a["hypothesis"]), None)
        if hyp is None:
            problems.append(f"{r.id} anchors a reading limit to "
                            f"{a['study']}/{a['hypothesis']}, which data/slate.json does not "
                            "contain; the hypothesis was renamed or the anchor is wrong")
            continue
        got = (hyp.get("reading_limit") or {}).get("retraction")
        if got != r.id:
            problems.append(
                f"{a['study']}/{a['hypothesis']} renders verdict "
                f"{hyp.get('verdict')} with no reading limit naming {r.id} "
                f"(found {got!r}). The ledger says this verdict rests on a withdrawn "
                "reading; the page would publish it without one. Re-run "
                "platform/build_slate.py, and if that does not fix it the join in "
                "build_slate.py is gone.")
    return problems


def run(root: Path, *, remote: bool = False
        ) -> tuple[list[Hit], list[Path], list[str], list[str]]:
    recs = R.load(root / "retractions.jsonl")
    hits: list[Hit] = []
    scanned: list[Path] = []
    notes: list[str] = []
    reads: list[str] = []
    for p in surfaces(root):
        text = read_text(p)
        if text is None:
            continue
        scanned.append(p)
        rel = str(p.relative_to(root))
        doc = as_json(p, text)
        hits.extend(scan_structured(rel, text, doc, recs) if doc is not None
                    else scan_prose(rel, text, recs))
    remote_hits, skip, read = github_about(remote)
    hits.extend(remote_hits)
    if skip:
        notes.append(f"github:About — {skip}")
    if read:
        reads.append(f"github:About — {read}")
    # One claim, one line, one report. Three fingerprints on the same record all matching the
    # same sentence is one defect, and printing it three times would make a fixed surface
    # look like a worsening one.
    seen: set[tuple[str, int, str]] = set()
    unique: list[Hit] = []
    for h in hits:
        key = (h.path, h.line, h.rec.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(h)
    return unique, scanned, notes, reads


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--remote", action="store_true",
                    help="also read the GitHub About field via `gh`")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    print("=" * 78)
    print("retraction guard: a withdrawn claim may appear, but never without its withdrawal")
    print("=" * 78)
    try:
        hits, scanned, notes, reads = run(root, remote=args.remote)
    except R.LedgerError as exc:
        print(f"\nFAIL — {exc}\n")
        return 1

    recs = R.load(root / "retractions.jsonl")
    unlanded = check_anchors_landed(root, recs)
    unlanded_fields = check_plan_fields_landed(root, recs)
    n_anchored = sum(1 for r in recs for a in r.anchors
                     if a.get("kind") == "decision_rule")
    n_fields = sum(1 for r in recs for a in r.anchors
                   if a.get("kind") == "plan_field")
    print(f"\n{len(recs)} withdrawn claim(s) · {len(scanned)} surface(s) scanned · "
          f"{len(EXEMPT_DIRS)} director{'y' if len(EXEMPT_DIRS) == 1 else 'ies'} exempt")
    if n_anchored:
        print(f"    joins    {n_anchored - len(unlanded)}/{n_anchored} reading limit(s) "
              "landed in data/slate.json")
    if n_fields:
        print(f"    joins    {n_fields - len(unlanded_fields)}/{n_fields} republished plan "
              "field(s) carry their correction in data/slate.json")
    if not args.quiet:
        for d, why in EXEMPT_DIRS:
            print(f"    exempt   {d:<20} {why[:88]}")
        for d, why in NOT_SCANNED:
            print(f"    not read {d:<20} {why[:88]}")
    for n in notes:
        print(f"    SKIP     {n}")
    # Printed on the same ledger as the skips and at the same width, so the eye that learned
    # to look for SKIP finds the answer in the same column when the flag is passed.
    for n in reads:
        print(f"    remote   {n}")

    if unlanded:
        print(f"\nFAIL — {len(unlanded)} reading limit(s) the ledger requires are not on "
              "the page:\n")
        for p in unlanded:
            print(f"  {p}\n")
    if unlanded_fields:
        print(f"\nFAIL — {len(unlanded_fields)} republished plan field(s) the ledger "
              "corrects are on the page without the correction:\n")
        for p in unlanded_fields:
            print(f"  {p}\n")

    if not hits:
        if unlanded or unlanded_fields:
            return 1
        print(f"\nPASS — no surface asserts a retracted claim without its withdrawal, and "
              "every\nreading limit and plan-field correction the ledger requires is on the "
              "page.\n")
        return 0

    by_file: dict[str, list[Hit]] = {}
    for h in hits:
        by_file.setdefault(h.path, []).append(h)
    print(f"\nFAIL — {len(hits)} unwithdrawn assertion(s) of a retracted claim "
          f"across {len(by_file)} surface(s):\n")
    for path in sorted(by_file):
        for h in sorted(by_file[path], key=lambda x: x.line):
            loc = f"{h.path}:{h.line}" if h.line else h.path
            print(f"  {loc}   [{h.rec.id}]")
            print(f"    {h.why}")
            print(f"    | {h.text}")
            print(f"    withdrawn {h.rec.retracted_by.get('date')} by "
                  f"{h.rec.retracted_by.get('study') or h.rec.retracted_by.get('agent')}")
            print(f"    read instead: {h.rec.replacement[:150]}")
            print()
    print("Each is fixed either by correcting the surface to the replacement reading, or by "
          "\nattaching the withdrawal beside the claim. Never by editing retractions.jsonl.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
