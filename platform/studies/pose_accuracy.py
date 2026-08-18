#!/usr/bin/env python3
"""Study #6: pose accuracy and physical validity, stratified by what the model had seen.

The question is not "can Boltz-2 place a ligand" but "how much of that placement is recall".
Boltz-2's structure training used every PDB entry up to 2023-06-01, so a complex deposited
before that date may simply be remembered.

Three strata were planned. Only two could be built, and that is a result rather than a
shortfall:

  RECALL                deposited before the cutoff; the complex itself could be in training
  CONGENERIC EXTENSION  deposited after the cutoff, but the RECEPTOR has pre-cutoff entries,
                        so the fold and pocket were seen and only the ligand is new
  RECEPTOR DISJOINT     receptor with no pre-cutoff entries at all — NOT CONSTRUCTIBLE

For the third: 14 distinct receptors from post-cutoff protein-ligand X-ray depositions were
checked and every one already had pre-cutoff entries in the PDB, ranging from 13 to 1172.
Recently deposited protein-ligand structures are overwhelmingly of proteins that were already
well characterised. So this study measures the recall-to-congeneric step and CANNOT measure
receptor generalisation, and no number here should be read as evidence about novel folds.

RMSD uses RDKit CalcRMS: symmetry-corrected and computed in place. PoseBusters' paper says it
uses GetBestRMS; its code never has, and the difference decides the benchmark — measured here,
a pose translated 3.0 A scores CalcRMS 3.0 (fails) and GetBestRMS 0.0 (would pass).

    ./.venv/bin/python platform/studies/pose_accuracy.py --register
    ./.venv/bin/python platform/studies/pose_accuracy.py --run
    ./.venv/bin/python platform/studies/pose_accuracy.py --analyse
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cbc import posebench as pb, prespec as ps  # noqa: E402
from cbc.compute import structure as st  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
STUDY_ID = "pose-accuracy-v1"
SET = Path("/tmp/posebench_set.json")
WORK = Path("/tmp/cbc_pose")
REFS = Path("/tmp/cbc_pose_refs")
RESULT = REPO / "data" / "study_pose_accuracy.json"

#: The field's conventional success threshold for a docked pose.
RMSD_SUCCESS = 2.0


def build_prespec(n: int) -> ps.Prespecification:
    return ps.Prespecification(
        study_id=STUDY_ID,
        question=(
            "When Boltz-2 places a small molecule in a protein pocket on this hardware, how "
            "often is the pose within 2 A of the crystallographic pose, and does that "
            "accuracy differ between complexes that could have been in its training set and "
            "complexes deposited after its cutoff?"),
        primary_metric="fraction_rmsd_under_2A",
        primary_metric_justification=(
            "The fraction of poses within 2 A symmetry-corrected RMSD is the field's "
            "conventional success criterion and the one PoseBusters thresholds on, so it is "
            "comparable to published numbers. It is preferred over mean RMSD because the "
            "RMSD distribution for docking is strongly bimodal — poses are broadly right or "
            "in the wrong subpocket entirely — and a mean over a bimodal distribution "
            "describes neither mode. RMSD is computed with CalcRMS, symmetry-corrected and "
            "IN PLACE after superposing on the binding-pocket backbone only; whole-chain "
            "superposition would charge a global chain shift to the pose, and GetBestRMS "
            "would re-superimpose the ligand and discard the placement error entirely."),
        decision_threshold=(
            "H1 confirmed if the recall stratum achieves fraction_rmsd_under_2A > 0.5; "
            "H2 confirmed if the congeneric-extension stratum is at least 0.2 lower than the "
            "recall stratum; H3 confirmed if PoseBusters physical validity is achieved by "
            "more than 0.8 of poses in both strata."),
        n_planned=n,
        n_comparisons=3,
        multiplicity_correction="holm",
        alpha=0.05,
        test_type="parametric",
        stopping_rule=(
            "Fixed: every curated entry is predicted exactly once at seed 1, in a fixed "
            "order. No entry is added or removed after the first prediction. An entry whose "
            "prediction or scoring fails technically is reported as a failure with its error "
            "and excluded with the exclusion stated."),
        analysis_plan=(
            "For each entry, predict the complex with Boltz-2 2.2.1 from the deposited "
            "construct sequence plus the ligand SMILES, msa=empty, gpu, seed 1, "
            "diffusion_samples 1. Superpose the prediction onto the crystal structure using "
            "backbone atoms within 10 A of the crystal ligand, apply that transform to the "
            "predicted ligand, and compute symmetry-corrected RMSD in place with CalcRMS. "
            "Run PoseBusters in 'redock' mode for physical validity. Report "
            "fraction_rmsd_under_2A per stratum with a Wilson 95% interval, and compare "
            "strata by Fisher exact test. Holm across the three hypotheses."),
        hypotheses=(
            ps.Hypothesis(
                name="H1_recall_accuracy",
                statement=("On complexes that could be in its training set, Boltz-2 places "
                           "the ligand within 2 A more often than not."),
                predicted_by="published docking benchmarks on pre-cutoff data",
                confirmed_if="recall stratum fraction_rmsd_under_2A > 0.5",
                falsified_if="recall stratum fraction_rmsd_under_2A <= 0.5"),
            ps.Hypothesis(
                name="H2_interpolation_premium",
                statement=("Accuracy drops on complexes deposited after the cutoff, i.e. "
                           "some of the recall-stratum accuracy is memorisation rather than "
                           "docking ability."),
                predicted_by=("the leakage argument: a complex in training can be recalled "
                              "rather than predicted"),
                confirmed_if=("congeneric stratum is at least 0.2 below the recall stratum "
                              "in fraction_rmsd_under_2A"),
                falsified_if=("congeneric stratum is less than 0.2 below the recall "
                              "stratum, i.e. no meaningful premium")),
            ps.Hypothesis(
                name="H3_physical_validity",
                statement=("Whatever the placement accuracy, the poses are physically valid "
                           "molecules — correct bond lengths, no internal clashes, not "
                           "interpenetrating the protein."),
                predicted_by=("the claim that a co-folding model produces chemically sound "
                              "output, which PoseBusters was written to test"),
                confirmed_if="PoseBusters validity rate > 0.8 in both strata",
                falsified_if="PoseBusters validity rate <= 0.8 in either stratum"),
        ),
        secondary_metrics=(
            "median_rmsd", "mean_rmsd", "pocket_backbone_rmsd", "fraction_rmsd_under_5A",
            "posebusters_pass_rate", "per_entry_rmsd", "wall_clock_seconds_per_complex",
        ),
        exclusions=(
            "Entries are single-protein-entity X-ray structures under 2.5 A with exactly one "
            "non-polymer entity that is not a crystallisation additive, a ligand of 12-50 "
            "heavy atoms, and a chain under 300 residues. One entry per UniProt accession, so "
            "no single well-studied target dominates. Entries whose ligand cannot be matched "
            "between prediction and crystal are excluded with the reason recorded."),
        known_confounds=(
            "1. THE RECEPTOR-DISJOINT STRATUM DOES NOT EXIST IN THIS STUDY. Every post-cutoff "
            "receptor checked already had pre-cutoff PDB entries (13 to 1172). So H2 measures "
            "the step from 'this exact complex was seen' to 'this pocket was seen with other "
            "ligands', which is the SMALLER of the two gaps the field cares about. Nothing "
            "here bears on novel folds. 2. Predictions run in single-sequence mode, which "
            "Boltz documents as degrading accuracy, so all strata are depressed together and "
            "the DIFFERENCE between strata is the interpretable quantity, not the levels. "
            "3. n is 8 per stratum, so a Wilson interval on a proportion is wide — roughly "
            "+/-0.3 near 0.5 — and only a large premium would be detectable. 4. Deposition "
            "date bounds when coordinates could enter a training snapshot but does not prove "
            "they did; Boltz's split is not published."),
    )


def _fetch_sequence(pdb_id: str) -> str | None:
    """The construct sequence actually crystallised, not the UniProt canonical."""
    try:
        entry = pb._get(f"{pb.RCSB_DATA}/entry/{pdb_id}")
        peid = (entry.get("rcsb_entry_container_identifiers", {})
                .get("polymer_entity_ids") or ["1"])[0]
        pe = pb._get(f"{pb.RCSB_DATA}/polymer_entity/{pdb_id}/{peid}")
        return pe.get("entity_poly", {}).get("pdbx_seq_one_letter_code_can", "").replace("\n", "")
    except Exception:  # noqa: BLE001
        return None


def run() -> None:
    plan = ps.load(STUDY_ID)
    entries = json.loads(SET.read_text())
    rows: list[dict] = []

    for i, e in enumerate(entries, 1):
        pid = e["pdb_id"]
        print(f"[{i}/{len(entries)}] {pid} {e['stratum']:22s} ", end="", flush=True)
        seq = _fetch_sequence(pid)
        if not seq or len(seq) < 30:
            print("no usable sequence")
            rows.append({**e, "ok": False, "error": "no construct sequence"})
            continue
        try:
            ref = pb.fetch_structure(pid, REFS)
        except Exception as exc:  # noqa: BLE001
            print(f"reference download failed: {exc}")
            rows.append({**e, "ok": False, "error": f"ref download: {exc}"})
            continue

        t0 = time.time()
        try:
            res = st.run_boltz(
                [st.Chain("A", seq, "protein", msa="empty"),
                 st.Chain("B", e["ligand_smiles"], "smiles")],
                WORK / pid, accelerator="gpu", seed=1, diffusion_samples=1,
                recycling_steps=3, timeout=3600)
        except Exception as exc:  # noqa: BLE001
            print(f"prediction raised: {exc}")
            rows.append({**e, "ok": False, "error": str(exc)[:200]})
            continue
        dt = time.time() - t0
        model_path = (res.get("files") or {}).get("model")
        if res.get("returncode") != 0 or not model_path:
            # A zero return code with no coordinate file is a real outcome, not a crash:
            # Boltz declines some inputs (e.g. organometallic ligands such as heme) without
            # erroring. The registered plan requires recording it as a failure with its
            # reason rather than letting it abort the study.
            reason = ((res.get("stderr_tail") or "").strip()[-200:]
                      or "returned 0 but produced no coordinate file")
            print(f"no model produced: {reason[:70]}")
            rows.append({**e, "ok": False, "seconds": round(dt, 1), "error": reason})
            continue

        pred_cif = Path(model_path)
        aln = pb.pocket_aligned_rmsd(pred_cif, ref, e["ligand"])
        rec = {**e, "ok": aln.get("ok", False), "seconds": round(dt, 1),
               "pred_cif": str(pred_cif), "ref_cif": str(ref), "alignment": aln}
        if aln.get("ok"):
            import numpy as np
            P = np.array(aln["pred_ligand_xyz"])
            Q = np.array(aln["ref_ligand_xyz"])
            # Without an atom correspondence, report the crude all-atom RMSD only if the
            # counts match; the symmetry-corrected value is computed in the analysis step
            # from written SDFs.
            if len(P) == len(Q):
                rec["naive_rmsd"] = round(float(np.sqrt(((P - Q) ** 2).sum(1).mean())), 3)
            rec["centroid_distance"] = round(
                float(np.linalg.norm(P.mean(0) - Q.mean(0))), 3)
            print(f"{dt:5.1f}s  pocket_bb={aln['pocket_backbone_rmsd']:.2f}A  "
                  f"centroid_d={rec['centroid_distance']:.2f}A")
        else:
            print(f"{dt:5.1f}s  alignment failed: {aln.get('reason')}")
        rows.append(rec)

    RESULT.write_text(json.dumps(
        {"study_id": STUDY_ID, "prespec_hash": plan["hash"],
         "n_observed": sum(1 for r in rows if r.get("ok")), "rows": rows}, indent=1))
    print(f"\nwrote {RESULT.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    if a.register:
        n = len(json.loads(SET.read_text()))
        spec = build_prespec(n)
        problems = spec.check()
        if problems:
            print("NOT REGISTRABLE:")
            for p in problems:
                print("  -", p)
            return 1
        print(f"registered {spec.register().relative_to(REPO)}")
        print(f"  hash {spec.hash()}   n = {n}")
        return 0
    if a.run:
        run()
        return 0
    if a.analyse:
        from cbc import pose_analysis
        return pose_analysis.main(RESULT, STUDY_ID)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
