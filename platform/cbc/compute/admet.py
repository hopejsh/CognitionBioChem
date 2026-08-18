#!/usr/bin/env python3
"""Real ADMET prediction, with an enforced applicability domain.

Replaces the legacy hand-typed safety strings ("hERG IC50 > 50 uM (0% Risk)",
"Seizure Index: 0.01") with trained-model output carrying probabilities.

The single most important behaviour here is REFUSAL. The legacy platform reported a hERG
value for every candidate, including 3-11 kDa polycationic peptides. Small-molecule ADMET
models are trained on drug-like organics; a peptide of that size and charge is far outside
the chemical space they saw, so a number they emit for it is not a prediction, it is an
extrapolation dressed as one. This module detects that case and returns a refusal with a
reason, rather than a figure.

Models used
-----------
ADMET-AI (Swanson et al., Bioinformatics 2024) — Chemprop-RDKit multitask models trained on
Therapeutics Data Commons. Installed from PyPI; runs on CPU in well under a second per
molecule. Values here are that model's output, not this project's.

QED (Bickerton et al., Nat Chem 2012) and synthetic accessibility (Ertl & Schuffenhauer,
J Cheminform 2009) come from RDKit's own implementations, so no coefficient is transcribed
by hand.

Deliberately NOT implemented yet: CNS MPO. Its six desirability transforms must be
transcribed exactly from Wager et al. (ACS Chem Neurosci 2010), and transcribing a
piecewise-linear function from memory is the precise failure mode this project exists to
remove. It is added once the published breakpoints have been independently verified.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .. import provenance as pv

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors
    RDLogger.DisableLog("rdApp.*")
    RDKIT = True
except ImportError:  # pragma: no cover
    RDKIT = False

_ADMET_MODEL = None


# --------------------------------------------------------------------------- #
# Applicability domain
# --------------------------------------------------------------------------- #

#: ADMET-AI's training sets are TDC drug-like small molecules. These bounds describe that
#: space; outside them the model is extrapolating and its output is not reportable.
AD_MAX_MW = 1000.0
AD_MAX_HEAVY_ATOMS = 70
AD_MAX_ABS_CHARGE = 4


@dataclass
class DomainVerdict:
    in_domain: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"in_domain": self.in_domain, "reasons": self.reasons}


def check_applicability(smiles: str) -> DomainVerdict:
    """Is this molecule inside the space the ADMET models were trained on?"""
    if not RDKIT:
        return DomainVerdict(False, ["RDKit unavailable; cannot assess"])
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return DomainVerdict(False, ["structure does not parse"])

    reasons: list[str] = []
    mw = Descriptors.MolWt(mol)
    heavy = mol.GetNumHeavyAtoms()
    charge = Chem.GetFormalCharge(mol)

    if mw > AD_MAX_MW:
        reasons.append(
            f"molecular weight {mw:.0f} Da exceeds {AD_MAX_MW:.0f} Da. TDC ADMET training "
            "sets are drug-like small molecules; nothing of this size is represented.")
    if heavy > AD_MAX_HEAVY_ATOMS:
        reasons.append(f"{heavy} heavy atoms exceeds {AD_MAX_HEAVY_ATOMS}")
    if abs(charge) > AD_MAX_ABS_CHARGE:
        reasons.append(f"formal charge {charge:+d} is outside +/-{AD_MAX_ABS_CHARGE}")

    # Peptide detection. An earlier version required >= 6 amide bonds AND MW > 600, which
    # let a pentapeptide through and the model duly returned hERG = 0.82 for it — the exact
    # failure this guard exists to stop. A peptide backbone is the structural signature, so
    # match that directly and do not gate it on size.
    backbone = Chem.MolFromSmarts("[NX3][CX4H1,CX4H2][CX3](=[OX1])[NX3][CX4H1,CX4H2][CX3](=[OX1])")
    n_bb = len(mol.GetSubstructMatches(backbone)) if backbone else 0
    amide = Chem.MolFromSmarts("[NX3][CX3](=[OX1])")
    n_amide = len(mol.GetSubstructMatches(amide)) if amide else 0
    if n_bb >= 2 or n_amide >= 4:
        reasons.append(
            f"peptide backbone detected ({n_amide} amide bonds, {mw:.0f} Da). "
            "Small-molecule ADMET endpoints — hERG, Caco-2, CYP inhibition, oral "
            "bioavailability — are not defined for this modality, and the TDC training "
            "sets contain essentially no peptides. The governing liabilities here are "
            "proteolytic stability, immunogenicity, renal clearance and, for polycationic "
            "amphipaths, membrane lysis; none of those is predicted by these models.")
    return DomainVerdict(not reasons, reasons)


# --------------------------------------------------------------------------- #
# ADMET-AI
# --------------------------------------------------------------------------- #

def _model():
    global _ADMET_MODEL
    if _ADMET_MODEL is None:
        try:
            from admet_ai import ADMETModel
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "admet-ai is not installed. `./.venv/bin/pip install admet-ai`") from exc
        _ADMET_MODEL = ADMETModel()
    return _ADMET_MODEL


#: Endpoints surfaced by default, with what each actually means. ADMET-AI emits 100+
#: columns; showing all of them invites the reader to treat noise as signal.
KEY_ENDPOINTS = {
    "BBB_Martins": ("Blood-brain barrier penetration", "probability",
                    "classification; Martins et al. dataset via TDC"),
    "hERG": ("hERG channel blockade", "probability",
             "classification; a probability, never a 0% risk statement"),
    "AMES": ("Ames mutagenicity", "probability", "classification"),
    "DILI": ("Drug-induced liver injury", "probability", "classification"),
    "Caco2_Wang": ("Caco-2 permeability", "log cm/s", "regression"),
    "Solubility_AqSolDB": ("Aqueous solubility", "log mol/L", "regression"),
    "Lipophilicity_AstraZeneca": ("Lipophilicity (logD7.4)", "log units", "regression"),
    "CYP3A4_Veith": ("CYP3A4 inhibition", "probability", "classification"),
    "CYP2D6_Veith": ("CYP2D6 inhibition", "probability", "classification"),
    "Clearance_Hepatocyte_AZ": ("Hepatocyte clearance", "uL/min/10^6 cells", "regression"),
    "Half_Life_Obach": ("Half-life", "hours", "regression"),
    "PPBR_AZ": ("Plasma protein binding", "%", "regression"),
    "Bioavailability_Ma": ("Oral bioavailability", "probability", "classification"),
}

CITATION_ADMETAI = ("Swanson, Walther, Leitz, Mukherjee, Wu, Shivnaraine & Zou, "
                    "'ADMET-AI: a machine learning ADMET platform', "
                    "Bioinformatics 40:btae416 (2024)")


def predict(smiles_list: Sequence[str], names: Sequence[str] | None = None,
            enforce_domain: bool = True) -> list[dict[str, Any]]:
    """Predict ADMET for each molecule, refusing where out of domain.

    Returns one record per input. A refused record carries `predicted: False` and the
    reasons, and contains no numbers — so nothing downstream can render a value that the
    model was not entitled to produce.
    """
    names = list(names or [f"mol{i}" for i in range(len(smiles_list))])
    verdicts = [check_applicability(s) for s in smiles_list]

    runnable = [(i, s) for i, (s, v) in enumerate(zip(smiles_list, verdicts))
                if v.in_domain or not enforce_domain]
    preds: dict[int, dict[str, float]] = {}
    if runnable:
        model = _model()
        df = model.predict(smiles=[s for _, s in runnable])
        if hasattr(df, "to_dict"):
            rows = df.to_dict(orient="records")
        else:  # a single-molecule call returns a dict
            rows = [df]
        for (idx, _), row in zip(runnable, rows):
            preds[idx] = row

    out: list[dict[str, Any]] = []
    for i, (name, smi) in enumerate(zip(names, smiles_list)):
        v = verdicts[i]
        rec: dict[str, Any] = {"name": name, "smiles": smi,
                               "applicability": v.to_dict()}
        if i not in preds:
            rec["predicted"] = False
            rec["endpoints"] = {}
            rec["refusal"] = (
                "No ADMET values are reported for this molecule: it lies outside the "
                "applicability domain of the underlying models. "
                + " ".join(v.reasons))
            out.append(rec)
            continue

        rec["predicted"] = True
        row = preds[i]
        eps: dict[str, Any] = {}
        for key, (label, units, note) in KEY_ENDPOINTS.items():
            if key not in row:
                continue
            val = row[key]
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            eps[key] = pv.predicted(
                round(float(val), 4), units,
                software="ADMET-AI 2.0.1 (Chemprop-RDKit, TDC)",
                label=label, method=note, source_id=CITATION_ADMETAI,
                uncertainty=("model output is a point estimate; ADMET-AI does not emit a "
                             "calibrated interval, so treat it as a ranking signal rather "
                             "than a measurement"),
            ).to_dict()
        rec["endpoints"] = eps
        rec["n_endpoints_available"] = len(row)
        out.append(rec)
    return out


# --------------------------------------------------------------------------- #
# RDKit-native scores (no coefficient transcribed by hand)
# --------------------------------------------------------------------------- #

def rdkit_scores(smiles: str) -> dict[str, Any]:
    """QED and synthetic accessibility, computed by RDKit's own implementations."""
    if not RDKIT:
        return {}
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {}

    out: dict[str, Any] = {}
    out["qed"] = pv.computed(
        round(QED.qed(mol), 4), "0-1", "RDKit QED.qed", "RDKit 2026.03.5",
        label="Quantitative estimate of drug-likeness",
        uncertainty="a desirability aggregate, not a probability of success",
    ).to_dict()

    try:
        import rdkit
        contrib = Path(rdkit.__file__).parent / "Contrib" / "SA_Score"
        if str(contrib) not in sys.path:
            sys.path.append(str(contrib))
        import sascorer  # type: ignore
        out["sa_score"] = pv.computed(
            round(sascorer.calculateScore(mol), 3), "1-10 (1 = easy)",
            "RDKit Contrib SA_Score", "RDKit 2026.03.5",
            label="Synthetic accessibility",
            uncertainty="fragment-frequency heuristic, not a route assessment",
        ).to_dict()
    except Exception:  # noqa: BLE001
        out["sa_score"] = pv.not_computed(
            "1-10", label="Synthetic accessibility",
            note="RDKit SA_Score contrib module unavailable").to_dict()

    for key, val, units, label in [
        ("mol_weight", round(Descriptors.MolWt(mol), 2), "Da", "Molecular weight"),
        ("clogp", round(Crippen.MolLogP(mol), 3), "", "cLogP (Crippen)"),
        ("tpsa", round(Descriptors.TPSA(mol), 2), "A^2", "TPSA"),
        ("hbd", rdMolDescriptors.CalcNumHBD(mol), "", "H-bond donors"),
        ("hba", rdMolDescriptors.CalcNumHBA(mol), "", "H-bond acceptors"),
        ("rotatable_bonds", rdMolDescriptors.CalcNumRotatableBonds(mol), "",
         "Rotatable bonds"),
        ("fsp3", round(rdMolDescriptors.CalcFractionCSP3(mol), 3), "", "Fsp3"),
    ]:
        out[key] = pv.computed(val, units, "RDKit descriptor", "RDKit 2026.03.5",
                               label=label).to_dict()
    return out


def cns_mpo_status() -> dict[str, Any]:
    """CNS MPO is intentionally absent until its transforms are verified.

    Reporting this explicitly, rather than omitting it silently, is the point: a reader
    should be able to see what was deliberately not computed and why.
    """
    return pv.not_computed(
        "0-6", label="CNS MPO score",
        note=("Not implemented yet. The six desirability transforms from Wager et al. "
              "(ACS Chem Neurosci 1:435, 2010) must be transcribed exactly from the paper; "
              "reconstructing a piecewise-linear function from memory is precisely the "
              "class of error this platform was rebuilt to eliminate. It is added once the "
              "published breakpoints have been independently verified."),
    ).to_dict()
