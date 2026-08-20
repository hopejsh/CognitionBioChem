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
    #: Membrane topology: TRANSMEM, TOPO_DOM and INTRAMEM features, in canonical numbering.
    #: Empty for a soluble protein. Recorded because a receptor's mature chain is NOT the
    #: surface a ligand can reach: for a single-pass receptor the mature chain also contains
    #: a transmembrane helix and a cytoplasmic tail, which are inaccessible from the
    #: extracellular side and which a structure predictor will nonetheless happily dock a
    #: hydrophobic peptide onto.
    topology: list[Feature] = field(default_factory=list)
    #: Disulfide bonds. An INTERCHAIN one is a statement that the chain does not exist alone:
    #: its partner cysteine is on another subunit, so a lone-chain construct presents an
    #: unpaired thiol plus the surface that partner would bury.
    disulfides: list[Feature] = field(default_factory=list)
    #: Isoform-variable spans (UniProt Alternative sequence). A terminal one marks where the
    #: common core of the protein ends and an isoform-specific extension begins.
    isoform_variable: list[Feature] = field(default_factory=list)
    #: UniProt SUBUNIT text. Recorded because a monomeric construct of an oligomeric receptor
    #: can be topologically correct and still score a site that does not exist: an interface
    #: buried between subunits in the assembly becomes free solvent-exposed surface when one
    #: copy is folded alone. That is the same artefact class as a transmembrane helix folded
    #: in isolation, and neither the transmembrane test nor the assembly-segment test sees it.
    subunit: str = ""
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

    @property
    def is_membrane_protein(self) -> bool:
        return any(f.kind == "transmembrane" for f in self.topology)

    @property
    def ligand_accessible_span(self) -> tuple[int, int] | None:
        """Canonical [start, end] of the span an extracellular ligand can physically reach.

        For a soluble or GPI-anchored protein this is the mature chain: every residue is on
        the same side of the membrane, so the mature chain is already the accessible surface.

        For a membrane protein it is the LARGEST extracellular topological domain, clipped to
        the mature chain. Returning the mature chain there would be a category error: the
        transmembrane helix and the cytoplasmic tail are not solvent-exposed on the ligand's
        side, so scoring an interface against them measures a contact that cannot form in the
        cell. The largest such domain is taken (rather than their union) because the domains
        of a multi-pass receptor are separated by membrane-spanning segments and are not a
        single contiguous chain; concatenating them would fabricate a covalent bond.

        Returns None when the protein is annotated as multi-pass but has no extracellular
        topological domain, which is a refusal, not a fallback to the mature chain.
        """
        lo, hi = self.chain if self.chain else (1, self.length)
        for ex in self.construct_exclusions():          # trim obligate-assembly tails first
            s_, e_ = ex["span"]
            if e_ >= hi:
                hi = min(hi, s_ - 1)
            elif s_ <= lo:
                lo = max(lo, e_ + 1)
        if not self.is_membrane_protein:
            return (lo, hi)
        extra = [f for f in self.topology
                 if f.kind == "topological_domain"
                 and "extracellular" in f.description.lower()]
        if not extra:
            return None
        clipped = [(max(f.start, lo), min(f.end, hi)) for f in extra]
        clipped = [(s, e) for s, e in clipped if e > s]
        if not clipped:
            return None
        return max(clipped, key=lambda se: se[1] - se[0])

    #: Stated convention, not a derived quantity. An extracellular segment of a polytopic
    #: receptor shorter than this is a connecting loop, not an independently folding domain:
    #: excising it and folding it alone predicts a structure that does not exist in the cell,
    #: and docking a peptide onto it measures nothing. Applied only where no annotated
    #: structural domain lies inside the segment, which is the evidence that would settle the
    #: question directly. The floor is deliberately conservative; the two constructs this
    #: platform actually builds (TREM2 156 aa, CHRNA7 211 aa) clear it by a wide margin, and
    #: TREM2 independently satisfies the domain-annotation test via its Ig-like V-type domain.
    MIN_INDEPENDENT_DOMAIN_AA = 100

    def _interchain_cys(self) -> list[int]:
        """Residues whose disulfide partner is on another chain, per UniProt."""
        return sorted({f.start for f in self.disulfides
                       if "interchain" in f.description.lower()})

    #: Phrases that indicate the full-length protein assembles. Matching only the compound
    #: nouns ("homotetramer") missed AChE, whose SUBUNIT text says "organize into tetramers"
    #: in prose. But matching the bare noun as a substring is worse: "tetramer" occurs inside
    #: "heterotetramer", so the obligate heterotetramers GRIN2A and GRIN2B were classified
    #: homomer. The bare forms are therefore matched only where they are NOT preceded by
    #: hetero/homo, and the explicit compound forms are matched separately.
    _HOMO_EXPLICIT = ("homodimer", "homotrimer", "homotetramer", "homopentamer",
                      "homohexamer", "homooligomer", "homomultimer")
    _HETERO_EXPLICIT = ("heterodimer", "heterotrimer", "heterotetramer", "heteropentamer",
                        "heterooligomer", "heteromultimer")
    #: Bare nouns, matched only when not part of a hetero-/homo- compound.
    _BARE = ("dimer", "trimer", "tetramer", "pentamer", "hexamer", "oligomeriz",
             "self-associat")

    #: Sentence openings that describe a PARTNER's complex rather than the target's own
    #: assembly state. TLR4's SUBUNIT text says it "forms a heterodimer with TLR6" inside a
    #: sentence about interacting with CD36 -- a partner-specific complex, not TLR4's obligate
    #: state -- and matching it classified the record as a heteromer on someone else's
    #: stoichiometry.
    _PARTNER_OPENERS = ("interacts with", "found in a complex", "component of",
                        "(microbial infection)", "part of a complex", "associates with")

    def _self_text(self) -> str:
        """The SUBUNIT sentences that are about this protein rather than about a partner."""
        import re as _re
        keep = []
        for sent in _re.split(r"(?<=\.)\s+", self.subunit or ""):
            low = sent.strip().lower()
            if low and not low.startswith(self._PARTNER_OPENERS):
                keep.append(sent)
        return " ".join(keep).lower()

    def _subunit_hits(self) -> tuple[list[str], list[str]]:
        """(homo-evidence, hetero-evidence) phrases the target states about ITSELF."""
        import re as _re
        t = self._self_text()
        homo = [w for w in self._HOMO_EXPLICIT if w in t]
        hetero = [w for w in self._HETERO_EXPLICIT if w in t]
        homo += [w for w in self._BARE
                 if _re.search(r"(?<!hetero)(?<!homo)" + w, t)]
        return sorted(set(homo)), sorted(set(hetero))

    @property
    def oligomeric_evidence(self) -> dict[str, list[str]]:
        """The phrases that drove the classification, split by what they indicate."""
        homo, hetero = self._subunit_hits()
        return {"homo": homo, "hetero": hetero}

    @property
    def oligomeric_state(self) -> str | None:
        """"homomer"/"heteromer"/"both"/"monomer-or-unstated", from UniProt's SUBUNIT text.

        DELIBERATELY COARSE, and paired with oligomeric_evidence for that reason. Its purpose
        is to make a monomeric construct of an oligomeric receptor VISIBLE in the record, not
        to decide a study's design automatically: for CHRNA7 ("Homopentamer") the orthosteric
        site sits between adjacent subunits, so a lone extracellular domain presents that
        interface as free surface. A keyword scan cannot settle stoichiometry, and nothing in
        this repository treats it as if it could — "both" is emitted where the text describes
        both kinds of assembly rather than silently picking one.

        It UNDER-reports, and measurably: KEAP1's SUBUNIT text says the ligase complex holds
        "2 molecules of KEAP1", which is a homodimer stated as a stoichiometry rather than as
        a noun, and no keyword matches it. That is why oligomeric_evidence is emitted
        alongside: an empty evidence list means "no phrase matched", never "the protein is a
        monomer". Anything that turns on the distinction must read the SUBUNIT text itself.
        """
        if not (self.subunit or "").strip():
            return None
        homo, hetero = self._subunit_hits()
        if homo and hetero:
            return "both"
        if homo:
            return "homomer"
        if hetero:
            return "heteromer"
        return "monomer-or-unstated"

    def construct_exclusions(self) -> list[dict]:
        """Spans that must be cut from a lone-chain construct, with the annotation that says so.

        A transmembrane segment is not the only part of a chain that cannot be folded alone.
        An obligate-oligomerisation segment is the same problem wearing different clothes: it
        is solvent-exposed only until its partner arrives, and folded by itself it presents
        exactly the exposed amphipathic surface a structure predictor will dock a peptide onto.

        Human AChE is the case that forced this. UniProt P22303 annotates a disulfide at 611
        as INTERCHAIN and annotates 575-614 as isoform-variable (present in AChE-T, replaced in
        AChE-H and AChE-R). Those two annotations together say the C-terminal 40 residues are
        an isoform-specific assembly segment whose partner is absent from a monomer construct.
        Folded alone here they came back at pLDDT 50-67 against 95 for the catalytic domain,
        and they absorbed 19 of 32 and 18 of 31 interface residues in two of the four AChE
        complexes -- while occupying under 7% of the chain.

        The rule is derived, never per-target: an isoform-variable terminal span that contains
        an interchain-disulfide residue is excluded. Nothing about AChE is written down here.
        """
        lo, hi = self.chain if self.chain else (1, self.length)
        out = []
        for f in self.isoform_variable:
            if f.end < hi - 1 and f.start > lo + 1:
                continue                      # internal alternative exon, not a terminal tail
            cys = [c for c in self._interchain_cys() if f.start <= c <= f.end]
            if cys:
                out.append({"span": [f.start, f.end], "kind": "obligate_assembly_segment",
                            "reason": (f"isoform-variable ({f.description}) and carries the "
                                       f"interchain disulfide at {cys[0]}; its partner chain "
                                       "is not present in a monomer construct")})
        return out

    @property
    def construct_basis(self) -> str | None:
        """How a docking construct for this target may be built, or None to refuse.

        "mature_chain"  soluble/GPI-anchored: every residue is on the ligand's side.
        "ectodomain"    membrane protein with an extracellular segment that is a domain.
        None            refuse. Either the protein is annotated as membrane-embedded with no
                        extracellular topological domain, or its largest extracellular
                        segment is a loop. A GPCR or a transporter falls here, correctly: its
                        ligand site lies inside the membrane-embedded bundle, so no
                        soluble-phase construct of it can host that interaction at all.
        """
        if not self.is_membrane_protein:
            return "mature_chain_trimmed" if self.construct_exclusions() else "mature_chain"
        span = self.ligand_accessible_span
        if span is None:
            return None
        has_domain = any(f.start >= span[0] and f.end <= span[1] for f in self.domains)
        if has_domain or (span[1] - span[0] + 1) >= self.MIN_INDEPENDENT_DOMAIN_AA:
            return "ectodomain"
        return None

    def unpaired_cysteines(self) -> list[int]:
        """Cysteines in the construct with no ANNOTATED disulfide partner inside it.

        DIAGNOSTIC, NOT A GATE, and the distinction is the point. Odd cysteine parity is a real
        defect for a peptide, which is why validate.py gates on it there. For a receptor
        construct it is not: a cytosolic protein sits in a reducing compartment and free
        cysteines are its normal state — KEAP1 has 27 here, which is its documented sensor
        chemistry, not an error — and even an extracellular domain can carry a genuine free
        cysteine, as CHRNA7's does. Measured across this registry, a parity gate would fire on
        9 of 13 constructs, i.e. it would be noise, and a check that fires on everything gets
        switched off and then protects nothing.

        The check that DOES discriminate is construct_exclusions(): a cysteine UniProt marks as
        INTERCHAIN names a partner on another molecule, and that is evidence about the
        construct rather than about the compartment.
        """
        span = self.ligand_accessible_span
        if span is None or not self.sequence:
            return []
        lo, hi = span
        paired = {c for f in self.disulfides
                  for c in (f.start, f.end)
                  if lo <= f.start <= hi and lo <= f.end <= hi and f.start != f.end}
        return sorted(i for i in range(lo, hi + 1)
                      if self.sequence[i - 1] == "C" and i not in paired)

    def accessible_sequence(self) -> str | None:
        """The sequence a soluble ligand can dock against, or None if the target refuses one.

        This, not the mature chain, is what a docking study must fold. The mature chain of a
        receptor is not its ligand-accessible surface.
        """
        if self.construct_basis is None:
            return None
        span = self.ligand_accessible_span
        if span is None or not self.sequence:
            return None
        return self.sequence[span[0] - 1:span[1]]

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
        d["topology"] = [asdict(f) for f in self.topology]
        d["disulfides"] = [asdict(f) for f in self.disulfides]
        d["isoform_variable"] = [asdict(f) for f in self.isoform_variable]
        d["construct_exclusions"] = self.construct_exclusions()
        d["oligomeric"] = self.oligomeric_state
        d["oligomeric_evidence"] = self.oligomeric_evidence
        d["ligand_accessible_span"] = self.ligand_accessible_span
        d["construct_basis"] = self.construct_basis
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
               f"length,sequence,ft_signal,ft_chain,ft_domain,ft_transmem,ft_topo_dom,"
               f"ft_intramem,ft_disulfid,ft_var_seq,cc_subunit,xref_pdb")
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
        elif t == "Disulfide bond":
            rec.disulfides.append(Feature("disulfide", s, e, f.get("description", "")))
        elif t == "Alternative sequence":
            rec.isoform_variable.append(
                Feature("alternative_sequence", s, e, f.get("description", "")))
        elif t in ("Transmembrane", "Topological domain", "Intramembrane"):
            rec.topology.append(Feature(t.lower().replace(" ", "_"), s, e,
                                        f.get("description", "")))

    # UniProt emits SEVERAL SUBUNIT comments per entry. Assigning inside the loop kept only
    # the LAST one, which for TLR4 was an ebolavirus-interaction note 174 characters long --
    # so the obligate LY96/MD-2 partnership, the one fact that makes a lone TLR4 ectodomain
    # construct incomplete, was overwritten and never reached the record. The 600-character
    # truncation then cut NTRK1's text mid-sentence at exactly the cap. Accumulate all of
    # them, and classify on the whole thing.
    subunit_texts = [t.get("value", "")
                     for c in raw.get("comments", [])
                     if c.get("commentType") == "SUBUNIT"
                     for t in c.get("texts", [])]
    rec.subunit = " ".join(x for x in subunit_texts if x)

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
