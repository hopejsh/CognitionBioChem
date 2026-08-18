#!/usr/bin/env python3
"""Run every check in the repository and summarize.

    python3 verify_all.py

Exits non-zero if any suite fails. Note the deliberate inversion for the data gate:
`platform/validate.py` is *expected* to exit non-zero on the legacy dataset, because that
dataset genuinely violates the contract. A gate that passed on it would be the bug.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
VENV = REPO / ".venv" / "bin" / "python"
PY = str(VENV) if VENV.exists() else sys.executable

SUITES = [
    ("Memory ledger regression suite", [sys.executable, "memory/tests/test_mem.py"], 0,
     "74 checks: 16-writer concurrency, idempotency, torn-tail recovery, and one test "
     "per flaw the three critics found in the rejected v1 spec"),
    ("Platform regression suite", [PY, "platform/tests/test_platform.py"], 0,
     "93 checks: thermodynamics, peptide properties, RDKit validation, provenance "
     "enforcement, and predictor parsing against real AlphaFold output"),
    ("Front-end contract verification", [PY, "platform/verify_frontend.py"], 0,
     "48 checks: DOM contract, data contract, fabricated-renderer removal, "
     "resource lifecycle"),
    ("Data-integrity gate (expected to FAIL on legacy data)",
     [PY, "platform/validate.py"], 1,
     "91 violations across 13 categories — the gate correctly rejects the original data"),
    ("Dataset build + provenance audit", [PY, "platform/build_dataset.py"], 0,
     "every numeric value carries a provenance record"),
    ("Naming guard (pooled potency must not be rendered as free energy)",
     [PY, "platform/check_naming.py"], 0,
     "no code path converts affinity_pred_value into kcal/mol or names it an apparent dG"),
]


def main() -> int:
    print("=" * 78)
    print("CognitionBioChem — full verification")
    print("=" * 78)
    results = []
    for name, cmd, expected, blurb in SUITES:
        t0 = time.time()
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        dt = time.time() - t0
        ok = r.returncode == expected
        results.append((name, ok, r.returncode, expected, dt, blurb, r))
        mark = "PASS" if ok else "FAIL"
        print(f"\n[{mark}] {name}")
        print(f"       exit {r.returncode} (expected {expected})  ·  {dt:.1f}s")
        print(f"       {blurb}")
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
