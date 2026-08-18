#!/usr/bin/env python3
"""Provenance-carrying values.

The root cause of CognitionBioChem's failure was that a number and its origin were
separable: `"ΔG = -18.4 kcal/mol"` was a string in a UI array with nothing recording where
it came from, so a typed-in guess and a computed result were indistinguishable at the point
of display.

This module makes that impossible. A `Value` cannot be constructed without a `Provenance`,
and `render()` refuses to emit a number whose status is NOT_COMPUTED or PLACEHOLDER without
also emitting the label that says so. The UI consumes `Value.to_display()` and therefore
cannot show a bare number that nobody vouched for.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Any


class Status(str, Enum):
    """Where a value came from. There is no default: every value must choose."""

    COMPUTED = "computed"          # this repo computed it; method + software recorded
    MEASURED = "measured"          # a wet-lab measurement, with a citation
    LITERATURE = "literature"      # taken from a publication, with DOI/PMID
    DATABASE = "database"          # retrieved from a public database, with accession
    PREDICTED = "predicted"        # a model output, with model name + version
    PLACEHOLDER = "placeholder"    # illustrative only; MUST be labelled in the UI
    NOT_COMPUTED = "not_computed"  # honestly absent; the UI renders an empty state


#: Statuses that must never be displayed as if they were results.
UNTRUSTWORTHY = {Status.PLACEHOLDER, Status.NOT_COMPUTED}


def git_sha(repo: Path | None = None) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=repo or Path(__file__).resolve().parents[2],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


@dataclass(frozen=True)
class Provenance:
    status: Status
    method: str = ""                 # how it was obtained
    software: str = ""               # name + version, for COMPUTED / PREDICTED
    source_id: str = ""              # DOI, PMID, UniProt, PDB, CID, or a file path
    uncertainty: str = ""            # interval, sd, or the honest "unquantified"
    applicability: str = ""          # domain of validity, if the method has one
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, Status):
            object.__setattr__(self, "status", Status(self.status))
        if self.status in (Status.COMPUTED, Status.PREDICTED) and not self.software:
            raise ValueError(
                f"status={self.status.value} requires `software` (name and version): "
                "a computed number without a recorded tool is not reproducible")
        if self.status in (Status.LITERATURE, Status.MEASURED, Status.DATABASE) \
                and not self.source_id:
            raise ValueError(
                f"status={self.status.value} requires `source_id` (DOI/PMID/accession)")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass(frozen=True)
class Value:
    """A scientific value that knows where it came from."""

    value: Any
    units: str
    provenance: Provenance
    label: str = ""

    @property
    def trustworthy(self) -> bool:
        return self.provenance.status not in UNTRUSTWORTHY

    def to_display(self) -> dict[str, Any]:
        """What the UI is allowed to render. A value that nobody vouched for arrives
        with `display=None` and a `caveat`, so the front-end has nothing to print."""
        st = self.provenance.status
        if st is Status.NOT_COMPUTED:
            return {"label": self.label, "display": None, "units": self.units,
                    "status": st.value, "badge": "not computed",
                    "caveat": self.provenance.note or
                              "This value has not been computed. No result is available."}
        if st is Status.PLACEHOLDER:
            return {"label": self.label, "display": None, "units": self.units,
                    "status": st.value, "badge": "ILLUSTRATIVE PLACEHOLDER",
                    "placeholder_value": self.value,
                    "caveat": "Illustrative placeholder — not a model output and not a "
                              "measurement. Do not cite or act on this number."}
        return {
            "label": self.label,
            "display": self.value,
            "units": self.units,
            "status": st.value,
            "badge": st.value,
            "method": self.provenance.method,
            "software": self.provenance.software,
            "source_id": self.provenance.source_id,
            "uncertainty": self.provenance.uncertainty or "unquantified",
            "applicability": self.provenance.applicability,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "units": self.units, "label": self.label,
                "provenance": self.provenance.to_dict()}


# --- convenience constructors ------------------------------------------------ #

def computed(value: Any, units: str, method: str, software: str, *, label: str = "",
             uncertainty: str = "", applicability: str = "") -> Value:
    return Value(value, units, Provenance(Status.COMPUTED, method=method,
                                          software=software, uncertainty=uncertainty,
                                          applicability=applicability), label)


def database(value: Any, units: str, source_id: str, *, label: str = "",
             method: str = "retrieved") -> Value:
    return Value(value, units, Provenance(Status.DATABASE, method=method,
                                          source_id=source_id), label)


def literature(value: Any, units: str, source_id: str, *, label: str = "",
               uncertainty: str = "") -> Value:
    return Value(value, units, Provenance(Status.LITERATURE, source_id=source_id,
                                          uncertainty=uncertainty), label)


def predicted(value: Any, units: str, software: str, *, label: str = "",
              method: str = "", uncertainty: str = "", source_id: str = "") -> Value:
    return Value(value, units, Provenance(Status.PREDICTED, method=method,
                                          software=software, source_id=source_id,
                                          uncertainty=uncertainty), label)


def not_computed(units: str = "", *, label: str = "", note: str = "") -> Value:
    return Value(None, units, Provenance(Status.NOT_COMPUTED, note=note), label)


def placeholder(value: Any, units: str = "", *, label: str = "", note: str = "") -> Value:
    return Value(value, units, Provenance(Status.PLACEHOLDER, note=note), label)


# --- record-level validation -------------------------------------------------- #

class ProvenanceError(ValueError):
    pass


def audit(record: dict[str, Any], path: str = "") -> list[str]:
    """Walk a nested record and report every numeric leaf lacking provenance.

    This is the check that would have caught the original dataset: a bare float sitting
    in a data structure with no story attached.
    """
    problems: list[str] = []
    for key, val in record.items():
        here = f"{path}.{key}" if path else key
        if isinstance(val, dict):
            if "provenance" in val and "value" in val:
                st = (val.get("provenance") or {}).get("status")
                if st not in {s.value for s in Status}:
                    problems.append(f"{here}: unknown provenance status {st!r}")
            else:
                problems.extend(audit(val, here))
        elif isinstance(val, list):
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    problems.extend(audit(item, f"{here}[{i}]"))
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            if key not in _EXEMPT_KEYS:
                problems.append(
                    f"{here}: bare numeric value {val!r} with no provenance record")
    return problems


#: Structural/bookkeeping numbers that are not scientific claims.
_EXEMPT_KEYS = {
    "id", "rank", "index", "count", "n", "length", "schema_version", "version",
    "start", "end", "start_index", "end_index", "position", "residue_index", "order",
}
