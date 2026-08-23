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

Everything else must match an artefact value to the digit.

What that does and does not establish is worth stating plainly, because the check is easy to
over-read. Collecting every value in several renderings gives a set of about 21,000 strings,
and against a set that dense a plausible-looking invention often matches by coincidence: at
one decimal place roughly six of every seven values in the range the paper uses are members.
So this is a membership test -- the number exists somewhere in data/ -- and not a claim that
it is the value being described. It catches a number with no basis at all; it does not catch a
real number put in the wrong sentence.

The case that would actually change the paper's meaning is a transposition, and that is what
check_anchors() below is for: the study's central quantities are bound to the artefact field
they come from and to the words that introduce them, and each must be the number its NEAREST
label names. Swapping the designed and decoy means passes the membership test and fails there.
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
#: The trailing guard rejects a period only when a DIGIT follows it, so that "3" in "3.14"
#: is not read as a number on its own. Rejecting every following period also hid every
#: sentence-final numeral -- 46 of them, including the "divided by 0.14943." that four
#: stated ratios are derived from, which is how two correct ratios came to look invented.
NUM = re.compile(r"(?<![A-Za-z0-9.])(?<!-)(?<![A-Za-z]-)(\d+(?:\.\d+)?)(?![A-Za-z0-9])(?!\.\d)")
CITED_LINE = re.compile(r"\[@[^\]]+\]")
FIG_LINE = re.compile(r"^\s*\[FIGURE:")

#: The citation exemption is per SENTENCE, not per paragraph. Exempting the paragraph let one
#: citation anywhere in it excuse every numeral in it -- 72% of the manuscript's numbers, which
#: is most of a guard that exists to check numbers. A paragraph that opens on the literature
#: and closes on this study's own result is the normal shape of scientific prose, and it was
#: exactly the shape that went unchecked. Sentence-level exemption brings the covered share
#: from 28% to 53%.
#:
#: The lookbehinds are the abbreviations that end in a period without ending a sentence. Get
#: this wrong in the permissive direction and a sentence merges with its neighbour, which only
#: widens the exemption again; get it wrong the other way and a literature number is demanded
#: from data/, which is a visible failure rather than a silent one.
_ABBR = (r"(?<!\bet al)(?<!\bFig)(?<!\bcf)(?<!\bi\.e)(?<!\be\.g)(?<!\bvs)(?<!\bNo)"
         r"(?<!\bapprox)(?<!\bDr)(?<!\bSt)(?<!\bibid)(?<!\bca)")
SENTENCE = re.compile(_ABBR + r"(?<=[.!?])[\"\'\u201d]?\s+(?=[A-Z\uac00-\ud7a3\u201c\"(\[])")


def sentences(body: str) -> list[str]:
    """Split prose into sentences for the purpose of the citation exemption only."""
    return SENTENCE.split(body) or [body]


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


#: The quantities the paper's conclusion rests on, each bound to the artefact field it comes
#: from and to the words that introduce it in each edition.
#:
#: The numeral check above is a membership test: it asks whether a digit string exists anywhere
#: in data/, not whether it is the value being described. Against 21,789 renderings that set is
#: dense, and the demonstration that matters is a transposition -- swapping the designed and
#: decoy means reverses the study's central result and still passes, because both strings are
#: genuine artefact values. Membership cannot see that. Binding a handful of numbers to their
#: own label closes the case that would actually change the paper's meaning.
ANCHORS = [
    ("designed mean ipTM", "data/study_msa_specificity.json",
     ("analysis", "metrics", "mean_native_iptm"), {"en": "designed", "ko": "설계"}),
    ("decoy mean ipTM", "data/study_msa_specificity.json",
     ("analysis", "metrics", "mean_decoy_iptm"), {"en": "decoy", "ko": "디코이"}),
]

#: How far back a label may sit and still be the label of the number that follows it.
ANCHOR_WINDOW = 90


def _dig(obj, path):
    for k in path:
        if not isinstance(obj, dict) or k not in obj:
            return None
        obj = obj[k]
    return obj


def check_anchors() -> None:
    """Each central quantity must be the one its NEAREST label names.

    The numeral check above is a membership test: it asks whether a digit string exists
    somewhere in data/, not whether it is the value being described. Against 21,789 renderings
    that set is dense enough that the case which would actually change the paper's meaning
    passes -- swap the designed and decoy means and the study's central result reverses while
    every digit string remains a genuine artefact value.

    Asking "does the number appear near its label" does not close it either: in the sentence
    that states both means, both labels are inside the window, so a swap keeps passing. What
    has to hold is that the number's own label is the NEAREST one, which is exactly what a
    transposition breaks and what a reader relies on.
    """
    print("\n[anchors] each central number is the one its nearest label names")
    sys.path.insert(0, str(REPO / "platform"))
    from cbc.paper import parse as _parse, plain as _plain
    lib = SRC / "REFERENCES_PAPER.json"
    editions = {"en": _parse(SRC, lib, lang="en"), "ko": _parse(SRC, lib, lang="ko")}
    text = {lang: " ".join(" ".join(_plain(b.get("runs", []) or []) for b in p.blocks).split())
            for lang, p in editions.items()}

    for label, rel, path, cues in ANCHORS:
        raw = _dig(J(rel), path)
        if raw is None:
            check(f"{label}: the artefact still carries it", False, f"{rel} {'.'.join(path)}")
            continue
        rivals = [c for lab, r, pth, c in ANCHORS if lab != label and r == rel]
        # test the string the paper actually prints, not a rendering of our own choosing
        cands = [f"{raw:.{n}f}".rstrip("0").rstrip(".") for n in range(6, 1, -1)] + [f"{raw}"]
        val = next((c for c in cands if c and c in text["en"]), cands[0])

        good = bad = 0
        detail = []
        for lang in ("en", "ko"):
            body, cue = text[lang], cues[lang]
            i = body.find(val)
            while i >= 0:
                window = body[max(0, i - ANCHOR_WINDOW):i].lower()
                mine = window.rfind(cue.lower())
                theirs = max((window.rfind(r[lang].lower()) for r in rivals), default=-1)
                if mine < 0:
                    pass                      # no label in reach; neither right nor wrong
                elif mine > theirs:
                    good += 1
                else:
                    bad += 1
                    if len(detail) < 3:
                        detail.append(f"{lang}: ...{body[max(0, i - 70):i + len(val)]}")
                i = body.find(val, i + 1)

        check(f"{label} ({val}) is never stated under a rival label",
              good >= 2 and bad == 0,
              f"{good} correctly labelled, {bad} mislabelled"
              + ("; " + " | ".join(detail) if detail else ""))


def check_editions() -> None:
    """The Korean edition must be the same paper, not a paper about the same work.

    Both editions render from one reference library and one figure map, so a citation carries
    the same number in each and a figure carries the same number in each. What a translator
    can still do is drop a value or a whole clause, and a reader holding the two side by side
    would find the paper disagreeing with itself.
    """
    print("\n[editions] the Korean edition matches the English one")
    sys.path.insert(0, str(REPO / "platform"))
    from cbc.paper import parse as _parse, plain as _plain
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
    # The list above is the BIBLIOGRAPHY's order -- a key enters it once, on first appearance.
    # Reordering two already-cited keys inside one bracket in one edition leaves it untouched
    # while the two documents print [106,108] and [108,106] at the same sentence. Compare the
    # rendered markers, which is what the check's name has always claimed to compare.
    def markers(paper):
        return [r["t"] for b in paper.blocks for r in (b.get("runs") or []) if r.get("cite")]
    m_en, m_ko = markers(en), markers(ko)
    first = next((f"#{i}: {a} vs {b}" for i, (a, b) in enumerate(zip(m_en, m_ko)) if a != b),
                 f"lengths {len(m_en)} vs {len(m_ko)}")
    check("both editions print the same citation markers at the same points", m_en == m_ko,
          f"{len(m_en)} markers" if m_en == m_ko else first)

    # A numbered figure that no sentence refers to carries no information, and a cross-edition
    # divergence here means one edition points a reader at a different figure.
    def figrefs(paper, label):
        import re as _re
        pat = _re.compile(_re.escape(label).replace(r"\{n\}", r"(\d+)"))
        body = " ".join(_plain(b.get("runs", []) or []) for b in paper.blocks)
        return sorted(set(pat.findall(body)))
    r_en, r_ko = figrefs(en, en.fig_label), figrefs(ko, ko.fig_label)
    want = sorted(str(i + 1) for i in range(len(en.figures)))
    check("every figure is referred to in the prose, identically in both editions",
          r_en == want and r_ko == want,
          f"en {r_en}, ko {r_ko}, printed {want}")

    missing = _paper_numerals(en) - _paper_numerals(ko)
    check("every number in the English edition appears in the Korean one", not missing,
          f"missing: {dict(list(missing.items())[:6])}")


def main() -> int:
    print("=" * 76)
    print("CognitionBioChem manuscript — numeric provenance")
    print("=" * 76)
    verbose = "--verbose" in sys.argv

    # The drafted sections are the author's manuscript and are deliberately not published:
    # paper/ is untracked and ignored, so a clone does not carry them. This guard therefore
    # SKIPS rather than fails when they are absent -- a check that cannot run has not passed,
    # and saying so is the honest report. It still runs in full for whoever holds the prose.
    if not SRC.exists() or not any(SRC.glob("sec_*.md")):
        print("\n  paper/ is not present in this checkout.")
        print("  The manuscript sections are the author's and are not published with the code,")
        print("  so this guard has nothing to read. SKIPPED -- not passed.")
        print("\n0 passed, 0 failed, 1 skipped")
        return 0

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
            toks = NUM.findall(body)
            for sent in sentences(" ".join(body.split())):
                if CITED_LINE.search(sent):
                    total += len(NUM.findall(sent))
                    continue
                for tok in NUM.findall(sent):
                    total += 1
                    if is_prose_numeral(tok) or tok in known:
                        continue
                    # arithmetic may draw on the whole paragraph, not just this sentence
                    if derivable(tok, toks, known):
                        derived += 1
                        continue
                    unmatched.setdefault(tok, []).append((f.name, sent[:170]))

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
        check_anchors()

    print("\n" + "=" * 76)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  -", f)
    print("=" * 76)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
