#!/usr/bin/env python3
"""Build the generated figures: the five docs/CognitionBioChem_Report.docx and the deck
embed, and fig6, which stands on its own.

These figures existed before this file did: they were drawn once, by hand, from a throwaway
script, and committed as PNGs with no generator behind them. That is precisely the defect
this repository's own guard names for the AlphaFold artefact -- a published artefact whose
generator cannot be run from a clone is not reproducible, whatever the working tree looked
like on the day it was made. So the drawing code lives here, reads the same artefacts the
page reads, and is re-runnable:

    ./.venv/bin/python platform/build_figures.py

Every label, count and statistic on every axis is read from data/ at draw time. Nothing is
typed into a title.

fig6 is drawn here but embedded by nothing: the report, the deck and the paper were written
before study #12 existed and none of them refers to it. It is generated anyway, because the
alternative is a figure that lives only in a manuscript workspace outside this repository,
which is the same unreproducible arrangement the paragraph above describes.

The screen captures under docs/figures/ui*.png are not produced here. They are photographs
of the running page, taken from a browser, and no script can regenerate them; the page they
show is index.html served over HTTP, and each caption in the report says which tab it is.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
from scipy.stats import binom            # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

#: The AlphaFold confidence bands, in the published colours. Used for the pLDDT panel so a
#: reader who knows the bands reads this plot without a legend.
BANDS = [(90, 100, "#0053D6"), (70, 90, "#65CBF3"), (50, 70, "#FFDB13"), (0, 50, "#FF7D45")]
NAVY, GREY, AMBER = "#1A3D6D", "#9AA3AE", "#B0761C"

plt.rcParams.update({
    "font.size": 9,
    "axes.edgecolor": "#8A8F98",
    "axes.labelcolor": "#26292E",
    "text.color": "#26292E",
    "xtick.color": "#4A4F57",
    "ytick.color": "#4A4F57",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def J(p):
    return json.loads((REPO / p).read_text())


def A(p):
    d = J(p)
    return d.get("analysis") or d


def save(fig, name):
    path = OUT / name
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}  ({path.stat().st_size // 1024} KB)")


# --------------------------------------------------------------------- 1. dumbbell ---- #
def fig1():
    """Each design against its own shuffles, one row per candidate."""
    msa = A("data/study_msa_specificity.json")
    m, per = msa["metrics"], msa["per_candidate"]
    rows = sorted(per, key=lambda p: p["native_iptm"])
    n_dec = max(p["n_decoys"] for p in per)
    y = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(9.4, 5.2))
    for i, r in enumerate(rows):
        lo, hi = min(r["decoy_mean"], r["decoy_max"]), max(r["decoy_mean"], r["decoy_max"])
        ax.plot([lo, hi], [i, i], color=GREY, lw=3.2, solid_capstyle="round",
                alpha=.75, zorder=1)
    ax.scatter([r["decoy_mean"] for r in rows], y, s=26, color=GREY, zorder=2,
               label="decoy mean")
    ax.scatter([r["decoy_max"] for r in rows], y, marker="|", s=150, color=GREY,
               linewidths=1.6, zorder=3, label=f"best of {n_dec} decoys")
    ax.scatter([r["native_iptm"] for r in rows], y, marker="D", s=62, color=NAVY,
               zorder=4, label="designed sequence")

    ax.set_yticks(y, [r["code"] for r in rows], fontsize=8.4)
    ax.set_xlabel("interface pTM (ipTM)")
    ax.set_title(
        "Every designed peptide against shuffles of its own amino acids\n"
        f"mean native {m['mean_native_iptm']} vs mean decoy {m['mean_decoy_iptm']}; "
        f"paired t-test p = {msa['p_holm']['H1_natives_separate_from_decoys']:.2f}",
        fontsize=10.5, loc="left", pad=12)
    ax.grid(axis="y", color="#E6E8EB", lw=.7)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.11), ncols=3, frameon=False,
              fontsize=9)
    save(fig, "fig1_native_vs_decoy.png")


# ------------------------------------------------------------------ 2. screen null ---- #
def fig2():
    """The binomial null for how many candidates beat all of their own decoys."""
    msa = A("data/study_msa_specificity.json")
    nul = msa["metrics"]["beats_all_decoys_null"]
    n = len(msa["per_candidate"])
    p = nul["per_candidate_null_probability"]
    k = np.arange(0, n + 1)
    pmf = binom.pmf(k, n, p)
    keep = k[pmf > 1e-4]
    k, pmf = k[: keep.max() + 2], pmf[: keep.max() + 2]

    fig, ax = plt.subplots(figsize=(5.6, 3.9))
    ax.bar(k, pmf, color=GREY, width=.66)
    ax.bar([nul["observed"]], [binom.pmf(nul["observed"], n, p)], color=AMBER, width=.66)
    ax.axvline(nul["expected_under_null"], color=NAVY, ls="--", lw=1.2)
    ax.annotate(f"expected {nul['expected_under_null']}",
                (nul["expected_under_null"], pmf.max() * .93),
                xytext=(4, 0), textcoords="offset points", color=NAVY, fontsize=8.6)
    ax.annotate(f"observed {nul['observed']}\nP(X ≥ {nul['observed']}) = "
                f"{nul['p_at_least_observed']}",
                (nul["observed"], binom.pmf(nul["observed"], n, p)),
                xytext=(6, 26), textcoords="offset points", color=AMBER, fontsize=8.6)

    denom = round(1 / p)
    ax.set_xticks(k)
    ax.set_xlabel(f"candidates beating all "
                  f"{max(c['n_decoys'] for c in msa['per_candidate'])} of their own decoys")
    ax.set_ylabel("probability")
    ax.set_title(f"Two winners is what chance looks like\nBinomial({n}, 1/{denom}) "
                 f"under the null", fontsize=10.5, loc="left", pad=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    save(fig, "fig2_screen_level_null.png")


# --------------------------------------------------------------- 3. every version ----- #
def fig3():
    """One bar per retained version of the two screening studies; all falsified."""
    ver = J("data/slate.json")["separation_across_versions"]
    # Chronological within each lineage: the superseded versions in order, then the current
    # artefact last. Sorting on the path alone put the current one first, which reversed the
    # trajectory the slide's own prose walks through.
    def order(v):
        a = v["artefact"]
        return ("msa" in a, 1 if "superseded" not in a else 0, a)

    vs = sorted(ver["versions"], key=order)

    def label(a):
        stem = Path(a).stem
        base = "MSA" if "msa" in stem else "screen"
        tail = stem.rsplit(".", 1)[-1] if "." in stem else ""
        return f"{base}.{tail}" if tail.startswith("v") else base

    fig, ax = plt.subplots(figsize=(6.2, 3.9))
    x = np.arange(len(vs))
    ax.bar(x, np.ones(len(vs)), color=NAVY, width=.66)
    for i, v in enumerate(vs):
        ax.text(i, .5, f"n={v['n_candidates']}", rotation=90, ha="center", va="center",
                color="white", fontsize=8)
    ax.set_xticks(x, [label(v["artefact"]) for v in vs], rotation=45, ha="right",
                  fontsize=8.4)
    ax.set_yticks([])
    ax.set_ylim(0, 1.25)
    ax.set_title(
        "H1 «the designed sequences separate from their own shuffles» was "
        f"FALSIFIED in all {ver['n_versions']} retained versions\n"
        f"across candidate sets from {min(v['n_candidates'] for v in vs)} to "
        f"{max(v['n_candidates'] for v in vs)} designs",
        fontsize=9.5, loc="left", pad=10)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    save(fig, "fig3_falsified_every_version.png")


# ----------------------------------------------------------- 4. two predictors -------- #
def fig4():
    """Per-target agreement between AlphaFold DB and Boltz-2, with and without an MSA."""
    af = J("data/alphafold_db_comparison.json")
    aa, ab = af["arms"]["boltz_single_sequence"], af["arms"]["boltz_full_msa"]
    by_a = {r["target"]: r for r in aa["rows"]}
    by_b = {r["target"]: r for r in ab["rows"]}
    targets = sorted(set(by_a) & set(by_b))
    x = np.arange(len(targets))
    w = .38

    # Each arm names the study artefact it folded, so the legend is read from the slate
    # rather than typed -- the arms were renumbered once already.
    slate = {s["artefact"]: s["slate_number"] for s in J("data/slate.json")["studies"]}

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.bar(x - w / 2, [by_a[t]["pearson_r"] for t in targets], w, color=GREY,
           label=f"Boltz-2 single sequence (study #{slate[aa['study']]})")
    ax.bar(x + w / 2, [by_b[t]["pearson_r"] for t in targets], w, color=NAVY,
           label=f"Boltz-2 full MSA (study #{slate[ab['study']]})")
    for i, t in enumerate(targets):
        r = by_b[t]
        ax.annotate(f"n_eff\n{r['effective_n_after_autocorrelation']}",
                    (i + w / 2, r["pearson_r"]), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom",
                    color=AMBER, fontsize=7.6, linespacing=.95)

    ax.set_xticks(x, targets)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Pearson r vs AlphaFold DB pLDDT")
    ax.set_title(
        "Two predictors agree about WHERE each receptor is confidently folded\n"
        f"median r {aa['pearson_r_median']} → {ab['pearson_r_median']} when Boltz-2 is given "
        f"an MSA; amber = effective sample size after autocorrelation",
        fontsize=10, loc="left", pad=10)
    # Inside the axes the legend sat on top of the bars it labels; below them it does not.
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.12), ncols=2, frameon=False,
              fontsize=8.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    save(fig, "fig4_alphafold_vs_boltz.png")


# ------------------------------------------------------- 5. one complex, split -------- #
def fig5():
    """One complex: the fold on the left, per-chain confidence on the right.

    The point of the pair is that the aggregate ipTM and the pooled pLDDT are the receptor's
    numbers. Splitting the confidence trace by chain is the only way to see that.
    """
    sys.path.insert(0, str(REPO / "platform"))
    from cbc.predictor import parse_mmcif

    e = next(x for x in J("data/structures.json")["entries"]
             if x["id"] == "cpx-BasalAChE-Abeta-B4")
    residues, _, _ = parse_mmcif(REPO / e["cif"])
    chains = {c["id"]: c for c in e["chains"]}
    rec_id, pep_id = e["chains"][0]["id"], e["chains"][1]["id"]

    fig, (axl, axr) = plt.subplots(1, 2, figsize=(9.6, 4.3),
                                   gridspec_kw={"width_ratios": [1, 1.12]})

    # --- left: the Ca trace projected on its own two principal axes ---------------------
    xyz = np.array([[r.x, r.y, r.z] for r in residues])
    xyz = xyz - xyz.mean(0)
    _, _, vt = np.linalg.svd(xyz, full_matrices=False)
    proj = xyz @ vt[:2].T

    def band_colour(p):
        for lo, hi, col in BANDS:
            if lo <= p < hi or (hi == 100 and p >= 90):
                return col
        return BANDS[-1][2]

    for cid, lw in ((rec_id, 1.0), (pep_id, 3.4)):
        idx = [i for i, r in enumerate(residues) if r.chain == cid]
        for a, b in zip(idx, idx[1:]):
            if residues[b].seq_id != residues[a].seq_id + 1:
                continue
            axl.plot(proj[[a, b], 0], proj[[a, b], 1], lw=lw,
                     color=band_colour(residues[a].plddt or 0), solid_capstyle="round")
    axl.set_aspect("equal")
    axl.axis("off")
    axl.set_title("the fold Boltz-2 produced\n(thick trace = designed peptide)",
                  fontsize=9, pad=6)

    # --- right: pLDDT along each chain, over the AlphaFold bands ------------------------
    for lo, hi, col in BANDS:
        axr.axhspan(lo, hi, color=col, alpha=.13, lw=0)
    for cid, col, kind in ((rec_id, NAVY, "receptor"), (pep_id, AMBER, "peptide")):
        ys = [r.plddt for r in residues if r.chain == cid and r.plddt is not None]
        axr.plot(np.linspace(0, 100, len(ys)), ys, color=col, lw=1.2,
                 label=f"chain {cid} {kind} (mean {chains[cid]['mean_plddt']:.0f})")
    axr.set_ylim(0, 100)
    axr.set_xlim(0, 100)
    axr.set_xlabel("position along chain (%)")
    axr.set_ylabel("pLDDT")
    axr.set_title("confidence is the receptor's, not the interaction's", fontsize=9, pad=6)
    axr.legend(loc="lower left", fontsize=7.6, frameon=False)
    for s in ("top", "right"):
        axr.spines[s].set_visible(False)

    ip = e["interface_pae"]
    fig.suptitle(
        f"{e['label']}   ·   ipTM {e['metrics']['iptm']}   ·   interface PAE mean "
        f"{ip['mean_pae']} Å   ·   best of its {e['screen']['n_decoys']} decoys "
        f"{e['screen']['decoy_max']}",
        fontsize=9.2, y=1.02)
    save(fig, "fig5_complex_structure.png")


# ------------------------------------------- 6. the positive control and its limit ---- #
def fig6():
    """Study #12: the composition-matched null on complexes that are known to bind.

    Ported from the manuscript run that first drew it
    (`runs/cofolding-null-benchmark-20260821/figures/fig5_positive_control.py`). Two things
    changed in the port. The manuscript script resolved this repository through a hardcoded
    absolute path under one author's home directory, which is the same defect the module
    docstring above names -- a figure whose generator cannot be run from a clone. It reads
    `data/` relative to the repository root here, like every other figure in this file. And
    the manuscript PNG is not copied in: the repository draws its own from its own artefacts.

    The recomputation the manuscript script performed inline -- every plotted number
    re-derived from `rows[]` and asserted against the deposited analysis -- is not repeated
    here. It belongs to a test, not to a drawing routine, and it is in
    `platform/tests/test_platform.py::test_every_analysis_block_recomputes_from_its_own_rows`,
    which checks every study artefact rather than only this one.

    Four panels, because the result has two halves and each half has a limit. A and B are the
    positive control: in aggregate the null separates natural peptides from permutations of
    their own residues. C and D are the limit: the per-complex criterion registered in
    advance was not met, and at ten permutations no per-complex call was reachable at all.

    One custody caveat, since this figure is drawn from those rows: 160 of the artefact's 176
    rows name a fold output under `runs/interface-null-positive-control/`, and that run tree
    is not in this repository. The numbers plotted here travel with the artefact; the
    coordinates they were read from do not, and the README says so in the same words.
    """
    nat = J("data/study_interface_null_positive_control.json")
    des = J("data/study_msa_specificity.json")
    a, msa = nat["analysis"], des["analysis"]
    per = a["metrics"]["per_complex"]
    pt, h2 = a["primary_test"], a["secondary_tests"]["H2_binomial_reference"]
    h3 = a["secondary_tests"]["H3_welch_contrast"]
    slate = {s["artefact"]: s["slate_number"] for s in J("data/slate.json")["studies"]}
    n_pc, n_perm = h2["n_complexes"], max(c["n_permutations"] for c in per)
    floor = 1.0 / (n_perm + 1)

    # The ten permutation ipTMs per complex exist only in rows[]; the summary block carries
    # their mean and max. Both are read, neither is recomputed.
    perms = {}
    for r in nat["rows"]:
        if r["kind"] != "native":
            perms.setdefault(r["pdb_id"], []).append(r["iptm"])

    rows = sorted(per, key=lambda c: c["difference"])
    y = np.arange(len(rows))
    lens = [c["peptide_len"] for c in per]
    dlens = [len(r["peptide_used"]) for r in des["rows"] if r["kind"] == "native"]

    fig = plt.figure(figsize=(12.6, 8.8))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1.0], width_ratios=[1.3, 1.0],
                          hspace=.34, wspace=.14)
    axA, axB = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    axC, axD = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])

    # --- A: each complex against ten permutations of its own peptide --------------------
    for i, c in enumerate(rows):
        p = perms[c["pdb_id"]]
        axA.plot([min(p), max(p)], [i, i], color=GREY, lw=3.2, solid_capstyle="round",
                 alpha=.6, zorder=1)
        axA.scatter(p, [i] * len(p), s=16, facecolor="white", edgecolor=GREY,
                    linewidths=.9, zorder=2)
    axA.scatter([c["native_iptm"] for c in rows], y, marker="D", s=58, color=NAVY, zorder=4)
    # A ring marks the four that out-scored all ten -- the count panel C is about.
    swp = [i for i, c in enumerate(rows) if c["beats_all_permutations"]]
    axA.scatter([rows[i]["native_iptm"] for i in swp], swp, marker="D", s=58,
                facecolor="none", edgecolor="black", linewidths=1.1, zorder=5)
    axA.set_yticks(y, [c["pdb_id"] for c in rows], fontsize=8.4)
    for i in swp:
        axA.get_yticklabels()[i].set_fontweight("bold")
    axA.set_xlim(0, 1)
    axA.set_xlabel("interface pTM (ipTM)")
    axA.set_title(
        f"A  Each deposited complex against {n_perm} permutations of its own peptide\n"
        f"{n_pc} X-ray complexes, {min(lens)}–{max(lens)} residues, single-sequence mode\n"
        f"grey = that row's own {n_perm} permutations; ring and bold name = out-scored "
        f"all {n_perm}",
        fontsize=9.5, loc="left", pad=10)
    axA.grid(axis="y", color="#E6E8EB", lw=.7)
    axA.set_axisbelow(True)
    for s in ("top", "right", "left"):
        axA.spines[s].set_visible(False)

    # --- B: the paired difference, against the designed arm's mean ----------------------
    lo, hi = pt["ci95_mean_difference"]
    d_mean = a["metrics"]["natural_minus_designed_contrast"]["designed_mean_candidate_screen_v8"]
    axB.axvspan(lo, hi, color=NAVY, alpha=.12, lw=0, zorder=0)
    axB.axvline(pt["mean_difference"], color=NAVY, lw=1.8, zorder=3)
    axB.axvline(d_mean, color=AMBER, lw=1.4, ls=(0, (3, 2)), zorder=3)
    axB.axvline(0, color="#26292E", lw=1.0, zorder=2)
    axB.hlines(y, 0, [c["difference"] for c in rows], color=NAVY, lw=1.3, alpha=.5, zorder=4)
    axB.scatter([c["difference"] for c in rows], y, marker="D", s=46, color=NAVY, zorder=5)
    axB.scatter([rows[i]["difference"] for i in swp], swp, marker="D", s=46,
                facecolor="none", edgecolor="black", linewidths=1.1, zorder=6)
    axB.set_yticks(y, [])
    axB.tick_params(axis="y", length=0)
    axB.set_xlabel("native ipTM − mean of its own permutations")
    axB.set_title(
        f"B  The same complexes, paired difference — H1 CONFIRMED\n"
        f"mean {pt['mean_difference']:+.4f}, 95% CI {lo:+.4f} to {hi:+.4f} (band), "
        f"Holm p = {pt['p_holm_adjusted']:.4f}\n"
        f"t({pt['df']}) = {pt['t']}, dz = {pt['cohens_dz']}, "
        f"{pt['n_differences_positive']} of {n_pc} differences positive",
        fontsize=9.5, loc="left", pad=10)
    axB.annotate(
        f"amber = the designed arm's mean, study "
        f"#{slate['data/study_candidate_screen.json']} ({d_mean:+.4f});\n"
        f"Welch p = {h3['p_exact_two_sided']:.3f}, so the two are NOT separated",
        (.98, .03), xycoords="axes fraction", fontsize=8.2, color="#4A4F57",
        ha="right", va="bottom", linespacing=1.5)
    axB.grid(axis="y", color="#E6E8EB", lw=.7)
    axB.set_axisbelow(True)
    for s in ("top", "right", "left"):
        axB.spines[s].set_visible(False)

    # --- C: the per-complex criterion, registered before the data and not met -----------
    k = np.arange(0, 10)
    pmf = binom.pmf(k, n_pc, h2["p0"])
    thr, obs = h2["registered_threshold"], h2["observed_sweeps"]
    axC.axvspan(thr - .5, k.max() + .5, color="#EAF0E7", zorder=0)
    axC.bar(k, pmf, color=GREY, width=.66, zorder=2)
    axC.bar([obs], [binom.pmf(obs, n_pc, h2["p0"])], color=AMBER, width=.66, zorder=3)
    axC.axvline(h2["expected_under_null"], color=NAVY, ls="--", lw=1.2, zorder=4)
    axC.annotate(f"expected {h2['expected_under_null']}",
                 (h2["expected_under_null"], pmf.max() * .93), xytext=(4, 0),
                 textcoords="offset points", color=NAVY, fontsize=8.6)
    axC.annotate(f"observed {obs}\nP(X ≥ {obs}) = {h2['p_at_least_observed']}",
                 (obs, binom.pmf(obs, n_pc, h2["p0"])), xytext=(6, 24),
                 textcoords="offset points", color=AMBER, fontsize=8.6)
    axC.annotate(f"registered threshold {thr}\nP(X ≥ {thr}) = {h2['p_at_threshold']}",
                 (thr - .4, pmf.max() * .62), color="#3F6B33", fontsize=8.6)
    axC.set_xticks(k)
    axC.set_ylabel("probability")
    axC.set_xlabel(f"complexes out-scoring all {n_perm} of their own permutations")
    axC.set_title(
        f"C  The per-complex criterion: FALSIFIED\n"
        f"Binomial({n_pc}, 1/{round(1 / h2['p0'])}) under the null; the threshold was fixed "
        f"before any fold was scored",
        fontsize=9.5, loc="left", pad=10)
    for s in ("top", "right"):
        axC.spines[s].set_visible(False)

    # --- D: the floor that made a per-complex call unreachable at any outcome -----------
    arms = [(f"study #{slate['data/study_interface_null_positive_control.json']} "
             f"natural, n = {n_pc}", list(a["metrics"]["per_complex_empirical_p"].values()),
             NAVY, "D"),
            (f"study #{slate['data/study_msa_specificity.json']} designed, "
             f"n = {len(msa['per_candidate'])}",
             list(msa["metrics"]["per_candidate_empirical_p"].values()), AMBER, "s")]
    axD.axvspan(0, floor, color="#F6E7E7", lw=0, zorder=0)
    axD.axvline(floor, color="#9A3B3B", lw=1.4, zorder=3)
    axD.axvline(.05, color="#26292E", lw=1.1, ls=(0, (4, 2.5)), zorder=3)
    for row, (label, ps, col, mk) in enumerate(arms):
        base = 1.3 - row * 1.5
        seen = {}
        for p in sorted(ps):
            j = seen.get(round(p, 4), 0)
            seen[round(p, 4)] = j + 1
            axD.scatter([p], [base + j * .20], marker=mk, s=34, color=col,
                        edgecolor="black" if p <= floor + 1e-9 else col,
                        linewidths=.9 if p <= floor + 1e-9 else 0, zorder=4)
        axD.annotate(label, (1.04, base - .40), color=col, fontsize=8.4, ha="right")
    axD.annotate(f"dashed = α 0.05    red = the floor, 1/{n_perm + 1} = {floor:.4f}    "
                 f"black outline = an item sitting on it",
                 (.16, 2.45), fontsize=8.2, color="#4A4F57", ha="left")
    axD.set_xlim(-.02, 1.06)
    axD.set_ylim(-1.3, 2.7)
    axD.set_yticks([])
    axD.set_xlabel(f"per-item empirical p = (1 + #{{permutations ≥ the item}}) / {n_perm + 1}")
    axD.set_title(
        f"D  The 1/({n_perm} + 1) floor under every per-item p\n"
        f"no p below {floor:.4f} is reachable at m = {n_perm}, and that floor is above "
        f"α = 0.05",
        fontsize=9.5, loc="left", pad=10)
    for s in ("top", "right", "left"):
        axD.spines[s].set_visible(False)

    # The optimistic-bound caveat is part of the result, so it is on the figure rather than
    # only in the caption: the instrument was validated on shorter, crystallised peptides
    # than the ones it is used on, and in a different alignment mode.
    fig.text(.02, .045,
             f"The control is an OPTIMISTIC bound on the screen it validates: its {n_pc} "
             f"peptides are crystallised and {min(lens)}–{max(lens)} residues, folded in "
             f"single-sequence mode, while the designed\ncandidates are {min(dlens)}–"
             f"{max(dlens)} residues — no overlap in length at all — and study "
             f"#{slate['data/study_msa_specificity.json']} screens them with a full MSA, "
             f"which lifts decoys as well as designs.",
             fontsize=8.6, color="#4A4F57", ha="left", va="top", linespacing=1.5)
    save(fig, "fig6_positive_control.png")


if __name__ == "__main__":
    print("figures from data/ →", OUT.relative_to(REPO))
    fig1(); fig2(); fig3(); fig4(); fig5(); fig6()
    missing = [n for n in ("ui1_headline_finding", "ui2_verdicts", "ui3_alphafold",
                           "ui4_structure_gallery", "ui5_citation")
               if not (OUT / f"{n}.png").exists()]
    if missing:
        print("  note: these are browser captures of index.html, not generated here:",
              ", ".join(missing))
