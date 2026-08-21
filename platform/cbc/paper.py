"""Turn the drafted paper sections into a format-neutral block list.

The paper exists once, as markdown with two kinds of marker:

    [@key]  or  [@key1; @key2]        a citation, resolved against the verified library
    [FIGURE: name.png - caption]      a figure, numbered by position

Four documents are rendered from that one source -- English and Korean, Word and slides -- so
the parsing lives here and each renderer only decides how a block LOOKS. A citation number is
assigned on first appearance across the whole paper, which is why numbering cannot be done
per section and cannot be done in the renderer.

Nothing in this module formats anything, and nothing in it invents a number: a [@key] with no
entry in the reference library raises rather than rendering as itself, for the same reason
cite() raises in the report generators.
"""

from __future__ import annotations

import json
import re

from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The order the drafted sections appear in the finished paper. The second field opens a new
#: top-level part; the third names it.
ORDER = [
    ("intro_1_landscape", 1, "Introduction"),
    ("intro_2_prediction", 0, None),
    ("intro_3_rationale", 0, None),
    ("methods", 1, "Methods"),
    ("results_1_gate", 1, "Results"),
    ("results_2_screen", 0, None),
    ("results_3_anatomy", 0, None),
    ("discussion_1_meaning", 1, "Discussion"),
    ("discussion_2_method", 0, None),
    ("discussion_3_limits", 0, None),
    ("conclusions", 1, "Conclusions"),
]

#: Where each figure actually belongs. Every section author called for the figures relevant
#: to their own argument, which is right for a section and wrong for a manuscript: five images
#: were placed fifteen times. A figure appears once, at the point where it is first discussed
#: substantively, and every later mention is a cross-reference. Placement is by section rather
#: than by first appearance because the first appearance is usually the Introduction, which is
#: not where a result belongs.
FIGURE_HOME = {
    "fig1_native_vs_decoy.png": "results_2_screen",
    "fig2_screen_level_null.png": "results_2_screen",
    "fig3_falsified_every_version.png": "results_2_screen",
    "fig5_complex_structure.png": "results_3_anatomy",
    "fig4_alphafold_vs_boltz.png": "results_3_anatomy",
}

CITE = re.compile(r"\[@([^\]]+)\]")

#: An inline reference to a figure: [FIG: fig1_native_vs_decoy.png] renders as "Figure 3" in
#: English and "그림 3" in Korean. The number is never written in the source. Five figures were
#: printed with numbers that no sentence ever used, which is how a display item ends up
#: carrying no information -- and writing "Figure 3" by hand would break the moment FIGURE_HOME
#: moved one, silently, in both editions at once.
FIGREF = re.compile(r"\[FIG:\s*([\w.\-]+)\s*\]")
FIGURE = re.compile(r"^\[FIGURE:\s*([\w.\-]+)\s*(?:—|--|-)\s*(.+?)\]\s*$")

#: A citation is replaced by this before inline formatting is parsed, so that the square
#: brackets of a rendered citation are never mistaken for markdown and the numbers are never
#: mistaken for text to be emphasised.
_CITE_TOKEN = re.compile(r"\{\{CITE:([\d,]+)\}\}")


@dataclass
class Paper:
    blocks: list[dict] = field(default_factory=list)
    cited: list[str] = field(default_factory=list)        # keys, in citation order
    refs: dict[str, dict] = field(default_factory=dict)   # key -> reference record
    figures: list[tuple[str, str]] = field(default_factory=list)
    fig_numbers: dict[str, int] = field(default_factory=dict)
    fig_label: str = "Figure {n}"

    def numbered_references(self) -> list[dict]:
        return [dict(self.refs[k], n=i + 1) for i, k in enumerate(self.cited)]


def load_library(path: str | Path) -> dict[str, dict]:
    lib = json.loads(Path(path).read_text())
    out = {}
    for r in lib["references"]:
        out[r["key"]] = dict(r, kind="journal")
    for r in lib.get("non_pubmed", []):
        out[r["key"]] = {
            "key": r["key"], "pmid": "", "doi": r.get("doi", ""),
            "authors": r.get("first_author", ""), "year": str(r.get("year", "")),
            "title": r.get("title", ""), "journal": r.get("journal", ""),
            "citation": "", "is_review": False,
            "used_for": r.get("claim_it_supports", ""),
            "verified": r.get("verified_note",
                              "Consensus/Semantic Scholar; not PubMed-indexed"),
            "kind": "preprint",
        }
    return out


def _figure_numbers(d: Path, suffix: str) -> dict[str, int]:
    """Assign each figure its number by walking ORDER, before any prose is parsed."""
    seen: list[str] = []
    for sec_id, _, _ in ORDER:
        path = d / f"sec_{sec_id}{suffix}.md"
        if not path.exists():
            continue
        for line in path.read_text().split("\n"):
            m = FIGURE.match(line.strip())
            if not m:
                continue
            name = m.group(1)
            home = FIGURE_HOME.get(name)
            if home and home != sec_id:
                continue
            if name not in seen:
                seen.append(name)
    return {name: i + 1 for i, name in enumerate(seen)}


def _inline(text: str, paper: Paper) -> list[dict]:
    """Split a line into styled runs, resolving citations to numbers as they are met."""

    def cite_sub(m):
        nums = []
        for raw in m.group(1).split(";"):
            key = raw.strip().lstrip("@").strip()
            if key not in paper.refs:
                raise KeyError(
                    f"[@{key}] is not in the verified reference library -- refusing to render "
                    f"a citation that was never checked")
            if key not in paper.cited:
                paper.cited.append(key)
            nums.append(str(paper.cited.index(key) + 1))
        return "{{CITE:" + ",".join(nums) + "}}"

    def fig_sub(m):
        name = m.group(1)
        if name not in paper.fig_numbers:
            raise KeyError(
                f"[FIG: {name}] refers to a figure this paper does not print -- refusing to "
                f"render a cross-reference that points at nothing")
        return paper.fig_label.format(n=paper.fig_numbers[name])

    text = FIGREF.sub(fig_sub, text)
    text = CITE.sub(cite_sub, text)

    runs: list[dict] = []
    pat = re.compile(r"(\{\{CITE:[\d,]+\}\}|\*\*.+?\*\*|`[^`]+`|(?<!\*)\*(?!\*).+?(?<!\*)\*(?!\*))")
    for part in pat.split(text):
        if not part:
            continue
        m = _CITE_TOKEN.fullmatch(part)
        if m:
            runs.append({"t": "[" + m.group(1) + "]", "cite": True})
        elif part.startswith("**") and part.endswith("**"):
            runs.append({"t": part[2:-2], "bold": True})
        elif part.startswith("`") and part.endswith("`"):
            runs.append({"t": part[1:-1], "mono": True})
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            runs.append({"t": part[1:-1], "italic": True})
        else:
            runs.append({"t": part})
    return [r for r in runs if r["t"]]


def _flush(buf: list[str], paper: Paper) -> None:
    if buf:
        text = " ".join(x.strip() for x in buf).strip()
        if text:
            paper.blocks.append({"t": "p", "runs": _inline(text, paper)})
        buf.clear()


def _parse_section(md: str, paper: Paper, sec_id: str = "") -> None:
    buf: list[str] = []
    rows: list[list[str]] = []

    def flush_table():
        nonlocal rows
        if rows:
            head = rows[0]
            body = [r for r in rows[1:]
                    if not all(set(c.strip()) <= set("-: ") for c in r)]
            paper.blocks.append({
                "t": "table",
                "head": [_inline(c, paper) for c in head],
                "rows": [[_inline(c, paper) for c in r] for r in body],
            })
            rows = []

    pending = md.split("\n")
    while pending:
        line = pending.pop(0).rstrip()

        if line.startswith("|"):
            _flush(buf, paper)
            rows.append([c.strip() for c in line.strip("|").split("|")])
            continue
        flush_table()

        # A figure marker is one logical line, but an author writing 90-column markdown wraps
        # it, and a wrapped marker matched nothing and printed as literal source text in the
        # middle of the Discussion -- in both editions, because both authors wrapped it. Join
        # the continuation lines before matching, and refuse to render one that never closes.
        stripped = line.strip()
        if stripped.startswith("[FIGURE:") and not stripped.endswith("]"):
            joined = [stripped]
            while pending and not joined[-1].endswith("]"):
                joined.append(pending.pop(0).strip())
            stripped = " ".join(joined)
            if not stripped.endswith("]"):
                raise ValueError(
                    f"a [FIGURE: ...] marker in {sec_id or 'a section'} is never closed with "
                    f"']' -- it would print as literal markup: {stripped[:90]}")

        m = FIGURE.match(stripped)
        if m:
            _flush(buf, paper)
            name = m.group(1)
            home = FIGURE_HOME.get(name)
            if home and sec_id and home != sec_id:
                continue            # discussed here, printed where it belongs
            if any(name == n for n, _ in paper.figures):
                continue            # already placed
            paper.figures.append((name, m.group(2)))
            paper.blocks.append({"t": "figure", "name": name,
                                 "caption": _inline(m.group(2), paper),
                                 "n": len(paper.figures)})
            continue

        if line.startswith("#"):
            _flush(buf, paper)
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("# ").strip()
            # Three authors opened with a heading that repeats the part they were writing --
            # "## Introduction" under Introduction. Printing both gives the same word twice
            # in two sizes. Drop the echo; keep a heading that says something new.
            prev = paper.blocks[-1] if paper.blocks else None
            if prev and prev["t"] == "part" and text.lower() == prev["title"].lower():
                continue
            paper.blocks.append({"t": "h", "level": min(level, 3),
                                 "runs": _inline(text, paper)})
            continue

        if re.match(r"^\s*[-*]\s+\S", line):
            _flush(buf, paper)
            paper.blocks.append({"t": "li",
                                 "runs": _inline(re.sub(r"^\s*[-*]\s+", "", line), paper)})
            continue

        if not line.strip():
            _flush(buf, paper)
            continue
        buf.append(line)

    _flush(buf, paper)
    flush_table()


#: What each top-level part is called, per edition. Only the labels are translated; the
#: structure, the citation numbers and the figure numbers are the same object in both.
#: How a figure is named in running prose. The caption label lives in the renderer; this is
#: the in-text form, and the two must agree, which is why both are per-edition constants.
FIG_LABEL = {"en": "Figure {n}", "ko": "그림 {n}"}

PART_TITLES = {
    "en": {"Introduction": "Introduction", "Methods": "Methods", "Results": "Results",
           "Discussion": "Discussion", "Conclusions": "Conclusions"},
    "ko": {"Introduction": "서론", "Methods": "재료 및 방법", "Results": "결과",
           "Discussion": "고찰", "Conclusions": "결론"},
}


def parse(section_dir: str | Path, library: str | Path, *, lang: str = "en") -> Paper:
    """Read every drafted section in ORDER and return one block list for the whole paper.

    `lang="ko"` reads sec_<id>.ko.md instead of sec_<id>.md. Both editions walk the same
    ORDER and the same reference library, so a citation carries the same number in both and
    a figure carries the same number in both -- which is the only way a reader can hold the
    two side by side.
    """
    d = Path(section_dir)
    suffix = "" if lang == "en" else f".{lang}"
    paper = Paper(refs=load_library(library))
    paper.fig_numbers = _figure_numbers(d, suffix)
    paper.fig_label = FIG_LABEL[lang]
    for sec_id, opens, part_title in ORDER:
        path = d / f"sec_{sec_id}{suffix}.md"
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing; the paper cannot be assembled")
        if opens:
            paper.blocks.append({"t": "part",
                                 "title": PART_TITLES[lang][part_title]})
        _parse_section(path.read_text(), paper, sec_id)
    return paper


def plain(runs: list[dict]) -> str:
    return "".join(r["t"] for r in runs)


def render_reference(r: dict) -> str:
    """One bibliography entry. Never translated: a citation has to be findable."""
    bits = [f"{r['authors']} ({r['year']}). {r['title']}."]
    if r.get("journal"):
        bits.append(r["journal"] + (f" {r['citation']}." if r.get("citation") else "."))
    if r.get("pmid"):
        bits.append(f"PMID {r['pmid']}.")
    if r.get("doi"):
        bits.append(f"doi:{r['doi']}")
    return " ".join(bits)
