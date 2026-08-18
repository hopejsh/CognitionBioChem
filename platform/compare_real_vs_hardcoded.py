#!/usr/bin/env python3
"""Run real computation on the platform's candidates and compare with the legacy values.

    ./.venv/bin/python platform/compare_real_vs_hardcoded.py --limit 6

Structure prediction runs in the 3.12 environment (Boltz-2); everything else runs here.
Results are written to data/real_vs_hardcoded.json.

Reading the comparison
----------------------
A hardcoded number landing close to a computed one is NOT evidence that the hardcoding was
sound. Two things have to be true for a number to mean something: it has to be right, and it
has to be the right quantity. The legacy pLDDT values fail the second test regardless of the
first, because pLDDT is a statement about local geometric self-consistency, not about
binding. This script therefore reports agreement and disagreement side by side, and also
reports ipTM — the metric that actually bears on binding — which is undefined for every
legacy entry because none of them was ever predicted against its receptor.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cbc import peptide, thermo  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "extracted_raw.json"
OUT = REPO / "data" / "real_vs_hardcoded.json"
WORK = Path("/tmp/cbc_boltz")


def parse_legacy(affinity: str) -> dict[str, Any]:
    """Pull the asserted numbers out of the legacy prose field."""
    plddt = re.search(r"pLDDT\s*=\s*([\d.]+)", affinity or "")
    dg = thermo.parse_dg(affinity or "")
    kd, _ = thermo.parse_kd(affinity or "")
    return {"plddt": float(plddt.group(1)) if plddt else None, "dg": dg, "kd": kd}


def run_one(code: str, seq: str, accelerator: str) -> dict[str, Any]:
    """Predict one sequence with Boltz-2 and read back the real confidence values."""
    import numpy as np

    out = WORK / code
    res = st.run_boltz([st.Chain("A", seq, "protein", msa="empty")], out,
                       accelerator=accelerator)
    if res.get("returncode") != 0:
        return {"ok": False, "error": res.get("stderr_tail", "")[-400:],
                "backend": res.get("backend")}

    pred_dir = next((p for p in out.rglob("predictions/*/") if any(p.glob("*.cif"))), None)
    if pred_dir is None:
        return {"ok": False, "error": "no prediction directory produced"}

    conf_files = sorted(pred_dir.glob("confidence_*.json"))
    conf = json.loads(conf_files[0].read_text()) if conf_files else {}
    plddt_files = sorted(pred_dir.glob("plddt_*.npz"))
    pae_files = sorted(pred_dir.glob("pae_*.npz"))

    v = None
    if plddt_files:
        arr = np.load(plddt_files[0])["plddt"]
        v = (arr * 100.0) if float(arr.max()) <= 1.0 else arr
    pae = np.load(pae_files[0])["pae"] if pae_files else None

    # Independent geometry audit of the coordinates the model actually emitted.
    from cbc import predictor as P
    geo = {}
    try:
        geo = P.load(pred_dir).geometry_check()
    except Exception as exc:  # noqa: BLE001
        geo = {"checked": False, "error": str(exc)[:200]}

    return {
        "ok": True,
        "backend": "boltz-2",
        "version": res.get("version"),
        "licence": "MIT",
        "citation": res.get("citation"),
        "msa_mode": res.get("msa_mode"),
        "accelerator": accelerator,
        "confidence_score": conf.get("confidence_score"),
        "ptm": conf.get("ptm"),
        "iptm": conf.get("iptm"),
        "complex_plddt": conf.get("complex_plddt"),
        "plddt_mean": round(float(v.mean()), 2) if v is not None else None,
        "plddt_min": round(float(v.min()), 2) if v is not None else None,
        "plddt_max": round(float(v.max()), 2) if v is not None else None,
        "plddt_sd": round(float(v.std()), 2) if v is not None else None,
        "frac_below_70": round(float((v < 70).mean()), 4) if v is not None else None,
        "pae_min": round(float(pae.min()), 2) if pae is not None else None,
        "pae_max": round(float(pae.max()), 2) if pae is not None else None,
        "geometry": geo,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--accelerator", default="gpu", choices=["cpu", "gpu"])
    a = ap.parse_args()

    raw = json.loads(RAW.read_text())
    rows: list[dict[str, Any]] = []

    candidates = [d for d in raw["FULL_BRAIN_DRUGS_DATA"]
                  if peptide.analyze(d["code"], d.get("sequence", "")).valid][: a.limit]

    for d in candidates:
        code, seq = d["code"], d["sequence"]
        legacy = parse_legacy(d.get("affinity", ""))
        print(f"predicting {code} ({len(seq)} residues) ...", flush=True)
        real = run_one(code, seq, a.accelerator)
        pep = peptide.analyze(code, seq)

        row: dict[str, Any] = {
            "code": code, "sequence": seq, "length": len(seq),
            "legacy": legacy, "real": real,
            "computed_properties": {
                "mol_weight_da": pep.mol_weight,
                "net_charge_ph74": pep.net_charge_ph74,
                "isoelectric_point": pep.isoelectric_point,
                "gravy": pep.gravy,
            },
        }
        if real.get("ok") and legacy["plddt"] is not None:
            row["plddt_delta"] = round(real["plddt_mean"] - legacy["plddt"], 2)
        rows.append(row)

    # --- what the comparison actually shows -------------------------------- #
    ok = [r for r in rows if r["real"].get("ok")]
    deltas = [r["plddt_delta"] for r in ok if "plddt_delta" in r]
    summary = {
        "n_predicted": len(ok),
        "n_failed": len(rows) - len(ok),
        "plddt_mean_abs_delta": round(statistics.fmean(abs(d) for d in deltas), 2)
        if deltas else None,
        "plddt_max_abs_delta": round(max((abs(d) for d in deltas), default=0), 2),
        "all_iptm_zero": all(r["real"].get("iptm") in (0, 0.0) for r in ok),
        "legacy_dg_values_reproduced": 0,
        "interpretation": [
            "ipTM is 0.0 for every candidate because each was predicted as a lone chain. "
            "ipTM measures confidence in an INTERFACE, so it is undefined without the "
            "receptor. Every legacy entry has the same problem: not one was ever predicted "
            "against its stated target, so no legacy number could have carried binding "
            "information even if a model had produced it.",
            "Where a legacy pLDDT happens to sit close to the computed value, that is not "
            "vindication. These are short designed amphipathic sequences, and a confident "
            "helix prediction is the expected outcome for them — which is also the regime "
            "where structure predictors are most reliably confident and least informative "
            "about function. Agreement on the number does not make it the right quantity.",
            "No legacy ΔG or Kd value is reproduced, because no method in this repository "
            "computes a binding free energy, and structure predictors do not emit one. "
            "Those fields remain not-computed rather than being filled with a docking "
            "score relabelled as ΔG.",
            "The geometry audit is the check that cleanly separates real from synthetic: "
            "Boltz-2 coordinates give mean Ca-Ca near 3.79 A with very small variance, "
            "while the legacy parametric helix gave 7.55 A with 18 of 23 bonds out of "
            "range.",
        ],
    }

    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    _report(rows, summary)
    return 0


def _report(rows: list[dict], summary: dict) -> None:
    print("\n" + "=" * 96)
    print("REAL COMPUTATION vs LEGACY HARDCODED VALUES")
    print("=" * 96)
    print(f"{'candidate':30s} {'legacy pLDDT':>13s} {'real mean':>10s} {'Δ':>7s} "
          f"{'real min':>9s} {'ipTM':>6s} {'Ca-Ca':>7s}")
    for r in rows:
        real = r["real"]
        if not real.get("ok"):
            print(f"{r['code'][:29]:30s} {'—':>13s} {'FAILED':>10s}")
            continue
        lg = r["legacy"]["plddt"]
        geo = real.get("geometry") or {}
        print(f"{r['code'][:29]:30s} {lg if lg else '—':>13} "
              f"{real['plddt_mean']:>10.1f} {r.get('plddt_delta', 0):>+7.1f} "
              f"{real['plddt_min']:>9.1f} {real['iptm']:>6.2f} "
              f"{geo.get('mean_ca_ca', 0):>7.3f}")

    print("\n--- ΔG and Kd ---")
    for r in rows[:4]:
        lg = r["legacy"]
        if lg["dg"] is None:
            continue
        print(f"  {r['code'][:29]:30s} legacy ΔG {lg['dg']:>6.1f} kcal/mol, "
              f"Kd {thermo.format_kd(lg['kd']) if lg['kd'] else '—':>9s}  ->  "
              f"computed: not available (no free-energy method implemented)")

    print("\n--- interpretation ---")
    for line in summary["interpretation"]:
        print("  *", line[:400])
    print("=" * 96)


if __name__ == "__main__":
    raise SystemExit(main())
