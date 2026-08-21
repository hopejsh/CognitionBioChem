#!/usr/bin/env python3
"""Guard: every number the paper states about THIS study must exist in an artefact.

    ./.venv/bin/python platform/check_paper.py [--verbose]

The manuscript was drafted by agents from a fact sheet. A fact sheet is a summary, and a
summary is a place where a number can be paraphrased into something that is nearly right.
This does not read the fact sheet. It walks data/ directly, collects every value the
repository actually holds -- metrics, per-candidate scores, chain lengths, counts, run and
plan totals -- and then checks the manuscript against that set.

Two kinds of numeral are exempt, and the exemption is narrow:

  * a numeral in a sentence that carries a citation marker, which is someone else's number
    and is the reference list's problem, not this file's;
  * a numeral that is a year, a section or figure number, a small count under twenty, or a
    p-value threshold -- the vocabulary of scientific prose rather than a measurement.

Everything else must match an artefact value to the digit. The point is not to prove the
paper correct; it is to make an invented measurement impossible to ship quietly.
"""

from __future__ import annotations

import json
import re
import sys

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "paper"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def J(p: str):
    return json.loads((REPO / p).read_text())


def A(p: str):
    d = J(p)
    return d.get("analysis") or d


def _walk(o, out: set[str]) -> None:
    """Every scalar number anywhere in an artefact, in several renderings."""
    if isinstance(o, dict):
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)
    elif isinstance(o, bool):
        return
    elif isinstance(o, (int, float)):
        out.add(f"{o}")
        if isinstance(o, float):
            for nd in range(0, 6):
                out.add(f"{round(o, nd)}")
                out.add(f"{o:.{nd}f}")
            out.add(f"{abs(o):.4f}")
            if 0 < abs(o) <= 1:
                for nd in (0, 1, 2):
                    out.add(f"{o * 100:.{nd}f}")
    elif isinstance(o, str) and re.fullmatch(r"-?\d+(\.\d+)?", o.strip()):
        out.add(o.strip())


def artefact_numbers() -> set[str]:
    known: set[str] = set()
    for rel in ("data/study_msa_specificity.json", "data/study_candidate_screen.json",
                "data/study_inference_variance_analysis.json",
                "data/study_peptide_interface.json", "data/study_pose_accuracy.json",
                "data/study_ache_affinity.json", "data/study_affinity_corrected.json",
                "data/study_prodigy.json", "data/slate.json", "data/structures.json",
                "data/alphafold_db_comparison.json"):
        _walk(J(rel), known)
    _walk(J("data/dataset.json").get("disclosure", {}), known)
    for t in list(J("data/dataset.json")["target_records"].values())[0]:
        _walk({k: v for k, v in t.items() if k in ("length",)}, known)
    # counts that are properties of the repository rather than of a study
    for n in (len(J("runs/manifest.json")["runs"]),
              len(list((REPO / "prespec").glob("*.json"))),
              len(J("data/structures.json")["entries"]),
              len(list(J("data/dataset.json")["target_records"].values())[0]),
              len(J("data/dataset.json")["candidates"])):
        known.add(str(n))
    # peptide and receptor lengths, which live only inside rows
    for rel in ("data/study_peptide_interface.json", "data/study_msa_specificity.json",
                "data/study_candidate_screen.json"):
        for r in J(rel)["rows"]:
            for k in ("peptide_len", "receptor_len"):
                if r.get(k):
                    known.add(str(r[k]))
            if r.get("peptide_used"):
                known.add(str(len(r["peptide_used"])))
    for e in J("data/structures.json")["entries"]:
        for c in e.get("chains", []):
            for k in ("length", "mean_plddt"):
                if c.get(k) is not None:
                    _walk(c[k], known)
    return known


# `\w` matches Hangul, so a Korean counter suffix ("8257명") hides the numeral from a naive
# pattern and the Korean edition looks as though it dropped two hundred numbers. Bound the
# match on ASCII letters and the decimal point only.
#
# The negative lookbehind also skips a digit that is part of a hyphenated identifier --
# SHA-256, Boltz-2, GluN2A, AlphaFold-2 -- because those are names, not measurements. Counting
# the 256 in SHA-256 as a quantity made the guard demand it appear in the Korean edition, and
# would have made it demand provenance for it from data/.
NUM = re.compile(r"(?<![A-Za-z0-9.])(?<!-)(?<![A-Za-z]-)(\d+(?:\.\d+)?)(?![A-Za-z0-9.])")
CITED_LINE = re.compile(r"\[@[^\]]+\]")
FIG_LINE = re.compile(r"^\s*\[FIGURE:")


def is_prose_numeral(tok: str) -> bool:
    if re.fullmatch(r"(19|20)\d\d", tok):            # a year
        return True
    if re.fullmatch(r"\d+\.\d+", tok) and tok.count(".") == 1:
        a, b = tok.split(".")
        if len(a) <= 1 and len(b) <= 1:              # a section number like 2.4
            return True
    v = float(tok)
    if v.is_integer() and 0 <= v <= 20:              # small counts and ordinals
        return True
    return tok in {"0.05", "0.01", "0.001", "95", "0.5", "100"}


def derivable(tok: str, neighbours: list[str], known: set[str]) -> bool:
    """Is `tok` the sum, difference, product or quotient of two numbers beside it?

    The manuscript states derived quantities -- a margin, a ratio of a margin to a standard
    deviation, a gain between two medians -- and declares them as arithmetic. Taking the word
    "arithmetic" as sufficient would be trusting the sentence rather than checking it, so the
    arithmetic is actually performed here against the other numerals in the same paragraph,
    at least one of which must itself be an artefact value.
    """
    target = float(tok)
    dp = len(tok.split(".")[1]) if "." in tok else 0
    vals = []
    for n in neighbours:
        if n == tok:
            continue
        try:
            vals.append((float(n), n in known))
        except ValueError:
            pass
    for i, (a, a_known) in enumerate(vals):
        for b, b_known in vals[i + 1:]:
            if not (a_known or b_known):
                continue
            for got in (a - b, b - a, a + b, a * b,
                        (a / b if b else None), (b / a if a else None)):
                if got is None:
                    continue
                if abs(round(got, dp) - target) < 10 ** -dp / 2:
                    return True
                # "a factor above 160" and the like: a floor on a ratio
                if dp == 0 and 0 < target <= got < target * 1.1:
                    return True
    return False


def _paper_numerals(paper) -> "collections.Counter":
    import collections as _c
    from cbc.paper import plain as _plain
    c: _c.Counter = _c.Counter()
    for b in paper.blocks:
        for key in ("runs", "caption"):
            for r in b.get(key, []) or []:
                if not r.get("cite"):
                    c.update(NUM.findall(r["t"]))
        for cell in b.get("head", []) or []:
            c.update(NUM.findall(_plain(cell)))
        for row in b.get("rows", []) or []:
            for cell in row:
                c.update(NUM.findall(_plain(cell)))
    return c


def check_editions() -> None:
    """The Korean edition must be the same paper, not a paper about the same work.

    Both editions render from one reference library and one figure map, so a citation carries
    the same number in each and a figure carries the same number in each. What a translator
    can still do is drop a value or a whole clause, and a reader holding the two side by side
    would find the paper disagreeing with itself.
    """
    print("\n[editions] the Korean edition matches the English one")
    sys.path.insert(0, str(REPO / "platform"))
    from cbc.paper import parse as _parse
    lib = SRC / "REFERENCES_PAPER.json"
    missing_ko = [s for s in SRC.glob("sec_*.md")
                  if ".ko." not in s.name and not (SRC / s.name.replace(".md", ".ko.md")).exists()]
    if not check("every section has a Korean counterpart", not missing_ko,
                 ", ".join(m.name for m in missing_ko) or "14 of 14"):
        return
    en = _parse(SRC, lib, lang="en")
    ko = _parse(SRC, lib, lang="ko")
    check("both editions cite the same references in the same order",
          en.cited == ko.cited, f"{len(en.cited)} vs {len(ko.cited)}")
    check("both editions carry the same figures in the same order",
          [n for n, _ in en.figures] == [n for n, _ in ko.figures],
          f"{len(en.figures)} vs {len(ko.figures)}")
    missing = _paper_numerals(en) - _paper_numerals(ko)
    check("every number in the English edition appears in the Korean one", not missing,
          f"missing: {dict(list(missing.items())[:6])}")


def main() -> int:
    print("=" * 76)
    print("CognitionBioChem manuscript — numeric provenance")
    print("=" * 76)
    verbose = "--verbose" in sys.argv

    files = sorted(SRC.glob("sec_*.md"))
    files = [f for f in files if not re.search(r"\.\w\w\.md$", f.name)]
    if not check("the drafted sections are present", bool(files), f"{len(files)} files"):
        print("\n0 passed, 1 failed")
        return 1

    known = artefact_numbers()
    print(f"\n[artefacts] {len(known)} distinct numeric renderings collected from data/\n")

    # Paragraph, not line: markdown wraps a sentence across lines, so a citation routinely
    # lands on a different line from the number it supports. Checking per line reported
    # every wrapped literature figure as unsourced.
    unmatched: dict[str, list[tuple[str, str]]] = {}
    total = derived = 0
    for f in files:
        for para in re.split(r"\n\s*\n", f.read_text()):
            body = "\n".join(l for l in para.split("\n")
                             if not FIG_LINE.match(l) and not l.strip().startswith("#"))
            if not body.strip():
                continue
            has_cite = bool(CITED_LINE.search(body))
            toks = NUM.findall(body)
            for tok in toks:
                total += 1
                if has_cite or is_prose_numeral(tok) or tok in known:
                    continue
                if derivable(tok, toks, known):
                    derived += 1
                    continue
                unmatched.setdefault(tok, []).append(
                    (f.name, " ".join(body.split())[:170]))

    check("every uncited numeral traces to an artefact or to arithmetic on one", not unmatched,
          f"{len(unmatched)} unaccounted for; {derived} reproduced by arithmetic, "
          f"of {total} numerals seen")
    for tok, where in sorted(unmatched.items(), key=lambda kv: -len(kv[1])):
        print(f"      {tok}  ({len(where)}x)  first in {where[0][0]}")
        if verbose:
            for fn, line in where[:3]:
                print(f"         {fn}: {line}")

    if any((SRC / f"sec_{n}.ko.md").exists() for n in ("methods", "conclusions")):
        check_editions()

    print("\n" + "=" * 76)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  -", f)
    print("=" * 76)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
