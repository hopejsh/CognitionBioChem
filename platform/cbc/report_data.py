"""Every artefact the written account reads, and every quantity derived from them.

The English report and the Korean report are two renderings of one set of numbers. Left in
each generator, the binding block would be copied, and a copy is a thing that drifts: the
first time a study is re-run and only one file is updated, the two documents disagree about
a published figure while both claim to be generated. So the bindings live here, once, and
both generators unpack the same dict.

Nothing in this module formats anything. It reads data/ and returns values.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

PY = str(REPO / ".venv" / "bin" / "python")
if not Path(PY).exists():
    PY = sys.executable


def J(p: str) -> Any:
    return json.loads((REPO / p).read_text())


def A(p: str) -> Any:
    d = J(p)
    return d.get("analysis") or d


def suite_count(rel: str) -> int:
    """Run a verification suite and return its passing-check count.

    The count is taken from the suite's own output rather than typed into the prose, and a
    suite with any failing check raises instead of reporting a number -- a document that
    advertises "N checks, each verified to fail on the defect it names" must not be
    publishable while one of them is red.
    """
    r = subprocess.run([PY, rel], cwd=REPO, capture_output=True, text=True)
    m = re.search(r"(\d+) passed, (\d+) failed", r.stdout)
    if not m:
        raise RuntimeError(f"{rel} printed no 'N passed, M failed' line -- cannot count it")
    if int(m.group(2)):
        raise RuntimeError(
            f"{rel} reports {m.group(2)} failing check(s); refusing to build a report that "
            f"claims every check passes")
    return int(m.group(1))


#: The two names a screening artefact can give its native-minus-decoy mean. Study #9 wrote
#: the unpaired name and #10 the paired one; both are the same statistic for this design.
_SEP_KEYS = ("native_minus_decoy_mean", "paired_native_minus_decoy_mean")


def load(*, run_suites: bool = True) -> dict[str, Any]:
    """Read every artefact and derive every quantity the two reports quote."""
    D = {
        "msa": A("data/study_msa_specificity.json"),
        "scr": A("data/study_candidate_screen.json"),
        "iv": A("data/study_inference_variance_analysis.json"),
        "pi": A("data/study_peptide_interface.json"),
        "pa": A("data/study_pose_accuracy.json"),
        "ache": A("data/study_ache_affinity.json"),
        "ac": A("data/study_affinity_corrected.json"),
        "pro": A("data/study_prodigy.json"),
        "slate": J("data/slate.json"),
        "struct": J("data/structures.json"),
        "af": J("data/alphafold_db_comparison.json"),
        "ds": J("data/dataset.json"),
        "refs": J("docs/REFERENCES.json"),
    }
    msa, slate = D["msa"], D["slate"]
    m = msa["metrics"]
    per = msa["per_candidate"]
    ver = slate["separation_across_versions"]

    def _sep(path: str) -> float:
        mm = A(path)["metrics"]
        return next(mm[k] for k in _SEP_KEYS if k in mm)

    # The screen's own lineage, oldest first, so the trajectory of the margin is read from
    # the artefacts rather than transcribed. Both screening studies keep every superseded
    # version; this walks the one whose construct set was corrected three times.
    scr_line = sorted((v["artefact"] for v in ver["versions"]
                       if "candidate_screen" in v["artefact"]),
                      key=lambda a: (0, a) if "superseded" in a else (1, a))
    winners = sorted((p for p in per if p["beats_all_decoys"]),
                     key=lambda p: -p["difference"])
    retr = [x for x in D["ds"]["candidates"] if "retracted_claims" in x]
    aud = [x["retracted_claims"]["thermodynamic_audit"] for x in retr]

    D.update({
        "cit": D["ds"]["citation"],
        "m": m,
        "c": slate["counts"],
        "nul": m["beats_all_decoys_null"],
        "ver": ver,
        "per": per,
        "n_decoys": max(p["n_decoys"] for p in per),
        "winners": winners,
        # The formatted margins, unjoined: an English " and " baked in here surfaced verbatim
        # in the Korean edition. Each generator joins them in its own language.
        "win_margin_values": [format(w["native_iptm"] - w["decoy_max"], "+.3f")
                              for w in winners],
        "win_margins": " and ".join(
            format(w["native_iptm"] - w["decoy_max"], "+.3f") for w in winners),
        "scr_series": [_sep(a) for a in scr_line],
        "scr_decoys": len({r["kind"] for r in J("data/study_candidate_screen.json")["rows"]
                           if r["kind"] != "native"}),
        "retr": retr,
        "aud": aud,
        "runs": len(J("runs/manifest.json")["runs"]),
        # The custody test counts rows the study reports as having produced a result; a row
        # whose fold failed carries ok=False and has no run to resolve.
        "published_rows": sum(
            sum(1 for r in J(f"data/study_{k}.json")["rows"] if r.get("ok") is not False)
            for k in ("candidate_screen", "msa_specificity", "inference_variance",
                      "pose_accuracy", "peptide_interface", "ache_affinity")),
        "plans": len(list((REPO / "prespec").glob("*.json"))),
        "gate_pl": [r["peptide_len"] for r in J("data/study_peptide_interface.json")["rows"]],
        "gate_rl": [r["receptor_len"] for r in J("data/study_peptide_interface.json")["rows"]],
        "cand_pl": [len(r["peptide_used"])
                    for r in J("data/study_msa_specificity.json")["rows"]],
        "cand_rl": [r["receptor_len"]
                    for r in J("data/study_msa_specificity.json")["rows"]],
        "att": D["ds"]["disclosure"]["sequence_attribution_counts"],
        "n_checks": (suite_count("platform/tests/test_platform.py")
                     + suite_count("platform/verify_frontend.py")) if run_suites else None,
    })
    return D
