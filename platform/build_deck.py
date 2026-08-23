#!/usr/bin/env python3
"""Build docs/CognitionBioChem_Deck.html -- the conference deck.

Same rule as the report and the page: every number is read from an artefact at build time.
A slide that quotes a figure quotes it from data/, so re-running a study re-renders the deck
rather than leaving a stale number on a projector.

Figures are embedded as data URIs because the published artifact is served under a strict
CSP that admits no external host except Google Fonts. The deck is therefore one file, and it
is the same file whether it is opened from disk, published, or printed to PDF.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "platform"))
from cbc.provenance import git_sha  # noqa: E402

FIG = REPO / "docs" / "figures"
OUT = REPO / "docs" / "CognitionBioChem_Deck.html"


def J(p):
    return json.loads((REPO / p).read_text())


def A(p):
    d = J(p)
    return d.get("analysis") or d


def img(name: str) -> str:
    """Inline a figure as a data URI, refusing to emit a broken <img>."""
    path = FIG / name
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; the deck will not be built without it")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


# --------------------------------------------------------------------------- data ----- #
msa, scr = A("data/study_msa_specificity.json"), A("data/study_candidate_screen.json")
iv, pi = A("data/study_inference_variance_analysis.json"), A("data/study_peptide_interface.json")
pro = A("data/study_prodigy.json")
slate, struct, af, ds = (J("data/slate.json"), J("data/structures.json"),
                         J("data/alphafold_db_comparison.json"), J("data/dataset.json"))
m, c = msa["metrics"], slate["counts"]
nul = m["beats_all_decoys_null"]
per = msa["per_candidate"]
winners = sorted((p for p in per if p["beats_all_decoys"]), key=lambda p: -p["difference"])
n_decoys = max(p["n_decoys"] for p in per)
scr_decoys = len({r["kind"] for r in J("data/study_candidate_screen.json")["rows"]
                  if r["kind"] != "native"})
ver = slate["separation_across_versions"]
att = ds["disclosure"]["sequence_attribution_counts"]
cit = ds["citation"]
retr = [x for x in ds["candidates"] if "retracted_claims" in x]
runs = len(J("runs/manifest.json")["runs"])
e = next(x for x in struct["entries"] if x["id"] == "cpx-BasalAChE-Abeta-B4")
aa, ab = af["arms"]["boltz_single_sequence"], af["arms"]["boltz_full_msa"]
aa_top = max(aa["rows"], key=lambda r: r["pearson_r"])
win_margins = " and ".join(f'{w["native_iptm"] - w["decoy_max"]:+.3f}' for w in winners)

PY = str(REPO / ".venv" / "bin" / "python")
if not Path(PY).exists():
    PY = sys.executable


def suite_count(rel: str) -> int:
    """Run a verification suite and take the count from its own output.

    A suite with a failing check raises rather than reporting a number: a slide that says
    "N checks, each verified to fail on the defect it names" must not be projectable while
    one of them is red.
    """
    r = subprocess.run([PY, rel], cwd=REPO, capture_output=True, text=True)
    mt = re.search(r"(\d+) passed, (\d+) failed", r.stdout)
    if not mt:
        raise RuntimeError(f"{rel} printed no 'N passed, M failed' line -- cannot count it")
    if int(mt.group(2)):
        raise RuntimeError(f"{rel} reports {mt.group(2)} failing check(s); refusing to build")
    return int(mt.group(1))


N_CHECKS = (suite_count("platform/tests/test_platform.py")
            + suite_count("platform/verify_frontend.py"))


# ---------------------------------------------------------------------------- css ----- #
from cbc.deck_style import Deck, export_pdf  # noqa: E402


#: The deck is assembled through the shared shell; only its slides live in this file. The
#: stylesheet, the keyboard handling, the theme tokens and the PDF export are in
#: cbc/deck_style.py so that this deck and the paper deck cannot drift apart.
DECK = Deck("CognitionBioChem",
            "Conference deck: a structural pharmacology workbench that reports a negative result.")
slide = DECK.slide
figslide = DECK.figslide
SLIDES = DECK.slides
img = DECK.img


# ---- 01 title --------------------------------------------------------------------------
ids = "".join(f'<span>{i["value"]}</span>' for i in cit["identifiers"])
SLIDES.append(f'''<section class="slide title" data-kind="premise" aria-label="Title slide">
  <div class="eyebrow"><span class="kind">Structural pharmacology</span>
    <span>a workbench that reports a negative result</span></div>
  <div>
    <h1>CognitionBioChem</h1>
    <p class="thesis">Thirteen designed peptides do not separate from shuffles of their own
      amino acids &mdash; and the instrument was built so that answer would be believable
      either way.</p>
  </div>
  <div class="meta">
    <div>{cit["authors"][0]} &middot; ORCID {cit["orcid"][0].split("/")[-1]}
      &middot; v{cit["version"]} &middot; {cit["date_released"]}</div>
    <div class="ids">{ids}</div>
  </div>
  <footer class="foot"><span>Apache-2.0 code &middot; CC BY 4.0 / CC BY-SA 3.0 / CC0 / MIT data</span>
    <span class="no">01</span></footer>
</section>''')

# ---- 02 the failure it started from ----------------------------------------------------
slide("premise", "It began as a demo that was lying",
      f'''<div class="cols c-7-5">
  <div>
    <p>An earlier version of this project displayed affinity, confidence and safety numbers as
      though a structure predictor had produced them. No calculation had.</p>
    <p>A &ldquo;pLDDT&rdquo; curve was the expression
      <span class="mono">93 + sin(i&middot;0.4)&middot;4 + (charCode % 5)&middot;0.5</span>.
      Every one of the {len(retr)} stated &Delta;G/K<sub>d</sub> pairs is internally
      inconsistent at 298.15&nbsp;K against &Delta;G&nbsp;=&nbsp;RT&middot;ln(K<sub>d</sub>).</p>
    <p>They are not deleted. They are kept under <span class="mono">retracted_claims</span>,
      struck through, so the record of what was once asserted survives.</p>
  </div>
  <div class="stats">
    <div class="stat"><b>{len(retr)}</b><span>candidates carrying fabricated values</span></div>
    <div class="stat"><b>0</b><span>calculations behind them</span></div>
    <div class="stat"><b class="strike">&minus;18.4</b><span>kcal/mol, as asserted</span></div>
    <div class="stat"><b class="strike">0.32 nM</b><span>K<sub>d</sub>, as asserted &mdash; 4 orders apart</span></div>
  </div>
</div>''',
      sub="The reason the workbench cannot render a number without a provenance record.",
      foot="data/dataset.json &middot; retracted_claims")

figslide("premise", "What replaced it",
         "One path to the screen for every value, and a status attached to each: computed, "
         "predicted, database, literature, measured, placeholder, not_computed. The last two "
         "render as a label, never as a figure.",
         "ui1_headline_finding.png",
         "The workbench states the result before the capabilities. Every number in the card is "
         "read from a study artefact at build time rather than written into the markup &mdash; "
         "which is why the page cannot drift from the data behind it.",
         foot="index.html &middot; data/slate.json")

# ---- 03 what a predictor reports -------------------------------------------------------
slide("premise", "Confidence is not affinity",
      '''<div class="cols c-1-1">
  <ul class="led">
    <li><span class="k">pLDDT</span><span>Per-residue local accuracy, 0&ndash;100, written in the
      model&rsquo;s own B-factor column. A property of the fold, not of the pair.</span></li>
    <li><span class="k">PAE</span><span>Expected positional error of residue <i>i</i> when
      superposed on <i>j</i>. Directed, so genuinely asymmetric; its off-diagonal blocks say
      whether two chains are confidently placed relative to each other.</span></li>
    <li><span class="k">ipTM</span><span>The cross-chain part of that, condensed to one
      number.</span></li>
  </ul>
  <div>
    <p class="pull">A high ipTM says the model places the peptide somewhere definite. It does
      not say the peptide belongs there.</p>
    <p style="margin-top:1.1em">None of these is a binding affinity, and none of them is
      evidence of binding. They are the model&rsquo;s report on its own certainty about
      geometry. This distinction is the axis the whole project turns on.</p>
  </div>
</div>''',
      sub="Jumper et al. 2021, Nature 596:583 &mdash; AlphaFold2 predicts structure and reports calibrated confidence in itself.",
      foot="PMID 34265844")

# ---- 04 predictor choice ---------------------------------------------------------------
slide("method", "Boltz-2, and why not AlphaFold 3",
      f'''<div class="cols c-7-5">
  <div>
    <p>Every predicted structure here comes from <b>Boltz-2 v2.2.1</b>, whose code and weights
      are both MIT-licensed and which runs locally on Apple silicon. {runs} runs are under
      content-addressed custody.</p>
    <p><b>AlphaFold 3</b> was not used: its parameters are request-only, non-commercial and
      Linux/CUDA-bound, so no reproducible local pipeline could be built on it.</p>
    <p><b>AlphaFold Server</b> was not used and could not have been &mdash; its terms prohibit
      automated use for protein&ndash;ligand and protein&ndash;peptide binding prediction, which
      is exactly what the two screening studies do.</p>
    <p>The deposited <b>AlphaFold DB</b> is a separately licensed corpus, and is used under
      CC&nbsp;BY&nbsp;4.0 as an independent comparison.</p>
  </div>
  <div>
    <p class="pull">Boltz-2 carries an affinity head. This project deliberately never renders
      its output as a free energy.</p>
    <p style="margin-top:1em">The head is fitted to pooled K<sub>i</sub>, K<sub>d</sub>,
      IC<sub>50</sub> and EC<sub>50</sub> labels. An IC<sub>50</sub> depends on substrate
      concentration and on K<sub>m</sub>; converting one to a K<sub>i</sub> needs assumptions a
      pooled training label does not carry. A number fitted to that mixture has no single
      physical referent &mdash; and a build guard fails if any code path tries.</p>
  </div>
</div>''',
      sub="Licensing is not a footnote here; it decided the instrument.",
      foot="Passaro et al. 2025 &middot; Cheng &amp; Prusoff 1973, PMID 4202581")

# ---- 05 the null -----------------------------------------------------------------------
slide("method", "The composition-matched null",
      f'''<div class="cols c-7-5">
  <div>
    <p>For each candidate, <b>{n_decoys} decoys</b> are generated by shuffling that
      candidate&rsquo;s own amino acids. A decoy has identical composition &mdash; same
      molecular weight, same net charge, same hydropathy &mdash; and differs only in order.</p>
    <p>Each is folded against the same receptor construct, with the same seed, in the same
      order. If the design carries information about its target it should score above its own
      shuffles. If the model is responding to composition, it will not.</p>
    <p>The construct is not the full UniProt sequence: signal peptides removed, transmembrane
      and cytoplasmic segments excluded where the site is extracellular, and the span actually
      folded recorded per candidate with its basis and canonical numbering.</p>
  </div>
  <div class="stats">
    <div class="stat"><b>{len(per)}</b><span>constructs &middot; {
      (msa.get("peptide_multiplicity") or {}).get("n_distinct_peptides", len(per))
      } distinct peptides</span></div>
    <div class="stat"><b>{n_decoys}</b><span>shuffles each</span></div>
    <div class="stat"><b>{msa["n_observed"]}</b><span>folds, full-MSA arm</span></div>
    <div class="stat"><b>3</b><span>construct corrections &mdash; none changed the direction</span></div>
  </div>
</div>''',
      sub="A screen without this measures how confident the model is, not whether the design did anything.",
      stamp="plan 8511b6cc30ea", foot="Slate #10 &middot; data/study_msa_specificity.json")

# ---- 06 the gate -----------------------------------------------------------------------
pim = pi["metrics"]
gate_pl = [r["peptide_len"] for r in J("data/study_peptide_interface.json")["rows"]]
gate_rl = [r["receptor_len"] for r in J("data/study_peptide_interface.json")["rows"]]
cand_pl = [len(r["peptide_used"]) for r in J("data/study_msa_specificity.json")["rows"]]
cand_rl = [r["receptor_len"] for r in J("data/study_msa_specificity.json")["rows"]]
slide("method", "A gate the screen had to pass first",
      f'''<div class="cols c-7-5">
  <div>
    <p>Slate&nbsp;#7 was registered <i>before</i> the candidate screen was permitted to be
      believed. It asks whether this pipeline recovers interfaces it could have memorised:
      {pi["n_observed"]} peptide&ndash;receptor X-ray complexes, folded and scored with
      DockQ&nbsp;v2.</p>
    <p>That is the sense in which ipTM is used downstream &mdash; as a discrimination signal on
      this kind of complex, not as a calibrated probability.</p>
    <p>The same study measured the leakage that makes a gate necessary. The benchmark peptides
      are {min(gate_pl)}&ndash;{max(gate_pl)} residues against receptors of
      {min(gate_rl)}&ndash;{max(gate_rl)}; the candidates are
      {min(cand_pl)}&ndash;{max(cand_pl)} against {min(cand_rl)}&ndash;{max(cand_rl)}.
      <b>The sensitivity argument transfers. The numeric bands do not.</b></p>
  </div>
  <div class="stats">
    <div class="stat"><b>{pim["fraction_dockq_acceptable"]:.0%}</b><span>reach CAPRI-acceptable</span></div>
    <div class="stat"><b>{pim["median_dockq"]}</b><span>median DockQ</span></div>
    <div class="stat"><b>{pim["spearman_iptm_dockq"]}</b><span>Spearman <span class="sym">&rho;</span>, ipTM vs DockQ</span></div>
    <div class="stat"><b>{pim["median_fnat"]}</b><span>median native contacts recovered</span></div>
  </div>
</div>''',
      sub="Basu &amp; Wallner 2016 &middot; Mirabello &amp; Wallner 2024 &middot; Lensink et al. 2007",
      stamp="plan 515be79a7d12", foot="Slate #7 &middot; PMID 27560519 / 39348158 / 17918726")

# ---- 07 noise floor --------------------------------------------------------------------
ivm = iv["metrics"]
slide("method", "How big a difference has to be",
      f'''<div class="cols c-7-5">
  <div>
    <p>Slate&nbsp;#2 measured the sampler&rsquo;s own noise before any comparison was trusted.
      Folding the same complexes repeatedly under different seeds gives an across-seed standard
      deviation of <span class="hl">{ivm["across_seed_sd_iptm"]:.3f}</span> in ipTM and
      <span class="hl">{ivm["across_seed_sd_complex_plddt"]:.2f}</span> pLDDT units.</p>
    <p class="pull" style="margin-top:1em">Any difference smaller than that is not a
      measurement.</p>
    <p style="margin-top:1em">It is the reason the {len(winners)} apparent successes in the
      screen are reported as noise: they beat their best decoy by
      <span class="mono">{win_margins}</span>, against a one-standard-deviation spread of
      {ivm["across_seed_sd_iptm"]:.3f}.</p>
  </div>
  <div class="stats">
    <div class="stat"><b>{ivm["across_seed_sd_iptm"]:.3f}</b><span>SD, ipTM across seeds</span></div>
    <div class="stat"><b>{ivm["across_seed_sd_complex_plddt"]:.2f}</b><span>SD, complex pLDDT</span></div>
    <div class="stat"><b>{ivm["across_seed_sd_interface_pae_min"]:.2f}</b><span>SD, minimum interface PAE (&Aring;)</span></div>
    <div class="stat"><b>{iv["n_observed"]}</b><span>folds in the variance study</span></div>
  </div>
</div>''',
      sub="Measured first, so no later comparison could be argued about after the fact.",
      stamp="plan 8242c485e46a", foot="Slate #2 &middot; data/study_inference_variance_analysis.json")

# ---- 08 headline result ----------------------------------------------------------------
beaten = sum(1 for p in per if p["decoy_max"] > p["native_iptm"])
slide("result", "The designs do not separate from their own shuffles",
      f'''<div>
  <div class="stats">
    <div class="stat"><b>{m["mean_native_iptm"]}</b><span>mean native ipTM</span></div>
    <div class="stat"><b>{m["mean_decoy_iptm"]}</b><span>mean decoy ipTM</span></div>
    <div class="stat"><b>{m["mean_native_iptm"] - m["mean_decoy_iptm"]:+.4f}</b><span>paired difference</span></div>
    <div class="stat"><b>{msa["p_holm"]["H1_natives_separate_from_decoys"]:.2f}</b><span>p, paired t-test</span></div>
    <div class="stat"><b>{m["cohens_dz"]:+.3f}</b><span>Cohen&rsquo;s d<sub>z</sub></span></div>
    <div class="stat"><b>{beaten}/{len(per)}</b><span>beaten by their own best shuffle</span></div>
  </div>
  <p class="pull" style="margin-top:clamp(16px,2.2cqw,32px); max-width:74ch">The gap is
    {abs(m["mean_native_iptm"] - m["mean_decoy_iptm"]):.4f} ipTM against a sampler noise floor
    of {ivm["across_seed_sd_iptm"]:.3f} &mdash; it is
    {ivm["across_seed_sd_iptm"] / abs(m["mean_native_iptm"] - m["mean_decoy_iptm"]):.0f}&times;
    below the smallest difference this instrument can resolve.</p>
</div>''',
      sub=f"Full MSA, {n_decoys} shuffles per candidate, {msa['n_observed']} folds.",
      stamp="plan 8511b6cc30ea", foot="Slate #10 &middot; H1 FALSIFIED")

figslide("result", "Every design against its own shuffles", "",
         "fig1_native_vs_decoy.png",
         f"The diamond is the designed sequence; the bar spans the decoy mean to the best of "
         f"{n_decoys} shuffles. A design to the right of its bar outscored all of them &mdash; "
         f"{nul['observed']} of {len(per)} do. Data: data/study_msa_specificity.json.",
         stamp="plan 8511b6cc30ea", foot="Slate #10")

# ---- 10 the screen-level null -----------------------------------------------------------
slide("result", "Two winners is what chance looks like",
      f'''<div class="cols c-7-5">
  <div>
    <p>{nul["observed"]} of {len(per)} candidates beat all {n_decoys} of their own decoys:
      <span class="mono">{winners[0]["code"]}</span> and
      <span class="mono">{winners[1]["code"]}</span>.</p>
    <p>Under the null a candidate does so with probability
      {nul["per_candidate_null_probability"]} = 1/{n_decoys + 1}. So
      <span class="hl">{nul["expected_under_null"]}</span> of {len(per)} are expected by
      chance, and <span class="mono">P(X &ge; {nul["observed"]}) =
      {nul["p_at_least_observed"]}</span>. Every winner carries the same empirical
      p&nbsp;=&nbsp;{max(w["empirical_p"] for w in winners)}, the smallest value this design can
      produce.</p>
    <p class="pull" style="margin-top:1em">The composition-matched null does not protect a
      candidate from being read as a hit. Slate #12 put that reading to a registered test and it
      did not survive: the null separates natives from their own permutations across a set of
      pairs taken together, and licenses no verdict on a single pair. It does nothing for a
      screen read the same way either &mdash; and that is the same error one level up.</p>
    <p style="margin-top:.9em"><span class="mono" style="color:var(--muted)">This screen-level
      null was computed after the data were seen, and is flagged exploratory in the artefact for
      exactly that reason.</span></p>
  </div>
  <div class="figwrap"><img src="{img("fig2_screen_level_null.png")}"
    alt="Binomial null for the number of candidates beating all ten decoys"></div>
</div>''',
      sub="", stamp="plan 8511b6cc30ea", foot="Slate #10 &middot; H2")

# ---- 11 survived every correction --------------------------------------------------------
_SEP = ("native_minus_decoy_mean", "paired_native_minus_decoy_mean")
scr_line = sorted((v["artefact"] for v in ver["versions"] if "candidate_screen" in v["artefact"]),
                  key=lambda a: (0, a) if "superseded" in a else (1, a))
scr_series = [next(A(a)["metrics"][k] for k in _SEP if k in A(a)["metrics"]) for a in scr_line]
slide("result", "The verdict survived every correction. The margin did not.",
      f'''<div class="cols c-7-5">
  <div class="figwrap"><img src="{img("fig3_falsified_every_version.png")}"
    alt="Every retained version of the two screening studies, all falsified"></div>
  <div>
    <p>Three construct corrections, a de-duplication, two coverage expansions and a decoy
      expansion from {scr_decoys} to {n_decoys} shuffles. H1 was falsified in all
      <span class="hl-a">{ver["n_versions"]}</span> retained versions, over candidate sets from
      {min(v["n_candidates"] for v in ver["versions"])} to
      {max(v["n_candidates"] for v in ver["versions"])} constructs.</p>
    <p>What did not hold steady is the size of the gap. Across the screen&rsquo;s
      {len(scr_series)} versions the mean native&minus;decoy ran<br>
      <span class="mono">{" &nbsp;".join(f"{v:+.4f}" for v in scr_series)}</span><br>
      &mdash; growing several-fold, then back through zero, and never once leaving the
      &plusmn;{ivm["across_seed_sd_iptm"]:.3f} noise floor.</p>
    <p class="pull" style="margin-top:1em">Superseded versions are kept, not overwritten. Each
      records why.</p>
  </div>
</div>''',
      sub="", foot="data/slate.json &middot; data/superseded/")

# ---- 12 where the confidence comes from ---------------------------------------------------
share = e["chains"][0]["length"] / sum(ch["length"] for ch in e["chains"])
slide("result", "Where a good-looking score actually comes from",
      f'''<div class="cols c-7-5">
  <div class="figwrap"><img src="{img("fig5_complex_structure.png")}"
    alt="Predicted complex coloured by pLDDT band, with per-residue confidence per chain"></div>
  <div>
    <p><span class="mono">{e["code"]}</span> against {e["target"]} scores ipTM
      <span class="hl">{e["metrics"]["iptm"]}</span> &mdash; by the usual bands, a good
      interface.</p>
    <p>Split by chain: the receptor&rsquo;s mean pLDDT is
      <span class="hl-a">{e["chains"][0]["mean_plddt"]}</span>, the designed peptide&rsquo;s is
      <span class="hl-a">{e["chains"][1]["mean_plddt"]}</span>. The receptor is
      {share:.0%} of the complex by residue count
      ({e["chains"][0]["length"]} against {e["chains"][1]["length"]}).</p>
    <p class="pull" style="margin-top:1em">A single pooled mean is the receptor&rsquo;s number
      wearing the complex&rsquo;s name.</p>
    <p style="margin-top:.9em">And the best of this candidate&rsquo;s {n_decoys} shuffles
      reaches {e["screen"]["decoy_max"]}.</p>
  </div>
</div>''',
      sub="", foot="data/structures.json &middot; runs/" + e["cif"].split("/")[1])

# ---- 13 independent predictor ---------------------------------------------------------------
figslide("result", "An independent predictor agrees about the receptors",
         f"AlphaFold DB deposited models against Boltz-2 per-residue confidence over the same "
         f"construct span. Median Pearson r rises from {aa['pearson_r_median']} "
         f"(single-sequence) to {ab['pearson_r_median']} (full MSA); the mean pLDDT gap closes "
         f"from {aa['mean_offset_afdb_minus_boltz']} to {ab['mean_offset_afdb_minus_boltz']} "
         f"points.",
         "fig4_alphafold_vs_boltz.png",
         f"Exploratory, and bounded in the artefact: it is not a check on the peptide, the "
         f"interface, or any claim in the slate. Residues within one protein are not "
         f"independent, so no p-value is attached to any r &mdash; each row carries an "
         f"effective sample size instead. The largest correlation in the single-sequence arm "
         f"({aa_top['target']}, r = {aa_top['pearson_r']}) rests on "
         f"{aa_top['n_residues_compared']} residues worth about "
         f"{aa_top['effective_n_after_autocorrelation']} independent observations, which makes "
         f"it the least supported number in that column.",
         foot="data/alphafold_db_comparison.json &middot; Varadi et al. 2024, PMID 37933859")

# ---- 14 the slate ------------------------------------------------------------------------
rows = ""
for s_ in slate["studies"]:
    vs = "".join(
        f'<span class="chip {x["verdict"][0].lower()}">{x["verdict"][:1]}</span> '
        for x in s_["hypotheses"] if x["verdict"])
    # An n column that renders every study alike claimed a provenance one of them does not
    # have. 160 of study #12's 176 rows name a run tree this repository deliberately does not
    # carry, so its numbers are reproducible by re-running and not checkable against stored
    # bytes. build_slate.py counts that against runs/manifest.json; the slide says so where
    # the count is, rather than leaving the reader to assume the eight-study rule holds.
    cu = s_["custody"]
    gap = ('' if cu["complete"] is not False else
           f'<br><span style="color:#a05a00">'
           f'{cu["rows_whose_bytes_this_repository_does_not_hold"]} of {cu["rows"]} '
           f'rows have no folds here</span>')
    rows += (f'<tr><td class="h">#{s_["slate_number"]}</td><td>{s_["title"]}</td>'
             f'<td class="h">{s_["plan_hash"]}</td>'
             f'<td class="h" style="text-align:right">{s_["n_observed"] or "&mdash;"}{gap}</td>'
             f'<td style="white-space:nowrap">{vs}</td></tr>')
custody_foot = " ".join(
    f'<br><strong>#{s_["slate_number"]}:</strong> '
    f'{s_["custody"]["note"].split(" Everything needed")[0]}'
    for s_ in slate["studies"] if s_["custody"]["complete"] is False)
slide("result", "The whole slate, verdicts and all",
      f'''<div class="tablewrap"><table>
  <thead><tr><th>#</th><th>Study</th><th>Plan hash</th><th style="text-align:right">n</th>
    <th>Hypotheses</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
<p style="margin-top:1em; font-size:clamp(11px,1.02cqw,15px)">
  <span class="chip c">C</span> confirmed &nbsp;
  <span class="chip f">F</span> falsified &nbsp;
  <span class="chip n">N</span> not tested &mdash;
  in hues that carry no good/bad reading, because several of the confirmations here confirm
  unwelcome statements, and the central falsification is the finding.
  {custody_foot}
  Of {c["hypotheses"]} hypotheses, {c["decided_by_a_test"]} were decided by a test statistic and
  {c["decided_by_a_threshold"]} by a pre-specified threshold.
  <b>A confirmed criterion is not a test result.</b></p>''',
      sub=f"{c['studies']} studies, pre-registered under a content hash before their data was "
          f"seen. {len(list((REPO / 'prespec').glob('*.json')))} plans retained; superseded "
          f"versions kept, never overwritten.",
      foot="data/slate.json")

figslide("result", "Verdicts as the workbench renders them",
         "Colour marks whether a pre-registered rule fired &mdash; deliberately in hues that "
         "carry no good/bad reading.",
         "ui2_verdicts.png",
         "Several of the confirmations here confirm unwelcome statements: that a method does "
         "not discriminate, or that candidates fall in a failed band. Colouring confirmation "
         "green would have made the page argue for a conclusion the data does not support.",
         foot="index.html &middot; Slate tab")

# ---- 15 limits ----------------------------------------------------------------------------
prom = pro["metrics"]
# Read, not typed. This bullet said "Not one study in the slate is confirmatory"  [SLATE-COUNT-HISTORICAL: the superseded sentence, quoted]  and went on
# saying it after study #12's audit recorded confirmatory = true with an empty deviation list.
# The same sentence was hand-written on four surfaces -- this deck, both report editions and
# the Slate tab -- so correcting it in front of one reader left it standing for the other
# three. build_slate.py derives both the label and the sentence from the per-study audits.
_sc = slate["counts"]["studies_confirmatory"]
CONF_KEY = ("not confirmatory" if _sc == 0
            else f"{_sc} of {slate['counts']['studies']} confirmatory")
CONF_LINE = slate["confirmatory_headline"].replace("--", "&mdash;").replace("\u2014", "&mdash;")
slide("limit", "What this does not show",
      f'''<ul class="led" data-marks="neutral">
  <li><span class="k">not proof</span><span><b>It does not show these peptides cannot
    bind.</b> It shows this predictor, on this construct set, does not distinguish them from
    shuffles of their own residues. A wet-lab assay could still find binding; nothing here
    would have detected it.</span></li>
  <li><span class="k">not a verdict on the model</span><span>Two independent 2026 evaluations
    report related limitations in Boltz-2, but this project measured a property of a
    <i>screen</i>, not the accuracy of a model.</span></li>
  <li><span class="k">no affinity</span><span>No docking, MM-GBSA or FEP exists in the
    repository. The one method that did produce a &Delta;G &mdash; PRODIGY, Slate&nbsp;#11 &mdash;
    occupied {prom["fraction_of_fit_range_occupied"]:.0%} of the reference span, with a
    discrimination ratio whose bootstrap interval
    <span class="mono">{prom["discrimination_ratio_ci95_bootstrap"]}</span> straddles its
    threshold. The design cannot resolve whether it discriminates &mdash; which is not the same
    as saying it does not.</span></li>
  <li><span class="k">confounded</span><span>The AlphaFold comparison confounds predictor, MSA
    and monomer-versus-complex context at once. It says nothing about the peptide or the
    interface.</span></li>
  <li><span class="k">weak inputs</span><span>Of {att["attributed_motifs"] + att["unattributed_motif_entries"]}
    motif entries only {att["attributed_motifs"]} carry a UniProt accession;
    {att["candidates_carrying_one"]} of {att["candidates_total"]} candidates carry at least one
    of {att["distinct_unattributed_fragments"]} unattributed fragments. These are not optimised
    designs, and a negative result on them is not a negative result on peptide design.</span></li>
  <li><span class="k">{CONF_KEY}</span><span>{CONF_LINE}
    The deviations are machine-detected and listed per study. Pre-registration did not make
    those results confirmatory &mdash; it made the deviations visible.</span></li>
</ul>''',
      sub="Stated because they are load-bearing, not to pre-empt the question.",
      foot="every item is machine-checked in the artefacts")

# ---- 16 reproducibility -------------------------------------------------------------------
idrows = "".join(
    f'<tr><td class="h">{i["value"]}</td><td>{i.get("description", "")}</td></tr>'
    for i in cit["identifiers"])
slide("premise", "Reproducible, addressable, and checked",
      f'''<div class="cols c-7-5">
  <div>
    <div class="tablewrap"><table><thead><tr><th>Identifier</th><th>What it names</th></tr>
      </thead><tbody>{idrows}</tbody></table></div>
    <p style="margin-top:1em">Apache-2.0 for the code; the redistributed scientific data carries
      four further licences &mdash; CC&nbsp;BY&nbsp;4.0 (UniProt, AlphaFold&nbsp;DB),
      CC&nbsp;BY-SA&nbsp;3.0 (ChEMBL-derived), CC0 (RCSB), MIT (Boltz-2 outputs). The
      share-alike term carries an obligation onward, and NOTICE says which files it binds.</p>
  </div>
  <div class="stats">
    <div class="stat"><b>{runs}</b><span>runs under content-addressed custody</span></div>
    <div class="stat"><b>{len(struct["entries"])}</b><span>structures indexed and openable</span></div>
    <div class="stat"><b>{N_CHECKS}</b><span>automated checks, each verified to fail on the defect it names</span></div>
    <div class="stat"><b>4</b><span>generated files stamping the commit they were built from</span></div>
  </div>
</div>''',
      sub="A directory name is a hash over its files, so an identifier changes if any output changes.",
      foot="github.com/hopejsh/CognitionBioChem")

# ---- 17 closing ----------------------------------------------------------------------------
SLIDES.append(f'''<section class="slide title" data-kind="result" aria-label="Closing slide">
  <div class="eyebrow"><span class="kind">The finding</span>
    <span>and the reason it is worth reporting</span></div>
  <div>
    <h1 style="font-size:clamp(26px,3.5cqw,50px); line-height:1.05; max-width:22ch">
      A negative result is only worth anything if the instrument could have said yes.</h1>
    <p class="thesis" style="margin-top:.7em">Thirteen designs, {n_decoys} composition-matched
      shuffles each, a gate registered before the screen, a measured noise floor, and
      {ver["n_versions"]} retained versions &mdash; every one of them falsified. The verdict is
      what survived every correction. The margin never did.</p>
  </div>
  <div class="meta">
    <div>Cite as: {cit["authors"][0]} ({cit["date_released"][:4]}).
      CognitionBioChem v{cit["version"]}. {cit["identifiers"][0]["value"]} &middot;
      {cit["identifiers"][2]["value"]}</div>
  </div>
  <footer class="foot"><span>Report, data and every run: github.com/hopejsh/CognitionBioChem
      &nbsp;&middot;&nbsp; deck built from {git_sha()}</span>
    <span class="no">{len(SLIDES) + 1:02d}</span></footer>
</section>''')


# ---------------------------------------------------------------------------- page ---- #
OUT.write_text(DECK.html())
print(f"wrote {OUT.relative_to(REPO)}")
print(f"  slides: {len(SLIDES)}")
print(f"  size:   {OUT.stat().st_size / 1024:.0f} KB")

pdf = export_pdf(OUT)
if pdf:
    print(f"wrote {pdf.relative_to(REPO)}  ({pdf.stat().st_size / 1024:.0f} KB, 1120x630 pt pages)")
else:
    print("  (no Chrome found; skipped the PDF export)")
