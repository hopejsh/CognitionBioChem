"""Separating a pre-specified criterion from a statistical test.

Every study in this repository registers three hypotheses and declares
`multiplicity_correction: "holm"`. Most of those hypotheses are not tests. They are
pre-specified threshold comparisons on a descriptive statistic — "at least half the candidates
fall below ipTM 0.6", "every same-seed replicate is bit-identical" — decided by looking at the
number, with no sampling model and no null distribution.

Those were being encoded as `p = 0.0` when met and `p = 1.0` when not, fed into Holm alongside
the genuine tests, and the whole vector published under the key `p_holm`. Two things were wrong
with that, and the second is the serious one.

1. A p-value of exactly 0.0 is unattainable under any test. Emitting one into a public data
   file, and quoting it in the README as "Holm p", asserts an inferential statement that was
   never computed. In a repository whose whole point is that it removed hand-typed numbers
   presented as computed statistics, that is the original defect wearing a new hat.

2. Holm is a step-down procedure: the smallest p gets multiplier K, the next K-1, and so on. A
   sentinel 0.0 always sorts first and therefore CONSUMES a multiplier. In
   `study_peptide_interface.json` two sentinels fired, took ranks 0 and 1, and left the one real
   test — Spearman ipTM vs DockQ — with multiplier 1. Its published "Holm-adjusted" p was
   3e-05, byte-identical to its raw p. No correction had been applied at all, while the artefact
   said one had. The direction is anti-conservative and it varies with criteria that carry no
   information about the test.

So: `holm()` corrects genuine tests only, and `decide()` reports criteria as what they are.

There is a third trap, which `holm()` cannot fix and which callers must avoid. A hypothesis
confirmed by FAILING to reject — an equivalence claim such as "the MSA changes nothing" — is
made EASIER by any multiplicity correction, because adjustment only ever raises p. Correcting
such a hypothesis is not conservative, it is backwards. Those belong in `criteria` with an
explicit equivalence margin, never in `tests`.
"""

from __future__ import annotations

import statistics

from dataclasses import dataclass
from typing import Any


def holm(tests: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni step-down adjustment over genuine p-values.

    `tests` must contain only quantities produced by an actual test. Passing a deterministic
    0/1 indicator here is the defect this module exists to prevent, so it is rejected rather
    than silently corrected: a 0.0 would sort first and absorb the largest multiplier.
    """
    for name, p in tests.items():
        if not isinstance(p, (int, float)) or not (0.0 < p <= 1.0):
            raise ValueError(
                f"{name!r} has p={p!r}, which is not a p-value. Holm's guarantee requires "
                "every family member to be a real test statistic; a threshold criterion "
                "encoded as 0.0/1.0 both fabricates an unattainable p and steals a "
                "multiplier from the tests it is grouped with. Report it via decide(criteria=)."
            )
    k = len(tests)
    order = sorted(tests, key=lambda n: tests[n])
    out: dict[str, float] = {}
    run_max = 0.0
    for rank, name in enumerate(order):
        run_max = max(run_max, (k - rank) * tests[name])
        out[name] = min(1.0, run_max)
    return out


@dataclass(frozen=True)
class Criterion:
    """A pre-specified threshold comparison. Not a test, and never given a p-value."""

    met: bool
    observed: Any
    threshold: str
    #: Set when the criterion is confirmed by the ABSENCE of an effect, so a reader can see
    #: that "met" here means "no difference was detected", which is weaker than "no difference
    #: exists" and is not evidence of equivalence unless an interval says so.
    confirmed_by_absence: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = {"met": self.met, "observed": self.observed, "threshold": self.threshold}
        if self.confirmed_by_absence:
            d["note"] = ("confirmed by not detecting an effect; this is not evidence of "
                         "equivalence unless the interval excludes a material difference")
        return d


def decide(criteria: dict[str, Criterion], tests: dict[str, float],
           alpha: float = 0.05) -> dict[str, Any]:
    """Verdicts for a mixed family, with criteria and tests kept apart in the output.

    Returns `verdicts`, plus `criteria` (met/observed/threshold) and — only if there are
    genuine tests — `p_raw` and `p_holm` over those tests alone. A study with no real test
    emits no p_holm key at all, rather than a block of zeros and ones.
    """
    adjusted = holm(tests) if tests else {}
    verdicts = {name: ("CONFIRMED" if c.met else "FALSIFIED") for name, c in criteria.items()}
    for name, p in adjusted.items():
        verdicts[name] = "CONFIRMED" if p < alpha else "FALSIFIED"
    out: dict[str, Any] = {
        "verdicts": verdicts,
        "criteria": {n: c.to_dict() for n, c in criteria.items()},
        "multiplicity": {
            "family_size": len(tests),
            "correction": "holm" if tests else "none (no hypothesis in this study is decided "
                                              "by a test statistic)",
            "excluded_from_correction": sorted(criteria),
        },
    }
    if tests:
        out["p_raw"] = dict(tests)
        out["p_holm"] = adjusted
    return out


def format_verdicts(report: dict[str, Any]) -> str:
    """Render verdicts so a criterion is visibly not a test.

    A single printer, because the previous per-study printers all read `report['p_holm'][h]`
    for every hypothesis and so could only exist while every hypothesis had a p-value —
    which is exactly the thing that had to stop being true.
    """
    crit = report.get("criteria", {})
    ph = report.get("p_holm", {})
    raw = report.get("p_raw", {})
    lines = []
    for h, v in report.get("verdicts", {}).items():
        if h in ph:
            k = len(ph)
            note = (f"Holm p = {ph[h]:.5g} (raw {raw.get(h, float('nan')):.5g}, K={k})"
                    if k > 1 else f"p = {ph[h]:.5g} (sole test in family, no correction due)")
        elif h in crit:
            c = crit[h]
            note = f"criterion: {c['observed']} vs {c['threshold']} — not a test, no p-value"
        else:
            note = "no criterion recorded"
        lines.append(f"  {h:38s} {v:10s} {note}")
    m = report.get("multiplicity")
    if m:
        lines.append(f"  {'':38s} {'':10s} family_size={m['family_size']}, "
                     f"correction={m['correction']}")
    return "\n".join(lines)


def wall_clock(rows: list[dict]) -> dict:
    """Mean seconds per COMPUTED cell, plus how many were reused.

    Content-addressed reuse records seconds = 0.0 for a cell it did not recompute, and the
    old expression filtered those out with a truthiness test — so a run in which every cell
    was reused left an empty list and raised StatisticsError inside the analysis, taking down
    a registered secondary metric. "Not measured because nothing was recomputed" and "zero
    seconds" are different statements and are now reported as such.
    """
    # Callers pass a list they have ALREADY filtered to successful cells, and not every study
    # keeps an "ok" key on those rows -- requiring one here made pose_accuracy report 0
    # computed and 0 reused out of 13 real timings. Membership of `rows` is the caller's
    # statement that the cell counts; this function only separates computed from reused.
    computed = [r["seconds"] for r in rows
                if not r.get("reused") and r.get("seconds") is not None]
    n_reused = sum(1 for r in rows if r.get("reused"))
    return {
        "mean_seconds_per_computed_fold": (round(statistics.fmean(computed), 1)
                                           if computed else None),
        "n_computed": len(computed),
        "n_reused": n_reused,
        "note": ("no cell was recomputed in this run; every fold was served from a "
                 "content-verified cache" if not computed else ""),
    }

