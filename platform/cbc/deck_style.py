"""The shared look and shell of every slide deck this repository generates.

Two decks exist -- the workbench deck and the paper deck -- and a third will exist the moment
someone wants a lecture version. Copying the stylesheet into each would guarantee that a fix
to one leaves the others behind, so the type scale, the palette, the rail that types a slide,
the theme handling and the keyboard shell live here, once.

What a deck supplies for itself is only its slides.
"""

from __future__ import annotations

import base64
import mimetypes

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def img(name: str, fig_dir: Path | None = None) -> str:
    """Inline a figure as a data URI, refusing to emit a broken <img>.

    The published artifact is served under a CSP that admits no external host, so a deck is
    one self-contained file or it is a page of missing images.
    """
    d = fig_dir or (REPO / "docs" / "figures")
    path = d / name
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; the deck will not be built without it")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


CSS = """
:root{
  /* Light is the base state, defined on bare :root so the un-stamped document -- which is
     what most viewers see -- resolves a complete palette without any media query. */
  --ground:#F3F4F0; --panel:#FBFBF8; --ink:#171A19; --muted:#6C726D; --rule:#D8DBD4;
  --accent:#2F6F62; --accent-soft:#E2EBE7;
  --amber:#B0761C;            /* reserved for observed data marks, never decoration */
  --slate:#5A6B7C;            /* the second verdict hue */
  --shadow:0 1px 2px rgba(23,26,25,.05), 0 12px 34px rgba(23,26,25,.07);
  --rail-premise:#8A8F88; --rail-method:#2F6F62; --rail-result:#B0761C; --rail-limit:#5A6B7C;
}
:root:not([data-theme="light"]){ color-scheme:light dark; }
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#131615; --panel:#1B201E; --ink:#E7EAE5; --muted:#98A09A; --rule:#2C3330;
    --accent:#63A896; --accent-soft:#1E2A27;
    --amber:#D8A24E; --slate:#8FA3B5;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 14px 40px rgba(0,0,0,.45);
    --rail-premise:#767D77; --rail-method:#63A896; --rail-result:#D8A24E; --rail-limit:#8FA3B5;
  }
}
:root[data-theme="dark"]{
  --ground:#131615; --panel:#1B201E; --ink:#E7EAE5; --muted:#98A09A; --rule:#2C3330;
  --accent:#63A896; --accent-soft:#1E2A27;
  --amber:#D8A24E; --slate:#8FA3B5;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 14px 40px rgba(0,0,0,.45);
  --rail-premise:#767D77; --rail-method:#63A896; --rail-result:#D8A24E; --rail-limit:#8FA3B5;
}

*{box-sizing:border-box;}
body{
  background:var(--ground); color:var(--ink);
  font-family:"Newsreader",Iowan Old Style,Georgia,serif;
  font-optical-sizing:auto; font-size:17px; line-height:1.55;
  margin:0; padding:0 0 8vh;
  -webkit-font-smoothing:antialiased;
}
.deck{ display:flex; flex-direction:column; gap:26px; padding:26px 22px 0; align-items:center; }

/* ---- the slide frame ---------------------------------------------------------------- */
.slide{
  position:relative; width:min(1120px,100%); aspect-ratio:16/9;
  background:var(--panel); border:1px solid var(--rule); border-radius:3px;
  box-shadow:var(--shadow);
  display:grid; grid-template-rows:auto 1fr auto;
  padding:clamp(20px,3.1vw,42px) clamp(24px,3.6vw,52px) clamp(16px,2.2vw,30px);
  padding-left:clamp(34px,4.4vw,64px);
  overflow:hidden; container-type:inline-size;
}
.slide::before{                     /* the rail types the slide; it is not decoration */
  content:""; position:absolute; inset:0 auto 0 0; width:5px; background:var(--rail);
}
.slide[data-kind="premise"]{ --rail:var(--rail-premise); }
.slide[data-kind="method"] { --rail:var(--rail-method);  }
.slide[data-kind="result"] { --rail:var(--rail-result);  }
.slide[data-kind="limit"]  { --rail:var(--rail-limit);   }

/* ---- head, foot ---------------------------------------------------------------------- */
.eyebrow{
  display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
  font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,monospace;
  font-size:clamp(9px,.83cqw,11.5px); letter-spacing:.13em; text-transform:uppercase;
  color:var(--muted); margin-bottom:clamp(10px,1.3vw,18px);
}
.eyebrow .kind{ color:var(--rail); font-weight:600; }
.eyebrow .stamp{ margin-left:auto; letter-spacing:.06em; text-transform:none; }
h1,h2{ font-family:"IBM Plex Sans Condensed",ui-sans-serif,system-ui,sans-serif;
       font-weight:700; letter-spacing:-.005em; text-wrap:balance; margin:0; }
h2{ font-size:clamp(24px,3.05cqw,40px); line-height:1.06; }
.sub{ font-size:clamp(13px,1.28cqw,19px); color:var(--muted); margin:.5em 0 0; max-width:62ch; }
.body{ align-self:center; min-height:0; }
.body p{ margin:0 0 .74em; max-width:64ch; font-size:clamp(12px,1.17cqw,17.5px); }
.body p:last-child{ margin-bottom:0; }
.foot{
  display:flex; align-items:baseline; gap:16px; border-top:1px solid var(--rule);
  padding-top:9px; margin-top:clamp(10px,1.4vw,18px);
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:clamp(8.5px,.79cqw,11px); color:var(--muted); letter-spacing:.045em;
}
.foot .no{ margin-left:auto; font-variant-numeric:tabular-nums; }

/* ---- content devices ----------------------------------------------------------------- */
.cols{ display:grid; gap:clamp(18px,2.6cqw,40px); align-items:start; }
.c-7-5{ grid-template-columns:minmax(0,7fr) minmax(0,5fr); }
.c-1-1{ grid-template-columns:minmax(0,1fr) minmax(0,1fr); }
.figwrap{ display:flex; flex-direction:column; gap:8px; min-height:0; align-items:center;
          justify-content:center; }
.figwrap img{ max-width:100%; max-height:100%; min-height:0; object-fit:contain;
              border:1px solid var(--rule); border-radius:2px; background:#fff; }
.slide[data-fig="bleed"]{ grid-template-rows:auto minmax(0,1fr) auto; }
.slide[data-fig="bleed"] .body{ align-self:stretch; display:grid; min-height:0; }
.slide[data-fig="bleed"] .figwrap{ display:grid; grid-template-rows:minmax(0,1fr) auto;
          height:100%; justify-items:stretch; }
.slide[data-fig="bleed"] .figwrap img{ justify-self:center; }
.slide[data-fig="bleed"] .figwrap img{ height:100%; }
figcaption{ font-family:"IBM Plex Mono",ui-monospace,monospace;
            font-size:clamp(8.5px,.78cqw,11px); color:var(--muted); line-height:1.45;
            max-width:88ch; align-self:flex-start; text-align:left; }

.stats{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
        gap:clamp(10px,1.5cqw,22px); }
.c-7-5 > .stats:last-child{ grid-template-columns:repeat(2,minmax(0,1fr)); }
.stat{ border-top:2px solid var(--rail); padding-top:9px; }
.stat b{ display:block; font-family:"IBM Plex Sans Condensed",sans-serif; font-weight:700;
         font-size:clamp(21px,2.7cqw,38px); line-height:1; letter-spacing:-.01em;
         font-variant-numeric:tabular-nums; }
.stat > span{ display:block; margin-top:6px; font-family:"IBM Plex Mono",monospace;
            font-size:clamp(8.5px,.76cqw,10.5px); letter-spacing:.07em;
            text-transform:uppercase; color:var(--muted); line-height:1.4; }
.sym{ text-transform:none; }   /* Greek must not be case-mapped: uppercase rho reads as P */

.led{ list-style:none; margin:0; padding:0; display:grid;
      grid-template-columns:auto minmax(0,1fr); gap:clamp(8px,1.1cqw,15px) clamp(12px,1.3cqw,20px);
      align-items:baseline; font-size:clamp(12px,1.13cqw,17px); }
.led li{ display:contents; }
.led .k{ font-family:"IBM Plex Mono",monospace; font-size:clamp(8.5px,.76cqw,10.5px);
         letter-spacing:.09em; text-transform:uppercase; color:var(--accent);
         white-space:nowrap; }
.led[data-marks="neutral"] .k{ color:var(--muted); }

.chip{ font-family:"IBM Plex Mono",monospace; font-size:.78em; letter-spacing:.08em;
       text-transform:uppercase; padding:.16em .5em; border-radius:2px;
       border:1px solid currentColor; white-space:nowrap; }
.chip.c{ color:var(--accent); }
.chip.f{ color:var(--slate); }
.chip.n{ color:var(--muted); }

table{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums;
       font-size:clamp(10px,.98cqw,14px); }
th,td{ text-align:left; padding:.38em .55em; border-bottom:1px solid var(--rule); }
th{ font-family:"IBM Plex Mono",monospace; font-size:clamp(8px,.72cqw,10px);
    letter-spacing:.09em; text-transform:uppercase; color:var(--muted); font-weight:500; }
td.h{ font-family:"IBM Plex Mono",monospace; color:var(--muted); font-size:.88em; }
.tablewrap{ overflow-x:auto; }

.pull{ font-family:"IBM Plex Sans Condensed",sans-serif; font-weight:600;
       font-size:clamp(15px,1.6cqw,24px); line-height:1.24; letter-spacing:-.004em;
       border-left:3px solid var(--rail); padding-left:clamp(12px,1.4cqw,20px);
       text-wrap:balance; }
.mono{ font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }
.hl{ color:var(--amber); font-weight:600; }
.hl-a{ color:var(--accent); font-weight:600; }
.strike{ text-decoration:line-through; text-decoration-thickness:1px; color:var(--muted); }

/* ---- title slide ---------------------------------------------------------------------- */
.title{ display:grid; grid-template-rows:auto 1fr auto auto; gap:clamp(10px,1.4cqw,22px); }
.title > div:nth-of-type(1){ align-self:center; }
.title h1{ font-size:clamp(34px,5.1cqw,74px); line-height:.98; letter-spacing:-.018em; }
.title .thesis{ font-size:clamp(15px,1.66cqw,25px); max-width:36ch; color:var(--ink); }
.title .meta{ font-family:"IBM Plex Mono",monospace; font-size:clamp(9px,.82cqw,11.5px);
              letter-spacing:.07em; color:var(--muted); line-height:1.9; }
.title .ids{ display:flex; flex-wrap:wrap; gap:8px 18px; }

/* ---- viewer chrome --------------------------------------------------------------------- */
.bar{ position:fixed; left:0; right:0; bottom:0; height:3px; background:var(--rule); z-index:5; }
.bar i{ display:block; height:100%; width:0; background:var(--accent); transition:width .18s ease; }
.hint{ position:fixed; right:14px; bottom:14px; z-index:6;
       font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.08em;
       color:var(--muted); background:var(--panel); border:1px solid var(--rule);
       border-radius:2px; padding:5px 9px; }
:focus-visible{ outline:2px solid var(--accent); outline-offset:3px; }
@media (prefers-reduced-motion:reduce){ *{ scroll-behavior:auto !important;
       transition-duration:.001ms !important; } }

/* The Korean edition swaps the text faces for one with Hangul coverage. Everything else --
   the scale, the palette, the rails, the mono column -- is unchanged, so the two editions of
   a deck sit side by side and differ only in language. */
[data-lang="ko"]{ font-family:"Noto Sans KR","Apple SD Gothic Neo",sans-serif; }
[data-lang="ko"] h1,[data-lang="ko"] h2,[data-lang="ko"] .pull,
[data-lang="ko"] .stat b,[data-lang="ko"] .title .thesis{
  font-family:"Noto Sans KR","Apple SD Gothic Neo",sans-serif; font-weight:700;
  letter-spacing:-.01em; }
[data-lang="ko"] .body p,[data-lang="ko"] .sub,[data-lang="ko"] .led li{
  font-family:"Noto Sans KR","Apple SD Gothic Neo",sans-serif; font-weight:400;
  line-height:1.62; word-break:keep-all; }

@media screen and (max-width:760px){
  .slide{ aspect-ratio:auto; min-height:78vh; }
  .cols{ grid-template-columns:minmax(0,1fr); }
  .hint{ display:none; }
}
@page{ size:1120px 630px; margin:0; }
@media print{
  body{ background:var(--panel); padding:0; }
  .deck{ gap:0; padding:0; }
  .bar,.hint{ display:none; }
  .slide{ box-shadow:none; border:none; border-radius:0;
          width:1120px; height:630px; aspect-ratio:auto;
          page-break-after:always; break-after:page; break-inside:avoid; }
  .slide:last-child{ page-break-after:auto; break-after:auto; }
}
"""



JS = """
(function(){
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var bar = document.querySelector('.bar i');
  function mark(){
    var mid = window.innerHeight / 2, cur = 0;
    slides.forEach(function(s, i){
      var r = s.getBoundingClientRect();
      if (r.top <= mid && r.bottom >= 0) cur = i;
    });
    bar.style.width = ((cur + 1) / slides.length * 100).toFixed(2) + '%';
  }
  function go(i){
    i = Math.max(0, Math.min(slides.length - 1, i));
    slides[i].scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  function current(){
    var mid = window.innerHeight / 2, cur = 0;
    slides.forEach(function(s, i){
      var r = s.getBoundingClientRect();
      if (r.top <= mid && r.bottom >= 0) cur = i;
    });
    return cur;
  }
  document.addEventListener('keydown', function(ev){
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var k = ev.key;
    if (k === 'ArrowRight' || k === 'PageDown' || k === ' ') { ev.preventDefault(); go(current() + 1); }
    else if (k === 'ArrowLeft' || k === 'PageUp') { ev.preventDefault(); go(current() - 1); }
    else if (k === 'Home') { ev.preventDefault(); go(0); }
    else if (k === 'End') { ev.preventDefault(); go(slides.length - 1); }
  });
  window.addEventListener('scroll', mark, {passive: true});
  window.addEventListener('resize', mark);
  mark();
})();
"""



#: The type a slide carries, which sets its rail colour and its eyebrow. These are real
#: categories in the argument, not decoration: a viewer can see at a glance whether they are
#: being shown a premise, a method, a result or a limit.
SECTION = {"premise": "Premise", "method": "Method", "result": "Result", "limit": "Limits"}
EYEBROW = {
    "premise": "why this exists",
    "method": "how the question was asked",
    "result": "what the data says",
    "limit": "what this does not show",
}


class Deck:
    """Accumulates slides and renders the finished page."""

    def __init__(self, title: str, description: str, *, section=None, eyebrow=None,
                 hint: str = "&larr; &rarr; to navigate", fig_dir: Path | None = None,
                 lang: str = "en"):
        self.slides: list[str] = []
        self.title = title
        self.description = description
        self.section = section or SECTION
        self.eyebrow = eyebrow or EYEBROW
        self.hint = hint
        self.fig_dir = fig_dir
        self.lang = lang

    # -- raw ---------------------------------------------------------------------------
    def raw(self, html: str) -> None:
        self.slides.append(html)

    def img(self, name: str) -> str:
        return img(name, self.fig_dir)

    # -- the ordinary slide -------------------------------------------------------------
    def slide(self, kind: str, title: str, body: str, *, sub: str = "", stamp: str = "",
              foot: str = "", fig: str = "", cls: str = "") -> None:
        n = len(self.slides) + 1
        head = ""
        if title:
            head = (f'<header><div class="eyebrow"><span class="kind">'
                    f'{self.section[kind]}</span><span>{self.eyebrow[kind]}</span>'
                    + (f'<span class="stamp">{stamp}</span>' if stamp else "")
                    + f'</div><h2>{title}</h2>'
                    + (f'<p class="sub">{sub}</p>' if sub else "") + "</header>")
        self.slides.append(
            f'<section class="slide{(" " + cls) if cls else ""}" data-kind="{kind}"'
            + (f' data-fig="{fig}"' if fig else "")
            + f' aria-label="Slide {n}">{head}<div class="body">{body}</div>'
            f'<footer class="foot"><span>{foot or self.title}</span>'
            f'<span class="no">{n:02d}</span></footer></section>')

    # -- a slide that is one figure ------------------------------------------------------
    def figslide(self, kind: str, title: str, sub: str, name: str, caption: str,
                 stamp: str = "", foot: str = "") -> None:
        self.slide(kind, title,
                   f'<div class="figwrap"><img src="{self.img(name)}" alt="{caption}">'
                   f"<figcaption>{caption}</figcaption></div>",
                   sub=sub, stamp=stamp, foot=foot, fig="bleed")

    # -- the page ------------------------------------------------------------------------
    def html(self) -> str:
        return (
            # Without this the file is correct UTF-8 that a browser guesses is Latin-1, and
            # every middot, em dash and umlaut renders as mojibake. The published artifact
            # supplies its own head and so never showed it; the local PDF export did.
            '<meta charset="utf-8">\n'
            f"<title>{self.title}</title>\n"
            f'<meta name="description" content="{self.description}">\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            'family=IBM+Plex+Mono:wght@400;500;600&'
            'family=IBM+Plex+Sans+Condensed:wght@600;700&'
            'family=Newsreader:ital,opsz,wght@0,6..72,300..600;1,6..72,300..500&'
            'family=Noto+Sans+KR:wght@400;500;700&display=swap">\n'
            f"<style>{CSS}</style>\n"
            f'<main class="deck" data-lang="{self.lang}">\n' + "\n".join(self.slides) + "\n</main>\n"
            '<div class="bar" aria-hidden="true"><i></i></div>\n'
            f'<div class="hint" aria-hidden="true">{self.hint}</div>\n'
            f"<script>{JS}</script>\n"
        )


def export_pdf(out_html: Path) -> Path | None:
    """Print the deck to a 16:9 PDF with the browser that is installed.

    Written by the same command that writes the HTML, so the two cannot drift: a deck exported
    once by hand goes stale the first time a study is re-run.
    """
    import http.server
    import socketserver
    import subprocess
    import threading

    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.exists():
        return None
    pdf = out_html.with_suffix(".pdf")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(out_html.parent), **kw)

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as srv:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        r = subprocess.run(
            [str(chrome), "--headless=new", "--disable-gpu", "--window-size=1440,900",
             "--virtual-time-budget=10000", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf}", f"http://127.0.0.1:{port}/{out_html.name}"],
            capture_output=True, text=True, timeout=180)
        srv.shutdown()
    if not pdf.exists() or pdf.stat().st_size < 100_000:
        raise RuntimeError(f"Chrome produced no usable PDF: {r.stderr[-400:]}")
    return pdf
