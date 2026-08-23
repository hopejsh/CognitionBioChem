#!/usr/bin/env python3
"""The retraction ledger: the one place that says *this claim is withdrawn, and by what*.

WHY THIS FILE EXISTS
--------------------
A study artefact in this repository can record a verdict, a threshold, a deviation, a
confound, an exploratory metric and a custody note. Until now it could not record a
withdrawal. There was no field -- not in `data/study_*.json`, not in `data/slate.json`, not
in the `prespec` schema -- that said *this claim is withdrawn, by this study, on this
evidence*. So a withdrawal had nowhere to live, and the only way to express one was prose on
whichever surface the author happened to be editing.

That is the mechanism behind every survivor of the misleading-claims audit. A finding is
minted once and fans out into README prose, a registered plan's `statement`, `data/*.json`
prose fields, `CITATION.cff`, `docs/`, `paper/`, module docstrings and the GitHub About
field. When a later study kills it, the author corrects the surface in front of them, because
that is the surface in front of them. Nothing records that the sentence had *n* copies. One
retracted clause had five. A stale slate count spans eleven files.

`retractions.jsonl` at the repository root holds each withdrawn claim ONCE. Everything else
-- generators and the guard alike -- reads it from here.

THE INVARIANT THIS ENFORCES
---------------------------
    A retracted claim may still appear on a public surface, but never alone.

Two ways to satisfy that, and the guard (`platform/check_retractions.py`) knows both:

  * STRUCTURED, for JSON and the JS mirrors of it. The object that carries the retracted
    string must also carry a `retraction` (or `retractions`) field naming the record id.
    That is exact -- no proximity, no heuristics.
  * PROSE, for Markdown, Python, JavaScript, HTML and the rendered documents. A withdrawal
    marker must appear within a few lines of the match: the record id itself, or one of
    `WITHDRAWAL_MARKERS`.

WHAT IS EXEMPT, AND THE PRECISE SHAPE OF THE EXEMPTION
------------------------------------------------------
Three directories are exempt AS FILES: `prespec/`, `data/superseded/` and `memory/ledger/`.
They are the same kind of object -- an append-only or content-hashed record of what was
registered or believed at the time -- and rewriting any of them to match a later finding
would destroy the property the project is built on.

The exemption is by PATH and it stops there. A `prespec` statement that `build_slate.py`
republishes into `data/slate.json` and onto the page is NOT exempt, because at that point it
is a live claim on a public surface rather than a record of what was registered. Neither is
`memory/views/claims.md`, which is a rendering of the exempt ledger. That distinction is the
whole point: what is exempt is the *record*, never the *rendering*.

WHERE A RETRACTION ATTACHES
---------------------------
Not to the plan. `prespec/*.json` is hash-locked and its content hash is checked; a
registered hypothesis statement is a record of what was said in advance and stays
byte-identical forever. A retraction is a later fact and must stay appendable, so putting it
inside the plan would force a choice between lying and breaking the hash.

It attaches at the point of RENDERING, by anchor. An anchor names a join key that already
exists in the plan -- `(study_id, hypothesis name)` -- so the ledger points at the plan and
the plan never points back. `build_slate.py` performs that join on every build, which is why
the retraction cannot be forgotten: it is re-attached from scratch each time `slate.json` is
written. And the guard checks the result independently of the generator, so deleting the join
fails the build rather than quietly un-retracting the claim.

TWO WAYS A CLAIM CAN BE LIVE ON A VERDICT, AND THEY ARE NOT THE SAME REPAIR
---------------------------------------------------------------------------
The first sweep of the page found both, and rendering them alike would have printed a
falsehood in the act of correcting one.

  `kind: "hypothesis"` -- THE STATEMENT IS WITHDRAWN. Study #7 registered
  `H2_iptm_calibration` as "ipTM predicts whether the interface is right, so it can be used
  as a screening filter". That sentence is superseded. It still renders exactly as
  registered, struck, with the withdrawal beside it.

  `kind: "plan_field"` -- THE PLAN SAYS SOMETHING TRUE OF ITS OWN MOMENT AND WRONG NOW, AND
  THE PLAN IS NOT THE PROBLEM; THE REPUBLICATION IS. A lineage note, a rationale, an
  exclusions clause -- a plan field that is not a hypothesis at all -- can state a fact the
  repository has since measured differently. `msa-specificity-v9`'s `supersedes_reason`
  says the screened set gives "13 distinct designs"; the two screens have since recorded 13
  candidate-receptor constructs covering 12 distinct peptides. The registered plan keeps
  that sentence forever, because that is what was registered and the hash says so. What
  cannot keep it is `build_slate.py`, which copies the field onto the Studies tab, where it
  is no longer a record of what was registered but a live count in front of a reader. So
  the anchor names the FIELD rather than a hypothesis, carries the `correction` in the
  ledger, and the renderer prints the registered wording and the correction together. The
  field is never rewritten on the way out: a reader who is told the plan is byte-identical
  must be able to see the bytes.

  `kind: "decision_rule"` -- THE STATEMENT STANDS AND SO DOES THE VERDICT; WHAT IS WITHDRAWN
  IS WHAT THE VERDICT LICENSES. Study #10 registered "at least one candidate is both better
  than its null and confident in absolute terms", and 2 of 13 candidates cleared the
  registered conjunction, so CONFIRMED is a true record of a threshold firing. But the rule
  reads the composition-matched null one candidate at a time, and that reading is `ret_0001`,
  withdrawn by study #12. Striking that statement would assert something false -- nothing
  about it was withdrawn. So a `decision_rule` anchor carries its own `limit` sentence, the
  renderer leaves the statement and the verdict intact, and what it prints beside them is the
  boundary: what this verdict does not license, and on whose measurement.

The distinction is the reason anchors are typed at all. A single `retraction` field on a
hypothesis could not tell a renderer which of the two it was looking at.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "retractions.jsonl"

#: Words that count as a withdrawal being present next to a retracted claim in prose. A
#: record may narrow or extend this with its own `withdrawal_markers`.
WITHDRAWAL_MARKERS = (
    r"retract(?:ed|ion|s)?",
    r"withdraw(?:n|al|s)?",
    r"does not stand",
    r"no longer (?:stands|holds|true)",
    r"supersed(?:ed|es)",
    r"struck",
    r"refuted",
    r"❌",
)
_MARKER_RE = re.compile("|".join(WITHDRAWAL_MARKERS), re.I)


def states_a_withdrawal(text: str | None) -> bool:
    """True when `text` withdraws something in its own words.

    A generator uses this to decide how loudly to render a passage it is copying: an
    artefact's `interpretation_key` that says "this key previously ended ... and it is
    withdrawn" is a correction, and a correction rendered at the same weight as a caption is
    a correction the reader does not see.
    """
    return bool(text and _MARKER_RE.search(text))

#: How far from a match a prose withdrawal marker may sit. Same line counts as distance 0.
#: Twelve lines is a long paragraph in this repository's README, which is the surface that
#: does this correctly today (the Slate #7 gate paragraph quotes the retracted clause and
#: withdraws it four lines later).
#:
#: A hard line count alone is not enough, and the first run of this guard proved it on real
#: data: `memory/views/claims.md` renders 860 claims as consecutive two-line list items, so a
#: `❌` on one claim cleared a completely unrelated claim six lines below it -- and the claim
#: it cleared was audit finding 4. The window is therefore clipped to the authored block that
#: contains the match (see `block_around`), and the line count is only the outer bound.
PROSE_WINDOW_LINES = 12

#: A line that begins a new authored unit: a Markdown list item, a heading, or a table row.
#: The window never crosses one of these, because the sentence on the other side was written
#: by someone making a different claim.
_BLOCK_START = re.compile(r"^\s{0,3}(?:[-*+•]\s|\d+[.)]\s|#{1,6}\s|\|)")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def block_around(lines: list[str], ln: int, window: int = PROSE_WINDOW_LINES) -> list[str]:
    """The authored block containing line `ln` (1-indexed), clipped to `window` lines.

    Bounded below by a blank line or the start of the next block. Bounded above the same
    way, with one exception that indentation makes unambiguous: a NESTED list item is part
    of its parent, so the walk climbs out to the outermost bullet. `memory/views/refuted.md`
    is why -- its `- rationale:` and `- refuting claim:` bullets sit under a parent item
    whose `❌` and "refuted by" line is the withdrawal for all of them. A sibling at the same
    indent stops the walk, because that is a different claim.
    """
    i = ln - 1
    cur = _indent(lines[i]) if _BLOCK_START.match(lines[i]) else 1 << 30
    lo = i
    while lo > 0:
        prev = lines[lo - 1]
        if not prev.strip():
            break
        if _BLOCK_START.match(prev):
            if _indent(prev) < cur:
                lo -= 1
                cur = _indent(prev)
                if cur == 0:
                    break
                continue
            break
        if i - lo >= window:
            break
        lo -= 1
    hi = i
    while hi + 1 < len(lines) and lines[hi + 1].strip() \
            and not _BLOCK_START.match(lines[hi + 1]):
        if hi - i >= window:
            break
        hi += 1
    return lines[lo:hi + 1]

_REQUIRED = ("schema_version", "id", "status", "claim", "first_asserted", "retracted_by",
             "evidence", "replacement", "fingerprints")
_ID_RE = re.compile(r"^ret_\d{4}$")

#: Anchor kinds a generator can join on, and the keys each one needs to be joinable. An
#: anchor whose kind is not here is provenance only -- `constant`, for instance, records
#: which module holds the withdrawn value and no generator reads it. An anchor whose kind IS
#: here but is missing a key is a join that will silently never fire, which is the failure
#: this ledger exists to stop, so `check_ledger` rejects it.
ANCHOR_KEYS: dict[str, tuple[str, ...]] = {
    "hypothesis": ("study", "name"),
    "decision_rule": ("study", "hypothesis", "limit"),
    # `correction` is required for the same reason `limit` is: the ledger holds the claim and
    # the replacement, but what a reader of THIS field needs is the one sentence that says
    # what the field now reads as. Leaving it to the renderer would put it in a generator,
    # which is where every fanned-out sentence in this repository started.
    "plan_field": ("study", "field", "correction"),
}


class LedgerError(ValueError):
    """The ledger itself is malformed. Never downgraded to a warning: a retraction ledger
    that cannot be parsed is indistinguishable from no retraction ledger at all, and the
    failure mode of the second one is the entire audit."""


class Retraction:
    """One withdrawn claim, held once."""

    def __init__(self, rec: dict, line: int) -> None:
        self.rec = rec
        self.line = line
        self.id: str = rec["id"]
        self.claim: str = rec["claim"]
        self.replacement: str = rec["replacement"]
        self.evidence: str = rec["evidence"]
        self.retracted_by: dict = rec["retracted_by"]
        self.first_asserted: dict = rec["first_asserted"]
        self.anchors: list[dict] = rec.get("anchors") or []
        self.notes: str = rec.get("notes", "")
        self.patterns = [re.compile(p) for p in rec["fingerprints"]]
        markers = rec.get("withdrawal_markers")
        self.marker_re = (re.compile("|".join(markers), re.I) if markers else _MARKER_RE)

    # -- matching ----------------------------------------------------------- #

    def search(self, text: str) -> list[re.Match]:
        """Every place this claim appears in `text`."""
        return [m for p in self.patterns for m in p.finditer(text)]

    def acknowledged_in(self, text: str) -> bool:
        """True when `text` carries the record id or a withdrawal marker."""
        return self.id in text or bool(self.marker_re.search(text))

    def matches_anchor(self, kind: str, **keys) -> bool:
        for a in self.anchors:
            if a.get("kind") != kind:
                continue
            if all(a.get(k) == v for k, v in keys.items()):
                return True
        return False

    # -- what a generator renders ------------------------------------------- #

    def as_rendered(self) -> dict:
        """The block a generator attaches beside the claim it withdraws.

        Deliberately small and deliberately complete: what was withdrawn, who withdrew it,
        on what evidence, and what to read instead. A reader who sees only this block and
        never opens the ledger has the whole correction.
        """
        by = self.retracted_by
        return {
            "id": self.id,
            "claim": self.claim,
            "retracted_by": {k: by.get(k) for k in
                             ("kind", "study", "prespec", "artefact", "hypothesis",
                              "verdict", "date") if by.get(k) is not None},
            "evidence": self.evidence,
            "replacement": self.replacement,
            "ledger": "retractions.jsonl",
        }

    def as_reading_limit(self, anchor: dict) -> dict:
        """The block a generator attaches beside a verdict whose RULE rests on this claim.

        Note what is deliberately absent: any suggestion that the statement or the verdict
        was withdrawn. Neither was. The block says what the verdict does not license and
        who established the boundary, and it quotes the withdrawn reading so a reader can
        see for themselves that the two are different objects.

        `retraction` carries the record id inside the block on purpose. It is what the
        withdrawn clause quoted in `withdrawn_reading` needs beside it for
        `check_retractions.py` to accept this as a withdrawal rather than an assertion --
        the same rule that governs every other structured surface, applied here rather than
        exempted here.
        """
        by = self.retracted_by
        return {
            "retraction": self.id,
            "limit": anchor["limit"],
            "withdrawn_reading": self.claim,
            "withdrawn_by": {k: by.get(k) for k in
                             ("kind", "study", "prespec", "artefact", "hypothesis",
                              "verdict", "date") if by.get(k) is not None},
            "read_instead": self.replacement,
            "applies_to": "what the verdict licenses, not the statement and not the verdict",
            "ledger": "retractions.jsonl",
        }

    def as_plan_field_correction(self, anchor: dict) -> dict:
        """The block a generator attaches beside a REPUBLISHED PLAN FIELD it has outlived.

        `registered_wording` is the plan's own bytes, carried here so the correction and the
        text it corrects can never be separated -- and so a renderer has no reason to edit
        the field on the way out. It is the same string `build_slate.py` copies from the
        plan; a reader comparing the page against `prespec/` must find them identical.

        `retraction` sits inside the block for the reason it does in `as_reading_limit`: the
        withdrawn wording is quoted here, and a quotation of a withdrawn claim is only a
        withdrawal if the record id is beside it. Same rule as every other structured
        surface, applied here rather than exempted here.
        """
        by = self.retracted_by
        return {
            "retraction": self.id,
            "field": anchor["field"],
            "correction": anchor["correction"],
            "registered_wording": anchor.get("registered_wording"),
            "withdrawn_wording": self.claim,
            "withdrawn_by": {k: by.get(k) for k in
                             ("kind", "study", "prespec", "artefact", "hypothesis",
                              "verdict", "date") if by.get(k) is not None},
            "read_instead": self.replacement,
            "applies_to": ("the wording this page republishes, not the registered plan, "
                           "which is hash-locked and stays byte-identical"),
            "ledger": "retractions.jsonl",
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Retraction {self.id}: {self.claim[:60]}...>"


def load(path: Path | None = None, *, validate: bool = True) -> list[Retraction]:
    """Read the ledger. Raises LedgerError rather than returning a partial list."""
    p = path or LEDGER
    if not p.exists():
        raise LedgerError(f"{p} does not exist; the retraction ledger is not optional")
    out: list[Retraction] = []
    for i, raw in enumerate(p.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("//"):
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{p.name}:{i} is not JSON: {exc}") from exc
        out.append(Retraction(rec, i))
    if validate:
        problems = check_ledger(out, repo=p.parent)
        if problems:
            raise LedgerError(f"{p.name} is malformed:\n  " + "\n  ".join(problems))
    return out


def check_ledger(recs: list[Retraction], *, repo: Path | None = None) -> list[str]:
    """Every way a retraction record can be wrong that a machine can see.

    The interesting two are the last pair, and neither is bureaucratic:

    * A fingerprint that does not match its own `claim` is a fingerprint for some other
      sentence. It will either catch nothing or catch the wrong thing, and both failures are
      silent.
    * A fingerprint that matches the `replacement` would make the corrected reading trip the
      guard forever, which trains people to add exemptions. The one thing a retraction must
      never do is make the truth harder to publish than the error.
    """
    root = repo or REPO
    problems: list[str] = []
    seen: dict[str, int] = {}
    for r in recs:
        at = f"retractions.jsonl:{r.line}"
        for k in _REQUIRED:
            if k not in r.rec:
                problems.append(f"{at} missing required field {k!r}")
        if not _ID_RE.match(r.id or ""):
            problems.append(f"{at} id {r.id!r} is not of the form ret_NNNN")
        if r.id in seen:
            problems.append(f"{at} duplicate id {r.id} (first at line {seen[r.id]}); a "
                            "withdrawn claim is held ONCE, and two records for one claim is "
                            "the fan-out this ledger exists to stop")
        seen[r.id] = r.line
        if r.rec.get("status") != "withdrawn":
            problems.append(f"{at} status {r.rec.get('status')!r}: the only status a record "
                            "may carry today is 'withdrawn'; reinstating a claim is a new "
                            "record, never an edit to this one")
        if not r.rec.get("fingerprints"):
            problems.append(f"{at} has no fingerprints, so nothing on any surface can be "
                            "matched against it")
        by = r.retracted_by
        for field in ("prespec", "artefact", "study", "ledger_record"):
            if field in by and by[field] is None and f"{field}_absent_reason" not in by:
                problems.append(f"{at} retracted_by.{field} is null with no "
                                f"{field}_absent_reason; a missing citation must be stated, "
                                "not omitted")
        pre = by.get("prespec")
        if pre and root:
            hits = sorted((root / "prespec").glob(f"*.{pre}.json"))
            if len(hits) != 1:
                problems.append(f"{at} retracted_by.prespec {pre!r} matches {len(hits)} "
                                "registered plans; it must match exactly one")
        art = by.get("artefact")
        if art and root and not (root / art).exists():
            problems.append(f"{at} retracted_by.artefact {art!r} does not exist")
        if not (r.replacement or "").strip():
            problems.append(f"{at} has no replacement reading; a withdrawal that does not "
                            "say what to read instead leaves the reader worse off")
        # An anchor is the ledger's one statement of WHERE a claim is live. A malformed one
        # does not raise -- it joins against nothing, forever, and the page goes on
        # publishing the claim while the ledger reads as though it were handled.
        if r.anchors and "anchors_absent_reason" in r.rec:
            problems.append(f"{at} carries {len(r.anchors)} anchor(s) and an "
                            "anchors_absent_reason; one of the two is untrue")
        if not r.anchors and not r.rec.get("anchors_absent_reason"):
            problems.append(f"{at} has no anchors and no anchors_absent_reason; a record "
                            "that joins to nothing must say why, or it is indistinguishable "
                            "from one whose join was forgotten")
        for i, a in enumerate(r.anchors):
            kind = a.get("kind")
            if not kind:
                problems.append(f"{at} anchors[{i}] has no kind")
                continue
            for k in ANCHOR_KEYS.get(kind, ()):
                if not str(a.get(k) or "").strip():
                    problems.append(f"{at} anchors[{i}] is kind {kind!r} and needs a "
                                    f"non-empty {k!r} to join on; without it the join "
                                    "never fires and nothing says so")
            if kind == "plan_field":
                problems += _check_plan_field(at, i, r, a, root)
        for pat, src in zip(r.patterns, r.rec["fingerprints"]):
            if not pat.search(r.claim):
                problems.append(f"{at} fingerprint {src!r} does not match its own claim")
            if pat.search(r.replacement):
                problems.append(f"{at} fingerprint {src!r} also matches the replacement "
                                "reading, so the correction would trip the guard")
    return problems


def _check_plan_field(at: str, i: int, r: "Retraction", a: dict,
                      root: Path) -> list[str]:
    """A `plan_field` anchor must quote a plan field that exists and still says it.

    Three ways this anchor rots, all silent, all checked here rather than left to a reader:

    * The plan is not there, or the field is not in it. The join fires against nothing and
      the ledger reads as though the republication were handled.
    * The field no longer carries the claim -- someone edited a plan, which is a much larger
      problem, or the anchor names the wrong field. Either way the page would print a
      correction beside text that does not contain the error.
    * `registered_wording` has drifted from the plan's bytes. That field exists so the
      correction travels with the exact string it corrects; a copy that is merely similar is
      worse than none, because it invites a reader to believe they have compared them.
    """
    out: list[str] = []
    study, field = a.get("study"), a.get("field")
    if not (study and field):
        return out
    hits = sorted((root / "prespec").glob(f"{study}.*.json"))
    if len(hits) != 1:
        return [f"{at} anchors[{i}] names plan {study!r}, which matches {len(hits)} files "
                "in prespec/; it must match exactly one"]
    try:
        content = json.loads(hits[0].read_text()).get("content") or {}
    except json.JSONDecodeError as exc:
        return [f"{at} anchors[{i}]: {hits[0].name} does not parse: {exc}"]
    text = content.get(field)
    if not isinstance(text, str):
        return [f"{at} anchors[{i}] names field {field!r} of {study}, which the registered "
                "plan does not carry as a string; the join would never fire"]
    if not r.search(text):
        out.append(f"{at} anchors[{i}] corrects {study}/{field}, but none of this record's "
                   "fingerprints match what that field says; the correction would be "
                   "rendered beside text that does not contain the claim")
    reg = a.get("registered_wording")
    if reg is not None and reg != text:
        out.append(f"{at} anchors[{i}].registered_wording is not byte-identical to "
                   f"{study}/{field} in prespec/{hits[0].name}; a quotation of a hash-locked "
                   "plan that does not match it is worse than no quotation")
    return out


# --------------------------------------------------------------------------- #
# The generator-facing API. build_slate.py and any future generator use these two
# and nothing else, so there is exactly one join and it lives here.
# --------------------------------------------------------------------------- #

def for_hypothesis(recs: list[Retraction], study_id: str, name: str,
                   statement: str | None = None) -> Retraction | None:
    """The retraction that attaches to one registered hypothesis, if any.

    Anchor first, because an anchor is an explicit statement by whoever filed the record
    that THIS hypothesis is the one. Fingerprint second, so that a claim whose text is
    republished under a name nobody anticipated is still caught -- the same reason
    build_slate.py walks the artefact's verdicts rather than the plan's hypothesis list.
    """
    for r in recs:
        if r.matches_anchor("hypothesis", study=study_id, name=name):
            return r
    if statement:
        for r in recs:
            if r.search(statement):
                return r
    return None


def reading_limit_for(recs: list[Retraction], study_id: str,
                      name: str) -> tuple[Retraction, dict] | None:
    """The withdrawn reading a hypothesis's DECISION RULE rests on, if any.

    Anchor only, with no fingerprint fallback, and the asymmetry with `for_hypothesis` is
    deliberate. A withdrawn STATEMENT can be recognised by its own text, because the text is
    the claim. A withdrawn READING cannot: study #10's H2 says "at least one candidate is
    both better than its null and confident in absolute terms" and contains not one word of
    the clause `ret_0001` withdraws. Whether that rule reads the null one candidate at a time
    is a judgement about what the rule does, and a judgement is filed, never inferred. So the
    join fires only where someone wrote the anchor down, and the `limit` sentence they wrote
    with it travels as part of it.
    """
    for r in recs:
        for a in r.anchors:
            if (a.get("kind") == "decision_rule" and a.get("study") == study_id
                    and a.get("hypothesis") == name):
                return r, a
    return None


def plan_field_for(recs: list[Retraction], study_id: str,
                   field: str) -> tuple[Retraction, dict] | None:
    """The correction that attaches to one republished PLAN FIELD, if any.

    Anchor only, and unlike `reading_limit_for` the reason is not that the text cannot be
    recognised -- it can, the withdrawn wording is exactly what the plan says and the
    fingerprint matches it. The reason is that the `correction` sentence is a judgement about
    what the field should be read as now, and a judgement is filed, never inferred.

    The fingerprint is not wasted. A republication this join misses is still a live withdrawn
    claim on a public surface, so `check_retractions.py` fails the build on it by text. The
    two halves cover different failures: the anchor makes the page say the right thing, the
    fingerprint makes sure the page cannot stay quiet.
    """
    for r in recs:
        for a in r.anchors:
            if (a.get("kind") == "plan_field" and a.get("study") == study_id
                    and a.get("field") == field):
                return r, a
    return None


def for_text(recs: list[Retraction], text: str) -> list[Retraction]:
    """Every retraction whose claim appears in `text`, unacknowledged or not."""
    return [r for r in recs if r.search(text)]


def main() -> int:
    """`python3 platform/retractions.py` -- validate and list the ledger."""
    try:
        recs = load()
    except LedgerError as exc:
        print(f"FAIL — {exc}")
        return 1
    print("=" * 78)
    print(f"retraction ledger: {len(recs)} withdrawn claim(s)")
    print("=" * 78)
    for r in recs:
        by = r.retracted_by
        src = by.get("study") or by.get("agent") or "?"
        pre = by.get("prespec") or by.get("prespec_absent_reason", "")
        print(f"\n{r.id}  withdrawn {by.get('date')}  by {src}")
        print(f"     plan      {pre}")
        print(f"     claim     {r.claim[:120]}")
        print(f"     instead   {r.replacement[:120]}")
        print(f"     patterns  {len(r.patterns)}   anchors {len(r.anchors)}")
        for a in r.anchors:
            if a.get("kind") == "decision_rule":
                print(f"     limits    {a['study']} / {a['hypothesis']}")
            elif a.get("kind") == "hypothesis":
                print(f"     withdraws {a['study']} / {a['name']}")
            elif a.get("kind") == "plan_field":
                print(f"     corrects  {a['study']} / {a['field']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
