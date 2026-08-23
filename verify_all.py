#!/usr/bin/env python3
"""Run every check in the repository and summarize.

    python3 verify_all.py

Exits non-zero if any suite fails. Note the deliberate inversion for the data gate:
`platform/validate.py` is *expected* to exit non-zero on the legacy dataset, because that
dataset genuinely violates the contract. A gate that passed on it would be the bug.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
VENV = REPO / ".venv" / "bin" / "python"
PY = str(VENV) if VENV.exists() else sys.executable

#: (name, argv, expected_exit, what the suite covers).
#: The blurbs say what a suite EXAMINES, never how many checks it contains or how many
#: violations it found. Those counts used to be written out here by hand, and they went
#: stale the moment the project improved: this file claimed "109 checks" against 121, and
#: "124 violations ... 45 residue identities" after the residue-attribution fix had already
#: brought those to 102 and 23. A summary that has to be edited whenever the thing it
#: summarises changes will eventually lie. The counts are now read back from each suite's
#: own output, so they cannot disagree with it.
SUITES = [
    # This ran under sys.executable while every other suite ran under the project venv. On
    # a clean checkout that follows the README, sys.executable has no numpy, so the FIRST
    # suite died at import and the documented "run everything" command reported FAIL.
    ("Memory ledger regression suite", [PY, "memory/tests/test_mem.py"], 0,
     "16-writer concurrency, idempotency, torn-tail recovery, and one test "
     "per flaw the three critics found in the rejected v1 spec"),
    ("Platform regression suite", [PY, "platform/tests/test_platform.py"], 0,
     "thermodynamics, peptide properties, RDKit validation, provenance enforcement, "
     "predictor parsing, stale-artifact detection, and numbering-convention resolution"),
    ("Front-end contract verification", [PY, "platform/verify_frontend.py"], 0,
     "DOM contract, data contract, fabricated-renderer removal, resource lifecycle"),
    ("Data-integrity gate (expected to FAIL on legacy data)",
     [PY, "platform/validate.py"], 1,
     "the legacy dataset genuinely violates the contract; residue identities are "
     "resolved live against the UniProt registry"),
    ("Dataset build + provenance audit", [PY, "platform/build_dataset.py"], 0,
     "every numeric value carries a provenance record"),
    ("Naming guard (pooled potency must not be rendered as free energy)",
     [PY, "platform/check_naming.py"], 0,
     "no code path converts affinity_pred_value into kcal/mol or names it an apparent dG"),
    # RESOLVED, AND RECORDED SO THE HOLE IS NOT MISTAKEN FOR AN OVERSIGHT. Two entries stood
    # here: check_reports.py, which held the English and Korean report editions to each
    # other, and check_paper.py, which bound every numeral in the manuscript to an artefact.
    # Both were guards over prose this repository no longer publishes -- the prose, the six
    # generators that rendered it and these two guards are all untracked and ignored (see the
    # block at the end of .gitignore). They ran green for the author, whose working copy has
    # them, and in a CLONE the files are absent, python exits 2, no evidence line is printed,
    # and this command reported two FAILs. A suite that can only pass on one machine is not a
    # suite this file should list.
    #
    # Removing them lowered len(SUITES) from twelve to ten, and check_metadata_counts.py
    # binds that number to every sentence that states a suite count, so this was done as the
    # one change the note at the bottom of this list prescribes: the two entries and their
    # EVIDENCE keys dropped, the README badge, the README Quick start line and the
    # .zenodo.json clause corrected, docs/RELEASE_NOTES_v<VERSION>.md rebuilt with
    # platform/build_release_notes.py, and check_metadata_counts.py confirmed still exiting 0.
    #
    # The two guards over the mechanism that produced this repository's misleading claims:
    # a finding is minted once, fans out across dozens of surfaces, is later withdrawn by a
    # measurement made inside this same repository, and survives on every surface the person
    # making the correction was not looking at. Neither guard asks whether a sentence is
    # true. Each asks whether it still agrees with the artefacts, which is the half that
    # failed all nine times.
    ("Retraction guard (a withdrawn claim never travels without its withdrawal)",
     [PY, "platform/check_retractions.py"], 0,
     "every public surface against retractions.jsonl -- README, the page, the citable "
     "metadata, data/ prose fields, docs/*.md, paper/ where it exists, module docstrings, "
     "the generated ledger views -- plus the joins the ledger requires on the page; "
     "prespec/, data/superseded/ and memory/ledger/ are exempt AS FILES"),
    ("Metadata count guard (hand-typed slate counts equal the artefacts)",
     [PY, "platform/check_metadata_counts.py"], 0,
     "every count typed beside studies, hypotheses, plans, suites, candidates or a verdict "
     "total, in numerals AND in number-words AND as nouns, bound to data/slate.json, "
     "len(glob('prespec/*.json')) and len(SUITES) in this file -- and, separately, every "
     "text file in the tree classified as either a watched surface or a named exemption, "
     "because the three counts that went stale here did so on files nobody had decided "
     "about"),
    # The third guard over the same mechanism, one field further out. The two above hold what
    # the repository SAYS about its work to the artefacts. This one holds what it says about
    # ITSELF -- the version a reader is told to cite -- to VERSION and to what has actually
    # been published. Ten stamps across six files read 1.0.0 while VERSION read 1.1.0, and
    # release.sh's only version check compares VERSION to the argument you type, so
    # `./release.sh 1.1.0` passed every gate above and would have published a tag whose
    # citable record said 1.0.0.
    ("Version stamp guard (every stamp names the version it is about)",
     [PY, "platform/check_version_stamps.py"], 0,
     "every stamp describing this tree equals VERSION; every reference pinned to a "
     "published deposit -- a version DOI, a tag URL, a release tarball -- names a release "
     "that exists and is never relabelled to follow VERSION"),
    # Listed last because it runs the three guards above some seventy times, against scratch
    # copies of this repository with a defect planted in each. It is the answer to the
    # question those three entries cannot answer about themselves: a green line is
    # indistinguishable from a green line, and the prose guard that used to sit in this list
    # reported 10 passed / 0 failed on a manuscript whose slate counts were a month out of
    # date. On its first run it found that the retraction guard could not fail on a Word or
    # PowerPoint file -- the whole document was collapsed to one line, so the word
    # "retracted" anywhere in it acknowledged every withdrawn claim in it, and the rendered
    # manuscript is exactly where one of the nine was hiding. Those documents are no longer
    # published and no longer watched; the finding is kept because it is why the reader in
    # check_retractions.py splits on paragraphs.
    ("Mutation suite (each guard proven able to fail, on every surface it watches)",
     [PY, "platform/tools/mutation_suite.py"], 0,
     "plants the defect each guard exists to catch in a scratch copy and requires the guard "
     "to fail on it and to name the file; slots are enumerated from the guards' own surface "
     "lists, so a surface added without a mutation reports UNCOVERED rather than passing"),
    #
    # A NOTE ON ADDING AN ENTRY HERE, which is not a one-line edit any more.
    #
    # check_metadata_counts.py reads len(SUITES) from this list and binds it to every
    # sentence that states a suite count -- the README badge, the "N suites." line in the
    # Quick start, the "N verification suites" clause in .zenodo.json, and the generated
    # release note. The counts are not repeated here: a note that names them is one more
    # surface to go stale, and this one already had, saying "Eleven"/"11" against a list of
    # twelve. Append an entry without correcting the real surfaces and the guard fails on the
    # commit that added the suite, which is the intended behaviour and is why the count is
    # bound rather than typed.
    # Do it as one change: append the entry, correct the surfaces, rebuild
    # docs/RELEASE_NOTES_v<VERSION>.md with platform/build_release_notes.py, and confirm
    # `./.venv/bin/python platform/check_metadata_counts.py` still exits 0.
]

#: What each suite must PRINT for its exit code to be believed.
#:
#: An exit code alone cannot separate a suite that failed from one that crashed, because
#: Python also exits 1 on an uncaught exception. That is harmless for every suite whose
#: success is exit 0 -- a crash gives 1 and mismatches -- but the data gate's success IS
#: exit 1, so corrupting an input it reads made it die at import and this file printed
#: "[PASS] Data-integrity gate (expected to FAIL on legacy data) · exit 1 (expected 1)".
#: The gate's own violation line was already being parsed for display; it just was not
#: required. Now every suite must show its own summary, and a crash cannot impersonate one.
EVIDENCE = {
    "Memory ledger regression suite": re.compile(r"^\d+ passed, \d+ failed", re.M),
    "Platform regression suite": re.compile(r"^\d+ passed, \d+ failed", re.M),
    "Front-end contract verification": re.compile(r"^\d+ passed, \d+ failed", re.M),
    "Data-integrity gate (expected to FAIL on legacy data)":
        re.compile(r"^FAIL — \d+ violations across \d+ categories", re.M),
    "Dataset build + provenance audit": re.compile(r"PROVENANCE AUDIT:", re.M),
    "Naming guard (pooled potency must not be rendered as free energy)":
        re.compile(r"^PASS — no code path converts", re.M),
    # The scale line, not the verdict line: it is printed on both the passing and the failing
    # path, so a crash cannot impersonate either one.
    "Retraction guard (a withdrawn claim never travels without its withdrawal)":
        re.compile(r"^\d+ withdrawn claim\(s\) · \d+ surface\(s\) scanned", re.M),
    "Metadata count guard (hand-typed slate counts equal the artefacts)":
        re.compile(r"^\d+ count claim\(s\) bound across \d+ surface\(s\)", re.M),
    # The scale line again, not the verdict: printed on both paths, so a crash at import
    # cannot impersonate either one.
    "Version stamp guard (every stamp names the version it is about)":
        re.compile(r"^\d+ identity stamp\(s\) and \d+ pinned reference\(s\) checked",
                   re.M),
    "Mutation suite (each guard proven able to fail, on every surface it watches)":
        re.compile(r"^\d+ caught, \d+ survived", re.M),
}

#: (pattern, how to say what it counted). Each recovers a suite's own self-reported scale
#: from its output; none of them is asserted here, because a number typed into this file is
#: the same fan-out the retraction ledger exists to stop.
SCALE = (
    (re.compile(r"^(\d+) passed, (\d+) failed", re.M),
     lambda m: f"{int(m.group(1)) + int(m.group(2))} checks"),
    (re.compile(r"^FAIL — (\d+) violations across (\d+) categories", re.M),
     lambda m: f"{m.group(1)} violations across {m.group(2)} categories"),
    (re.compile(r"^(\d+) withdrawn claim\(s\) · (\d+) surface\(s\) scanned", re.M),
     lambda m: f"{m.group(2)} surfaces against {m.group(1)} withdrawn claims"),
    # One pattern spanning both of the count guard's scale lines, because `measured_scale`
    # returns the FIRST entry that matches and a second entry for the coverage line would
    # therefore never be reached. The two numbers are the two halves of that guard -- what it
    # bound, and how much of the tree it decided about -- and printing only the first is how
    # a reader concludes that 54 surfaces is the whole repository.
    (re.compile(r"^(\d+) count claim\(s\) bound across (\d+) surface\(s\)\n"
                r"(\d+) text file\(s\) classified: (\d+) watched, (\d+) exempted",
                re.M),
     lambda m: f"{m.group(1)} counts bound across {m.group(2)} surfaces · "
               f"{m.group(3)} text files classified, {m.group(5)} exempted by name"),
    (re.compile(r"^(\d+) identity stamp\(s\) and (\d+) pinned reference\(s\) checked "
                r"across (\d+) surface\(s\)", re.M),
     lambda m: f"{int(m.group(1)) + int(m.group(2))} version stamps across "
               f"{m.group(3)} surfaces"),
    (re.compile(r"^(\d+) caught, (\d+) survived", re.M),
     lambda m: f"{int(m.group(1)) + int(m.group(2))} mutations planted"),
)


def measured_scale(out: str) -> str:
    """The suite's own count, read from what it printed. Never asserted independently."""
    for pattern, say in SCALE:
        m = pattern.search(out)
        if m:
            return say(m)
    return ""

def main() -> int:
    print("=" * 78)
    print("CognitionBioChem — full verification")
    print("=" * 78)
    results = []
    for name, cmd, expected, blurb in SUITES:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        dt = time.time() - t0
        out = r.stdout + r.stderr
        scale = measured_scale(out)
        evidence = EVIDENCE[name].search(out) is not None
        # An exit code alone cannot tell a suite that FAILED from one that CRASHED: Python
        # exits 1 on an uncaught exception too, and the one suite here whose success IS exit 1
        # therefore reported PASS when a corrupt input made the gate die at import. Demanding
        # the suite's own summary line closes that: a crashed run prints no scale, so it can
        # no longer impersonate the expected failure. The suites expecting 0 are not
        # vulnerable (a crash gives 1, which already mismatches) but are held to the same rule
        # so that a silently empty run cannot pass either. No count is written here on
        # purpose: this comment named "five" while SUITES held twelve, eleven of them
        # expecting 0, and nothing was scanning this file for slate counts at the time.
        ok = r.returncode == expected and evidence
        results.append((name, ok, r.returncode, expected, dt, blurb, r, scale))
        mark = "PASS" if ok else "FAIL"
        print(f"\n[{mark}] {name}")
        out = r.stdout + r.stderr
        scale = measured_scale(out)
        evidence = EVIDENCE[name].search(out) is not None
        print(f"       exit {r.returncode} (expected {expected})  ·  {dt:.1f}s"
              + ("" if evidence else "  ·  the suite printed no summary of its own, "
                                        "which is what a crash looks like"))
        print(f"       {scale + ' — ' if scale else ''}{blurb}")
        if not ok:
            tail = (r.stdout + r.stderr).strip().splitlines()[-15:]
            for line in tail:
                print("       | " + line)

    print("\n" + "=" * 78)
    failed = [r for r in results if not r[1]]
    if failed:
        print(f"{len(results) - len(failed)}/{len(results)} suites OK — "
              f"{len(failed)} FAILED")
        for f in failed:
            print("  -", f[0])
    else:
        print(f"ALL {len(results)} SUITES OK")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
