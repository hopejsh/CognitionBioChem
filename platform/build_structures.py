"""Build data/structures.json: an index of every real structure this repository can show.

The workbench has always been able to display a prediction -- but only one a reader dragged
in from their own AlphaFold or Boltz run. Meanwhile the repository itself holds hundreds of
folds it computed, under custody in runs/, and the viewer could not reach a single one of
them. A reader clicking a candidate saw its sequence, its liabilities and its ipTM, and no
structure at all, which is the one thing a structure viewer is for.

This index closes that gap. It publishes exactly one derived number and labels it as one:
`interface_pae`, computed here from the retained PAE array. Everything else is copied from a
retained run's own confidence JSON or parsed from its own mmCIF, and every entry names the run
directory it came from so a reader can open the same file.

THREE GROUPS, AND THEY ARE NOT INTERCHANGEABLE.

  peptide_monomer   the designed peptide folded ALONE, single sequence. There is no receptor
                    and therefore no ipTM. A high pLDDT here says the peptide has a definite
                    shape, not that it binds anything.
  complex           the candidate folded WITH its receptor construct, full MSA (study #10).
                    This is the fold the slate's ipTM comes from. Chain A is the receptor,
                    chain B the peptide.
  receptor_afdb     AlphaFold DB's deposited monomer for the receptor. Downloaded under
                    CC BY 4.0, not computed here, and shown as the independent reference it
                    is -- a different model's opinion about the same protein.

WHAT IS DELIBERATELY NOT INDEXED. Decoys. Every complex has ten composition-matched
scrambles whose folds are retained, and several of them score ABOVE their native. They are
the reason the slate's answer is negative and they are reported in the README, but putting
them in a structure picker invites a reader to browse for the best-looking one, which is the
exact error the null was built to prevent. The gallery shows natives; the numbers show both.
"""

from __future__ import annotations

import json
import subprocess
import sys

from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np                                                  # noqa: E402

from cbc.predictor import parse_mmcif                               # noqa: E402
from cbc.provenance import git_sha                                  # noqa: E402
from studies.candidate_screen import CANDIDATE_TARGETS              # noqa: E402

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "runs" / "manifest.json"
OUT = REPO / "data" / "structures.json"
OUT_JS = REPO / "data" / "structures.js"
PAE_DIR = REPO / "data" / "pae"

# A PAE matrix is n_tokens^2 floats, and the page fetches exactly one of them at a time,
# only when a reader opens that structure. The largest complex here is 649 tokens -- 2.2 MB
# of JSON -- which is the same order as the deposited AlphaFold DB matrices the page already
# serves and renders without trouble. The cap exists to stop something pathological, not to
# exclude the complexes: an interface PAE is the one quantity that says whether the peptide
# is PLACED against the receptor rather than merely folded, and study #7 measured that it
# tracks DockQ. Omitting it left a 0.81 ipTM standing on the page with nothing beside it.
PAE_MAX_TOKENS = 1024


def sha() -> str | None:
    """Delegates to cbc.provenance.git_sha, which marks a dirty tree. See its docstring."""
    return git_sha(REPO)


def runs_by_kind(kind: str) -> list[dict]:
    return [r for r in json.loads(MANIFEST.read_text())["runs"] if r.get("kind") == kind]


def has_ligand(cif: Path) -> bool:
    """True when the model carries a non-polymer atom. Decides whether `ligand_iptm` means
    anything for this structure, rather than assuming it never does."""
    _res, _chains, lig = parse_mmcif(cif)
    return bool(lig)


def chains_of(cif: Path) -> list[dict]:
    residues, chain_ids, _lig = parse_mmcif(cif)
    out = []
    for c in chain_ids:
        rs = [r for r in residues if r.chain == c]
        vals = [r.plddt for r in rs if r.plddt is not None]
        # DEFENSIVE, NOT ACTIVE. An earlier comment here claimed "Boltz writes pLDDT as a
        # fraction", which is false and was worth checking rather than believing: all 35
        # Boltz models under custody carry 0-100 in the mmCIF B-factor column (global range
        # 29.78-98.94), so this branch has never fired. The fraction appears in the
        # confidence JSON, which is a different file. The guard stays because a mixed-scale
        # file would otherwise be drawn on the wrong colour ramp in silence, but no reader
        # should be told a transform happens that does not.
        if vals and max(vals) <= 1.0:
            vals = [v * 100.0 for v in vals]
        out.append({"id": c, "length": len(rs),
                    "mean_plddt": round(sum(vals) / len(vals), 2) if vals else None,
                    # `metrics.complex_plddt` is copied from the confidence JSON on 0-1 while
                    # this is parsed from the B-factor column on 0-100, and both sat in one
                    # entry unlabelled -- the exact 0.96-beside-97.5 hazard the parser's own
                    # docstring warns about, shipped in the index.
                    "mean_plddt_scale": "0-100 (parsed from the mmCIF B-factor column)"})
    return out


def interface_pae(arr, chains: list[dict]) -> dict | None:
    """Mean and minimum PAE across the first chain pair, computed here from the same array.

    This is a DESCRIPTIVE quantity attached to a displayed structure, not a study result: no
    plan registered it, no hypothesis turns on it, and it appears in no verdict. It is
    included because study #7 measured that interface PAE tracks DockQ, so a reader looking
    at a complex should be able to see whether the peptide is placed confidently against the
    receptor, not only how the complex scored.
    """
    if len(chains) < 2:
        return None
    n_a = chains[0]["length"]
    n_b = chains[1]["length"]
    if n_a + n_b > arr.shape[0]:
        # Ligand or modified-residue tokens shift the mapping; refusing is the only honest
        # option, because a wrong slice would still produce a plausible number.
        return None
    block = arr[:n_a, n_a:n_a + n_b]
    block_t = arr[n_a:n_a + n_b, :n_a]
    both = np.concatenate([block.ravel(), block_t.ravel()])
    return {"chain_pair": f"{chains[0]['id']}-{chains[1]['id']}",
            "mean_pae": round(float(both.mean()), 2),
            "min_pae": round(float(both.min()), 2),
            "n_pairs": int(both.size),
            "note": "descriptive, computed here from the retained array; not a "
                    "pre-registered quantity and not part of any verdict"}


def write_pae(run: Path, entry_id: str) -> tuple[str | None, dict | None]:
    """Emit the PAE matrix as browser-readable JSON, and the interface summary beside it."""
    npz = sorted(run.glob("*pae*.npz"))
    if not npz:
        return None, None
    arr = np.load(npz[0])["pae"]
    if arr.shape[0] > PAE_MAX_TOKENS:
        return None, None
    PAE_DIR.mkdir(parents=True, exist_ok=True)
    out = PAE_DIR / f"{entry_id}.json"
    body = json.dumps({
        "source": str(npz[0].relative_to(REPO)),
        "n_tokens": int(arr.shape[0]),
        "max": round(float(arr.max()), 2),
        # One decimal is 0.1 A on a 0-32 A scale -- below any resolution a reader can see in
        # a heat map, and it keeps the file a third of the size of full float repr.
        "matrix": [[round(float(v), 1) for v in row] for row in arr],
    })
    # Only touch the file when its content actually changes. The staleness test in
    # platform/tests/test_platform.py runs this generator and restores the index afterwards;
    # rewriting 35 identical matrices every time would leave those files modified in `git
    # status` for no reason, so a test that changes nothing now changes nothing on disk.
    if not out.exists() or out.read_text() != body:
        out.write_text(body)
    return str(out.relative_to(REPO)), arr


def confidence(run: Path, n_chains: int, has_ligand: bool) -> dict:
    """Confidences copied from the run's own JSON, with terms that score nothing removed.

    Boltz emits a full confidence block whatever it folded, so a zero appears wherever the
    quantity is undefined rather than bad. Two of those zeros were being published:

      * `iptm`, `protein_iptm`, `ligand_iptm` on a SINGLE-CHAIN fold. There is no interface;
        beside a designed peptide, `ipTM 0` reads as the worst possible binding result, which
        is the opposite of "undefined".
      * `ligand_iptm` on all 13 two-chain PROTEIN complexes. Not one contains a ligand, so
        that 0.0 is the same defect one column over -- and it shipped in the artefact the page
        links, in a file whose header claims no value here is unearned.

    `complex_iplddt` goes with them for monomers: Boltz emits it byte-identical to
    `complex_plddt` there, so it is a duplicate wearing an interface name.
    """
    f = sorted(run.glob("*confidence*.json"))
    if not f:
        return {}
    d = json.loads(f[0].read_text())
    keep = ("iptm", "ptm", "complex_plddt", "complex_iplddt", "ligand_iptm", "protein_iptm")
    out = {k: round(v, 4) for k, v in d.items()
           if k in keep and isinstance(v, (int, float))}
    if out:
        out["scale"] = ("0-1, as the predictor's confidence JSON writes them. Per-chain "
                        "mean_plddt elsewhere in this entry is 0-100, parsed from the "
                        "model's B-factor column; the two are the same quantity on "
                        "different scales.")
    # Two distinct reasons, and they must not be merged into one sentence: the ipTM family is
    # dropped because the predictor emitted a literal 0.0 for a quantity with no referent,
    # while complex_iplddt is dropped because on a monomer Boltz emits it byte-identical to
    # complex_plddt. Saying complex_iplddt "= 0.0" would be a false statement about the file.
    zeros = sorted({k for k in out if "iptm" in k
                    and (n_chains < 2 or (k == "ligand_iptm" and not has_ligand))})
    dupes = ["complex_iplddt"] if (n_chains < 2 and "complex_iplddt" in out) else []
    for k in zeros + dupes:
        out.pop(k, None)
    why = []
    if zeros:
        reason = ("this model has one chain, so it has no interface" if n_chains < 2
                  else "this model contains no ligand")
        why.append(f"{reason}, and the predictor emitted {', '.join(zeros)} = 0.0 — "
                   "an absence rather than a score")
    if dupes:
        why.append("complex_iplddt is emitted byte-identical to complex_plddt for a "
                   "single-chain model, so it carries no information of its own")
    if why:
        out["terms_undefined"] = "; ".join(why) + ". They are not published here."
    return out


def build() -> int:
    screen = json.loads((REPO / "data" / "study_candidate_screen.json").read_text())
    msa = json.loads((REPO / "data" / "study_msa_specificity.json").read_text())
    afcmp = json.loads((REPO / "data" / "alphafold_db_comparison.json").read_text())
    dataset = json.loads((REPO / "data" / "dataset.json").read_text())
    registry = json.loads((REPO / "data" / "target_registry.json").read_text())["targets"]
    known_codes = {c["code"] for c in dataset["candidates"]}

    entries: list[dict] = []

    # -- 1. designed peptides folded alone ------------------------------------------------ #
    # Each peptide was folded twice and both runs are retained, but only one of the pair kept
    # its PAE array -- the retention policy stores PAE for `candidate-fold`, and the earlier
    # of the two runs predates it. Taking whichever came first alphabetically threw away every
    # PAE matrix in the index, so prefer the run that HAS one, then the newer.
    by_job: dict[str, list[Path]] = {}
    for r in runs_by_kind("candidate-fold"):
        by_job.setdefault(r["job"], []).append(REPO / r["path"])
    for code in sorted(by_job):
        # Tie-break on the run directory NAME, which is the content hash of the run, not on
        # mtime. git does not preserve mtime, so an mtime tie-break makes the published
        # structure depend on checkout order: two clones of the same commit could show
        # different folds of the same peptide, with no way to tell which.
        run = max(by_job[code], key=lambda d: (bool(list(d.glob("*pae*.npz"))), d.name))
        cifs = sorted(run.glob("*.cif"))
        if not cifs:
            continue
        eid = f"pep-{code}"
        chains = chains_of(cifs[0])
        pae_path, _arr = write_pae(run, eid)
        entries.append({
            "id": eid, "group": "peptide_monomer", "code": code, "target": None,
            "label": f"{code} — peptide alone",
            "cif": str(cifs[0].relative_to(REPO)),
            "pae": pae_path,
            "chains": [dict(c, role="designed peptide") for c in chains],
            "metrics": confidence(run, len(chains), has_ligand(cifs[0])),
            "in_dataset": code in known_codes,
            "provenance": {"predictor": "Boltz-2 v2.2.1", "msa": "empty (single sequence)",
                           "run": str(run.relative_to(REPO)), "kind": "candidate-fold",
                           "note": "monomer fold; no receptor is present, so there is no "
                                   "ipTM and nothing here speaks to binding"},
        })

    # -- 2. candidate + receptor complexes, from the study the slate reports -------------- #
    per = {p["code"]: p for p in msa["analysis"]["per_candidate"]}
    idx: dict[str, list[Path]] = {}
    for r in runs_by_kind("msa-specificity"):
        for name in [r["job"], *(r.get("identical_jobs") or [])]:
            idx.setdefault(name, []).append(REPO / r["path"])
    for row in sorted((x for x in msa["rows"] if x.get("kind") == "native" and x.get("ok")),
                      key=lambda x: x["code"]):
        code = row["code"]
        want = row["receptor_len"]
        # Aliases accumulate across study versions, so select the run whose chain A actually
        # holds the construct this row says it folded rather than the first one listed.
        # Two runs can hold the same model: rescuing the PAE array changed the run's content
        # hash, so the fold now exists both with and without it. Both match on chain length,
        # and ordering by mtime alone picked between them at random -- which silently dropped
        # every interface PAE from the index. Prefer the copy that carries the array.
        pick = None
        for run in sorted(idx.get(f"{code}_native", []),
                          key=lambda d: (-len(list(d.glob("*pae*.npz"))), d.name)):
            cifs = sorted(run.glob("*.cif"))
            if cifs and next((c["length"] for c in chains_of(cifs[0]) if c["id"] == "A"), 0) == want:
                pick = (run, cifs[0])
                break
        if pick is None:
            continue
        run, cif = pick
        eid = f"cpx-{code}"
        chains = chains_of(cif)
        roles = {"A": f"{row['target']} receptor construct", "B": "designed peptide"}
        p = per.get(code, {})
        pae_path, arr = write_pae(run, eid)
        entries.append({
            "id": eid, "group": "complex", "code": code, "target": row["target"],
            "label": f"{code} + {row['target']}",
            "cif": str(cif.relative_to(REPO)),
            "pae": pae_path,
            "interface_pae": interface_pae(arr, chains) if arr is not None else None,
            "chains": [dict(c, role=roles.get(c["id"], "chain " + c["id"])) for c in chains],
            "metrics": confidence(run, len(chains), has_ligand(cif)),
            "construct": row["construct"],
            # `empirical_p` and `iptm_study9` were dropped from this block, and both are
            # what stops a green "beats all decoys" from being read as a hit: the empirical p
            # of BOTH winners is 0.0909, which clears no conventional threshold, and one of
            # them scored 0.221 without an MSA. Carrying the verdict without the numbers that
            # qualify it is how a null gets quietly discarded at the display layer.
            "screen": {"native_iptm": p.get("native_iptm"), "decoy_mean": p.get("decoy_mean"),
                       "decoy_max": p.get("decoy_max"), "n_decoys": p.get("n_decoys"),
                       "beats_all_decoys": p.get("beats_all_decoys"),
                       "band": p.get("band"),
                       "empirical_p": p.get("empirical_p"),
                       "iptm_without_msa": (round(p["iptm_study9"], 4)
                                            if p.get("iptm_study9") is not None else None),
                       "delta_vs_single_sequence": p.get("delta_vs_study9"),
                       "decoy_mean_beats_native": (
                           p.get("decoy_mean") is not None
                           and p["decoy_mean"] > p.get("native_iptm", 0))},
            "in_dataset": code in known_codes,
            "provenance": {"predictor": "Boltz-2 v2.2.1", "msa": "full (--use_msa_server)",
                           "run": str(run.relative_to(REPO)), "kind": "msa-specificity",
                           "study": "data/study_msa_specificity.json",
                           "plan": msa["analysis"]["prespec_hash"],
                           "note": "the fold study #10 scored. Its ten composition-matched "
                                   "decoys are retained but deliberately not in this picker"},
        })

    # -- 3. AlphaFold DB receptors -------------------------------------------------------- #
    cmp_by_target = {x["target"]: x for x in afcmp["arms"]["boltz_full_msa"]["rows"]}
    afdir = REPO / "data" / "alphafold_db"
    for symbol in sorted(p.name for p in afdir.iterdir() if p.is_dir()):
        cifs = sorted((afdir / symbol).glob("*.cif"))
        if not cifs:
            continue
        pae_json = sorted((afdir / symbol).glob("*predicted_aligned_error*.json"))
        eid = f"afdb-{symbol}"
        entries.append({
            "id": eid, "group": "receptor_afdb", "code": None, "target": symbol,
            "label": f"{symbol} — AlphaFold DB",
            "cif": str(cifs[0].relative_to(REPO)),
            # Deposited PAE is already JSON and is left where it is; a 600x600 matrix is not
            # copied into data/pae/ just to change its filename.
            "pae": str(pae_json[0].relative_to(REPO)) if pae_json else None,
            "pae_format": "alphafold_db" if pae_json else None,
            "chains": [dict(c, role=f"{symbol} full canonical sequence")
                       for c in chains_of(cifs[0])],
            "metrics": {},
            "uniprot": registry[symbol]["uniprot"],
            "comparison": ({"pearson_r": cmp_by_target[symbol]["pearson_r"],
                            "n_residues_compared": cmp_by_target[symbol]["n_residues_compared"],
                            "afdb_mean_plddt": cmp_by_target[symbol]["afdb_mean_plddt"],
                            "boltz_mean_plddt": cmp_by_target[symbol]["boltz_mean_plddt"]}
                           if symbol in cmp_by_target else None),
            "in_dataset": True,
            "provenance": {"predictor": "AlphaFold (deposited model)",
                           "msa": "full (as deposited)",
                           "source": "AlphaFold Protein Structure Database",
                           "url": f"https://alphafold.ebi.ac.uk/entry/{registry[symbol]['uniprot']}",
                           "licence": "CC BY 4.0",
                           "note": "downloaded, not computed here. AlphaFold Server was not "
                                   "used: its terms prohibit automated use for "
                                   "protein-peptide binding prediction"},
        })

    by_candidate: dict[str, list[str]] = {}
    for e in entries:
        if e["code"]:
            by_candidate.setdefault(e["code"], []).append(e["id"])

    groups = {g: sum(1 for e in entries if e["group"] == g)
              for g in ("peptide_monomer", "complex", "receptor_afdb")}
    # Measure the coverage gap rather than describing it from memory: an earlier note said
    # every unfolded candidate was either invalid or a duplicate, and four are neither.
    seqs = {c["code"]: c["sequence"] for c in dataset["candidates"]}
    validity = {c["code"]: c["valid"] for c in dataset["candidates"]}
    with_fold = {e["code"] for e in entries if e["code"]}
    folded_seqs = {seqs[c] for c in with_fold if c in seqs}
    # Why a catalogued candidate has no COMPLEX, computed rather than described. The three
    # causes are different and were being merged into one sentence with a wrong count.
    cpx_pairs = {(seqs[e["code"]], e["target"]) for e in entries
                 if e["group"] == "complex" and e["code"] in seqs}
    with_cpx = {e["code"] for e in entries if e["group"] == "complex"}
    n_never_nominated = sum(1 for c in seqs if c not in CANDIDATE_TARGETS)
    deduped = sorted(c for c in seqs
                     if c not in with_cpx and c in CANDIDATE_TARGETS
                     and (seqs[c], CANDIDATE_TARGETS[c]) in cpx_pairs)
    n_deduped = len(deduped)
    unfolded = [c for c in seqs if c not in with_fold]
    n_invalid = sum(1 for c in unfolded if not validity[c])
    n_shared = sum(1 for c in unfolded if validity[c] and seqs[c] in folded_seqs)
    orphan = [c for c in unfolded if validity[c] and seqs[c] not in folded_seqs]
    n_orphan = len(orphan)
    n_screened = len(msa["analysis"]["per_candidate"])
    index = {
        "schema_version": "1.0",
        "built": date.today().isoformat(),
        "git_sha": sha(),
        "note": "Every entry points at a file under custody in this repository. Confidences "
                "are copied verbatim from each run's own confidence JSON, and every value in "
                "`screen` is copied from study #10's artefact. FOUR things are derived here "
                "and are the only ones: `interface_pae` (mean and minimum PAE across the two "
                "chains, from the retained array), `chains[].mean_plddt` (a mean over the "
                "B-factor column), `screen.decoy_mean_beats_native` (a comparison of two "
                "copied values, which the study did not make) and the `coverage` counts. An "
                "earlier version of this sentence said exactly one quantity was derived, "
                "which was wrong by three.",
        "groups": groups,
        "coverage": {
            "candidates_in_dataset": len(known_codes),
            "candidates_with_a_peptide_fold": sum(
                1 for c in known_codes if any(e["group"] == "peptide_monomer"
                                              and e["code"] == c for e in entries)),
            "candidates_with_a_complex": sum(
                1 for c in known_codes if any(e["group"] == "complex"
                                              and e["code"] == c for e in entries)),
            "candidates_screened_in_study_10": n_screened,
            "note": (
                f"Not every catalogued candidate has a fold, and the reasons do not cover "
                f"all of them. Of the {len(known_codes) - len(by_candidate)} catalogued "
                f"candidates with no fold at all: {n_invalid} fail sequence validation and "
                f"were never submitted to a predictor; {n_shared} carry a sequence that is "
                f"byte-identical to one that WAS folded, so the computation exists under "
                f"another code; and {n_orphan} are valid, carry a sequence nothing else "
                f"shares, and were simply never folded -- {', '.join(sorted(orphan))}. That "
                f"last group is an omission, not a policy, and is stated rather than "
                f"absorbed into the first two."),
            "complex_group_is_study_10": (
                f"The {groups['complex']} complexes are not a selection from the "
                f"{groups['peptide_monomer']} peptides -- they ARE study #10's native rows, "
                f"so the decomposition is: of {len(known_codes)} catalogued candidates, "
                f"{n_never_nominated} were never nominated for a receptor complex at all "
                f"(they appear in no target map, so no complex was ever attempted for them), "
                f"{n_deduped} was dropped by the screen's de-duplication on (peptide, target) "
                f"because an earlier code carries the identical pair "
                f"({', '.join(deduped) or 'none'}), and the rest were folded. The earlier "
                f"wording said five codes were de-duplication casualties; one is, and the "
                f"other four share a peptide with a folded complex against a DIFFERENT "
                f"target, which is a different situation and was being counted as the same "
                f"one."),
        },
        "not_indexed": {
            "decoys": "Each complex has 10 composition-matched scrambles under custody. They "
                      "are excluded from this picker on purpose: several score above their "
                      "own native, and letting a reader browse for the best-looking fold is "
                      "the error the null exists to prevent.",
        },
        "entries": entries,
        "by_candidate": by_candidate,
    }
    OUT.write_text(json.dumps(index, indent=2) + "\n")
    OUT_JS.write_text("// GENERATED by platform/build_structures.py -- do not edit.\n"
                      "// Byte-for-byte the same object as data/structures.json; this form\n"
                      "// exists only so the page still works when opened from a file: URL.\n"
                      "window.__CBC_STRUCTURES__ = " + json.dumps(index, indent=2) + ";\n")
    print(f"wrote {OUT.relative_to(REPO)} and {OUT_JS.relative_to(REPO)}")
    for g, n in groups.items():
        print(f"  {g:16s} {n}")
    print(f"  PAE matrices emitted: {sum(1 for e in entries if e['pae'] and e['group'] != 'receptor_afdb')}")
    print(f"  interface PAE computed: {sum(1 for e in entries if e.get('interface_pae'))}")
    print(f"  candidates with a complex: {index['coverage']['candidates_with_a_complex']}"
          f" of {index['coverage']['candidates_in_dataset']} catalogued")
    missing = [e["id"] for e in entries if not (REPO / e["cif"]).exists()]
    if missing:
        print(f"  BROKEN: {len(missing)} entries point at a file that does not exist")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
