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
    # This ran under sys.executable while the other five ran under the project venv. On a
    # clean checkout that follows the README, sys.executable has no numpy, so the FIRST of
    # six suites died at import and the documented "run everything" command reported FAIL.
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
    # Not in the platform suite: both report generators run that suite to take their check
    # count from it, so a check there comparing the two finished editions is circular.
    ("Report editions agree (English vs Korean)",
     [PY, "platform/check_reports.py"], 0,
     "the two editions describe the same work; no number stated in English is missing "
     "from the Korean"),
    # The prose guard was written and then left out of this list, so the command
    # the README calls "run everything" ran everything except the check on the longest
    # document in the repository. It walks data/ directly rather than trusting the fact sheet
    # the drafters worked from, which is the reason it belongs here and not in a build script.
    ("Prose-to-artefact numeric provenance",
     [PY, "platform/check_paper.py"], 0,
     "every numeral the paper states about this study traces to an artefact or to "
     "arithmetic on one; the two editions agree on numbers, citations and figures"),
]

#: What each suite must PRINT for its exit code to be believed.
#:
#: An exit code alone cannot separate a suite that failed from one that crashed, because
#: Python also exits 1 on an uncaught exception. That is harmless for the five suites whose
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
    "Report editions agree (English vs Korean)":
        re.compile(r"^\d+ passed, \d+ failed", re.M),
    "Prose-to-artefact numeric provenance":
        re.compile(r"^\d+ passed, \d+ failed", re.M),
}

#: Patterns that recover a suite's own self-reported scale from its output.
SCALE = (
    re.compile(r"^(\d+) passed, (\d+) failed", re.M),
    re.compile(r"^FAIL — (\d+) violations across (\d+) categories", re.M),
)


def measured_scale(out: str) -> str:
    """The suite's own count, read from what it printed. Never asserted independently."""
    m = SCALE[0].search(out)
    if m:
        return f"{int(m.group(1)) + int(m.group(2))} checks"
    m = SCALE[1].search(out)
    if m:
        return f"{m.group(1)} violations across {m.group(2)} categories"
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
        # no longer impersonate the expected failure. The five suites expecting 0 are not
        # vulnerable (a crash gives 1, which already mismatches) but are held to the same rule
        # so that a silently empty run cannot pass either.
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
