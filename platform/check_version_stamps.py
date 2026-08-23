#!/usr/bin/env python3
"""Guard: every version stamp must name the version it is actually about.

The defect this exists for
--------------------------
`VERSION` read `1.1.0`. Ten stamps across six files read `1.0.0`, and one of them read this:

    - type: doi
      value: 10.5281/zenodo.22032685
      description: Version DOI -- permanently fixed to v1.0.0 (this release)

So a cold reader arriving at the repository was told, by the file GitHub's *Cite this
repository* button reads, to cite **Version 1.0.0** and DOI `...22032685` -- while the
abstract three lines above it described nine studies, study #12, the +0.0895 aggregate and
the withdrawal of the per-candidate reading. Study #12 was registered 2026-08-22T06:43:11Z;
the deposit behind `...22032685` was made 2026-08-20. The citation instruction and the
content it sat beside were two days and one retraction apart.

Nothing bound them. `release.sh` line 41 checks that `VERSION` equals the version *typed on
the command line* and nothing else, so `./release.sh 1.1.0` would have passed every gate and
published a tag whose citable record said 1.0.0.

The distinction this guard is built on
--------------------------------------
A repository carries two kinds of version stamp and they must not be made to agree:

**IDENTITY** -- "what version is this tree?" `CITATION.cff: version`, `codemeta.json .version`,
`.zenodo.json .version`, `biotools.json .version[]`, the README's how-to-cite blocks, and the
citation block `platform/build_dataset.py` copies onto the Provenance tab. Every one of these
must equal `VERSION`.

**PINNED** -- "what is this already-published thing?" A Zenodo *version* DOI is frozen to the
bytes of one deposit forever. A `releases/tag/v1.0.0.tar.gz` URL can only name a tag that has
been pushed. These must name a version that is **published**, and relabelling them to follow
`VERSION` would make the repository assert something Zenodo and GitHub will never make true.

The naive repair -- rewrite every `1.0.0` to `1.1.0` -- fixes the first class and breaks the
second, which is why both halves are asserted here rather than one rule over every numeral.

The half that was missing until 2026-08-23
------------------------------------------
Both rules above read the version NUMBER beside an identifier. Neither read the identifier.
So on the day v1.1.0 was deposited, every version string in this repository correctly said
1.1.0 and four citation surfaces still carried the DOI Zenodo minted for the v1.0.0 deposit
of 2026-08-20 -- and this guard passed, because "permanently fixed to v1.1.0" is a pinned
stamp naming a published release no matter which DOI it is describing. Checking the numeral
typed next to a version DOI and never the DOI is checking the caption, not the photograph.

`zenodo_dois.json` now declares which DOI belongs to which release, and the section beginning
"The DOI half" below holds the rules: every live citation slot must name the DOI declared for
this version, a superseded DOI may appear in prose but never without the version it belongs
to, and `--remote` resolves the concept DOI through the Zenodo API to confirm the declaration
against the archive itself.

What "published" means, mechanically
------------------------------------
Not a list in this file. `platform/build_release_notes.py` already owns the distinction: a
note whose first 4 KB contain `RELEASE-NOTE-FROZEN` belongs to a release that has been
published and the generator refuses to overwrite it; a note marked `RELEASE-NOTE-GENERATED`
is rebuilt from the artefacts on demand. So the published set is read from `docs/` under
exactly that rule, and a release becomes published here at the moment the author freezes its
note -- one edit, in the place the release actually happens.

The disclosure
--------------
When `VERSION` is not a published version, the tree is a version in preparation and every
surface that tells a reader how to cite must say so. The sentence is *derived* from the two
versions and required verbatim, so it cannot be half-corrected on one surface and left stale
on four -- which is the fan-out that produced this defect and the one before it.

The shape it takes, shown here with the versions it carried while 1.1.0 was in preparation
(1.1.0 was deposited on 2026-08-23, so this is an example of the form, not a statement about
the tree today):

    Version 1.1.0 is not yet deposited: it has no git tag and no version DOI. The most
    recent published release is v1.0.0, and the concept DOI resolves to that record until
    1.1.0 is published.

When `VERSION` is a published version -- between cutting a release and bumping `VERSION` for
the next cycle -- the rule inverts: the sentence must be ABSENT from every surface, and a
copy left behind is reported for removal.

Run `--disclosure` to print the current text to paste.

Two surfaces deliberately do NOT carry it, and the reasons are not the same:

* `.zenodo.json` is the description of the *next* deposit. By the time anyone reads it on
  zenodo.org, the version it describes has been published, so a sentence saying that version
  is undeposited would be false exactly where it is read.
* `docs/RELEASE_NOTES_v*.md` is generated by `build_release_notes.py` and frozen on release;
  a hand-added sentence there would be erased by the next rebuild or would falsify a frozen
  record.

Scope
-----
Sources, not built documents. `docs/*.docx`, `*.pptx`, `*.pdf` and `*.html` are gitignored
reading copies that do not exist in a clone; the generators that wrote them are not published
here either, and every version string they interpolated came from `CITATION.cff` -- so the
stamp is caught here, at the source, whether or not anything downstream renders it. The same
reasoning `platform/check_metadata_counts.py` gives for scanning generators rather than their
output.

`prespec/`, `data/superseded/` and `memory/ledger/` are not scanned. A record of what was
registered or believed is never rewritten to match today.

Usage
-----
    ./.venv/bin/python platform/check_version_stamps.py
    ./.venv/bin/python platform/check_version_stamps.py --self-test
    ./.venv/bin/python platform/check_version_stamps.py --disclosure
    ./.venv/bin/python platform/check_version_stamps.py --remote
    ./.venv/bin/python platform/check_version_stamps.py --root /path/to/scratch/tree
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retractions as R                                              # noqa: E402

FROZEN_TOKEN = "RELEASE-NOTE-FROZEN"
#: Byte-for-byte `platform/build_release_notes.py`'s own test, window included. The token has
#: to OPEN an HTML comment: `docs/RELEASE_NOTES_v1.1.0.md` names it in its generated header
#: ("replace this marker with RELEASE-NOTE-FROZEN"), so a bare substring search reports the
#: unreleased version as published -- which is the one mistake that would make this whole
#: guard invert, requiring the disclosure to be REMOVED from a tree that still needs it.
FROZEN_RE = re.compile(r"<!--\s*" + FROZEN_TOKEN)
FROZEN_WINDOW = 4096

#: `\b` does not exist between "v" and "1", so a `\b`-anchored pattern reads "fixed to
#: v1.0.0" as naming no version at all -- and a pinned reference that names no version is
#: exactly what this guard reports as a defect. The `v` is part of how every one of these is
#: written.
SEMVER = re.compile(r"(?<![\w.])v?(\d+\.\d+\.\d+)(?![\w.])")
NOTE_NAME = re.compile(r"^RELEASE_NOTES_v(\d+\.\d+\.\d+)\.md$")
#: A GitHub URL that can only name a tag that has been pushed.
TAG_URL = re.compile(r"/(?:releases/tag|archive/refs/tags)/v(\d+\.\d+\.\d+)")
#: A GitHub URL naming a file on the default branch -- it follows the tree, not a tag.
BLOB_URL = re.compile(r"/blob/[^/]+/docs/RELEASE_NOTES_v(\d+\.\d+\.\d+)\.md")

#: The phrase that turned a correct fact into the false belief. "permanently fixed to v1.0.0"
#: was true; "(this release)" was what told the reader those were the bytes in front of them.
THIS_RELEASE = re.compile(r"\bthis release\b", re.I)

#: The shape of the disclosure, used to find a STALE one after a release has been cut.
DISCLOSURE_SHAPE = re.compile(r"Version (\d+\.\d+\.\d+) is not yet deposited")


def disclosure(current: str, published: str) -> str:
    """Derived from the two versions. Never typed, so it cannot go half-stale."""
    return (f"Version {current} is not yet deposited: it has no git tag and no version DOI. "
            f"The most recent published release is v{published}, and the concept DOI "
            f"resolves to that record until {current} is published.")


#: Surfaces that tell a reader how to cite THIS TREE. See the docstring for the two that are
#: excluded and why they are excluded for different reasons.
DISCLOSURE_SURFACES: tuple[str, ...] = (
    "CITATION.cff",
    "codemeta.json",
    "biotools.json",
    "README.md",
    "docs/REGISTRATION.md",
    # Generated from CITATION.cff by platform/build_dataset.py and rendered by app.js's
    # renderCitation() into the Provenance tab. Listed so that a rebuild that drops the
    # sentence is caught here rather than on the page.
    "data/dataset.json",
    "data/dataset.js",
)


@dataclass(frozen=True)
class Stamp:
    """One version string, and which of the two kinds it is."""
    path: str
    line: int
    where: str          # human-readable locator
    kind: str           # "identity" | "pinned"
    version: str
    raw: str = ""


def _line_of(text: str, needle: str) -> int:
    i = text.find(needle)
    return text.count("\n", 0, i) + 1 if i >= 0 else 0


def _norm(s: str) -> str:
    return " ".join(s.split())


#: Line-leading markers that wrap prose without being part of it. The disclosure has to be
#: findable inside a markdown blockquote, a YAML comment and a JS comment, because those are
#: the shapes the surfaces it must appear on actually hold prose in -- `docs/REGISTRATION.md`
#: carries it in a `>` block, and a whitespace-only normalisation reads every `>` as a word.
_PROSE_MARKER = re.compile(r"^[ \t]*(?:[>#*\-]+|//|;)[ \t]*")


def _flatten(text: str) -> str:
    """Whole file as one line, with quote and comment markers removed."""
    return " ".join(_PROSE_MARKER.sub("", line).strip() for line in text.splitlines())


# --------------------------------------------------------------------------- #
# What is published
# --------------------------------------------------------------------------- #

def published_versions(root: Path) -> list[str]:
    """Versions whose release note carries the FROZEN marker, newest last.

    Read from `docs/`, under `build_release_notes.py`'s own rule, so this file holds no list
    of releases that could go stale against the releases themselves.
    """
    out = []
    for p in sorted((root / "docs").glob("RELEASE_NOTES_v*.md")):
        m = NOTE_NAME.match(p.name)
        if not m:
            continue
        if FROZEN_RE.search(p.read_text(errors="replace")[:FROZEN_WINDOW]):
            out.append(m.group(1))
    return sorted(out, key=lambda v: tuple(int(x) for x in v.split(".")))


# --------------------------------------------------------------------------- #
# Reading the stamps
# --------------------------------------------------------------------------- #

def _cff(root: Path) -> tuple[dict, str]:
    import yaml
    text = (root / "CITATION.cff").read_text()
    return yaml.safe_load(text), text


def dois(root: Path) -> tuple[str, str]:
    """(concept DOI, version DOI), both read out of CITATION.cff rather than typed here.

    The concept DOI is the root `doi:` field. The version DOI is the one entry under
    `identifiers:` of type doi that is not it. If that is ever ambiguous the guard refuses
    rather than guessing which record a reader would be sent to.
    """
    d, _ = _cff(root)
    concept = str(d.get("doi") or "")
    others = [str(i.get("value")) for i in (d.get("identifiers") or [])
              if i.get("type") == "doi" and str(i.get("value")) != concept]
    if not concept or len(others) != 1:
        raise SystemExit(
            f"CITATION.cff must carry one concept DOI in `doi:` and exactly one other DOI "
            f"under `identifiers:`; found doi={concept!r} and others={others}. "
            "Refusing to guess which one is frozen to a release.")
    return concept, others[0]


def stamps(root: Path) -> list[Stamp]:
    """Every version stamp on every source surface, classified."""
    out: list[Stamp] = []
    concept, version_doi = dois(root)

    # ---- CITATION.cff --------------------------------------------------------
    d, text = _cff(root)
    out.append(Stamp("CITATION.cff", _line_of(text, f"version: {d.get('version')}"),
                     "`version:`", "identity", str(d.get("version"))))
    for ident in d.get("identifiers") or []:
        if str(ident.get("value")) != version_doi:
            continue
        desc = _norm(str(ident.get("description") or ""))
        m = SEMVER.search(desc)
        out.append(Stamp("CITATION.cff", _line_of(text, version_doi),
                         f"the description of version DOI {version_doi}", "pinned",
                         m.group(1) if m else "", desc))

    # ---- codemeta.json -------------------------------------------------------
    text = (root / "codemeta.json").read_text()
    cm = json.loads(text)
    out.append(Stamp("codemeta.json", _line_of(text, f'"version": "{cm.get("version")}"'),
                     "`version`", "identity", str(cm.get("version"))))
    rn = str(cm.get("releaseNotes") or "")
    if rn:
        # A tag URL is pinned to a pushed tag; a blob-on-main URL follows the tree.
        m = TAG_URL.search(rn)
        if m:
            out.append(Stamp("codemeta.json", _line_of(text, rn),
                             "`releaseNotes` (a tag URL)", "pinned", m.group(1), rn))
        else:
            m = BLOB_URL.search(rn)
            out.append(Stamp("codemeta.json", _line_of(text, rn),
                             "`releaseNotes` (an in-tree note)", "identity",
                             m.group(1) if m else "", rn))

    # ---- .zenodo.json --------------------------------------------------------
    text = (root / ".zenodo.json").read_text()
    zn = json.loads(text)
    out.append(Stamp(".zenodo.json", _line_of(text, f'"version": "{zn.get("version")}"'),
                     "`version` (governs the NEXT deposit)", "identity",
                     str(zn.get("version"))))

    # ---- biotools.json -------------------------------------------------------
    text = (root / "biotools.json").read_text()
    bt = json.loads(text)
    for v in bt.get("version") or []:
        out.append(Stamp("biotools.json", _line_of(text, f'"{v}"'),
                         "`version[]`", "identity", str(v)))
    for dl in bt.get("download") or []:
        url = str(dl.get("url") or "")
        m = TAG_URL.search(url)
        if m:
            out.append(Stamp("biotools.json", _line_of(text, url),
                             "`download[].url` (a tag URL)", "pinned", m.group(1), url))
            # The sibling field must describe the archive its own URL points at. These were
            # two hand-typed copies of one fact sitting three lines apart.
            if str(dl.get("version") or "") != m.group(1):
                out.append(Stamp("biotools.json", _line_of(text, url),
                                 "`download[].version` (must equal its own URL's tag)",
                                 "pinned", str(dl.get("version") or ""), url))
            else:
                out.append(Stamp("biotools.json", _line_of(text, url),
                                 "`download[].version`", "pinned", str(dl.get("version"))))
    for oid in bt.get("otherID") or []:
        if version_doi not in str(oid.get("value") or ""):
            continue
        raw = _norm(str(oid.get("version") or ""))
        m = SEMVER.search(raw)
        out.append(Stamp("biotools.json", _line_of(text, str(oid.get("value"))),
                         f"`otherID[].version` beside version DOI {version_doi}", "pinned",
                         m.group(1) if m else "", raw))

    # ---- README.md -----------------------------------------------------------
    text = (root / "README.md").read_text()
    for pat, where in (
        (re.compile(r"\(Version (\d+\.\d+\.\d+)\) \[Computer software\]"),
         "the how-to-cite blockquote"),
        (re.compile(r"version\s*=\s*\{(\d+\.\d+\.\d+)\}"), "the BibTeX block"),
    ):
        for m in pat.finditer(text):
            out.append(Stamp("README.md", text.count("\n", 0, m.start()) + 1, where,
                             "identity", m.group(1), _norm(m.group(0))))
    for m in re.finditer(r"permanently fixed to v(\d+\.\d+\.\d+)", text):
        out.append(Stamp("README.md", text.count("\n", 0, m.start()) + 1,
                         "the version-DOI paragraph", "pinned", m.group(1),
                         _norm(text[max(0, m.start() - 60):m.end() + 60])))

    # The command the documentation tells a reader to paste. `release.sh` itself refuses when
    # VERSION disagrees with its argument, so a stale number here does not cut the wrong
    # release -- it wastes the reader's next five minutes and, worse, is the number they will
    # then type by hand. Its own `usage:` line is deliberately NOT bound: that string is a
    # shape example, and the script validates the real argument against VERSION.
    for rel in ("README.md", "docs/REGISTRATION.md"):
        p = root / rel
        if not p.is_file():
            continue
        body = p.read_text()
        for m in re.finditer(r"\./release\.sh (\d+\.\d+\.\d+)", body):
            out.append(Stamp(rel, body.count("\n", 0, m.start()) + 1,
                             "the `./release.sh` command a reader is told to run", "identity",
                             m.group(1), _norm(m.group(0))))

    # ---- the generated citation block, and the page that renders it ----------
    for rel in ("data/dataset.json", "data/dataset.js"):
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text()
        body = text
        if rel.endswith(".js"):
            body = body[body.find("{"):].rstrip().rstrip(";")
        cit = (json.loads(body) or {}).get("citation") or {}
        if not cit:
            continue
        out.append(Stamp(rel, _line_of(text, f'"version": "{cit.get("version")}"'),
                         "`citation.version` (rendered on the Provenance tab)", "identity",
                         str(cit.get("version"))))
        for ident in cit.get("identifiers") or []:
            if str(ident.get("value")) != version_doi:
                continue
            desc = _norm(str(ident.get("description") or ""))
            m = SEMVER.search(desc)
            out.append(Stamp(rel, _line_of(text, version_doi),
                             f"`citation.identifiers[{version_doi}].description`", "pinned",
                             m.group(1) if m else "", desc))
    return out


# --------------------------------------------------------------------------- #
# The rules
# --------------------------------------------------------------------------- #

def judge(st: Stamp, current: str, published: list[str]) -> str | None:
    """The complaint about this stamp, or None."""
    if st.kind == "identity":
        if st.version != current:
            return (f"states {st.version or '(none)'}, VERSION says {current}. This stamp "
                    "describes the tree, so it follows VERSION.")
        return None
    # pinned
    if not st.version:
        return ("names no version at all. A pinned reference must say which published "
                "release it is fixed to, or a reader assumes it is this one.")
    if st.version not in published:
        return (f"names v{st.version}, which is not a published release "
                f"(published: {', '.join('v' + v for v in published) or 'none'}). A version "
                "DOI, a tag URL and a release tarball can only name a release that exists.")
    if st.version != current and THIS_RELEASE.search(st.raw or ""):
        return (f"names v{st.version} and calls it \"this release\" while VERSION is "
                f"{current}. That phrase is what told a reader the deposit in front of them "
                "was the tree in front of them.")
    return None


def disclosure_hits(root: Path, current: str, published: list[str]) -> list[tuple]:
    """(path, line, complaint) for the undeposited-version disclosure."""
    hits = []
    latest = published[-1] if published else ""
    want = disclosure(current, latest) if latest else ""
    for rel in DISCLOSURE_SURFACES:
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text(errors="replace")
        flat = _norm(_flatten(text))
        stale = [m for m in DISCLOSURE_SHAPE.finditer(text) if m.group(1) != current]
        for m in stale:
            hits.append((rel, text.count("\n", 0, m.start()) + 1,
                         f"a disclosure about version {m.group(1)}, but VERSION is {current}. "
                         "It was left behind by a release."))
        if current in published:
            for m in DISCLOSURE_SHAPE.finditer(text):
                if m.group(1) == current:
                    hits.append((rel, text.count("\n", 0, m.start()) + 1,
                                 f"says version {current} is not yet deposited, but its "
                                 "release note is frozen, so it is. Remove the sentence."))
            continue
        if not want:
            continue
        if _norm(want) not in flat:
            hits.append((rel, 0, "does not carry the undeposited-version disclosure. "
                                 "Run --disclosure for the exact sentence."))
    return hits

# --------------------------------------------------------------------------- #
# The DOI half: which deposit does a version DOI actually name?
# --------------------------------------------------------------------------- #
#
# WHAT THE RULES ABOVE COULD NOT SEE
# ----------------------------------
# On 2026-08-23 the v1.1.0 deposit was published and every version string in this repository
# correctly read 1.1.0 -- and beside four of them sat the version DOI minted for the v1.0.0
# deposit of 2026-08-20. This guard passed. It read the NUMBER written next to the DOI and
# never read the DOI, so "Version DOI -- permanently fixed to v1.1.0" scored as a pinned
# stamp naming a published release while the identifier it described named a different one.
# A version DOI whose only checked property is the numeral typed beside it is a version DOI
# nothing is checking.
#
# THE CONSTRAINT
# --------------
# The fact needed here -- which deposit is DOI X -- lives on zenodo.org, and the guard has to
# work offline, in a clone, with no Zenodo account. So it takes the shape
# `check_retractions.py` already uses for the GitHub About field: the repository DECLARES the
# mapping, the guard enforces internal agreement offline, and `--remote` confirms the
# declaration against Zenodo when a network is there.
#
# The declaration is `zenodo_dois.json`, deliberately a file of its own. `CITATION.cff`,
# `codemeta.json`, `biotools.json` and `data/dataset.json` are all live citation surfaces; a
# mapping stored in any of them could only prove that surface agreed with itself, which is
# exactly what the defective tree did. The declaration has to be somewhere no reader is ever
# sent to cite from -- the arrangement `retractions.jsonl` has with `check_retractions.py`.
#
# TELLING AN INSTRUCTION FROM A HISTORICAL REFERENCE
# --------------------------------------------------
# The repository keeps true statements about the superseded v1.0.0 DOI on purpose, and
# README.md holds one of those and a live citation instruction five lines apart, so nothing
# can be settled by exempting a file. Two rules, each matched to the kind of surface:
#
#   SLOT   A machine-readable field that exists to answer "which DOI do I cite" --
#          `CITATION.cff identifiers[]`, `biotools.json otherID[]`, the README's how-to-cite
#          blockquote and BibTeX block, the generated `citation` block on the Provenance tab.
#          These are enumerated below, one by one, and each must hold the concept DOI or the
#          DOI declared for this version. No prose is read: a slot is an instruction because
#          of where it is, not because of what it says.
#
#   PROSE  Everywhere else, one rule: a superseded version DOI may appear, but never without
#          the version it belongs to. The withdrawal rule of `check_retractions.py`, one
#          identifier over -- and the same reasoning. A reader who meets
#          `10.5281/zenodo.22032685` and is not told it is the v1.0.0 deposit has been left
#          to assume it is the current one, which is how a historical sentence becomes an
#          instruction. The qualifier is the version string itself, in the same authored
#          block, found with `retractions.block_around` so the two guards agree on what a
#          block is. Every deliberate mention in this tree already carries it -- the run
#          prints how many it accepted -- so the rule costs a parenthetical and buys the
#          distinction. An UNDECLARED Zenodo DOI is judged only in a slot, never in prose:
#          a repository legitimately cites other people's deposits, and `research/` and
#          `memory/views/claims.md` both do.
#
# The error message is the fix. A slot naming an old DOI is told which version that DOI
# belongs to, because "CITATION.cff names 10.5281/zenodo.22032685, which belongs to v1.0.0"
# is the sentence that makes the defect obvious, and "the DOI is wrong" is not.

DECLARATION = "zenodo_dois.json"

#: A Zenodo DOI and its record id. Zenodo's record id is the DOI suffix, which is why the
#: declaration stores the DOI only -- a second copy of the same digits is a second thing to
#: get wrong. Prose writes a DOI three ways: in full, and in either shorthand (`...22032685`
#: and `…22032685`, both of which name the v1.0.0 deposit here). The prose rule below matches
#: on the record id alone, so it finds all three.
ZENODO_DOI = re.compile(r"10\.5281/zenodo\.(\d+)")


@dataclass(frozen=True)
class Deposit:
    """One published deposit, as declared."""
    version: str
    doi: str
    deposited: str
    note: str = ""

    @property
    def record(self) -> str:
        return self.doi.rsplit(".", 1)[-1]


@dataclass(frozen=True)
class Declaration:
    concept: str
    deposits: tuple[Deposit, ...]

    def by_version(self, version: str) -> Deposit | None:
        return next((d for d in self.deposits if d.version == version), None)

    def by_doi(self, doi: str) -> Deposit | None:
        return next((d for d in self.deposits if d.doi == doi), None)

    @property
    def concept_record(self) -> str:
        return self.concept.rsplit(".", 1)[-1]


def declaration(root: Path) -> Declaration:
    """Read and validate `zenodo_dois.json`.

    Refuses rather than guesses, the way `dois()` does. A declaration this guard had to
    interpret would be a second place for the same ambiguity to live.
    """
    p = root / DECLARATION
    if not p.is_file():
        raise SystemExit(
            f"{DECLARATION} is missing. It declares which Zenodo DOI belongs to which "
            "release and is the only thing that lets this guard check a version DOI "
            "offline. Nothing else in the tree carries that mapping.")
    try:
        doc = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{DECLARATION} does not parse: {exc}") from None

    concept = str(doc.get("concept_doi") or "")
    if not ZENODO_DOI.fullmatch(concept):
        raise SystemExit(f"{DECLARATION}: `concept_doi` must be a Zenodo DOI, got "
                         f"{concept!r}.")
    rows = doc.get("versions")
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"{DECLARATION}: `versions` must be a non-empty list, one row per "
                         "published deposit.")
    deposits: list[Deposit] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SystemExit(f"{DECLARATION}: versions[{i}] is not an object.")
        v, doi = str(row.get("version") or ""), str(row.get("doi") or "")
        if not SEMVER.fullmatch(v):
            raise SystemExit(f"{DECLARATION}: versions[{i}].version must be a semver, got "
                             f"{v!r}.")
        if not ZENODO_DOI.fullmatch(doi):
            raise SystemExit(f"{DECLARATION}: versions[{i}].doi must be a Zenodo DOI, got "
                             f"{doi!r}.")
        deposits.append(Deposit(v, doi, str(row.get("deposited") or ""),
                                _norm(str(row.get("note") or ""))))

    seen_v = [d.version for d in deposits]
    seen_d = [d.doi for d in deposits]
    if len(set(seen_v)) != len(seen_v):
        raise SystemExit(f"{DECLARATION}: a version is declared twice ({seen_v}). One "
                         "deposit per version.")
    if len(set(seen_d)) != len(seen_d):
        raise SystemExit(f"{DECLARATION}: one DOI is declared for two versions ({seen_d}). "
                         "A version DOI names one deposit and one only.")
    if concept in seen_d:
        raise SystemExit(f"{DECLARATION}: the concept DOI {concept} is also declared as a "
                         "version DOI. The concept DOI is never frozen to a release; it "
                         "resolves to the newest one.")
    deposits.sort(key=lambda d: tuple(int(x) for x in d.version.split(".")))
    return Declaration(concept, tuple(deposits))


def target_deposit(decl: Declaration, current: str, published: list[str]) -> Deposit | None:
    """The deposit every live citation surface must name, or None if there is not one yet.

    Normally this is the deposit for `VERSION`. It falls back to the newest published release
    while `VERSION` is IN PREPARATION, because in that state `VERSION` has no tag and no DOI:
    the citation surfaces legitimately name the previous deposit and say so through the
    disclosure sentence. Both states are real -- this tree sat in the second one for three
    days -- and a rule that only knew the first would demand a DOI Zenodo has not minted.
    """
    here = decl.by_version(current)
    if here is not None:
        return here
    for v in reversed(published):
        d = decl.by_version(v)
        if d is not None:
            return d
    return None


# --------------------------------------------------------------------------- #
# The live citation slots, enumerated
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Slot:
    """One machine-readable field that answers "which DOI do I cite"."""
    path: str
    line: int
    where: str
    doi: str


#: Files whose whole job includes telling a reader which deposit is this release. Each must
#: actually carry the target DOI, not merely avoid naming a wrong one -- a surface that
#: dropped the version DOI entirely would otherwise pass in silence.
MUST_NAME_TARGET: tuple[str, ...] = (
    "CITATION.cff",       # what GitHub's *Cite this repository* button reads
    "biotools.json",      # the ELIXIR registry record
    "data/dataset.json",  # generated from CITATION.cff, rendered on the Provenance tab
    "data/dataset.js",
)


def _finder(text: str):
    """Line numbers for repeated DOIs, advancing per DOI so the second mention of the concept
    DOI does not report the line of the first. Slots are collected in document order."""
    seen: dict[str, int] = {}
    def find(doi: str) -> int:
        i = text.find(doi, seen.get(doi, 0))
        if i < 0:
            i = text.find(doi)
        seen[doi] = i + 1 if i >= 0 else 0
        return text.count("\n", 0, i) + 1 if i >= 0 else 0
    return find


def _slot_dois(find, value: str, path: str, where: str) -> list[Slot]:
    return [Slot(path, find(m.group(0)), where, m.group(0))
            for m in ZENODO_DOI.finditer(value)]


def doi_slots(root: Path) -> list[Slot]:
    """Every Zenodo DOI sitting in a field that exists to be cited from."""
    out: list[Slot] = []

    # ---- CITATION.cff --------------------------------------------------------
    d, text = _cff(root)
    find = _finder(text)
    out += _slot_dois(find, str(d.get("doi") or ""), "CITATION.cff", "the root `doi:` field")
    for ident in d.get("identifiers") or []:
        if ident.get("type") != "doi":
            continue
        out += _slot_dois(find, str(ident.get("value") or ""), "CITATION.cff",
                          "`identifiers[]` of type doi")

    # ---- codemeta.json -------------------------------------------------------
    text = (root / "codemeta.json").read_text()
    cm, find = json.loads(text), _finder(text)
    for v in cm.get("identifier") or []:
        out += _slot_dois(find, str(v), "codemeta.json", "`identifier[]`")

    # ---- biotools.json -------------------------------------------------------
    text = (root / "biotools.json").read_text()
    bt, find = json.loads(text), _finder(text)
    for oid in bt.get("otherID") or []:
        if oid.get("type") != "doi":
            continue
        out += _slot_dois(find, str(oid.get("value") or ""), "biotools.json",
                          "`otherID[]` of type doi")

    # ---- README.md: the three blocks a reader copies out of ------------------
    text = (root / "README.md").read_text()
    for pat, where in (
        (re.compile(r"zenodo\.org/badge/DOI/(10\.5281/zenodo\.\d+)"), "the DOI badge"),
        (re.compile(r"^>\s*https://doi\.org/(10\.5281/zenodo\.\d+)", re.M),
         "the how-to-cite blockquote"),
        (re.compile(r"\b(?:doi|url)\s*=\s*\{(?:https://doi\.org/)?"
                    r"(10\.5281/zenodo\.\d+)\}"), "the BibTeX block"),
    ):
        for m in pat.finditer(text):
            out.append(Slot("README.md", text.count("\n", 0, m.start()) + 1, where,
                            m.group(1)))

    # ---- the generated citation block, and the page that renders it ----------
    for rel in ("data/dataset.json", "data/dataset.js"):
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text()
        body = text
        if rel.endswith(".js"):
            body = body[body.find("{"):].rstrip().rstrip(";")
        cit = (json.loads(body) or {}).get("citation") or {}
        if not cit:
            continue
        find = _finder(text)
        out += _slot_dois(find, str(cit.get("doi") or ""), rel, "`citation.doi`")
        for ident in cit.get("identifiers") or []:
            if ident.get("type") != "doi":
                continue
            out += _slot_dois(find, str(ident.get("value") or ""), rel,
                              "`citation.identifiers[]` of type doi")
    return out


def judge_slot(slot: Slot, decl: Declaration, tgt: Deposit, current: str) -> str | None:
    """The complaint about this slot, or None."""
    if slot.doi == decl.concept or slot.doi == tgt.doi:
        return None
    owner = decl.by_doi(slot.doi)
    if owner is None:
        return (f"names {slot.doi}, which {DECLARATION} does not declare — it is neither "
                f"the concept DOI {decl.concept} nor the version DOI of any release. Either "
                "a digit is wrong or a deposit was never written down.")
    return (f"names {slot.doi}. That DOI belongs to v{owner.version}"
            + (f", deposited {owner.deposited}" if owner.deposited else "")
            + f". VERSION is {current} and the DOI declared for it is {tgt.doi}"
            + (f" (v{tgt.version})" if tgt.version != current else "")
            + ". A version DOI is frozen to the bytes of one deposit forever, so this slot "
              "does not describe the wrong version — it sends the reader to it.")


# --------------------------------------------------------------------------- #
# Prose: a superseded DOI may appear, never without the version it belongs to
# --------------------------------------------------------------------------- #

#: Every surface a DOI can be read off, named explicitly rather than inferred from a walk,
#: for the reason `check_retractions.SURFACES` gives: an unlisted surface is an unwatched
#: one. `prespec/`, `data/superseded/` and `memory/ledger/` are absent for the reason the
#: module docstring gives -- a record of what was true then is never rewritten.
PROSE_SURFACES: tuple[str, ...] = (
    "README.md",
    "NOTICE",
    "CITATION.cff",
    "codemeta.json",
    "biotools.json",
    ".zenodo.json",
    "index.html",
    "app.js",
    "verify_all.py",
    "release.sh",
    "data/*.json",
    "data/*.js",
    "docs/*.md",
    "paper/*.md",
    "platform/**/*.py",
    "memory/*.md",
    "memory/views/*.md",
)

#: Exempt AS A FILE, for the reason `retractions.jsonl` is exempt from the retraction guard:
#: it is the ledger. It names every superseded DOI by construction -- that is its job, and it
#: names the owning version on the same row, which is the qualification the rule is about.
PROSE_EXEMPT_FILES: tuple[str, ...] = (DECLARATION,)

_PROSE_EXEMPT_DIRS: tuple[str, ...] = ("prespec/", "data/superseded/", "memory/ledger/")

#: A comment marker at the head of a line. `retractions.block_around` reads `#` as a Markdown
#: heading -- correct for `.md`, and in a `.py` or `.cff` file it cuts every comment line into
#: its own block, which would report a qualified two-line comment as unqualified. Stripping
#: the marker first hands that function the prose it was calibrated on, and a bare `#` or `//`
#: line becomes empty, which is the paragraph break the author meant by it.
_COMMENT_LEAD = re.compile(r"^(\s*)(?:#+:?|//+|\*)[ \t]?")


def qualified_by(block: str, version: str) -> bool:
    """Does this authored block say which version the DOI in it belongs to?

    The whole distinction between a citation instruction and a historical reference rests
    here, so it is one function with its own unit cases in `--self-test` rather than an
    expression buried in a loop. `v1.0.0` and `1.0.0` both count; `v1.0.10` does not, which is
    what the lookarounds are for.
    """
    return re.search(r"(?<![\w.])v?" + re.escape(version) + r"(?![\w.])", block) is not None


def _block_lines(rel: str, text: str) -> list[str]:
    lines = text.splitlines()
    if rel.endswith(".md"):
        return lines
    return [_COMMENT_LEAD.sub(r"\1", ln) for ln in lines]


def prose_surfaces(root: Path) -> list[Path]:
    out: list[Path] = []
    for pat in PROSE_SURFACES:
        for p in sorted(root.glob(pat)):
            if not p.is_file():
                continue
            rel = str(p.relative_to(root))
            if rel in PROSE_EXEMPT_FILES or any(rel.startswith(d)
                                                for d in _PROSE_EXEMPT_DIRS):
                continue
            out.append(p)
    return sorted(set(out))


def prose_hits(root: Path, decl: Declaration, tgt: Deposit) -> tuple[list[tuple], int, int]:
    """(hits, surfaces read, qualified mentions found).

    The count of qualified mentions is returned and printed for the reason
    `check_retractions.py` prints its remote read line: a rule that reports nothing is
    indistinguishable from a rule that matched nothing, and this one is supposed to be
    silently passing over fifteen deliberate historical references.
    """
    superseded = [d for d in decl.deposits if d.doi != tgt.doi]
    hits: list[tuple] = []
    qualified = 0
    files = prose_surfaces(root)
    for p in files:
        rel = str(p.relative_to(root))
        text = p.read_text(errors="replace")
        lines = _block_lines(rel, text)
        for dep in superseded:
            for m in re.finditer(r"(?<!\d)" + dep.record + r"(?!\d)", text):
                ln = text.count("\n", 0, m.start()) + 1
                if qualified_by("\n".join(R.block_around(lines, ln)), dep.version):
                    qualified += 1
                    continue
                hits.append((rel, ln,
                             f"names the version DOI {dep.doi} without saying, anywhere in "
                             f"the same block, that it belongs to v{dep.version}"
                             + (f" (deposited {dep.deposited})" if dep.deposited else "")
                             + ". An unqualified DOI reads as the one to cite. Name the "
                               "version beside it, or remove the mention."))
    return hits, len(files), qualified


def declaration_hits(root: Path, decl: Declaration, current: str,
                     published: list[str]) -> list[tuple]:
    """The declaration against the rest of the tree, offline."""
    hits: list[tuple] = []
    for dep in decl.deposits:
        if dep.version not in published:
            hits.append((DECLARATION, 0,
                         f"declares a version DOI for v{dep.version}, which is not a "
                         f"published release here (published: "
                         f"{', '.join('v' + v for v in published) or 'none'}). Zenodo mints "
                         "a version DOI only for a deposit, and a deposit follows a "
                         "release — freeze that release's note or remove the row."))
    if current in published and decl.by_version(current) is None:
        hits.append((DECLARATION, 0,
                     f"has no row for v{current}, which this tree says is published. The "
                     "webhook mints the version DOI after the tag is pushed, so the row is "
                     "added by hand at the release — that step has not been done."))
    concept, version_doi = dois(root)
    if concept != decl.concept:
        hits.append(("CITATION.cff", 0,
                     f"gives the concept DOI as {concept}; {DECLARATION} declares "
                     f"{decl.concept}. The concept DOI is minted once and never changes, so "
                     "one of these two was retyped."))
    return hits


# --------------------------------------------------------------------------- #
# --remote: the declaration against Zenodo itself
# --------------------------------------------------------------------------- #

ZENODO_API = "https://zenodo.org/api/records/{record}"

#: A test seam, and nothing else. `--remote` reads it so `platform/tools/mutation_suite.py`
#: can point the remote half at a `file://` copy of a Zenodo response and prove both branches
#: without a network -- the same move that let the retraction guard's GitHub surface be proven
#: with a stub `gh` on PATH instead of being declared UNPROVABLE. It is read ONLY when
#: `--remote` is passed, and the read line prints the address it actually used, so a run
#: pointed somewhere else says so in its own output.
ZENODO_API_ENV = "CBC_ZENODO_RECORD_URL"


def zenodo_latest(decl: Declaration, tgt: Deposit, enabled: bool
                  ) -> tuple[list[tuple], str | None, str | None]:
    """(hits, skip_reason, read_note). Exactly one of the two notes is set.

    The success case prints what it found, for the reason `check_retractions.github_about`
    gives at length: a silent success is indistinguishable from a skipped check, and the flag
    exists precisely so a reader can tell those two runs apart.

    A fetch that does not happen is a SKIP, not a FAIL. An unreachable network is a fact
    about the machine; only an answer that DISAGREES is a fact about the repository.
    """
    url = os.environ.get(ZENODO_API_ENV) or ZENODO_API.format(record=decl.concept_record)
    if not enabled:
        return [], (f"not resolved: pass --remote to read {url}. The declaration is checked "
                    "against the tree offline; only Zenodo can say what the latest version "
                    "actually is"), None
    import urllib.request                                            # noqa: PLC0415
    ctx = None
    try:
        import ssl                                                   # noqa: PLC0415
        import certifi                                               # noqa: PLC0415
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:                                                # noqa: BLE001
        ctx = None
    try:
        with urllib.request.urlopen(url, timeout=25, context=ctx) as fh:
            rec = json.loads(fh.read().decode())
    except Exception as exc:                                         # noqa: BLE001
        return [], (f"not resolved: {exc.__class__.__name__} reading {url}. `--remote` needs "
                    "a network; the offline rules above already ran"), None

    got_concept = str(rec.get("conceptdoi") or "")
    got_doi = str(rec.get("doi") or "")
    got_version = str((rec.get("metadata") or {}).get("version") or "")
    got_date = str((rec.get("metadata") or {}).get("publication_date") or "")
    hits: list[tuple] = []
    if got_concept and got_concept != decl.concept:
        hits.append((DECLARATION, 0,
                     f"declares the concept DOI {decl.concept}, but {url} answers with a "
                     f"record whose concept DOI is {got_concept}. The declaration is "
                     "pointing at a different Zenodo record entirely."))
    if got_doi != tgt.doi:
        hits.append((DECLARATION, 0,
                     f"declares {tgt.doi} for v{tgt.version}, but the concept DOI resolves "
                     f"to {got_doi} (Zenodo calls it version {got_version or '?'}, "
                     f"published {got_date or '?'}). Zenodo is the authority on this: the "
                     "row is wrong, or a newer deposit exists that was never written down."))
    elif got_version and got_version != tgt.version:
        hits.append((DECLARATION, 0,
                     f"declares {tgt.doi} as v{tgt.version}; Zenodo returns that DOI but "
                     f"labels the record version {got_version}. The DOI agrees and the "
                     "version string does not, which is the same mismatch this guard exists "
                     "for, one system over."))
    note = (f"resolved {url} — concept {got_concept or '(none)'} → record "
            f"{rec.get('id')}, DOI {got_doi}, version {got_version or '(unlabelled)'}, "
            f"published {got_date or '(undated)'}\n"
            f"{'':>13}declaration says v{tgt.version} is {tgt.doi} — "
            + ("Zenodo agrees" if not hits else f"{len(hits)} disagreement(s), below"))
    return hits, None, note


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #

#: (kind, version, raw, must_complain). Each case is a state this guard has to separate,
#: and every one of them is a state some surface of this repository was actually in.
SELF_TEST: tuple[tuple[str, str, str, bool], ...] = (
    # The defect, in both halves.
    ("identity", "1.0.0", "", True),                      # CITATION.cff version: 1.0.0
    ("identity", "1.1.0", "", False),
    ("pinned", "1.0.0", "Version DOI -- permanently fixed to v1.0.0 (this release)", True),
    ("pinned", "1.0.0", "Version DOI -- permanently fixed to v1.0.0, published 2026-08-20",
     False),
    # The naive repair: rewriting every 1.0.0 to 1.1.0 relabels a frozen deposit.
    ("pinned", "1.1.0", "Version DOI -- permanently fixed to v1.1.0", True),
    # A pinned reference that names nothing is the same failure with the number removed.
    ("pinned", "", "Version DOI", True),
    # An identity stamp is allowed to say "this release" -- it IS this release.
    ("identity", "1.1.0", "v1.1.0 (this release)", False),
)


#: A declaration to test the DOI rules against, with the shape this repository's own has:
#: one concept DOI and two deposits, the older superseded. The digits are the real ones,
#: because the messages these cases assert on are the messages a reader actually sees.
SELF_TEST_DECL = Declaration(
    "10.5281/zenodo.22032684",
    (Deposit("1.0.0", "10.5281/zenodo.22032685", "2026-08-20"),
     Deposit("1.1.0", "10.5281/zenodo.22070599", "2026-08-23")))

#: (doi, must_complain, must_name). Each row is a state a citation slot has been in or could
#: be put in by one careless edit. `must_name` is asserted because the requirement on this
#: rule is not only that it fires -- it is that the failure says which version the DOI it
#: found belongs to, since that is the sentence that turns "the DOI is wrong" into a fix.
SELF_TEST_SLOTS: tuple[tuple[str, bool, str], ...] = (
    ("10.5281/zenodo.22032684", False, ""),   # the concept DOI is always right to cite
    ("10.5281/zenodo.22070599", False, ""),   # the DOI declared for VERSION
    # The defect: a live slot left pointing at the previous deposit while every version
    # string around it correctly reads 1.1.0.
    ("10.5281/zenodo.22032685", True, "belongs to v1.0.0"),
    # A digit lost in transcription names a record that is not this project's at all.
    ("10.5281/zenodo.2203268", True, "does not declare"),
)

#: (block, version, is_qualified). The two rows that matter are the last two: the same
#: sentence with and without the version beside the DOI. Everything this guard claims about
#: telling an instruction from a historical reference reduces to that pair.
SELF_TEST_PROSE: tuple[tuple[str, str, bool], ...] = (
    ("frozen to the v1.0.0 deposit of 2026-08-20", "1.0.0", True),
    ("permanently fixed to 1.0.0", "1.0.0", True),
    # A different release whose string merely starts the same way must not qualify it.
    ("frozen to the v1.0.10 deposit", "1.0.0", False),
    ("Anyone who was given 10.5281/zenodo.22032685 should cite the concept DOI instead",
     "1.0.0", False),
    ("Anyone who was given 10.5281/zenodo.22032685, the v1.0.0 deposit, should cite the "
     "concept DOI instead", "1.0.0", True),
)


def self_test() -> int:
    current, published = "1.1.0", ["1.0.0"]
    failures = 0
    for kind, version, raw, must in SELF_TEST:
        st = Stamp("<self-test>", 0, "<self-test>", kind, version, raw)
        got = judge(st, current, published) is not None
        if got != must:
            print(f"  {'MISS' if must else 'FALSE POSITIVE'}  {kind} {version!r} {raw!r}\n"
                  f"        expected {'a complaint' if must else 'silence'}, got the other")
            failures += 1

    # The disclosure text is derived, so prove it is derived and not a constant.
    cases = [("1.1.0", "1.0.0"), ("2.0.0", "1.4.7")]
    for cur, pub in cases:
        s = disclosure(cur, pub)
        if f"Version {cur} is not yet deposited" not in s or f"v{pub}" not in s:
            print(f"  MISS  disclosure({cur!r}, {pub!r}) does not name both versions")
            failures += 1
        if not DISCLOSURE_SHAPE.search(s):
            print(f"  MISS  disclosure({cur!r}, {pub!r}) is not matched by its own shape, "
                  "so a stale one could never be found")
            failures += 1

    # ---- the DOI half ----------------------------------------------------
    tgt = SELF_TEST_DECL.by_version(current)
    for doi, must, must_name in SELF_TEST_SLOTS:
        why = judge_slot(Slot("<self-test>", 0, "<self-test>", doi), SELF_TEST_DECL, tgt,
                         current)
        if (why is not None) != must:
            print(f"  {'MISS' if must else 'FALSE POSITIVE'}  slot {doi}\n"
                  f"        expected {'a complaint' if must else 'silence'}, got the other")
            failures += 1
        elif why is not None and must_name not in why:
            print(f"  MISS  slot {doi} complained without saying {must_name!r}:\n"
                  f"        {why}")
            failures += 1
    for block, version, ok in SELF_TEST_PROSE:
        if qualified_by(block, version) != ok:
            print(f"  {'MISS' if ok else 'FALSE POSITIVE'}  prose {block[:60]!r} "
                  f"vs v{version}")
            failures += 1
    # A `#` comment run is one authored block. `retractions.block_around` reads `#` as a
    # Markdown heading and would cut this into three, reporting a qualified mention as
    # unqualified -- which is the one false positive that would push someone to exempt a file.
    py = ("# The naive fix would have made the repository assert that Zenodo\n"
          "# DOI 10.5281/zenodo.22032685 -- the v1.0.0 deposit -- names bytes\n"
          "# it will never name.\n")
    lines = _block_lines("platform/x.py", py)
    if not qualified_by("\n".join(R.block_around(lines, 2)), "1.0.0"):
        print("  MISS  a `#` comment run is not being read as one block, so a qualified "
              "mention in Python prose reports as unqualified")
        failures += 1

    total = (len(SELF_TEST) + 2 * len(cases) + len(cases)
             + len(SELF_TEST_SLOTS) + len(SELF_TEST_PROSE) + 1)
    print(f"self-test: {total - failures} passed, {failures} failed")
    return failures


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    """`--root DIR` points every read at another tree, for the mutation suite."""
    global REPO
    argv = sys.argv[1:] if argv is None else argv
    if "--root" in argv:
        REPO = Path(argv[argv.index("--root") + 1]).resolve()
    if "--self-test" in argv:
        return 1 if self_test() else 0

    current = (REPO / "VERSION").read_text().strip()
    published = published_versions(REPO)
    if "--disclosure" in argv:
        print(disclosure(current, published[-1]) if published
              else "(no published release: nothing to disclose against)")
        return 0

    found = stamps(REPO)
    hits = [(s.path, s.line, f"{s.where} {why}") for s in found
            if (why := judge(s, current, published))]
    hits += disclosure_hits(REPO, current, published)

    # ---- the DOI half ----------------------------------------------------
    decl = declaration(REPO)
    tgt = target_deposit(decl, current, published)
    slots = doi_slots(REPO)
    doi_hits: list[tuple] = declaration_hits(REPO, decl, current, published)
    prose_read = prose_qualified = 0
    remote_skip = remote_read = None
    if tgt is None:
        doi_hits.append((DECLARATION, 0,
                         f"declares no version DOI for {current} and none for any published "
                         f"release, so there is nothing a citation surface can be held to. "
                         f"Add the row minted for the newest published release."))
    else:
        doi_hits += [(s.path, s.line, f"{s.where} {why}") for s in slots
                     if (why := judge_slot(s, decl, tgt, current))]
        for rel in MUST_NAME_TARGET:
            if not (REPO / rel).is_file():
                continue
            if not any(s.path == rel and s.doi == tgt.doi for s in slots):
                doi_hits.append((rel, 0,
                                 f"carries no citation slot naming {tgt.doi}, the version "
                                 f"DOI declared for v{tgt.version}. This file's job includes "
                                 "telling a reader which deposit this release is; dropping "
                                 "the version DOI does not make that question go away."))
        ph, prose_read, prose_qualified = prose_hits(REPO, decl, tgt)
        doi_hits += ph
        rh, remote_skip, remote_read = zenodo_latest(decl, tgt, "--remote" in argv)
        doi_hits += rh
    # One defect, one line, one report. `check_retractions.run()` deduplicates for the same
    # reason: a comment naming a superseded DOI twice on one line is one thing to fix, and
    # printing it twice makes a repaired surface look like a worsening one.
    seen: set[tuple] = set()
    hits += [h for h in doi_hits if h not in seen and not seen.add(h)]

    print("=" * 78)
    print("version stamp guard: every stamp must name the version it is about")
    print("=" * 78)
    print(f"\nVERSION            {current}")
    print(f"published releases {', '.join('v' + v for v in published) or '(none)'}"
          f"   — read from {FROZEN_TOKEN} markers in docs/")
    print(f"state              {current} is "
          f"{'PUBLISHED' if current in published else 'IN PREPARATION (no tag, no DOI)'}")
    print(f"concept DOI        {decl.concept}   — declared in {DECLARATION}")
    if tgt is not None:
        print(f"version DOI        {tgt.doi}   — declared for v{tgt.version}"
              + ("" if tgt.version == current
                 else f", the newest published release while {current} is in preparation"))
    for dep in decl.deposits:
        if tgt is None or dep.doi != tgt.doi:
            print(f"superseded         {dep.doi}   — v{dep.version}, deposited "
                  f"{dep.deposited or '(undated)'}")

    ident = sum(1 for s in found if s.kind == "identity")
    pin = sum(1 for s in found if s.kind == "pinned")
    files = len({s.path for s in found} | set(DISCLOSURE_SURFACES))
    print(f"\n{ident} identity stamp(s) and {pin} pinned reference(s) checked "
          f"across {files} surface(s)")
    print(f"{len(slots)} citation slot(s) checked across "
          f"{len({s.path for s in slots})} surface(s)")
    # Printed on success as well as failure. A rule whose whole job is to stay silent over
    # deliberate historical references is indistinguishable, in its silence, from a rule that
    # matched nothing at all -- so it says how many it read and how many it let through.
    print(f"{prose_qualified} historical mention(s) of a superseded version DOI accepted "
          f"across {prose_read} prose surface(s),\n    each naming the version it belongs to")
    if remote_skip:
        print(f"    SKIP     zenodo:latest — {remote_skip}")
    if remote_read:
        print(f"    remote   zenodo:latest — {remote_read}")

    if not hits:
        print("\nPASS — every stamp that describes this tree equals VERSION, every stamp "
              "pinned to a\npublished deposit names a release that exists, every citation "
              "slot names the DOI\ndeclared for this version, and the release state is "
              "disclosed.\n")
        return 0

    print(f"\nFAIL — {len(hits)} stamp(s) naming the wrong version:\n")
    for path, line, why in sorted(hits):
        print(f"  {path}:{line}" if line else f"  {path}")
        print(f"    {why}")
    print("\nAn IDENTITY stamp follows VERSION. A PINNED reference — a version DOI, a tag "
          "URL, a\nrelease tarball — names the published release it is frozen to, and must "
          "never be\nrelabelled to follow VERSION. A version DOI is checked against "
          f"{DECLARATION},\nwhich says which deposit each DOI is: a live citation slot names "
          "this version's, and a\nsuperseded one may appear in prose only beside the version "
          "it belongs to. Run\n--disclosure for the sentence every citation surface must "
          "carry while VERSION is\nunreleased, and --remote to confirm the declaration "
          "against Zenodo.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
