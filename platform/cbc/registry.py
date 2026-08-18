#!/usr/bin/env python3
"""Target construct and numbering registry.

The defect this fixes is concrete. The platform's binding-site annotations mix numbering
conventions inside a single string — `AChE CAS (Trp84, Phe330, Tyr121) & PAS (Trp286, Tyr72,
Tyr341)` puts Torpedo californica numbering and human mature-chain numbering in one
parenthesis — and nothing anywhere records which convention any number is in. A residue
comparison across two records that use different conventions silently returns no overlap,
even when the records describe the same site.

So every residue annotation in this platform must now carry an explicit
`(accession, convention)` pair, and this module resolves between conventions against the
authoritative UniProt record rather than against anyone's recollection.

Conventions
-----------
CANONICAL   position in the full UniProt sequence, including any signal peptide.
MATURE      position in the mature chain, i.e. after signal-peptide cleavage. The offset is
            the CHAIN feature's start minus one, read from UniProt, never assumed.
AUTH        author numbering in a specific PDB entry, which may match neither.

Nothing here is cached from memory: the UniProt record is fetched, and the offset is derived
from its SIGNAL and CHAIN features.
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "targets"
UNIPROT = "https://rest.uniprot.org/uniprotkb"

Convention = Literal["canonical", "mature", "auth"]

THREE = {
    "A": "Ala", "R": "Arg", "N": "Asn", "D": "Asp", "C": "Cys", "Q": "Gln", "E": "Glu",
    "G": "Gly", "H": "His", "I": "Ile", "L": "Leu", "K": "Lys", "M": "Met", "F": "Phe",
    "P": "Pro", "S": "Ser", "T": "Thr", "W": "Trp", "Y": "Tyr", "V": "Val",
}
ONE = {v: k for k, v in THREE.items()}


class RegistryError(RuntimeError):
    pass


def _ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "CognitionBioChem/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as fh:
        return json.loads(fh.read())


@dataclass
class Feature:
    kind: str
    start: int
    end: int
    description: str = ""


@dataclass
class TargetRecord:
    symbol: str
    uniprot: str
    protein_name: str = ""
    organism: str = ""
    length: int = 0
    sequence: str = ""
    signal_peptide: tuple[int, int] | None = None
    chain: tuple[int, int] | None = None
    domains: list[Feature] = field(default_factory=list)
    pdb_entries: list[str] = field(default_factory=list)
    fetched_from: str = ""

    # -- the offset, derived rather than assumed --------------------------------- #

    @property
    def mature_offset(self) -> int:
        """canonical = mature + offset.

        Derived from the CHAIN feature start. A protein with no signal peptide has offset 0,
        which is why PTAFR's `His14` cannot be excused as a numbering artifact: P25105 has no
        signal peptide, so canonical and mature numbering coincide there.
        """
        if self.chain:
            return self.chain[0] - 1
        return 0

    def residue_at(self, position: int, convention: Convention = "canonical") -> str | None:
        """The one-letter residue at `position` under the stated convention."""
        if not self.sequence:
            return None
        idx = position - 1 if convention == "canonical" else position - 1 + self.mature_offset
        if 0 <= idx < len(self.sequence):
            return self.sequence[idx]
        return None

    def convert(self, position: int, frm: Convention, to: Convention) -> int:
        if frm == to:
            return position
        if frm == "mature" and to == "canonical":
            return position + self.mature_offset
        if frm == "canonical" and to == "mature":
            return position - self.mature_offset
        raise RegistryError(f"cannot convert {frm} -> {to} without a PDB alignment")

    def check_annotation(self, annotation: str) -> dict[str, Any]:
        """Resolve an annotation like 'Trp286' against both conventions.

        Returns which convention (if any) makes the annotation true. An annotation that is
        false in every convention is a fabricated residue identity, not a numbering problem.
        """
        m = re.fullmatch(r"([A-Z][a-z]{2})(\d+)", annotation.strip())
        if not m:
            return {"annotation": annotation, "parsed": False}
        want = ONE.get(m.group(1))
        pos = int(m.group(2))
        out: dict[str, Any] = {"annotation": annotation, "parsed": True,
                               "expected_residue": m.group(1), "position": pos,
                               "uniprot": self.uniprot}
        for conv in ("canonical", "mature"):
            got = self.residue_at(pos, conv)  # type: ignore[arg-type]
            out[conv] = None if got is None else THREE.get(got, got)
            out[f"{conv}_matches"] = (got == want)
        out["resolves_in"] = [c for c in ("canonical", "mature") if out.get(f"{c}_matches")]
        out["valid"] = bool(out["resolves_in"])
        if not out["valid"]:
            out["verdict"] = (
                f"{annotation} is not present in {self.uniprot} under EITHER convention "
                f"(canonical position {pos} is {out['canonical']}, mature position {pos} is "
                f"{out['mature']}). This is a wrong residue identity, not a numbering "
                f"convention problem.")
        elif len(out["resolves_in"]) == 2:
            out["verdict"] = (f"{annotation} resolves under both conventions, so it is "
                              f"ambiguous without a declared reference.")
        else:
            out["verdict"] = f"{annotation} resolves only in {out['resolves_in'][0]} numbering."
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mature_offset"] = self.mature_offset
        d["domains"] = [asdict(f) for f in self.domains]
        d["sequence_length_checked"] = len(self.sequence) == self.length
        return d


def fetch(symbol: str, accession: str, use_cache: bool = True) -> TargetRecord:
    """Fetch a target from UniProt, deriving the numbering offset from its features."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{accession}.json"
    if use_cache and cached.exists():
        raw = json.loads(cached.read_text())
    else:
        url = (f"{UNIPROT}/{accession}?fields=accession,id,protein_name,organism_name,"
               f"length,sequence,ft_signal,ft_chain,ft_domain,xref_pdb")
        try:
            raw = _get(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RegistryError(f"UniProt fetch failed for {accession}: {exc}") from exc
        cached.write_text(json.dumps(raw, indent=1))

    rec = TargetRecord(symbol=symbol, uniprot=accession,
                       fetched_from=f"{UNIPROT}/{accession}")
    rec.length = raw.get("sequence", {}).get("length", 0)
    rec.sequence = raw.get("sequence", {}).get("value", "")
    pn = raw.get("proteinDescription", {}).get("recommendedName", {})
    rec.protein_name = pn.get("fullName", {}).get("value", "")
    rec.organism = raw.get("organism", {}).get("scientificName", "")

    for f in raw.get("features", []):
        loc = f.get("location", {})
        s = loc.get("start", {}).get("value")
        e = loc.get("end", {}).get("value")
        if s is None or e is None:
            continue
        t = f.get("type", "")
        if t == "Signal":
            rec.signal_peptide = (s, e)
        elif t == "Chain":
            if rec.chain is None:
                rec.chain = (s, e)
        elif t == "Domain":
            rec.domains.append(Feature("domain", s, e, f.get("description", "")))

    rec.pdb_entries = [x["id"] for x in raw.get("uniProtKBCrossReferences", [])
                       if x.get("database") == "PDB"][:12]
    return rec


def build(targets: list[tuple[str, str]], use_cache: bool = True) -> dict[str, Any]:
    """Build the full registry."""
    records: dict[str, Any] = {}
    errors: list[str] = []
    for symbol, acc in targets:
        try:
            records[symbol] = fetch(symbol, acc, use_cache).to_dict()
        except RegistryError as exc:
            errors.append(str(exc))
    return {
        "schema_version": "1.0",
        "convention_note": (
            "Every residue position in this platform must be accompanied by (accession, "
            "convention). CANONICAL counts from the initiator methionine of the full UniProt "
            "sequence; MATURE counts from the first residue after signal-peptide cleavage; "
            "the offset between them is derived from the UniProt CHAIN feature and is "
            "recorded per target as mature_offset. A protein with no signal peptide has "
            "offset 0, so for such targets the two conventions coincide and cannot be "
            "invoked to excuse a mismatch."),
        "targets": records,
        "errors": errors,
    }
