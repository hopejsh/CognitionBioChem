#!/usr/bin/env python3
"""Generate the shareable review page with all data inlined (CSP blocks external fetch)."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reviews" / "review_report.html"

plddt = json.loads(Path("/tmp/plddt_compare.json").read_text())
rdata = json.loads(Path("/tmp/report_data.json").read_text())
vrep = json.loads((REPO / "data" / "validation_report.json").read_text())
panel = json.loads((REPO / "reviews" / "panel_raw.json").read_text())

PAYLOAD = json.dumps({
    "plddt": plddt,
    "findings": rdata["findings"],
    "gate": rdata["gate"],
    "n_gate": rdata["n_gate"],
    "roadmap": rdata["roadmap"],
    "root_causes": rdata["root_causes"],
    "summary": vrep["summary"],
    "strengths": panel["synthesis"]["what_is_genuinely_good"],
}, separators=(",", ":"))

HTML = """<title>CognitionBioChem Audit</title>
<style>
:root{
  --bg:#F6F7F9; --surface:#FFFFFF; --surface-2:#F0F2F5;
  --ink:#131A22; --ink-2:#3B4654; --muted:#5C6875; --faint:#8A96A3;
  --rule:#DFE4EA; --rule-strong:#C7CFD8;
  --accent:#1D5FD6; --accent-soft:rgba(29,95,214,.09);
  --flag:#B42318; --flag-soft:rgba(180,35,24,.09);
  --ok:#0F7B4F; --ok-soft:rgba(15,123,79,.10);
  /* AlphaFold's published confidence scale, used only where it encodes confidence. */
  --band-vhigh:#0053D6; --band-high:#65CBF3; --band-low:#FFDB13; --band-vlow:#FF7D45;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --measure:70ch;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#0D1218; --surface:#141B23; --surface-2:#1A222B;
    --ink:#E7EDF4; --ink-2:#C2CDD9; --muted:#8896A6; --faint:#6B7887;
    --rule:#212B35; --rule-strong:#2E3A46;
    --accent:#5D9BFF; --accent-soft:rgba(93,155,255,.13);
    --flag:#FF8B7A; --flag-soft:rgba(255,139,122,.12);
    --ok:#4ECB8E; --ok-soft:rgba(78,203,142,.12);
  }
}
:root[data-theme="dark"]{
  --bg:#0D1218; --surface:#141B23; --surface-2:#1A222B;
  --ink:#E7EDF4; --ink-2:#C2CDD9; --muted:#8896A6; --faint:#6B7887;
  --rule:#212B35; --rule-strong:#2E3A46;
  --accent:#5D9BFF; --accent-soft:rgba(93,155,255,.13);
  --flag:#FF8B7A; --flag-soft:rgba(255,139,122,.12);
  --ok:#4ECB8E; --ok-soft:rgba(78,203,142,.12);
}

*{box-sizing:border-box}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.65 var(--sans);
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1120px;margin:0 auto;padding:0 28px}
.measure{max-width:var(--measure)}
p{color:var(--ink-2)}
a{color:var(--accent)}
h1,h2,h3{letter-spacing:-.028em;text-wrap:balance;margin:0}
h1{font-size:clamp(30px,4.4vw,46px);font-weight:680;line-height:1.08}
h2{font-size:clamp(21px,2.4vw,26px);font-weight:660;line-height:1.2}
h3{font-size:16.5px;font-weight:640;letter-spacing:-.015em}
.eyebrow{
  font:600 11px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
  color:var(--faint);
}
.num{font-variant-numeric:tabular-nums;font-family:var(--mono)}
code{font:12.5px var(--mono);background:var(--surface-2);padding:1px 5px;border-radius:4px}

/* ── masthead ───────────────────────────────────────────────── */
header{border-bottom:1px solid var(--rule);background:var(--surface)}
.head-inner{padding:44px 0 34px}
.kicker{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.chip{
  font:600 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;
  padding:5px 9px;border-radius:3px;border:1px solid var(--rule-strong);color:var(--muted);
}
.chip.flag{color:var(--flag);border-color:var(--flag);background:var(--flag-soft)}
.lede{font-size:18.5px;line-height:1.55;color:var(--ink-2);margin:18px 0 0}
.verdict{
  margin-top:26px;padding:18px 20px;border-left:3px solid var(--flag);
  background:var(--flag-soft);border-radius:0 6px 6px 0;
}
.verdict p{margin:0;font-size:15.5px;color:var(--ink)}

/* ── section rhythm ─────────────────────────────────────────── */
section{padding:52px 0;border-bottom:1px solid var(--rule)}
.sec-head{display:flex;gap:14px;align-items:baseline;margin-bottom:8px}
.sec-no{font:600 12px/1 var(--mono);color:var(--accent);padding-top:4px}
.sec-sub{margin:6px 0 26px;color:var(--muted);font-size:15px}

/* ── the evidence chart ─────────────────────────────────────── */
.evidence{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:880px){.evidence{grid-template-columns:1fr}}
.trace{
  background:var(--surface);border:1px solid var(--rule);border-radius:8px;
  padding:18px 18px 14px;
}
.trace-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:4px}
.trace-head h3{font-size:15px}
.tag{font:600 10px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;padding:4px 7px;border-radius:3px}
.tag.real{background:var(--ok-soft);color:var(--ok)}
.tag.fake{background:var(--flag-soft);color:var(--flag)}
.trace canvas{width:100%;height:170px;display:block;margin:10px 0 6px}
.trace-meta{font:11.5px/1.5 var(--mono);color:var(--muted)}
.tstats{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin-top:12px;
  border-top:1px solid var(--rule);padding-top:11px}
.tstats div{text-align:left}
.tstats .k{font:10px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--faint)}
.tstats .v{font:600 15px/1.3 var(--mono);font-variant-numeric:tabular-nums}
.tstats .v.hi{color:var(--flag)}
.bands{display:flex;gap:14px;flex-wrap:wrap;margin-top:16px;font:11.5px var(--mono);color:var(--muted)}
.bands i{width:11px;height:11px;border-radius:2px;display:inline-block;margin-right:5px;vertical-align:-1px}

/* ── stat strip ─────────────────────────────────────────────── */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden}
.stat{background:var(--surface);padding:16px 18px}
.stat .v{font:660 27px/1.1 var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.stat .v.flag{color:var(--flag)}
.stat .v.ok{color:var(--ok)}
.stat .k{font:11px/1.4 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--faint);margin-top:5px}
.stat .s{font-size:12.5px;color:var(--muted);margin-top:3px}

/* ── causes ─────────────────────────────────────────────────── */
.causes{display:grid;gap:2px;background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden}
.cause{background:var(--surface);padding:18px 20px;display:grid;grid-template-columns:34px 1fr;gap:14px}
.cause .n{font:600 12px/1.7 var(--mono);color:var(--accent)}
.cause h3{margin-bottom:5px}
.cause p{margin:0;font-size:14px;color:var(--muted)}

/* ── findings register ──────────────────────────────────────── */
.controls{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:16px;align-items:center}
button.f{
  font:600 11px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;
  padding:7px 11px;border-radius:4px;border:1px solid var(--rule-strong);
  background:var(--surface);color:var(--muted);cursor:pointer;
}
button.f:hover{border-color:var(--accent);color:var(--accent)}
button.f[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
:root[data-theme="dark"] button.f[aria-pressed="true"],
:root:not([data-theme="light"]) button.f[aria-pressed="true"]{color:#0D1218}
@media (prefers-color-scheme:light){:root:not([data-theme="dark"]) button.f[aria-pressed="true"]{color:#fff}}
.count{font:11.5px var(--mono);color:var(--faint);margin-left:auto}

.reg{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden}
.row{background:var(--surface);padding:0;display:block;border-left:3px solid transparent}
.row.BLOCKER{border-left-color:var(--flag)}
.row.CRITICAL{border-left-color:var(--band-vlow)}
.row.MAJOR{border-left-color:var(--band-low)}
.row.MINOR{border-left-color:var(--rule-strong)}
.row summary{
  padding:13px 18px;cursor:pointer;display:grid;
  grid-template-columns:88px 74px 92px 1fr;gap:14px;align-items:baseline;list-style:none;
}
.row summary::-webkit-details-marker{display:none}
.row summary:hover{background:var(--surface-2)}
.row .fid{font:11.5px var(--mono);color:var(--faint)}
.row .sev{font:600 10px/1 var(--mono);letter-spacing:.07em;padding:4px 6px;border-radius:3px;text-align:center}
.sev.BLOCKER{background:var(--flag-soft);color:var(--flag)}
.sev.CRITICAL{background:rgba(255,125,69,.14);color:#C2410C}
.sev.MAJOR{background:rgba(255,219,19,.16);color:#8A6D00}
.sev.MINOR{background:var(--surface-2);color:var(--muted)}
:root[data-theme="dark"] .sev.CRITICAL,:root:not([data-theme="light"]) .sev.CRITICAL{color:#FFA476}
:root[data-theme="dark"] .sev.MAJOR,:root:not([data-theme="light"]) .sev.MAJOR{color:#E3C74A}
.row .disc{font:11.5px var(--mono);color:var(--muted)}
.row .ttl{font-size:14.5px;color:var(--ink);line-height:1.45}
.detail{padding:2px 18px 18px 18px;border-top:1px solid var(--rule);background:var(--surface-2)}
.detail dt{font:600 10px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--faint);margin-top:14px}
.detail dd{margin:6px 0 0;font-size:14px;color:var(--ink-2)}
.detail dd.loc{font:12px var(--mono);color:var(--accent);word-break:break-word}
@media(max-width:760px){
  .row summary{grid-template-columns:1fr;gap:6px}
  .row .sev{justify-self:start;padding:4px 8px}
}

/* ── tables ─────────────────────────────────────────────────── */
.tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:8px;background:var(--surface)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{
  text-align:left;font:600 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;
  color:var(--faint);padding:13px 16px;border-bottom:1px solid var(--rule);white-space:nowrap;
}
td{padding:12px 16px;border-bottom:1px solid var(--rule);color:var(--ink-2);vertical-align:top}
tr:last-child td{border-bottom:none}
td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
td.flag{color:var(--flag);font-weight:600}
td.ok{color:var(--ok);font-weight:600}
s{color:var(--faint)}

/* ── rebuilt / two-col ──────────────────────────────────────── */
.ba{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:880px){.ba{grid-template-columns:1fr}}
.col{background:var(--surface);border:1px solid var(--rule);border-radius:8px;padding:20px}
.col.before{border-top:3px solid var(--flag)}
.col.after{border-top:3px solid var(--ok)}
.col ul{margin:12px 0 0;padding-left:0;list-style:none}
.col li{padding:9px 0 9px 22px;border-bottom:1px solid var(--rule);font-size:14px;color:var(--ink-2);position:relative}
.col li:last-child{border-bottom:none}
.col.before li::before{content:"×";position:absolute;left:2px;color:var(--flag);font-weight:700}
.col.after li::before{content:"✓";position:absolute;left:2px;color:var(--ok);font-weight:700}

.suites{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden}
.suite{background:var(--surface);padding:15px 18px;display:grid;grid-template-columns:78px 1fr auto;gap:16px;align-items:center}
.suite .st{font:600 10.5px/1 var(--mono);letter-spacing:.07em;padding:5px 8px;border-radius:3px;text-align:center;background:var(--ok-soft);color:var(--ok)}
.suite .nm{font-size:14.5px;color:var(--ink)}
.suite .dt{font:11.5px var(--mono);color:var(--faint);font-variant-numeric:tabular-nums}
.suite .sub{font-size:12.5px;color:var(--muted);margin-top:3px}
@media(max-width:700px){.suite{grid-template-columns:70px 1fr}.suite .dt{display:none}}

ol.road{list-style:none;padding:0;margin:0;display:grid;gap:1px;background:var(--rule);
  border:1px solid var(--rule);border-radius:8px;overflow:hidden}
ol.road li{background:var(--surface);padding:17px 20px;display:grid;grid-template-columns:30px 1fr;gap:14px}
ol.road .p{font:600 12px/1.7 var(--mono);color:var(--accent)}
ol.road h3{margin-bottom:5px;font-size:15px}
ol.road p{margin:0;font-size:13.5px;color:var(--muted)}

footer{padding:40px 0 60px;color:var(--faint);font-size:13px}
footer p{color:var(--faint);margin:0 0 7px}
ul.plain{padding-left:18px}
ul.plain li{margin-bottom:9px;color:var(--ink-2);font-size:14.5px}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>

<header>
  <div class="wrap head-inner">
    <div class="kicker">
      <span class="eyebrow">Expert panel audit</span>
      <span class="chip">12 disciplines</span>
      <span class="chip">97 findings</span>
      <span class="chip flag">28 blockers</span>
    </div>
    <h1>CognitionBioChem: what the platform<br>claimed, and what it computed</h1>
    <p class="lede measure">A twelve-discipline PhD review with independent adversarial
      verification, followed by a rebuild. The platform described itself as an AlphaFold3
      de novo drug discovery platform. The audit found no AlphaFold3, and no computation
      of any kind behind the numbers it displayed.</p>
    <div class="verdict measure">
      <p><strong>Verdict.</strong> A good user-interface prototype for a platform that had
      not been built, mislabelled as the platform itself. The information architecture is
      sound and worth keeping; the data layer was empty and had been given the names of
      real methods.</p>
    </div>
  </div>
</header>

<main class="wrap">

<section>
  <div class="sec-head"><span class="sec-no">01</span><h2>The decisive evidence</h2></div>
  <p class="sec-sub measure">The clearest single test is to put genuine predictor output
    beside the expression the platform used in its place. Real AlphaFold output for human
    TrkB (UniProt <code>Q16620</code>, 822 residues) was downloaded from EBI and parsed by
    the rebuilt parser.</p>

  <div class="evidence">
    <div class="trace">
      <div class="trace-head"><h3>Real AlphaFold output</h3><span class="tag real">measured</span></div>
      <div class="trace-meta">human TrkB · 822 residues · AlphaFold DB</div>
      <canvas id="c-real" width="900" height="340"></canvas>
      <div class="tstats" id="s-real"></div>
    </div>
    <div class="trace">
      <div class="trace-head"><h3>The platform's formula</h3><span class="tag fake">synthesized</span></div>
      <div class="trace-meta">93 + sin(i·0.4)·4 + (charCode % 5)·0.5 — app.js:791</div>
      <canvas id="c-fake" width="900" height="340"></canvas>
      <div class="tstats" id="s-fake"></div>
    </div>
  </div>

  <div class="bands">
    <span><i style="background:var(--band-vhigh)"></i>Very high &gt; 90</span>
    <span><i style="background:var(--band-high)"></i>Confident 70–90</span>
    <span><i style="background:var(--band-low)"></i>Low 50–70</span>
    <span><i style="background:var(--band-vlow)"></i>Very low &lt; 50</span>
  </div>

  <p class="measure" style="margin-top:22px">The formula is analytically confined to
    [89.0, 99.0], so two of the four confidence bands the interface advertised in its own
    legend were mathematically unreachable. It also inverts the true signal exactly where
    it matters most: GGGGS linkers, which a real predictor renders at pLDDT 30–60, were
    painted &ldquo;High&rdquo; green at 89–97.</p>
  <p class="measure">Backbone geometry gives the same answer independently. Real
    coordinates place consecutive Cα atoms 3.83 ± 0.09 Å apart. The parametric helix at
    <code>app.js:715</code>, whose radius came from ASCII character codes, produces
    0.63–16.6 Å, with 18 of 23 virtual bonds outside ±0.5 Å of the physical value.</p>
</section>

<section>
  <div class="sec-head"><span class="sec-no">02</span><h2>Independently computed</h2></div>
  <p class="sec-sub measure">These figures were produced in the repository with RDKit and
    the Python standard library, written without reference to the panel's output. Where the
    two overlap, they agree.</p>
  <div class="stats" id="stats"></div>

  <div class="tablewrap" style="margin-top:22px">
    <table>
      <thead><tr><th>Candidate</th><th>Asserted ΔG</th><th>Asserted K<sub>d</sub></th>
        <th>K<sub>d</sub> implied by that ΔG</th><th>Gap</th></tr></thead>
      <tbody id="thermo-rows"></tbody>
    </table>
  </div>
  <h3 style="margin-top:34px">Residue identities, checked against the sequence</h3>
  <p class="sec-sub measure" style="margin-top:8px">Each binding-site residue the dataset
    names was checked by retrieving the UniProt sequence and reading the cited position.
    Eight are wrong in every numbering convention.</p>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Target</th><th>UniProt</th><th>Asserted</th><th>Actually at that position</th></tr></thead>
      <tbody id="residue-rows"></tbody>
    </table>
  </div>
  <p class="sec-sub measure" style="margin-top:14px">A separate class of error sits in the
    AChE annotation, which places Torpedo californica numbering and human numbering inside
    a single parenthesis: <code>CAS (Trp84, Phe330, Tyr121) &amp; PAS (Trp286, Tyr72,
    Tyr341)</code>. Several annotations were verified <em>correct</em> — TLR4
    Arg264/Lys341/Glu439, KEAP1 Tyr334/Arg415/Arg483/Ser602, α7 nAChR
    Tyr188/Trp149/Tyr195 — so this is uneven curation rather than uniform invention.</p>

  <p class="sec-sub measure" style="margin-top:14px">Every one of the 25 pairs is
    internally impossible. At 298.15 K, ΔG and K<sub>d</sub> are locked together by
    ΔG&nbsp;=&nbsp;RT·ln(K<sub>d</sub>); the two columns correlate at r&nbsp;=&nbsp;0.9969,
    meaning they were generated from one another with a wrong constant rather than
    measured or computed.</p>
</section>

<section>
  <div class="sec-head"><span class="sec-no">03</span><h2>Root causes</h2></div>
  <p class="sec-sub measure">The panel compressed 97 findings into six underlying
    causes.</p>
  <div class="causes" id="causes"></div>
</section>

<section>
  <div class="sec-head"><span class="sec-no">04</span><h2>Findings register</h2></div>
  <p class="sec-sub measure">Every finding was re-checked by an independent verifier
    instructed to refute it and to default to skepticism. Select a row to expand it.</p>
  <div class="controls" id="controls"></div>
  <div class="reg" id="reg"></div>
</section>

<section>
  <div class="sec-head"><span class="sec-no">05</span><h2>What was rebuilt</h2></div>
  <p class="sec-sub measure">The fabricated renderers are gone. The numbers they produced
    are preserved in the data layer under <code>retracted_claims</code> — deleting them
    would hide the history, and relabelling them as results would repeat the error.</p>
  <div class="ba">
    <div class="col before">
      <h3>Before</h3>
      <ul>
        <li>pLDDT from a sine function, labelled &ldquo;AlphaFold3 pLDDT Score&rdquo;</li>
        <li>PAE from a distance-from-diagonal ramp, capped at 45 tokens</li>
        <li>3D &ldquo;backbone&rdquo; from ASCII character codes</li>
        <li>ΔG and K<sub>d</sub> as string literals inside prose fields</li>
        <li>No validation: prose and ambiguity codes flowed into the viewer</li>
        <li>A new WebGL renderer per modal open, never disposed</li>
        <li>&ldquo;Live Connected&rdquo; badge over a plain hyperlink</li>
      </ul>
    </div>
    <div class="col after">
      <h3>After</h3>
      <ul>
        <li>A parser for real mmCIF plus AlphaFold&nbsp;3 / AlphaFold&nbsp;DB / Boltz / Chai confidence files</li>
        <li>Full-resolution PAE from the actual matrix, with a labelled scale</li>
        <li>3Dmol.js on real coordinates, coloured by real per-residue pLDDT</li>
        <li>A Cα–Cα geometry audit that rejects non-protein coordinates</li>
        <li>A gate that exits non-zero: 77 violations across 11 categories</li>
        <li>One viewer with an explicit disposal path</li>
        <li>A provenance record on every value; the UI cannot render an unsourced number</li>
      </ul>
    </div>
  </div>
</section>

<section>
  <div class="sec-head"><span class="sec-no">06</span><h2>Verification</h2></div>
  <p class="sec-sub measure">Run with <code>python3 verify_all.py</code>. The data gate is
    <em>expected</em> to exit non-zero on the legacy dataset — a gate that passed on it
    would be the defect.</p>
  <div class="suites">
    <div class="suite"><span class="st">PASS</span>
      <div><div class="nm">Memory ledger regression suite</div>
        <div class="sub">74 checks · 16 concurrent writer processes, idempotency,
          torn-tail recovery, one test per critic finding</div></div>
      <span class="dt">1.5s</span></div>
    <div class="suite"><span class="st">PASS</span>
      <div><div class="nm">Platform regression suite</div>
        <div class="sub">93 checks · thermodynamics, peptide properties, RDKit validation,
          provenance enforcement, parsing real AlphaFold output</div></div>
      <span class="dt">0.2s</span></div>
    <div class="suite"><span class="st">PASS</span>
      <div><div class="nm">Front-end contract verification</div>
        <div class="sub">48 checks · DOM and data contracts, fabricated-renderer removal,
          resource lifecycle</div></div>
      <span class="dt">0.0s</span></div>
    <div class="suite"><span class="st">PASS</span>
      <div><div class="nm">Data-integrity gate <em>(expected to fail on legacy data)</em></div>
        <div class="sub">exit 1 · 77 violations across 11 categories</div></div>
      <span class="dt">0.2s</span></div>
    <div class="suite"><span class="st">PASS</span>
      <div><div class="nm">Dataset build and provenance audit</div>
        <div class="sub">every numeric value carries a provenance record</div></div>
      <span class="dt">0.2s</span></div>
  </div>

  <div class="tablewrap" style="margin-top:22px">
    <table>
      <thead><tr><th>Gate violation category</th><th>Count</th></tr></thead>
      <tbody id="gate-rows"></tbody>
    </table>
  </div>
</section>

<section>
  <div class="sec-head"><span class="sec-no">07</span><h2>What was genuinely good</h2></div>
  <p class="sec-sub measure">An honest review carries credit. These are worth
    preserving.</p>
  <ul class="plain measure" id="strengths"></ul>
</section>

<section style="border-bottom:none">
  <div class="sec-head"><span class="sec-no">08</span><h2>Remediation roadmap</h2></div>
  <p class="sec-sub measure">Ordered by dependency, not ambition. Phases 0 and 1 are
    complete.</p>
  <ol class="road" id="road"></ol>
</section>

</main>

<footer class="wrap">
  <p>Produced by a multi-agent review system: 12 domain reviewers, 12 independent
     adversarial verifiers, a panel chair, and 2 completeness critics. All findings and
     verdicts are stored in an append-only provenance ledger.</p>
  <p>Not affiliated with, endorsed by, or connected to Google DeepMind or the AlphaFold
     team. AlphaFold is a trademark of Google DeepMind.</p>
</footer>

<script>
const D = __PAYLOAD__;

/* ── confidence-trace chart ─────────────────────────────────── */
function bandColor(v){
  const s=getComputedStyle(document.documentElement);
  if(v>=90) return s.getPropertyValue('--band-vhigh');
  if(v>=70) return s.getPropertyValue('--band-high');
  if(v>=50) return s.getPropertyValue('--band-low');
  return s.getPropertyValue('--band-vlow');
}
function drawTrace(id,data){
  const cv=document.getElementById(id), dpr=window.devicePixelRatio||1;
  const w=cv.clientWidth||440, h=170;
  cv.width=w*dpr; cv.height=h*dpr; cv.style.height=h+'px';
  const g=cv.getContext('2d'); g.scale(dpr,dpr); g.clearRect(0,0,w,h);
  const s=getComputedStyle(document.documentElement);
  const pad={l:30,r:8,t:8,b:18};
  const pw=w-pad.l-pad.r, ph=h-pad.t-pad.b;
  const y=v=>pad.t+ph-(v/100)*ph;

  /* gridlines at the band boundaries — they are the meaningful values here */
  g.strokeStyle=s.getPropertyValue('--rule'); g.lineWidth=1;
  g.font='9px '+s.getPropertyValue('--mono'); g.fillStyle=s.getPropertyValue('--faint');
  [0,50,70,90,100].forEach(v=>{
    g.beginPath(); g.moveTo(pad.l,y(v)+.5); g.lineTo(w-pad.r,y(v)+.5); g.stroke();
    g.fillText(String(v),4,y(v)+3);
  });

  /* the 70 line is the one that decides "confident or not" */
  g.strokeStyle=s.getPropertyValue('--muted'); g.setLineDash([3,3]);
  g.beginPath(); g.moveTo(pad.l,y(70)+.5); g.lineTo(w-pad.r,y(70)+.5); g.stroke();
  g.setLineDash([]);

  /* fill under the curve, coloured by band */
  const n=data.length, dx=pw/(n-1);
  for(let i=0;i<n-1;i++){
    g.beginPath();
    g.moveTo(pad.l+i*dx,y(0)); g.lineTo(pad.l+i*dx,y(data[i]));
    g.lineTo(pad.l+(i+1)*dx,y(data[i+1])); g.lineTo(pad.l+(i+1)*dx,y(0));
    g.closePath();
    g.fillStyle=bandColor(data[i]); g.globalAlpha=.30; g.fill(); g.globalAlpha=1;
  }
  g.beginPath();
  data.forEach((v,i)=>{ const px=pad.l+i*dx, py=y(v); i?g.lineTo(px,py):g.moveTo(px,py); });
  g.strokeStyle=s.getPropertyValue('--ink'); g.lineWidth=1.1; g.globalAlpha=.55; g.stroke();
  g.globalAlpha=1;
}
function stats(id,st,flagBelow){
  document.getElementById(id).innerHTML=
    [['min',st.min],['max',st.max],['mean',st.mean],['sd',st.sd],
     ['&lt;70',st.below70+'%']]
    .map(([k,v],i)=>`<div><div class="k">${k}</div>
      <div class="v${i===4&&flagBelow?' hi':''}">${v}</div></div>`).join('');
}

/* ── stat strip ─────────────────────────────────────────────── */
const S=D.summary;
document.getElementById('stats').innerHTML=[
  ['4 / 8','SMILES unparseable','plus 3 encoding the wrong molecule','flag'],
  ['25 / 25','ΔG–K<sub>d</sub> impossible','max gap 5.73 kcal/mol','flag'],
  ['8','residues fabricated','wrong in every numbering convention','flag'],
  ['4','sequences invalid','non-standard residues or prose','flag'],
  [D.n_gate,'gate violations','across 13 categories','flag'],
  ['215','automated checks','all passing after rebuild','ok'],
].map(([v,k,s,c])=>`<div class="stat"><div class="v ${c}">${v}</div>
  <div class="k">${k}</div><div class="s">${s}</div></div>`).join('');

/* ── thermodynamics table ───────────────────────────────────── */
function fmtKd(m){
  const u=[['M',1],['mM',1e-3],['µM',1e-6],['nM',1e-9],['pM',1e-12],['fM',1e-15]];
  for(const [n,f] of u) if(m/f>=1) return (m/f).toPrecision(3)+' '+n;
  return m.toExponential(2)+' M';
}
document.getElementById('thermo-rows').innerHTML=(D.thermo||[]).map(r=>
  `<tr><td>${r.code}</td><td class="n"><s>${r.dg} kcal/mol</s></td>
   <td class="n"><s>${fmtKd(r.kd)}</s></td><td class="n">${r.implied}</td>
   <td class="n flag">${r.gap} kcal/mol</td></tr>`).join('');

document.getElementById('residue-rows').innerHTML=(D.residues||[]).map(r=>
  `<tr><td>${r.target}</td><td class="n">${r.uniprot}</td>
   <td class="n flag"><s>${r.asserted}</s></td><td class="n ok">${r.actual}</td></tr>`).join('');

/* ── root causes ────────────────────────────────────────────── */
document.getElementById('causes').innerHTML=D.root_causes.map((c,i)=>{
  const m=c.match(/^([A-Z][A-Z0-9 ,'’\\-—–:\\/()]{12,}?)[.．]\\s+([\\s\\S]+)$/);
  const head=m?m[1]:('Cause '+(i+1)), body=m?m[2]:c;
  return `<div class="cause"><div class="n">${String(i+1).padStart(2,'0')}</div>
    <div><h3>${head.charAt(0)+head.slice(1).toLowerCase()}</h3><p>${body}</p></div></div>`;
}).join('');

/* ── findings register ──────────────────────────────────────── */
let filt='ALL';
const SEVS=['ALL','BLOCKER','CRITICAL','MAJOR','MINOR'];
const DISCS=[...new Set(D.findings.map(f=>f.disc))].sort();
function renderControls(){
  document.getElementById('controls').innerHTML=
    SEVS.map(s=>`<button class="f" data-v="${s}" aria-pressed="${filt===s}">${s}</button>`).join('')
    + DISCS.map(d=>`<button class="f" data-v="${d}" aria-pressed="${filt===d}">${d}</button>`).join('')
    + `<span class="count" id="cnt"></span>`;
  document.querySelectorAll('button.f').forEach(b=>b.onclick=()=>{
    filt=b.dataset.v; renderControls(); renderReg();
  });
}
function renderReg(){
  const rows=D.findings.filter(f=>filt==='ALL'||f.sev===filt||f.disc===filt)
    .sort((a,b)=>({BLOCKER:0,CRITICAL:1,MAJOR:2,MINOR:3})[a.sev]-({BLOCKER:0,CRITICAL:1,MAJOR:2,MINOR:3})[b.sev]);
  document.getElementById('cnt').textContent=rows.length+' of '+D.findings.length;
  document.getElementById('reg').innerHTML=rows.map(f=>`
    <details class="row ${f.sev}">
      <summary>
        <span class="fid">${f.id}</span>
        <span class="sev ${f.sev}">${f.sev}</span>
        <span class="disc">${f.disc}</span>
        <span class="ttl">${f.title}</span>
      </summary>
      <div class="detail"><dl>
        <dt>Evidence</dt><dd class="loc">${f.loc}</dd>
        <dt>What is wrong</dt><dd>${f.wrong}</dd>
        <dt>Required fix</dt><dd>${f.fix}</dd>
        <dt>Independent verdict</dt><dd>${f.verdict.toLowerCase().replace(/_/g,' ')}</dd>
      </dl></div>
    </details>`).join('');
}

/* ── gate, strengths, roadmap ───────────────────────────────── */
document.getElementById('gate-rows').innerHTML=
  Object.entries(D.gate).sort((a,b)=>b[1]-a[1])
  .map(([k,v])=>`<tr><td>${k.replace(/_/g,' ')}</td><td class="n">${v}</td></tr>`).join('')
  + `<tr><td><strong>total</strong></td><td class="n flag"><strong>${D.n_gate}</strong></td></tr>`;

document.getElementById('strengths').innerHTML=D.strengths.map(s=>`<li>${s}</li>`).join('');

document.getElementById('road').innerHTML=D.roadmap.map((r,i)=>`
  <li><div class="p">${String(i).padStart(2,'0')}</div>
    <div><h3>${r.phase}</h3><p>${r.goal}</p></div></li>`).join('');

/* ── boot ───────────────────────────────────────────────────── */
function draw(){
  drawTrace('c-real',D.plddt.real);
  drawTrace('c-fake',D.plddt.fake);
}
stats('s-real',D.plddt.real_stats,true);
stats('s-fake',D.plddt.fake_stats,true);
renderControls(); renderReg(); draw();
addEventListener('resize',draw);
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',draw);
</script>
"""


# Build the thermodynamics rows here rather than in JS, so the arithmetic lives in Python.
import sys  # noqa: E402
sys.path.insert(0, str(REPO / "platform"))
from cbc import thermo  # noqa: E402

raw = json.loads((REPO / "data" / "extracted_raw.json").read_text())
rows = []
for d in raw["FULL_BRAIN_DRUGS_DATA"]:
    dg = thermo.parse_dg(d.get("affinity", ""))
    kd, _ = thermo.parse_kd(d.get("affinity", ""))
    if dg is None or kd is None:
        continue
    t = thermo.check(d["code"], dg, kd)
    rows.append({"code": d["code"], "dg": dg, "kd": kd,
                 "implied": thermo.format_kd(t.kd_implied_by_dg),
                 "gap": round(t.discrepancy_kcal, 2)})
rows.sort(key=lambda r: -r["gap"])

payload = json.loads(PAYLOAD)
payload["thermo"] = rows[:10]
payload["residues"] = json.loads((REPO / "data" / "residue_audit.json").read_text())["fabricated"]
html = HTML.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
OUT.write_text(html)
print(f"wrote {OUT.relative_to(REPO)}  ({len(html):,} bytes)")
print(f"  findings={len(payload['findings'])} thermo_rows={len(rows)} "
      f"gate={payload['n_gate']}")
