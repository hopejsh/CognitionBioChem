#!/usr/bin/env python3
"""Binding thermodynamics: consistency checking and honest uncertainty.

The central relation is the standard-state binding free energy

    dG = R T ln(Kd / c0),    c0 = 1 M

so a (dG, Kd) pair is only self-consistent for one temperature. Reporting both, with
values that disagree, is a checkable arithmetic error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any

R_KCAL = 1.987204259e-3   # kcal / (mol K)
T_DEFAULT = 298.15        # K
RT = R_KCAL * T_DEFAULT   # 0.59248 kcal/mol

UNIT_TO_MOLAR = {
    "M": 1.0, "mM": 1e-3, "uM": 1e-6, "µM": 1e-6, "μM": 1e-6,
    "nM": 1e-9, "pM": 1e-12, "fM": 1e-15,
}

# Empirical reference points for "how tight is tight". These calibrate an ACHIEVABILITY
# question -- what affinity has actually been reached, by what modality, and after how much
# experimental work -- and none of them is a physical limit.
#
# An earlier version of this module took the loosest quoted biotin-streptavidin value
# (-18.3) as the tightest non-covalent binding physically available and rejected anything
# past it as not credible. This project's own verification refuted that reading on three
# counts and it is withdrawn as retraction ret_0004 (retractions.jsonl; verdict
# PARTIALLY_REFUTED by ver.computational-chemistry-binding-thermody, 2026-08-17):
#   (a) the source cited for the constant, Delgadillo et al., PLoS ONE 2019;14:e0204194,
#       reports K_D ~ 1e-15 M for biotin-avidin, i.e. -20.5 kcal/mol -- the -18.3 is the
#       loosest end of a range spanning two orders of magnitude in K_D;
#   (b) the ~-15 kcal/mol plateau of Kuntz et al., PNAS 1999;96:9997 is a per-heavy-atom
#       result for SMALL MOLECULES and says nothing about a peptide interface; and
#   (c) barnase-barstar, a natural non-covalent protein-protein complex, sits at
#       dG0 ~ -19 kcal/mol, so a value in that range is not outside non-covalent chemistry.
# What survived the refutation is the modality argument, and that is what this table and
# DE_NOVO_DESIGN_BEST_DG below now encode.
REFERENCE_AFFINITIES = {
    "barnase-barstar, natural protein-protein complex (Kd ~ 1.3e-14 M)": -18.9,
    "biotin-streptavidin, Kuntz et al. PNAS 1999 Table 1 (Kd 3.7e-14 M; other sources "
    "report K_D ~ 1e-15 M, i.e. -20.5)": -18.3,
    "Kuntz et al. PNAS 1999 plateau for tight SMALL-MOLECULE ligands (per heavy atom)": -15.0,
    "tightest de novo designed mini-binder measured, after experimental affinity "
    "maturation (Cao et al. Nature 2022; Kd ~ 20 pM)": -14.6,
    "typical high-affinity antibody-antigen": -12.5,
    "typical optimized small-molecule drug (Kd ~ 1 nM)": -12.3,
    "typical designed mini-binder (Kd ~ 100 nM)": -9.6,
    "typical unoptimized peptide-protein (Kd ~ 10 uM)": -6.8,
}

#: The plausibility threshold, and the reason it is not the minimum of the table above.
#: Cao et al., Nature 2022;605:551-560 (PMID 35332283) report de novo binders "smaller than
#: 65 amino acids" reaching "nanomolar to picomolar affinities" only "following experimental
#: optimization" -- Kd ~ 20 pM at the tightest, i.e. dG = RT ln(2e-11) = -14.60 kcal/mol.
#: A stated dG more negative than this is outside what the modality has been SHOWN to reach.
#: It is not outside what non-covalent chemistry permits, and this constant must never be
#: described that way: barnase-barstar is 4.3 kcal/mol tighter and is a real complex.
DE_NOVO_DESIGN_BEST_DG = -14.6

# Honest error bars for the methods that can actually produce a dG estimate.
METHOD_ACCURACY = {
    "docking score (Vina/Glide)": {
        "rmse_kcal": None,
        "note": "Docking scores are not free energies. Correlation with measured affinity "
                "is typically r ~ 0.3-0.5 across diverse targets; they rank poses far "
                "better than they rank compounds.",
    },
    "MM-GBSA / MM-PBSA rescoring": {
        "rmse_kcal": 2.5,
        "note": "Useful for relative ranking within a congeneric series; not quantitative "
                "in absolute terms.",
    },
    "relative FEP (alchemical, well-behaved series)": {
        "rmse_kcal": 1.1,
        "note": "The current practical ceiling for accuracy, and only for relative dG "
                "within a series, given adequate sampling and correct protonation.",
    },
    "absolute binding FEP": {
        "rmse_kcal": 1.8,
        "note": "Expensive and sampling-limited; ~1-2 kcal/mol RMSE at best.",
    },
    "structure prediction (AlphaFold2/3, Boltz-1, Chai-1)": {
        "rmse_kcal": None,
        "note": "Produces no free energy at all. pLDDT/PAE/ipTM are confidence in the "
                "predicted geometry, not affinity. Using them as an affinity proxy is a "
                "category error.",
    },
}


@dataclass
class ThermoReport:
    label: str
    dg_stated: float | None
    kd_stated_molar: float | None
    kd_stated_text: str
    temperature_k: float
    kd_implied_by_dg: float | None = None
    dg_implied_by_kd: float | None = None
    discrepancy_kcal: float | None = None
    discrepancy_orders: float | None = None
    consistent: bool | None = None
    plausible: bool | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dg_to_kd(dg_kcal: float, temperature: float = T_DEFAULT) -> float:
    """Kd in molar from dG in kcal/mol."""
    return math.exp(dg_kcal / (R_KCAL * temperature))


def kd_to_dg(kd_molar: float, temperature: float = T_DEFAULT) -> float:
    """dG in kcal/mol from Kd in molar."""
    return R_KCAL * temperature * math.log(kd_molar)


def format_kd(kd_molar: float) -> str:
    for unit in ("M", "mM", "uM", "nM", "pM", "fM"):
        v = kd_molar / UNIT_TO_MOLAR[unit]
        if v >= 1.0:
            return f"{v:.3g} {unit}"
    return f"{kd_molar:.3e} M"


def parse_kd(text: str) -> tuple[float | None, str]:
    """Extract a Kd from free text like 'Kd = 0.32 nM'."""
    import re
    m = re.search(r"Kd\s*[=:~]\s*([\d.]+)\s*(fM|pM|nM|[uµμ]M|mM|M)", text, re.I)
    if not m:
        return None, ""
    val, unit = float(m.group(1)), m.group(2)
    unit = {"uM": "uM", "µM": "uM", "μM": "uM"}.get(unit, unit)
    factor = UNIT_TO_MOLAR.get(unit) or UNIT_TO_MOLAR.get(unit.replace("m", "M"))
    if factor is None:
        return None, m.group(0)
    return val * factor, m.group(0)


def parse_dg(text: str) -> float | None:
    import re
    m = re.search(r"[ΔΔd]?G\s*[=:~]\s*(-?[\d.]+)\s*kcal", text, re.I)
    return float(m.group(1)) if m else None


def check(label: str, dg: float | None, kd_molar: float | None, kd_text: str = "",
          temperature: float = T_DEFAULT, tolerance_kcal: float = 1.0) -> ThermoReport:
    """Check a stated (dG, Kd) pair for internal consistency and physical plausibility."""
    rep = ThermoReport(label=label, dg_stated=dg, kd_stated_molar=kd_molar,
                       kd_stated_text=kd_text, temperature_k=temperature)

    if dg is not None:
        rep.kd_implied_by_dg = dg_to_kd(dg, temperature)
    if kd_molar is not None:
        rep.dg_implied_by_kd = kd_to_dg(kd_molar, temperature)

    if dg is not None and kd_molar is not None:
        rep.discrepancy_kcal = abs(dg - rep.dg_implied_by_kd)
        rep.discrepancy_orders = abs(math.log10(kd_molar / rep.kd_implied_by_dg))
        rep.consistent = rep.discrepancy_kcal <= tolerance_kcal
        if not rep.consistent:
            rep.issues.append(
                f"dG and Kd are mutually inconsistent at {temperature:.2f} K. "
                f"The stated dG = {dg:.1f} kcal/mol implies Kd = "
                f"{format_kd(rep.kd_implied_by_dg)}, but the record states Kd = "
                f"{format_kd(kd_molar)} — a gap of {rep.discrepancy_kcal:.1f} kcal/mol "
                f"({rep.discrepancy_orders:.1f} orders of magnitude in Kd). "
                "At most one of the two numbers can be right.")

    if dg is not None:
        # The comparison is against what de novo design has been shown to reach, NOT
        # against the tightest entry in REFERENCE_AFFINITIES -- that entry is a natural
        # protein-protein complex, and using it here is the ceiling argument withdrawn as
        # ret_0004. See DE_NOVO_DESIGN_BEST_DG.
        if dg < DE_NOVO_DESIGN_BEST_DG:
            rep.plausible = False
            rep.issues.append(
                f"dG = {dg:.1f} kcal/mol is {DE_NOVO_DESIGN_BEST_DG - dg:.1f} kcal/mol "
                f"beyond the tightest affinity de novo design has been measured to reach "
                f"({DE_NOVO_DESIGN_BEST_DG} kcal/mol, Kd ~ 20 pM; Cao et al., Nature 2022), "
                "and that was reached only after experimental affinity maturation and only "
                "for hyperstable folded mini-proteins under 65 residues. This is an "
                "achievability limit for the modality, not a limit on non-covalent binding: "
                "natural complexes bind tighter. A stated value past it needs an "
                "experimental measurement rather than a prediction.")
        else:
            rep.plausible = True
        if abs(dg * 10 - round(dg * 10)) < 1e-9:
            rep.issues.append(
                f"dG is reported to 0.1 kcal/mol with no uncertainty interval. The best "
                "available method (relative FEP) has ~1.1 kcal/mol RMSE — an order of "
                "magnitude larger than the stated precision. A single-point value implies "
                "an accuracy no method can deliver.")
    return rep


def method_note(method: str) -> dict[str, Any]:
    return METHOD_ACCURACY.get(method, {"rmse_kcal": None, "note": "unknown method"})


def ligand_efficiency(dg_kcal: float, heavy_atoms: int) -> float:
    """LE = -dG / N_heavy (kcal/mol per heavy atom). Values above ~0.6 are rare."""
    return -dg_kcal / heavy_atoms if heavy_atoms else float("nan")
