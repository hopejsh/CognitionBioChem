#!/usr/bin/env python3
"""Build guard: no code path may render a pooled potency score as a free energy.

The adjudication upheld and EXTENDED the prohibition on calling the Boltz-2 affinity head's
output a binding free energy, on three grounds:

  1. Pooled referent. The head is fitted to six endpoint types (Ki/Kd/IC50/EC50/AC50/XC50)
     on one axis. The information needed to recover a standard free energy — endpoint type,
     [S], Km, mechanism — was destroyed when the labels were pooled. That is an
     identifiability failure, and no multiplicative constant inverts a many-to-one map.
  2. IC50 is not Kd. At the most benign condition, [S] = Km for a competitive inhibitor,
     Cheng-Prusoff gives IC50/Ki = 2 exactly, i.e. 0.411 kcal/mol of one-signed bias — 
     44% of the 0.68 log10 (0.93 kcal/mol) inter-laboratory reproducibility floor for
     public IC50 data (Kalliokoski et al., PLoS ONE 8:e61007, 2013).
  3. Sign. The documented conversion (6 - y) * 1.364 yields +8.0372 for this project's
     huperzine A run, while thermo.kd_to_dg on the same back-transformed potency yields
     -8.0387. Equal magnitude, opposite sign. A caveated "apparent dG = +8.04" is not a
     hedged claim; it states the wrong direction for a thermodynamic driving force.

No qualified form is permitted -- not "apparent", not "effective". The defect is identity,
not precision, so widening an error bar does not repair it.

At the time of the ruling no executable path committed the error: `grep -rn "1.364"
platform/` returned zero matches, and the contradiction lived only in prose. This guard
exists so that remains true.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("platform", "memory")
SKIP_NAMES = {"check_naming.py"}

#: RT*ln(10) at 298.15 K. Appearing near an affinity-head symbol means someone is
#: converting a pooled potency score into energy units.
RT_LN10 = re.compile(r"\b1\.364\b")
AFFINITY = re.compile(r"affinity_pred_value|affinity_pred_value[12]|affinity head", re.I)

#: Naming a pooled score as a free energy.
FORBIDDEN = [
    (re.compile(r"(apparent|effective)\s+(binding\s+)?(free\s+energy|[Δd]G)", re.I),
     "no qualified free-energy form is permitted for a pooled potency score"),
    (re.compile(r"affinity_pred_value[^\n]{0,80}\b(kcal|[Δd]G)\b", re.I),
     "affinity_pred_value rendered in energy units or as dG"),
    (re.compile(r"\b[Δd]G\b[^\n]{0,60}affinity_pred_value", re.I),
     "dG derived from affinity_pred_value"),
]


def scan() -> list[tuple[str, int, str, str]]:
    hits: list[tuple[str, int, str, str]] = []
    for d in SCAN_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.py")):
            if p.name in SKIP_NAMES:
                continue
            for i, line in enumerate(p.read_text().splitlines(), 1):
                stripped = line.strip()
                # A comment explaining the prohibition is not a violation of it.
                if stripped.startswith("#") or stripped.startswith('"'):
                    continue
                for pat, why in FORBIDDEN:
                    if pat.search(line):
                        hits.append((str(p.relative_to(REPO)), i, why, stripped[:110]))
                if RT_LN10.search(line) and AFFINITY.search(line):
                    hits.append((str(p.relative_to(REPO)), i,
                                 "RT*ln(10) applied to an affinity-head value",
                                 stripped[:110]))
    return hits


def main() -> int:
    hits = scan()
    print("=" * 78)
    print("naming guard: pooled potency scores must not be rendered as free energies")
    print("=" * 78)
    if not hits:
        print("\nPASS — no code path converts affinity_pred_value into energy units,")
        print("       and no qualified 'apparent/effective dG' form appears.\n")
        return 0
    print(f"\nFAIL — {len(hits)} violation(s):\n")
    for path, line, why, src in hits:
        print(f"  {path}:{line}")
        print(f"    {why}")
        print(f"    | {src}")
    print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
