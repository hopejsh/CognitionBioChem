#!/usr/bin/env python3
"""Hash-locked pre-specification.

A pre-specification records the hypothesis, the primary metric, the decision threshold and
the analysis plan BEFORE any data is seen, and freezes them under a content hash. The run
then records that hash, so a reader can verify that the decision rule was not chosen after
the result.

Why this project needs it specifically
--------------------------------------
The original failure here was numbers written first and method names attached afterwards.
Pre-specification inverts that order structurally rather than by good intentions: the
analysis cannot be run until the plan exists, and the plan cannot be edited afterwards
without changing its hash and leaving the change visible.

The unreachable-verdict check
-----------------------------
A decision rule can be broken in two symmetric ways. It can be impossible to fail, which is
the defect this repository's data gate deliberately avoids by failing on legacy data. It can
also be impossible to PASS, which is subtler and was found in a real proposal during review:
a criterion of "Holm-corrected p < 0.05 with K = 20 controls" has a smallest attainable
adjusted p-value of 0.476 under the stated design, so it could never fire. Both are the same
defect -- a test whose outcome is fixed before the data arrives -- so both are checked here
arithmetically, at registration time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "prespec"


class PrespecError(RuntimeError):
    pass


@dataclass(frozen=True)
class Hypothesis:
    """One pre-stated hypothesis with an explicit falsification condition.

    `falsified_if` is mandatory and must be a concrete, checkable condition. A hypothesis
    with no way to fail is not a hypothesis.
    """

    name: str
    statement: str
    predicted_by: str          # which position/theory predicts it
    confirmed_if: str
    falsified_if: str

    def __post_init__(self) -> None:
        for f in ("statement", "confirmed_if", "falsified_if"):
            if not getattr(self, f).strip():
                raise PrespecError(f"hypothesis {self.name!r}: {f} must not be empty")
        if self.confirmed_if.strip() == self.falsified_if.strip():
            raise PrespecError(
                f"hypothesis {self.name!r}: confirmed_if and falsified_if are identical, so "
                "no observation could distinguish them")


@dataclass(frozen=True)
class Prespecification:
    """A frozen analysis plan. The hash is over the scientific content only."""

    study_id: str
    question: str
    primary_metric: str
    primary_metric_justification: str
    decision_threshold: str
    n_planned: int
    n_comparisons: int
    multiplicity_correction: Literal["none", "bonferroni", "holm", "bh"]
    alpha: float
    stopping_rule: str
    analysis_plan: str
    hypotheses: tuple[Hypothesis, ...]
    #: How the p-value is produced. This matters for reachability: a permutation test's
    #: resolution is bounded by the number of permutations (1/(B+1)), whereas a parametric
    #: test can return arbitrarily small p at fixed n. Conflating the two makes the
    #: reachability check wrong in both directions.
    test_type: Literal["permutation", "parametric", "exact", "none"] = "parametric"
    n_permutations: int = 0
    secondary_metrics: tuple[str, ...] = ()
    exclusions: str = ""
    known_confounds: str = ""
    registered_utc: str = ""

    # ---- content hash ------------------------------------------------------- #

    def content(self) -> dict[str, Any]:
        """The scientific content. Deliberately excludes the timestamp, so re-registering
        an unchanged plan yields the same hash."""
        d = asdict(self)
        d.pop("registered_utc", None)
        return d

    def hash(self) -> str:
        blob = json.dumps(self.content(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    @property
    def short(self) -> str:
        return self.hash()[:12]

    # ---- validity checks run at registration -------------------------------- #

    def min_attainable_p(self) -> float:
        """Smallest adjusted p-value this design could ever produce.

        The raw floor depends on the test:
          * permutation / Monte-Carlo: p >= 1/(B+1) where B is the number of permutations.
            This is a hard resolution limit -- no amount of signal produces a smaller value.
          * exact rank tests: the floor is set by the number of distinct orderings; for a
            two-sided test at n observations it is bounded below by 2/n! but in practice by
            the tie structure, so 1/(n+1) is used as a conservative stand-in.
          * parametric: no floor from n alone, so only the multiplicity penalty applies.
        Under Bonferroni, and for the most significant comparison under Holm, the raw p is
        multiplied by K.
        """
        if self.test_type == "permutation":
            b = self.n_permutations or self.n_planned
            raw_min = 1.0 / (b + 1)
        elif self.test_type == "exact":
            raw_min = 1.0 / (self.n_planned + 1)
        else:
            raw_min = 0.0
        k = max(self.n_comparisons, 1)
        if self.multiplicity_correction in ("bonferroni", "holm"):
            return min(1.0, raw_min * k)
        return raw_min

    def check(self) -> list[str]:
        """Return the reasons this plan is not registrable. Empty means valid."""
        problems: list[str] = []
        if not self.hypotheses:
            problems.append("no hypotheses: nothing could be confirmed or falsified")
        if self.n_planned < 1:
            problems.append("n_planned must be at least 1")
        if not 0 < self.alpha < 1:
            problems.append(f"alpha must be in (0, 1), got {self.alpha}")

        pmin = self.min_attainable_p()
        if pmin > self.alpha:
            problems.append(
                f"UNREACHABLE VERDICT: with a {self.test_type} test "
                f"(B={self.n_permutations or self.n_planned}), K={self.n_comparisons} "
                f"comparisons and {self.multiplicity_correction} correction, the smallest "
                f"attainable adjusted p-value is {pmin:.4f}, which already exceeds "
                f"alpha={self.alpha}. This test can never fire. Raise the permutation count "
                f"to at least {self._n_needed()}, or reduce the number of comparisons.")

        names = [h.name for h in self.hypotheses]
        if len(names) != len(set(names)):
            problems.append("duplicate hypothesis names")

        # A plan whose hypotheses are all predicted by the same position cannot
        # discriminate between competing positions.
        predictors = {h.predicted_by for h in self.hypotheses}
        if len(self.hypotheses) > 1 and len(predictors) == 1:
            problems.append(
                f"all hypotheses are predicted by {predictors.pop()!r}, so no outcome could "
                "distinguish competing positions. State at least one hypothesis that a "
                "rival position predicts differently.")
        return problems

    def _n_needed(self) -> int:
        """Permutations (or observations, for an exact test) needed to make alpha reachable."""
        k = max(self.n_comparisons, 1) if self.multiplicity_correction in (
            "bonferroni", "holm") else 1
        return int(k / self.alpha - 1) + 1

    # ---- registration -------------------------------------------------------- #

    def register(self, registry: Path | None = None) -> Path:
        problems = self.check()
        if problems:
            raise PrespecError(
                f"pre-specification is not registrable:\n  - " + "\n  - ".join(problems))
        reg = registry or REGISTRY
        reg.mkdir(parents=True, exist_ok=True)
        path = reg / f"{self.study_id}.{self.short}.json"
        if path.exists():
            return path                      # idempotent: same content, same file
        payload = {
            "hash": self.hash(),
            "registered_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "min_attainable_p": round(self.min_attainable_p(), 6),
            "content": self.content(),
        }
        path.write_text(json.dumps(payload, indent=1, sort_keys=False))
        return path


def load(study_id: str, registry: Path | None = None) -> dict[str, Any]:
    reg = registry or REGISTRY
    hits = sorted(reg.glob(f"{study_id}.*.json"))
    if not hits:
        raise PrespecError(
            f"no pre-specification registered for {study_id!r}. Register the plan before "
            "running the analysis — that is the whole point.")
    if len(hits) > 1:
        raise PrespecError(
            f"{len(hits)} pre-specifications exist for {study_id!r}: "
            f"{[h.name for h in hits]}. More than one plan for one study is exactly the "
            "degree of freedom pre-registration exists to remove. Resolve it explicitly.")
    return json.loads(hits[0].read_text())


def verify_result(study_id: str, result: dict[str, Any],
                  registry: Path | None = None) -> dict[str, Any]:
    """Check a result against its plan and report every deviation.

    Deviations are reported, never blocked: unplanned analysis is legitimate science as long
    as it is labelled exploratory rather than presented as the confirmatory test.
    """
    plan = load(study_id, registry)
    c = plan["content"]
    dev: list[str] = []

    if result.get("prespec_hash") != plan["hash"]:
        dev.append(
            f"result records prespec hash {result.get('prespec_hash')!r} but the registered "
            f"plan hashes to {plan['hash']}")
    n = result.get("n_observed")
    if n is not None and n != c["n_planned"]:
        dev.append(f"n_observed={n} differs from n_planned={c['n_planned']}")
    if result.get("primary_metric") != c["primary_metric"]:
        dev.append(
            f"primary metric reported as {result.get('primary_metric')!r} but "
            f"{c['primary_metric']!r} was pre-specified — switching the primary metric after "
            "seeing data is the specific defect pre-registration exists to prevent")

    reported = set(result.get("metrics", {}))
    planned = {c["primary_metric"], *c["secondary_metrics"]}
    extra = reported - planned
    if extra:
        dev.append(f"metrics reported that were not pre-specified (exploratory): "
                   f"{sorted(extra)}")

    return {
        "study_id": study_id,
        "prespec_hash": plan["hash"],
        "registered_utc": plan["registered_utc"],
        "deviations": dev,
        "confirmatory": not dev,
        "note": ("All pre-specified analyses were carried out as planned."
                 if not dev else
                 "Deviations from the registered plan are listed. Results affected by them "
                 "are exploratory, not confirmatory."),
    }
