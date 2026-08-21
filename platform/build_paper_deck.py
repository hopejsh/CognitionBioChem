#!/usr/bin/env python3
"""Render the manuscript's conference deck, in English or Korean.

    ./.venv/bin/python platform/build_paper_deck.py         -> CognitionBioChem_Paper_Deck.html
    ./.venv/bin/python platform/build_paper_deck.py --ko    -> ..._Paper_Deck_KO.html

The slide copy is data, not code: it lives in deck_copy.json and deck_copy.ko.json, written
against the manuscript and audited against it. This module turns that data into the same
slide language the workbench deck uses -- the stylesheet, the rails, the theme handling and
the keyboard shell all come from cbc.deck_style, so the two decks cannot drift apart.

Both editions render from the same JSON schema, so a slide that exists in one exists in the
other, carries the same figure and sits in the same position.
"""

from __future__ import annotations

import html as _html
import json
import sys

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "platform"))
from cbc.deck_style import Deck, export_pdf  # noqa: E402
from cbc.provenance import git_sha  # noqa: E402

SRC = REPO / "paper"

LANG = {
    "en": {
        "copy": "deck_copy.json",
        "out": "CognitionBioChem_Paper_Deck.html",
        "hint": "&larr; &rarr; to navigate",
        "section": {"premise": "Premise", "method": "Method", "result": "Result",
                    "limit": "Limits"},
        "eyebrow": {"premise": "the question", "method": "how it was asked",
                    "result": "what the data says", "limit": "what this does not show"},
    },
    "ko": {
        "copy": "deck_copy.ko.json",
        "out": "CognitionBioChem_Paper_Deck_KO.html",
        "hint": "&larr; &rarr; 로 이동",
        "section": {"premise": "전제", "method": "방법", "result": "결과", "limit": "한계"},
        "eyebrow": {"premise": "무엇을 물었는가", "method": "어떻게 물었는가",
                    "result": "데이터가 말하는 것", "limit": "이 작업이 보여주지 않는 것"},
    },
}


def esc(s) -> str:
    """Escape, but leave the few entities the copy is allowed to carry."""
    out = _html.escape(str(s), quote=False)
    for ent in ("&mdash;", "&ndash;", "&middot;", "&nbsp;", "&ge;", "&le;", "&rarr;",
                "&larr;", "&times;", "&plusmn;", "&rho;", "&sigma;", "&Delta;", "&alpha;",
                "&beta;", "&mu;", "&deg;"):
        out = out.replace(_html.escape(ent, quote=False), ent)
    return out


def _stats(items) -> str:
    cells = "".join(
        f'<div class="stat"><b{" class=\"strike\"" if it.get("struck") else ""}>'
        f'{esc(it["value"])}</b><span>{esc(it["label"])}</span></div>'
        for it in items)
    return f'<div class="stats">{cells}</div>'


def _paras(paras) -> str:
    return "".join(f"<p>{esc(p)}</p>" for p in paras or [])


def _pull(text) -> str:
    return f'<p class="pull">{esc(text)}</p>' if text else ""


def _led(rows) -> str:
    items = "".join(f'<li><span class="k">{esc(r["key"])}</span>'
                    f'<span>{esc(r["text"])}</span></li>' for r in rows)
    return f'<ul class="led">{items}</ul>'


def _table(head, rows) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def build(lang: str = "en") -> int:
    cfg = LANG[lang]
    copy_path = SRC / cfg["copy"]
    if not copy_path.exists():
        raise FileNotFoundError(f"{copy_path} is missing; the slide copy has not been written")
    copy = json.loads(copy_path.read_text())
    out = REPO / "docs" / cfg["out"]

    deck = Deck(copy["title"], copy["description"], section=cfg["section"],
                eyebrow=cfg["eyebrow"], hint=cfg["hint"], lang=lang)

    for i, s in enumerate(copy["slides"], 1):
        kind = s.get("kind", "premise")
        t = s.get("type", "prose")

        if t == "title":
            meta = "".join(f"<div>{esc(m)}</div>" for m in s.get("meta", []))
            deck.raw(
                f'<section class="slide title" data-kind="{kind}" aria-label="Slide {i}">'
                f'<div class="eyebrow"><span class="kind">{esc(s.get("eyebrow_kind", cfg["section"][kind]))}'
                f'</span><span>{esc(s.get("sub", ""))}</span></div>'
                f'<div><h1>{esc(s["headline"])}</h1>'
                + (f'<p class="thesis">{esc(s["thesis"])}</p>' if s.get("thesis") else "")
                + f'</div><div class="meta">{meta}</div>'
                f'<footer class="foot"><span>{esc(s.get("foot", ""))}</span>'
                f'<span class="no">{i:02d}</span></footer></section>')
            continue

        if t == "figure":
            deck.figslide(kind, esc(s["headline"]), esc(s.get("sub", "")),
                          s["fig"], esc(s.get("caption", "")),
                          stamp=esc(s.get("stamp", "")), foot=esc(s.get("foot", "")))
            continue

        if t == "stats":
            body = _stats(s.get("stats", [])) + (
                f'<p class="pull" style="margin-top:clamp(16px,2.2cqw,32px)">'
                f'{esc(s["pull"])}</p>' if s.get("pull") else "")
        elif t == "led":
            body = _led(s.get("led", []))
        elif t == "table":
            body = _table(s.get("head", []), s.get("rows", [])) + _paras(s.get("paras"))
        elif t == "split":
            left = _paras(s.get("paras")) + _pull(s.get("pull"))
            right = _stats(s.get("stats", [])) if s.get("stats") else _paras(s.get("right"))
            body = f'<div class="cols c-7-5"><div>{left}</div><div>{right}</div></div>'
        else:
            body = _paras(s.get("paras")) + _pull(s.get("pull"))

        deck.slide(kind, esc(s["headline"]), body, sub=esc(s.get("sub", "")),
                   stamp=esc(s.get("stamp", "")), foot=esc(s.get("foot", "")))

    out.write_text(deck.html())
    print(f"wrote {out.relative_to(REPO)}")
    print(f"  slides: {len(deck.slides)}   size: {out.stat().st_size / 1024:.0f} KB")
    print(f"  built from {git_sha()}")

    pdf = export_pdf(out)
    if pdf:
        print(f"wrote {pdf.relative_to(REPO)}  ({pdf.stat().st_size / 1024:.0f} KB)")
    else:
        print("  (no Chrome found; skipped the PDF export)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build("ko" if "--ko" in sys.argv else "en"))
