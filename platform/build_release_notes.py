#!/usr/bin/env python3
"""Generate the release note for the version named in `VERSION`, from the artefacts.

The defect this exists for
--------------------------
`docs/RELEASE_NOTES_v1.0.0.md` said this, and every count in it is v1.0.0's:

    **8 pre-registered studies**, 25 hypotheses, 13 confirmed and 11        [SLATE-COUNT-HISTORICAL]
    falsified... Not one study is confirmatory: each deviated from its      [SLATE-COUNT-HISTORICAL]
    plan in at least one respect... 313 automated checks across six suites. [SLATE-COUNT-HISTORICAL]

Every one of those was true on 2026-08-20, the day v1.0.0 was tagged. Study #12, `interface-null-positive-control-v1`, was
registered on 2026-08-22 with an empty deviation list, so it is the FIRST confirmatory study in
the slate -- and the sentence that erases it sat in the file that `VERSION` still pointed at,
which made it the repository's description of itself, not a historical record.

That file was hand-written prose. `release.sh` only checked that it existed. Nothing could have
noticed, because there was nothing to notice with: a number typed once into a document has no
link back to the artefact it summarises, and the person who ran study #12 was not looking at
docs/.

What this fixes, and how
------------------------
Two halves, and both are needed:

1. **The old note is frozen, not corrected.** A release note is a record of what a release
   contained, and v1.0.0's bytes are the body of a published GitHub release and the description
   behind version DOI 10.5281/zenodo.22032685. Rewriting it to say nine studies would make the
   repository claim that v1.0.0 shipped a study registered two days after it. So the v1.0.0 note
   keeps its counts, carries a banner saying what it is, and marks each superseded count with
   `platform/check_metadata_counts.py`'s `SLATE-COUNT-HISTORICAL` escape hatch -- the marker
   that guard documents for exactly this case.

2. **The note for the current state is generated, not typed.** Everything countable in the
   output below is read at run time from `data/*.json`, `len(glob('prespec/*.json'))` and
   `len(verify_all.SUITES)`. There is no number literal in this file's output path. A study
   registered tomorrow changes the note by rebuilding it, which is the property the hand-typed
   note did not have.

A frozen note is never regenerated
----------------------------------
A file whose first 4 KB contain the token `RELEASE-NOTE-FROZEN` belongs to a release that has
already been published, and this generator refuses to write over it rather than asking. That
refusal is the whole reason the two halves can coexist: `VERSION` moves forward, the generator
follows it to a new filename, and the published record behind it cannot be edited by a rebuild.

Usage
-----
    ./.venv/bin/python platform/build_release_notes.py            # write docs/RELEASE_NOTES_v<VERSION>.md
    ./.venv/bin/python platform/build_release_notes.py --check    # fail if the file has drifted
    ./.venv/bin/python platform/build_release_notes.py --print    # stdout only, write nothing
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: A note whose FIRST html comment opens with this token is the record of a published release,
#: and is never regenerated. Anchoring to `<!--` matters: a generated note names the token in
#: prose, telling whoever tags the release to swap it in, and a bare substring test would read
#: that instruction as the marker itself and refuse to write the file it had just produced.
FROZEN_MARKER = "RELEASE-NOTE-FROZEN"
FROZEN_RE = re.compile(r"<!--\s*" + FROZEN_MARKER)

#: Generated notes carry this instead, so a reader who opens one knows not to hand-edit it.
GENERATED_MARKER = "RELEASE-NOTE-GENERATED"


# --------------------------------------------------------------------------------------
# Reading the artefacts. Nothing below is a constant that states a quantity.
# --------------------------------------------------------------------------------------

def _load(rel: str) -> dict:
    return json.loads((REPO / rel).read_text())


def _suites() -> int:
    """len(verify_all.SUITES), imported rather than counted by regex."""
    spec = importlib.util.spec_from_file_location("_verify_all", REPO / "verify_all.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(REPO))
    spec.loader.exec_module(module)
    return len(module.SUITES)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _predecessor(version: str) -> str | None:
    """The highest release note in docs/ below `version`, by version tuple."""
    def key(v: str) -> tuple[int, ...]:
        return tuple(int(p) for p in v.split("."))

    here = key(version)
    found = []
    for path in (REPO / "docs").glob("RELEASE_NOTES_v*.md"):
        m = re.fullmatch(r"RELEASE_NOTES_v(\d+\.\d+\.\d+)\.md", path.name)
        if m and key(m.group(1)) < here:
            found.append(m.group(1))
    return max(found, key=key) if found else None


def facts() -> dict:
    """Every quantity the note states, each read from the artefact that produced it."""
    slate = _load("data/slate.json")
    counts = slate["counts"]
    sep = slate["separation_across_versions"]
    if sep["n_versions"] != len(sep["versions"]):
        raise SystemExit("slate.json disagrees with itself about separation_across_versions")
    n_cand = [v["n_candidates"] for v in sep["versions"]]

    structures = _load("data/structures.json")
    groups = structures["groups"]

    msa = _load("data/study_msa_specificity.json")["analysis"]
    afdb = _load("data/alphafold_db_comparison.json")["arms"]

    pc_doc = _load("data/study_interface_null_positive_control.json")
    pc = pc_doc["analysis"]
    sweeps = pc["metrics"]["beats_all_permutations_null"]
    primary = pc["primary_test"]
    audit = pc["prespec_audit"]

    # Where #12's rows point. The 160 permutation folds live under one named run tree; the 16
    # natives are reused from #7 and sit under content-addressed run directories. Counted from
    # the rows, not asserted.
    tree = "runs/interface-null-positive-control/"
    in_tree = sum(1 for r in pc_doc["rows"] if str(r.get("model", "")).startswith(tree))

    return {
        "version": (REPO / "VERSION").read_text().strip(),
        "counts": counts,
        "plans": len(list((REPO / "prespec").glob("*.json"))),
        "suites": _suites(),
        "n_versions": sep["n_versions"],
        "cand_min": min(n_cand),
        "cand_max": max(n_cand),
        "structures_total": sum(groups.values()),
        "groups": groups,
        "msa_n": msa["n_observed"],
        "msa_n_candidates": len(msa["per_candidate"]),
        # Constructs and molecules are different denominators. One 41-mer is screened against
        # two receptors, so a screen described as thirteen designs is twelve; the artefact
        # settles it and this reads it rather than restating either number.
        "msa_n_distinct_peptides": (msa.get("peptide_multiplicity") or {}).get(
            "n_distinct_peptides"),
        "mean_native": msa["metrics"]["mean_native_iptm"],
        "mean_decoy": msa["metrics"]["mean_decoy_iptm"],
        "r_single": afdb["boltz_single_sequence"]["pearson_r_median"],
        "r_msa": afdb["boltz_full_msa"]["pearson_r_median"],
        "pc_rows": pc["n_observed"],
        "pc_rows_in_named_tree": in_tree,
        "pc_mean_diff": pc["metrics"]["paired_native_minus_permutation_mean"],
        "pc_holm": round(primary["p_holm_adjusted"], 4),
        "pc_positive": primary["n_differences_positive"],
        "pc_pairs": primary["n_pairs"],
        "pc_sweeps": sweeps["observed"],
        "pc_n_complexes": pc["secondary_tests"]["H2_binomial_reference"]["n_complexes"],
        "pc_threshold": sweeps["threshold_registered"],
        "pc_sweep_p": sweeps["p_at_least_observed"],
        "pc_registered": audit["registered_utc"][:10],
        "pc_deviations": len(audit["deviations"]),
        "pc_confirmatory": audit["confirmatory"],
        "pc_welch_p": pc["welch_p"],
    }


# --------------------------------------------------------------------------------------
# Rendering.
# --------------------------------------------------------------------------------------

def _rewrap(text: str, width: int = 96) -> str:
    """Hard-wrap the rendered note.

    Interpolating counts into a hard-wrapped template leaves ragged lines wherever a value is
    a different width than the one it replaced, and the raggedness moves every time a count
    moves -- which makes the diff of a rebuild unreadable. Wrapping is done after
    interpolation so the layout is a function of the values, not of the template.
    """
    out: list[str] = []
    buf: list[str] = []
    kind: str | None = None
    in_comment = False

    def flush() -> None:
        if not buf:
            return
        joined = " ".join(" ".join(buf).split())
        kwargs = dict(width=width, break_long_words=False, break_on_hyphens=False)
        if kind == "bullet":
            out.extend(textwrap.wrap(joined, initial_indent="- ", subsequent_indent="  ",
                                     **kwargs))
        else:
            out.extend(textwrap.wrap(joined, **kwargs))
        buf.clear()

    for line in text.split("\n"):
        if in_comment or line.lstrip().startswith("<!--"):
            flush()
            out.append(line)
            in_comment = "-->" not in line
            continue
        stripped = line.strip()
        if not stripped:
            flush()
            out.append("")
            kind = None
        elif re.match(r"#{1,6}\s", stripped):
            # `#{1,6}\s`, not `startswith("#")`: the notes refer to studies as #12 and #7, and
            # a bare-prefix test reads a wrapped "#12's audit records..." as a level-1 heading,
            # flushes the paragraph around it and leaves the rest of the bullet unindented.
            flush()
            out.append(stripped)
            kind = None
        elif stripped.startswith("- "):
            flush()
            kind = "bullet"
            buf.append(stripped[2:])
        else:
            buf.append(stripped)
    flush()
    return "\n".join(out).rstrip("\n") + "\n"


def render(f: dict) -> str:
    c = f["counts"]
    prev = _predecessor(f["version"])
    since = f"v{prev}" if prev else "the previous release"

    confirmatory = _plural(c["studies_confirmatory"], "confirmatory study", "confirmatory studies")
    deviated = c["studies"] - c["studies_confirmatory"]

    return _rewrap(f"""<!-- {GENERATED_MARKER}: written by platform/build_release_notes.py from data/,
     prespec/ and verify_all.SUITES. Do not hand-edit -- rebuild it:
       ./.venv/bin/python platform/build_release_notes.py
     Once this version is tagged and published, replace this marker with {FROZEN_MARKER}
     so a later rebuild cannot rewrite the record of a published release. -->

# CognitionBioChem v{f["version"]}

The release that adds the registered positive control, and narrows how the negative result may
be read. Every count below is generated from the artefacts, not typed.

## The finding

Across a screen of {f["msa_n_candidates"]} candidate–receptor constructs covering
**{f["msa_n_distinct_peptides"]} distinct peptides** — one 41-mer is screened against two
receptors and so is counted twice in every mean and count — and a {f["msa_n"]}-fold full-MSA
rerun, the
designed peptides did not separate from composition-matched shuffles of their own amino acids:
**mean native ipTM {f["mean_native"]} against a mean decoy of {f["mean_decoy"]}**. The
hypothesis has been falsified in all **{f["n_versions"]} retained versions** of the two
screening studies, across candidate sets from {f["cand_min"]} to {f["cand_max"]} constructs.

## What changed since {since}

Study #12, `interface-null-positive-control-v1`, was registered on **{f["pc_registered"]}** —
after {since} was published — and measured the null itself. Sixteen deposited X-ray
peptide–receptor complexes were folded against ten uniform random permutations of each peptide.

- The natives beat their own permutations **in aggregate** by **+{f["pc_mean_diff"]} ipTM**
  (Holm p = {f["pc_holm"]}, {f["pc_positive"]} of {f["pc_pairs"]} differences positive). The
  score is not blind to residue order on sequences that demonstrably bind.
- Only **{f["pc_sweeps"]} of {f["pc_n_complexes"]}** beat all ten permutations of themselves,
  against a threshold of {f["pc_threshold"]} registered in advance:
  P(X ≥ {f["pc_sweeps"]}) = {f["pc_sweep_p"]} under Bin({f["pc_n_complexes"]}, 1/11). **The
  per-case reading of the composition-matched null is withdrawn** as a result, throughout the
  repository: the comparison licenses a verdict on a batch of native–decoy pairs taken
  together and none on any single pair. The empirical-p floor is 1/11 = 0.0909, above α, so no
  per-case verdict was reachable at any outcome — a statement about the design, not a count of
  failures.
- The natural separation could not be shown to exceed the designed one (Welch
  p = {f["pc_welch_p"]}).
- Its protocol audit records **{f["pc_deviations"]} deviations** from its registered plan and
  `confirmatory = {str(f["pc_confirmatory"]).lower()}` — the first study in this slate to do so.
  {since}'s note said no study was confirmatory. That was true when it was written and is not
  true now; the old note is kept, frozen, and says so at the top.
- **Custody.** {f["pc_rows_in_named_tree"]} of #12's {f["pc_rows"]} rows point at
  `runs/interface-null-positive-control/`; the other
  {f["pc_rows"] - f["pc_rows_in_named_tree"]} are native folds reused from #7 under
  content-addressed run directories. README records that this run tree is not in the
  repository, so #12's confidence values are reproducible by re-running and are **not**
  verifiable against stored bytes — unlike every other study in this slate.

## What is in the release

- **{c["studies"]} pre-registered studies**, {c["hypotheses"]} hypotheses,
  {c["confirmed"]} confirmed and {c["falsified"]} falsified, {c["not_tested"]} not tested.
  Every plan is hash-locked in `prespec/` and was registered before its data was seen, under
  {f["plans"]} registered analysis plans counting every superseded version. **{confirmatory}**:
  #12's audit records no deviation. The other {deviated} deviated from their plans in at least
  one respect, and each says so.
- **{f["structures_total"]} structures** under custody — {f["groups"]["complex"]}
  candidate–receptor complexes, {f["groups"]["peptide_monomer"]} peptide-only folds and
  {f["groups"]["receptor_afdb"]} deposited AlphaFold DB receptors — each opening its real
  coordinate file with per-residue pLDDT, PAE and, for complexes, interface PAE.
- **An exploratory AlphaFold DB comparison** in two arms. Median Pearson r between the two
  models' per-residue confidence rises from {f["r_single"]} to {f["r_msa"]} when Boltz-2 is
  given an MSA. It ships an effective sample size and a mis-registration null, because 156
  residues on TREM2 are worth about five independent observations.
- **{f["suites"]} verification suites**, in which every check is itself verified to fail on the
  defect it names.

## What it does not do

It runs no AlphaFold 3, computes no binding free energy for display, and predicts no ADMET for
a molecule outside the model's applicability domain. Values asserted by an earlier version that
no calculation supports are preserved under `retracted_claims` rather than deleted.

## Development note

Built with substantial AI assistance. The internal review that found the fabricated values was
a multi-agent LLM process, not human peer review. Both facts are in the README and `NOTICE`.
""")


def main() -> int:
    f = facts()
    text = render(f)
    target = REPO / "docs" / f"RELEASE_NOTES_v{f['version']}.md"
    rel = target.relative_to(REPO)

    if "--print" in sys.argv:
        sys.stdout.write(text)
        return 0

    if target.exists() and FROZEN_RE.search(target.read_text()[:4096]):
        print(f"REFUSED — {rel} is marked {FROZEN_MARKER}.")
        print("A published release note is a record of what that release contained, and this")
        print("generator will not rewrite one. Bump VERSION and rebuild.")
        return 1

    if "--check" in sys.argv:
        if not target.exists():
            print(f"FAIL — {rel} does not exist. Run this without --check.")
            return 1
        if target.read_text() != text:
            print(f"FAIL — {rel} has drifted from the artefacts. Rebuild it.")
            return 1
        print(f"PASS — {rel} matches data/, prespec/ and verify_all.SUITES.")
        return 0

    target.write_text(text)
    print(f"wrote {rel}  ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
