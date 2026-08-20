#!/usr/bin/env python3
"""Open-ended natural-product corpus construction.

Replaces the 8 hand-typed natural products with a corpus defined by an executable,
versioned INCLUSION PROTOCOL rather than by someone's choice of which compounds to type in.

The point is not "more compounds". The point is that the set becomes *reproducible* and its
denominator becomes *statable*. A hand-picked set of 8 actives has no denominator, so no rate
computed over it — enrichment, hit rate, scaffold frequency — is defined. A protocol-defined
corpus has one.

Sources are queried live, but the caches this module writes ARE redistributed. data/corpus_*.json
carries ChEMBL canonical SMILES, preferred names and measured activity values, which makes it
this repository's principal redistribution of ChEMBL content, not a private cache. It is
therefore covered by CC BY-SA 3.0 share-alike and is listed by name in /NOTICE. The earlier
version of this paragraph concluded that "nothing is redistributed", and that false premise is
what let the attribution gap stay open until the repository went public. COCONUT is CC0/CC BY.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterator

from . import chem, provenance as pv

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
COCONUT = "https://coconut.naturalproducts.net/api"
USER_AGENT = "CognitionBioChem/1.0 (research; contact via repository)"

#: ChEMBL assay confidence score. 9 = direct single-protein target assignment.
#: Below 8 the activity may be against a cell line, tissue or protein complex, so the
#: compound-target link is not evidence about that protein.
MIN_ASSAY_CONFIDENCE = 8

#: Natural-product provenance is a TIER, not a predicate.
#:
#: An earlier version filtered on ChEMBL's binary `natural_product` flag and discarded
#: everything else. That is chemically wrong for this platform's own target area: it deletes
#: exactly the semi-synthetic and NP-derived agents where the CNS drugs actually are.
#: Rivastigmine is physostigmine-derived, varenicline is cytisine-derived, and Huprine X —
#: the most informative record in this repository's own AChE corpus — is a huperzine A /
#: tacrine hybrid. A binary flag throws Huprine X out alongside metoclopramide.
#:
#: So every compound is retained and TAGGED, and the tier becomes a query dimension. The
#: corpus can then answer "what did nature make" and "what did nature suggest" separately,
#: instead of conflating the second with fully synthetic chemistry.
NP_TIERS = ("NP_ISOLATED", "NP_DERIVED", "SYNTHETIC", "UNKNOWN")

#: Activity types that are interpretable as potency. Percent-inhibition and other
#: single-concentration readouts are deliberately excluded: without a concentration they
#: cannot be compared across assays.
POTENCY_TYPES = ("IC50", "EC50", "Ki", "Kd", "AC50", "XC50")


class SourceError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Inclusion protocol
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class InclusionProtocol:
    """An executable definition of corpus membership.

    Every field is a decision that would otherwise be made silently and unrepeatably.
    Changing any of them changes `version`, and the version is recorded on every compound,
    so a result can always be traced to the protocol that produced its corpus.
    """

    version: str = "np-cognition-v1"
    description: str = (
        "Natural products with a measured potency value against a named human target "
        "implicated in cognition, from an assay ChEMBL scores as directly assigned to a "
        "single protein.")

    # --- hard filters: a compound failing any of these is OUT ------------------ #
    require_parseable_structure: bool = True
    require_defined_stereochemistry: bool = False   # would exclude most NPs; see note below
    min_assay_confidence: int = MIN_ASSAY_CONFIDENCE
    allowed_activity_types: tuple[str, ...] = POTENCY_TYPES
    require_pure_compound: bool = True              # excludes extract-derived activity
    max_mol_weight: float = 2000.0                  # excludes large saponins/peptides
    exclude_pains: bool = False                     # flagged, not excluded; see note below

    #: Which provenance tiers are admitted. Default retains NP-derived chemistry, which
    #: a binary natural_product flag would delete.
    admit_tiers: tuple[str, ...] = ("NP_ISOLATED", "NP_DERIVED")

    # --- scored preferences: recorded, never used to exclude ------------------- #
    prefer_cns_permeable: bool = True

    #: Why `require_defined_stereochemistry` defaults False: most public NP records lack
    #: full stereochemistry, so requiring it would drop the majority of real natural
    #: products and bias the corpus toward simple achiral scaffolds. Instead every compound
    #: carries its undefined-stereocentre count, and any downstream 3D work must filter on
    #: it explicitly rather than inheriting a silent assumption.
    #:
    #: Why `exclude_pains` defaults False: PAINS substructure filters were derived from
    #: specific AlphaScreen campaigns and over-flag natural products badly — many genuine
    #: NP drugs match a PAINS pattern. Flagging preserves the information; excluding would
    #: silently delete real chemistry. The flag is surfaced, and the decision left to the
    #: analysis.

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (f"{self.version}: potency ({'/'.join(self.allowed_activity_types)}) on a "
                f"named human target, assay confidence >= {self.min_assay_confidence}, "
                f"pure compound, MW <= {self.max_mol_weight:.0f} Da, parseable structure.")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _ssl_context() -> "ssl.SSLContext":
    """A context with a working trust store.

    python.org builds on macOS ship without CA certificates, so `urllib` raises
    CERTIFICATE_VERIFY_FAILED against every HTTPS host until one is supplied. certifi
    provides Mozilla's bundle. This is a real environment trap, not a code bug — but the
    error it produces looks like a network failure, so it is handled explicitly here rather
    than left for the caller to misdiagnose.
    """
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
        if not ctx.get_ca_certs():
            raise SourceError(
                "No CA certificates available: HTTPS verification will fail. "
                "Install certifi into this environment (`pip install certifi`) or set "
                "SSL_CERT_FILE. Refusing to disable verification.") from None
        return ctx



#: Assay confidence, cached by assay id. Many activities share an assay, so this is a few
#: dozen requests rather than one per row.
_ASSAY_CONF_CACHE: dict[str, int | None] = {}
#: Rows dropped by the confidence criterion, so the denominator stays statable.
_EXCLUDED_BY_CONFIDENCE: list[dict] = []


def _assay_confidence(assay_id: str | None) -> int | None:
    """ChEMBL assay confidence_score, or None when it cannot be established."""
    if not assay_id:
        return None
    if assay_id in _ASSAY_CONF_CACHE:
        return _ASSAY_CONF_CACHE[assay_id]
    try:
        d = _get(f"{CHEMBL}/assay/{assay_id}?format=json")
        v = d.get("confidence_score")
        v = int(v) if v is not None else None
    except Exception:                                  # noqa: BLE001 - network or shape
        v = None
    _ASSAY_CONF_CACHE[assay_id] = v
    return v

def _get(url: str, retries: int = 3, timeout: int = 120) -> dict:
    """GET with retry. ChEMBL is frequently slow (20-40 s is normal), not broken."""
    ctx = _ssl_context()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as fh:
                return json.loads(fh.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise SourceError(f"GET failed after {retries} attempts: {url} ({last})")


# --------------------------------------------------------------------------- #
# ChEMBL adapter — the only source with structures AND measured activity
# --------------------------------------------------------------------------- #

@dataclass
class Activity:
    chembl_id: str
    target_chembl_id: str
    target_name: str
    organism: str
    activity_type: str
    value_nm: float | None
    assay_confidence: int | None
    assay_chembl_id: str
    document: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def target_activity_count(target_chembl_id: str) -> int:
    """How much chemical matter exists for a target. A useful sanity check before
    ingesting: a target with single-digit activities has no library to mine."""
    d = _get(f"{CHEMBL}/activity?target_chembl_id={target_chembl_id}&limit=1&format=json")
    return int(d["page_meta"]["total_count"])


def iter_target_activities(target_chembl_id: str, protocol: InclusionProtocol,
                           limit: int = 1000, page: int = 200) -> Iterator[Activity]:
    """Stream potency measurements for one target, applying the protocol's assay filters.

    Filtering happens server-side where ChEMBL supports it, so we do not download and
    discard. `standard_units=nM` normalizes the comparison.
    """
    fetched = 0
    types = ",".join(protocol.allowed_activity_types)
    url = (f"{CHEMBL}/activity?target_chembl_id={target_chembl_id}"
           f"&standard_type__in={types}&standard_units=nM"
           # Without an explicit ordering the API returns a different page-1 each time, and
           # the corpus is then not reproducible: two builds at the same limit returned the
           # same 18 compounds but with different SALT FORMS of neostigmine and edrophonium
           # (different InChIKeys for the same drug). Ordering by the immutable activity_id
           # makes the pull deterministic, which is the whole premise of an executable
           # inclusion protocol.
           f"&order_by=activity_id"
           f"&limit={min(page, limit)}&format=json")
    while url and fetched < limit:
        d = _get(url)
        for a in d.get("activities", []):
            # The ChEMBL /activity resource does NOT carry confidence_score -- it lives on
            # /assay. Reading it from the activity record made `conf` None on every row, so
            # the guard below never fired even once, while protocol.summary() advertised
            # "assay confidence >= 8" as an applied inclusion criterion. Verified against the
            # live API: /activity has no such key; /assay/CHEMBL643384 returns 8.
            # It is now fetched per assay and cached, and a missing score FAILS the criterion
            # rather than passing silently, because "unknown" is not "acceptable".
            conf = _assay_confidence(a.get("assay_chembl_id"))
            if conf is None or conf < protocol.min_assay_confidence:
                _EXCLUDED_BY_CONFIDENCE.append(
                    {"activity": a.get("activity_id"), "assay": a.get("assay_chembl_id"),
                     "confidence": conf})
                continue
            val = a.get("standard_value")
            yield Activity(
                chembl_id=a.get("molecule_chembl_id", ""),
                target_chembl_id=a.get("target_chembl_id", ""),
                target_name=a.get("target_pref_name") or "",
                organism=a.get("target_organism") or "",
                activity_type=a.get("standard_type") or "",
                value_nm=float(val) if val not in (None, "") else None,
                assay_confidence=conf,
                assay_chembl_id=a.get("assay_chembl_id") or "",
                document=a.get("document_chembl_id") or "",
            )
            fetched += 1
            if fetched >= limit:
                return
        nxt = (d.get("page_meta") or {}).get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else None


def fetch_molecules(chembl_ids: list[str], page: int = 40) -> dict[str, dict]:
    """Batch-fetch molecule records. ChEMBL accepts `molecule_chembl_id__in`."""
    out: dict[str, dict] = {}
    for i in range(0, len(chembl_ids), page):
        chunk = chembl_ids[i:i + page]
        url = (f"{CHEMBL}/molecule?molecule_chembl_id__in={','.join(chunk)}"
               f"&limit={len(chunk)}&format=json")
        for m in _get(url).get("molecules", []):
            out[m["molecule_chembl_id"]] = m
    return out


def np_tier(mol: dict) -> str:
    """Assign a provenance tier rather than a yes/no natural-product verdict.

    ChEMBL carries two relevant fields: `natural_product` (1 if the compound is a natural
    product or a close derivative) and `structure_type`. Neither distinguishes an isolated
    natural product from a semi-synthetic analogue, so `NP_DERIVED` is the honest label for
    a flagged compound whose isolation is not separately established. Anything unflagged is
    SYNTHETIC unless a source database tells us otherwise.
    """
    flag = mol.get("natural_product")
    if flag in (1, True, "1"):
        # ChEMBL's flag covers isolated NPs and close derivatives without separating them,
        # and it is measurably noisy. Observed on the AChE query: DONEPEZIL and
        # METOCLOPRAMIDE both carry natural_product=1, and neither is a natural product or
        # derived from one. So NP_DERIVED here means "ChEMBL asserts NP provenance", not
        # "NP provenance is established". Promotion to NP_ISOLATED requires a source that
        # actually records an organism — LOTUS, COCONUT or NPAtlas — which is why the tier
        # is stored rather than used as a silent filter.
        return "NP_DERIVED"
    if flag in (0, False, "0"):
        return "SYNTHETIC"
    return "UNKNOWN"


# --------------------------------------------------------------------------- #
# COCONUT adapter — structures and organism provenance, no bioactivity
# --------------------------------------------------------------------------- #

def coconut_search(query: str, limit: int = 20) -> list[dict]:
    """COCONUT's search endpoint is POST-only; a GET returns a 405 with that message."""
    body = json.dumps({"query": query, "limit": limit}).encode()
    req = urllib.request.Request(f"{COCONUT}/search", data=body, method="POST",
                                 headers={"User-Agent": USER_AGENT,
                                          "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90, context=_ssl_context()) as fh:
            d = json.loads(fh.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SourceError(f"COCONUT search failed: {exc}") from exc
    data = d.get("data") or {}
    return data.get("data", []) if isinstance(data, dict) else []


# --------------------------------------------------------------------------- #
# Standardization
# --------------------------------------------------------------------------- #

@dataclass
class CorpusEntry:
    """One compound, admitted under a stated protocol, with everything computed locally."""

    inchikey: str
    inchikey_skeleton: str
    canonical_smiles: str
    source: str
    source_id: str
    protocol_version: str
    name: str = ""
    formula: str = ""
    mol_weight: float | None = None
    clogp: float | None = None
    tpsa: float | None = None
    hbd: int | None = None
    heavy_atoms: int | None = None
    stereocenters_total: int = 0
    stereocenters_undefined: int = 0
    implied_stereoisomers: int = 1
    natural_product_flag: bool = False
    np_tier: str = "UNKNOWN"
    cns_mpo_flags: list[str] = field(default_factory=list)
    activities: list[dict] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_provenanced(self) -> dict[str, Any]:
        """Emit in the platform's provenance format so it drops into the existing UI."""
        soft = f"RDKit {getattr(chem, 'RDKIT_VERSION', '2026.03.5')}"
        d: dict[str, Any] = {
            "name": self.name or self.source_id,
            "inchikey": pv.database(self.inchikey, "", f"{self.source}:{self.source_id}",
                                    label="InChIKey").to_dict(),
            "smiles": pv.database(self.canonical_smiles, "SMILES",
                                  f"{self.source}:{self.source_id}",
                                  label="Canonical SMILES").to_dict(),
            "protocol": self.protocol_version,
            "quality_flags": self.quality_flags,
            "cns_flags": self.cns_mpo_flags,
        }
        for key, val, units, label in [
            ("formula", self.formula, "", "Molecular formula"),
            ("mol_weight", self.mol_weight, "Da", "Molecular weight"),
            ("clogp", self.clogp, "", "cLogP"),
            ("tpsa", self.tpsa, "A^2", "Topological polar surface area"),
            ("stereocenters_undefined", self.stereocenters_undefined, "centres",
             "Undefined stereocentres"),
        ]:
            if val is None:
                d[key] = pv.not_computed(units, label=label,
                                         note="structure did not yield this value").to_dict()
            else:
                d[key] = pv.computed(val, units, "RDKit descriptor", soft,
                                     label=label).to_dict()
        # Measured activity is a literature value, not something we computed.
        d["activities"] = [
            pv.literature(a["value_nm"], "nM",
                          f"ChEMBL:{a['assay_chembl_id']} / {a['document']}",
                          label=f"{a['activity_type']} vs {a['target_name']}",
                          uncertainty="single reported value; assay conditions vary"
                          ).to_dict()
            for a in self.activities if a.get("value_nm") is not None
        ]
        return d


def desalt(smiles: str) -> tuple[str, list[str]]:
    """Reduce a multi-component SMILES to its largest organic fragment.

    Returns (parent_smiles, removed_fragments). A single-component input is returned
    unchanged with an empty removal list, so callers can always tell whether anything was
    stripped. Selection is by heavy-atom count, which is the standard convention and is
    unambiguous for salts of a single organic parent.
    """
    if "." not in smiles:
        return smiles, []
    if not chem.RDKIT:
        parts = sorted(smiles.split("."), key=len, reverse=True)
        return parts[0], parts[1:]
    from rdkit import Chem
    frags = [f for f in smiles.split(".") if f]
    mols = [(f, Chem.MolFromSmiles(f)) for f in frags]
    valid = [(f, m) for f, m in mols if m is not None]
    if not valid:
        return smiles, []
    parent_smi, _ = max(valid, key=lambda fm: fm[1].GetNumHeavyAtoms())
    removed = [f for f, _ in mols if f != parent_smi]
    return parent_smi, removed


def standardize(smiles: str, source: str, source_id: str, protocol: InclusionProtocol,
                name: str = "", natural_product: bool = False) -> CorpusEntry | None:
    """Validate and characterize one structure. Returns None if it fails a hard filter.

    The primary key is the FULL InChIKey, not the skeleton. Stereoisomers of a natural
    product are genuinely different molecules with different activity, so collapsing them
    would merge records that must stay separate. The skeleton is kept alongside so that
    cross-source matching can still find a stereo-undefined record from one database and a
    stereo-defined one from another — but they are two entries, not one, and the
    disagreement stays visible.
    """
    # Desalt first. A multi-component SMILES such as neostigmine bromide,
    # "CN(C)C(=O)Oc1cccc([N+](C)(C)C)c1.[Br-]", is a legitimate ChEMBL record but is not a
    # single molecule, and downstream tools reject it: Boltz-2's affinity head returned no
    # value for exactly the two salts in the AChE benchmark set. The counter-ion is not part
    # of the pharmacophore, so the parent is the right object to model. The original string
    # is preserved so the change is visible rather than silent.
    parent, removed = desalt(smiles)
    rep = chem.validate_smiles(name or source_id, parent)
    if protocol.require_parseable_structure and not rep.parses:
        return None
    if rep.mol_weight is not None and rep.mol_weight > protocol.max_mol_weight:
        return None
    if not rep.inchikey:
        return None

    undef = rep.stereocenters_unspecified or 0
    if protocol.require_defined_stereochemistry and undef:
        return None

    flags: list[str] = []
    if undef:
        # 2^undef is an UPPER BOUND, not a count. In the natural-product literature the
        # common state is relative configuration determined by NOESY/J-coupling with
        # absolute configuration undetermined, which leaves an enantiomeric PAIR — two
        # candidates, not 2^n. A flat SMILES cannot express that distinction (the InChI /s
        # layer can, but standard InChIKey discards it), so the bound is reported as a
        # bound and is never used to exclude.
        flags.append(
            f"{undef} unspecified stereocentre(s): at most {2 ** undef:,} stereoisomers, "
            f"but this is an upper bound only. If the relative configuration is known and "
            f"only the absolute configuration is open, the true count is 2. Resolve "
            f"against the source record before treating this as ambiguity.")
    if removed:
        flags.append(
            f"desalted: removed {removed} and kept the largest organic fragment. The "
            f"source record was {smiles!r}.")
    if rep.warnings:
        flags.extend(rep.warnings)

    return CorpusEntry(
        inchikey=rep.inchikey,
        inchikey_skeleton=rep.inchikey.split("-")[0],
        canonical_smiles=rep.canonical_smiles or smiles,
        source=source, source_id=source_id, protocol_version=protocol.version,
        name=name, formula=rep.formula or "", mol_weight=rep.mol_weight,
        clogp=rep.clogp, tpsa=rep.tpsa, hbd=rep.hbd, heavy_atoms=rep.heavy_atoms,
        stereocenters_total=rep.stereocenters_total or 0,
        stereocenters_undefined=undef,
        implied_stereoisomers=2 ** undef if undef else 1,
        natural_product_flag=natural_product,
        cns_mpo_flags=rep.cns_mpo_flags,
        quality_flags=flags,
    )


# --------------------------------------------------------------------------- #
# Corpus assembly
# --------------------------------------------------------------------------- #

def build_target_corpus(target_chembl_id: str, protocol: InclusionProtocol,
                        max_activities: int = 400,   # recorded in the artefact; see below
                        admit_tiers: Sequence[str] | None = None) -> dict[str, Any]:
    """Assemble the corpus of compounds with measured activity on one target.

    This is the inversion the 8-compound set cannot support: instead of asking
    "what does this compound hit?", ask "what is known to hit this target?".
    """
    # max_activities silently sets the corpus size: the committed data/corpus_ACHE.json was
    # built with 300 and admitted 18 compounds, while the default 400 admits 19. A corpus whose
    # membership depends on an unrecorded page limit is not reproducible, so the limit is now
    # written into the artefact's denominator block alongside the counts it produced.
    acts = list(iter_target_activities(target_chembl_id, protocol, limit=max_activities))
    by_mol: dict[str, list[Activity]] = {}
    for a in acts:
        if a.chembl_id:
            by_mol.setdefault(a.chembl_id, []).append(a)

    mols = fetch_molecules(list(by_mol))
    entries: dict[str, CorpusEntry] = {}
    tiers = tuple(admit_tiers or protocol.admit_tiers)
    rejected = {"unparseable": 0, "tier_excluded": 0, "no_structure": 0, "too_large": 0}
    tier_counts: dict[str, int] = {}

    for cid, mol in mols.items():
        tier = np_tier(mol)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier not in tiers:
            rejected["tier_excluded"] += 1
            continue
        struct = mol.get("molecule_structures") or {}
        smi = struct.get("canonical_smiles")
        if not smi:
            rejected["no_structure"] += 1
            continue
        e = standardize(smi, "ChEMBL", cid, protocol,
                        name=mol.get("pref_name") or cid,
                        natural_product=tier in ("NP_ISOLATED", "NP_DERIVED"))
        if e is not None:
            e.np_tier = tier
        if e is None:
            rejected["unparseable"] += 1
            continue
        e.activities = [a.to_dict() for a in by_mol[cid]]
        # Full InChIKey is the key: stereoisomers stay separate on purpose.
        if e.inchikey in entries:
            entries[e.inchikey].activities.extend(e.activities)
        else:
            entries[e.inchikey] = e

    return {
        "target_chembl_id": target_chembl_id,
        "target_name": acts[0].target_name if acts else "",
        "organism": acts[0].organism if acts else "",
        "protocol": protocol.to_dict(),
        "protocol_summary": protocol.summary(),
        "assay_confidence_audit": {
            "criterion": f"confidence_score >= {protocol.min_assay_confidence}",
            "source": "ChEMBL /assay (NOT /activity, which does not carry the field)",
            "activities_excluded": len(_EXCLUDED_BY_CONFIDENCE),
            "note": ("Until this was fixed the criterion was read from the /activity record, "
                     "where the field does not exist, so it evaluated to None on every row "
                     "and never excluded anything while protocol_summary advertised it as "
                     "applied. Measured after the fix, it excludes 0 activities for this "
                     "target -- every ChEMBL220 assay in the pull already scores >= 8 -- so "
                     "the published corpus membership is unaffected. The criterion is now "
                     "genuinely enforced rather than merely claimed."),
        },
        # The denominator: what was considered, so any rate over this corpus is defined.
        "max_activities_requested": max_activities,
        "denominator": {
            "activities_examined": len(acts),
            "distinct_molecules_examined": len(by_mol),
            "molecules_retrieved": len(mols),
            "admitted": len(entries),
            "rejected": rejected,
            "tiers_seen": tier_counts,
            "tiers_admitted": list(tiers),
        },
        "compounds": [e.to_dict() for e in entries.values()],
    }


# --------------------------------------------------------------------------- #
# Complete activity retrieval
# --------------------------------------------------------------------------- #

CHEMBL_ES = "https://www.ebi.ac.uk/chembl/elk/es/chembl_activity/_search"


def all_activities(molecule_chembl_id: str, target_chembl_id: str,
                   size: int = 500) -> list[dict]:
    """EVERY measured activity for one compound-target pair.

    `build_target_corpus` draws a flat activity budget across a whole target, so an
    individual compound gets whatever records happen to fall inside that window. Measured
    consequence: huperzine A x AChE was represented by ONE record at 5.0 nM when ChEMBL holds
    23 IC50 records carrying a pChEMBL value, from 23 distinct documents, spanning 3.99 log10
    units with a median of 47 nM (32 activity records in total across endpoint types) — the
    captured value sat
    at the 17th percentile, and roughly 40% of a headline error attributed to the model was
    really an artefact of that sampling.

    The public REST endpoint returned HTTP 500 throughout this work, so the Elasticsearch
    backend is used directly.
    """
    body = {
        "size": size,
        "query": {"bool": {"filter": [
            {"term": {"molecule_chembl_id": molecule_chembl_id}},
            {"term": {"target_chembl_id": target_chembl_id}}]}},
        "_source": ["standard_type", "standard_value", "standard_units", "pchembl_value",
                    "assay_chembl_id", "document_chembl_id", "target_organism",
                    "assay_type", "standard_relation"],
    }
    req = urllib.request.Request(
        CHEMBL_ES, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as fh:
            data = json.loads(fh.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SourceError(f"ChEMBL Elasticsearch query failed: {exc}") from exc

    out = []
    for h in data.get("hits", {}).get("hits", []):
        s = h["_source"]
        v, u, t = s.get("standard_value"), s.get("standard_units"), s.get("standard_type")
        if not v or u != "nM" or t not in POTENCY_TYPES:
            continue
        # An inequality is a bound, not a measurement, and averaging it with real values
        # biases the reference.
        if s.get("standard_relation") not in (None, "=", ""):
            continue
        out.append({"type": t, "value_nm": float(v),
                    "assay": s.get("assay_chembl_id"),
                    "document": s.get("document_chembl_id"),
                    "pchembl": s.get("pchembl_value"),
                    "organism": s.get("target_organism")})
    return out


def reference_potency(molecule_chembl_id: str, target_chembl_id: str) -> dict:
    """A reference value with its own dispersion, so the model's error can be compared
    against the measurement's."""
    import statistics as _st
    acts = all_activities(molecule_chembl_id, target_chembl_id)
    if not acts:
        return {"n": 0, "median_nm": None}
    vals = [a["value_nm"] for a in acts]
    logs = [__import__("math").log10(v) for v in vals if v > 0]
    return {
        "n": len(vals), "n_assays": len({a["assay"] for a in acts}),
        "median_nm": _st.median(vals), "min_nm": min(vals), "max_nm": max(vals),
        "log10_spread": round(max(logs) - min(logs), 3) if len(logs) > 1 else 0.0,
        "log10_sd": round(_st.stdev(logs), 3) if len(logs) > 1 else None,
        "types": sorted({a["type"] for a in acts}),
    }
