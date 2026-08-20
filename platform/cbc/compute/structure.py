#!/usr/bin/env python3
"""Structure prediction backends — real inference, not synthesis.

The platform previously drew a helix from ASCII character codes and labelled it
"AlphaFold3". This module runs actual models instead, and where no model can legally or
practically be run it says so rather than substituting one silently.

Backend selection is explicit and reported. A caller always knows which model produced a
structure, because the model name and version travel with the result.

Why not AlphaFold 3 itself
--------------------------
AF3 model parameters are available only on request from Google DeepMind, under terms that
forbid redistribution and commercial use, and the AlphaFold Server's prohibited-use policy
forbids automated prediction of protein-ligand and protein-peptide binding — which is
precisely what this platform would need. So AF3 cannot be an automated backend here. Boltz-2
is an AF3-class architecture under MIT licence and is used in its place, which is a licensing
substitution, not a scientific equivalence claim: the two models are not the same and their
outputs should not be reported interchangeably.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parents[3]

#: Heavy neural backends live in a separate Python 3.12 environment: Boltz pins a scipy with
#: no cp314 wheel, so it cannot be installed alongside the main 3.14 tooling.
VENV312 = REPO / ".venv312"
BOLTZ_BIN = VENV312 / "bin" / "boltz"


class BackendUnavailable(RuntimeError):
    """Raised when a backend cannot run here. Always explains why and what to do."""


@dataclass
class BackendInfo:
    name: str
    version: str
    licence: str
    available: bool
    reason: str = ""
    hardware: str = ""
    outputs: list[str] = field(default_factory=list)
    citation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "licence": self.licence,
                "available": self.available, "reason": self.reason,
                "hardware": self.hardware, "outputs": self.outputs,
                "citation": self.citation}


# --------------------------------------------------------------------------- #
# Backend registry
# --------------------------------------------------------------------------- #

def boltz_info() -> BackendInfo:
    if not BOLTZ_BIN.exists():
        return BackendInfo(
            "boltz-2", "unknown", "MIT", False,
            reason=(f"boltz CLI not found at {BOLTZ_BIN}. Create the 3.12 environment: "
                    f"`/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv312 && "
                    f"./.venv312/bin/pip install boltz`. It cannot be installed into the "
                    f"3.14 environment because it pins a scipy with no cp314 wheel."),
            citation="Wohlwend et al., Boltz-1 (2024); Passaro et al., Boltz-2 (2025)")
    ver = "unknown"
    try:
        out = subprocess.run([str(VENV312 / "bin" / "python"), "-c",
                              "import boltz; print(boltz.__version__)"],
                             capture_output=True, text=True, timeout=60)
        ver = out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        pass
    return BackendInfo(
        "boltz-2", ver, "MIT", True,
        hardware="CPU works but is slow; a GPU is strongly preferred",
        outputs=["*_model_*.cif", "confidence_*.json (confidence_score, ptm, iptm, "
                 "complex_plddt)", "pae_*.npz", "plddt_*.npz", "affinity_*.json"],
        citation="Wohlwend et al., Boltz-1 (2024); Passaro et al., Boltz-2 (2025)")


def alphafold_db_info() -> BackendInfo:
    return BackendInfo(
        "alphafold-db", "v6", "CC-BY-4.0", True,
        hardware="none: retrieval, not inference",
        reason="Retrieves an existing AlphaFold 2 prediction by UniProt accession. It "
               "cannot predict a designed sequence, only proteins already in the database.",
        outputs=["AF-<ACC>-F1-model_v*.cif", "*predicted_aligned_error*.json"],
        citation="Varadi et al., Nucleic Acids Res (2022, 2024)")


def alphafold3_info() -> BackendInfo:
    return BackendInfo(
        "alphafold-3", "n/a", "weights: request-only, non-commercial, non-redistributable",
        False,
        reason=("AF3 weights require a request to Google DeepMind and may not be "
                "redistributed, so they cannot be shipped or auto-installed. Separately, "
                "the AlphaFold Server terms prohibit automated use for predicting "
                "protein-ligand or protein-peptide binding, which is what this platform "
                "would need. Use Boltz-2, Chai-1, Protenix or OpenFold3 for automation, or "
                "run AF3 manually under your own licence and load the output files."),
        outputs=["<job>_model_*.cif", "<job>_full_data_*.json",
                 "<job>_summary_confidences_*.json"],
        citation="Abramson et al., Nature 634:493 (2024)")


def esmfold_api_info() -> BackendInfo:
    return BackendInfo(
        "esmfold-api", "n/a", "MIT (model)", False,
        reason=("The ESM Atlas fold endpoint returns cached results only. Measured: a "
                "well-known 33-mer returns in 0.7 s with a 2022 HEADER date, while any "
                "novel sequence — including a 20-mer — returns HTTP 504 Gateway Time-out. "
                "The endpoint no longer computes new folds, so it must not be relied on."),
        citation="Lin et al., Science 379:1123 (2023)")


def available_backends() -> list[BackendInfo]:
    return [boltz_info(), alphafold_db_info(), alphafold3_info(), esmfold_api_info()]


# --------------------------------------------------------------------------- #
# Boltz-2
# --------------------------------------------------------------------------- #

@dataclass
class Chain:
    """One entity in a prediction job."""
    chain_id: str
    sequence: str
    kind: str = "protein"        # protein | dna | rna | ccd | smiles
    msa: str = "empty"           # 'empty' disables MSA search; state this in provenance


def _write_boltz_input(chains: Sequence[Chain], path: Path,
                       affinity_binder: str | None = None) -> Path:
    """Boltz YAML input. Used rather than FASTA because it is the only form that
    supports ligands and the affinity head."""
    lines = ["version: 1", "sequences:"]
    for c in chains:
        if c.kind in ("protein", "dna", "rna"):
            lines += [f"  - {c.kind}:", f"      id: {c.chain_id}",
                      f"      sequence: {c.sequence}"]
            if c.kind == "protein" and c.msa is not None:
                # Omit the key entirely when the MSA is to be generated: writing
                # `msa: None` is a literal string Boltz silently ignores, and the run then
                # exits 0 in ~3 s having produced nothing. Absent means "generate it".
                lines.append(f"      msa: {c.msa}")
        elif c.kind == "smiles":
            lines += ["  - ligand:", f"      id: {c.chain_id}",
                      f"      smiles: '{c.sequence}'"]
        elif c.kind == "ccd":
            lines += ["  - ligand:", f"      id: {c.chain_id}",
                      f"      ccd: {c.sequence}"]
    if affinity_binder:
        lines += ["properties:", "  - affinity:", f"      binder: {affinity_binder}"]
    path.write_text("\n".join(lines) + "\n")
    return path


def boltz_cmd(yaml_path: str | Path, out: str | Path, *, accelerator: str = "cpu",
              recycling_steps: int = 3, diffusion_samples: int = 1,
              seed: int | None = None, use_msa_server: bool = False,
              sampling_steps: int | None = None) -> list[str]:
    """The exact argv Boltz is invoked with. Extracted so that anything reasoning about a
    previous run's identity builds it from the same code the run itself used."""
    cmd = [str(BOLTZ_BIN), "predict", str(yaml_path),
           "--out_dir", str(out), "--accelerator", accelerator,
           "--recycling_steps", str(recycling_steps),
           "--diffusion_samples", str(diffusion_samples),
           "--output_format", "mmcif", "--override"]
    # Without an explicit seed the sampler is unseeded, so a run cannot be repeated and the
    # across-seed variance of pLDDT/ipTM cannot be measured. Any structural number
    # interpreted without that envelope is being read to a precision it does not have.
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if use_msa_server:
        cmd += ["--use_msa_server"]
    if sampling_steps is not None:
        cmd += ["--sampling_steps", str(sampling_steps)]
    return cmd


def run_stamp(yaml_path: str | Path, out: str | Path, cmd: list[str],
              version: str) -> dict[str, Any]:
    """Identity of a run: the hash of the input Boltz consumed plus every sampling argument
    that lives on the command line rather than in the input file."""
    return {
        "input_yaml_sha256": hashlib.sha256(Path(yaml_path).read_bytes()).hexdigest(),
        "argv": [a for a in cmd[1:] if a not in (str(yaml_path), str(out))],
        "boltz_version": version,
    }


def run_boltz(chains: Sequence[Chain], out_dir: str | Path, *,
              affinity_binder: str | None = None, accelerator: str = "cpu",
              recycling_steps: int = 3, diffusion_samples: int = 1,
              timeout: int = 14400, seed: int | None = None,
              use_msa_server: bool = False,
              sampling_steps: int | None = None,
              reuse: bool = False) -> dict[str, Any]:
    """Run a real Boltz-2 prediction.

    `affinity_binder` names the ligand chain whose binding affinity should be predicted by
    Boltz-2's affinity head. That head is trained for small-molecule binders; do not point
    it at a protein chain and report the result as a peptide affinity.

    MSA note: `msa: empty` runs single-sequence mode. That is faster and needs no database,
    but single-sequence prediction is markedly less accurate than MSA-based prediction for
    natural proteins. The setting is recorded in the returned provenance so a reader can see
    which mode produced the structure.
    """
    info = boltz_info()
    if not info.available:
        raise BackendUnavailable(info.reason)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    yaml_path = _write_boltz_input(chains, out / "input.yaml", affinity_binder)

    cmd = boltz_cmd(yaml_path, out, accelerator=accelerator,
                    recycling_steps=recycling_steps, diffusion_samples=diffusion_samples,
                    seed=seed, use_msa_server=use_msa_server, sampling_steps=sampling_steps)
    # Content-addressed reuse. The manifest records a hash of the exact input.yaml Boltz
    # consumes plus every sampling argument that is passed on the command line rather than in
    # the yaml. Reuse happens only on an exact match of both, so changing the receptor
    # construct, the peptide, the seed or the recycling depth forces a recompute; a directory
    # keyed on a run label alone would have silently returned the old structure instead.
    manifest = out / "run_manifest.json"
    stamp = run_stamp(yaml_path, out, cmd, info.version)
    if reuse and manifest.exists():
        try:
            prior = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            prior = None
        if prior == stamp:
            cached = _collect_boltz_outputs(out)
            # The manifest alone is not sufficient evidence. A run that was interrupted, or
            # that itself consumed a stale preprocessing cache, can leave a manifest naming
            # the CURRENT input beside a model built from a PREVIOUS one -- which is exactly
            # what happened here once. So the cached model is checked against the requested
            # chains before it is trusted, and a mismatch falls through to a real run rather
            # than being reported as a reuse.
            has_conf = ((cached.get("confidence") or {}).get("iptm") is not None or
                        (cached.get("confidence") or {}).get("complex_plddt") is not None)
            if has_conf and not _chain_length_mismatch(chains, cached):
                return {"backend": "boltz-2", "version": info.version, "licence": "MIT",
                        "citation": info.citation, "command": " ".join(cmd),
                        "returncode": 0, "accelerator": accelerator,
                        "msa_mode": chains[0].msa if chains else "unknown",
                        "recycling_steps": recycling_steps,
                        "diffusion_samples": diffusion_samples, "seed": seed,
                        "use_msa_server": use_msa_server, "sampling_steps": sampling_steps,
                        "stdout_tail": "", "stderr_tail": "", "reused": True, **cached}

    # Boltz's --override replaces the PREDICTIONS but not the preprocessing cache under
    # boltz_results_*/processed/, which is keyed on the input record NAME. Rerunning into a
    # directory whose input.yaml has changed therefore folds the PREVIOUS input and writes a
    # result that looks fresh: measured here, a receptor rebuilt from 212 residues down to
    # 156 produced a model still 212 residues long and an ipTM identical to the old run to
    # all 16 digits. Nothing in the exit code, the logs or the output timestamps distinguishes
    # that from a real run. The stale tree is therefore removed before every actual run; the
    # only path that keeps it is the reuse path above, which has already proved the inputs
    # are byte-identical.
    for stale in out.glob("boltz_results_*"):
        if stale.is_dir():
            shutil.rmtree(stale)

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    result: dict[str, Any] = {
        "reused": False,
        "backend": "boltz-2",
        "version": info.version,
        "licence": "MIT",
        "citation": info.citation,
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "accelerator": accelerator,
        "msa_mode": chains[0].msa if chains else "unknown",
        "recycling_steps": recycling_steps,
        "diffusion_samples": diffusion_samples,
        "seed": seed,
        "use_msa_server": use_msa_server,
        "sampling_steps": sampling_steps,
        "stdout_tail": proc.stdout[-3000:],
        "stderr_tail": proc.stderr[-3000:],
    }
    if proc.returncode != 0:
        result["error"] = "boltz exited non-zero; see stderr_tail"
        return result

    result.update(_collect_boltz_outputs(out))

    # Post-condition. A prediction is only this prediction if the model it produced has the
    # chains that were asked for. Checking this is what turned a silent stale-cache reuse --
    # right exit code, fresh timestamps, plausible ipTM -- into a visible error. It costs one
    # pass over the mmCIF and it is the difference between a result and a result-shaped file.
    mismatch = _chain_length_mismatch(chains, result)
    if mismatch:
        result["returncode"] = 1
        result["error"] = f"model does not match the requested input: {mismatch}"
        result.pop("confidence", None)
        return result

    if (result.get("confidence") or {}):
        manifest.write_text(json.dumps(stamp, indent=1))
    return result


def _chain_length_mismatch(chains: Sequence[Chain], result: dict[str, Any]) -> str | None:
    """Compare the residue count per chain in the written model against what was requested.

    Returns a description of the discrepancy, or None if the model matches. Ligand chains are
    skipped: they are counted in atoms, not residues, so a residue tally says nothing there.

    The mmCIF atom_site column order is declared per file by the loop header and is not fixed,
    so the header is read rather than assumed. Assuming it silently yields one "chain" per
    residue number, which reads as a mismatch on every file and would have made this guard
    fire constantly and then be switched off.
    """
    model = (result.get("files") or {}).get("model")
    if not model:
        return None
    want = [len(c.sequence) for c in chains if c.kind == "protein"]
    if not want:
        return None
    try:
        lines = Path(model).read_text().splitlines()
    except OSError:
        return None

    cols: dict[str, int] = {}
    seen: dict[str, set[str]] = {}
    n = 0
    for line in lines:
        t = line.strip()
        if t.startswith("_atom_site."):
            cols[t.split(".", 1)[1].split()[0]] = n
            n += 1
            continue
        if not line.startswith(("ATOM", "HETATM")):
            continue
        ci, ri = cols.get("label_asym_id"), cols.get("label_seq_id")
        if ci is None or ri is None:
            return None
        f = line.split()
        if len(f) > max(ci, ri):
            seen.setdefault(f[ci], set()).add(f[ri])
    if not seen:
        return None
    got = [len(v) for _, v in sorted(seen.items())][:len(want)]
    if got != want:
        return f"requested protein chain lengths {want}, model contains {got}"
    return None


def _collect_boltz_outputs(out: Path) -> dict[str, Any]:
    """Locate and parse whatever Boltz actually wrote."""
    found: dict[str, Any] = {"files": {}}
    # Keep every model. Retaining only sorted(...)[0] silently discarded the rest, which
    # makes diffusion_samples > 1 pointless and rules out any ensemble analysis.
    cifs = sorted(out.rglob("*.cif"))
    if cifs:
        found["files"]["model"] = str(cifs[0])
        found["files"]["all_models"] = [str(c) for c in cifs]
        found["n_models"] = len(cifs)
    for pattern, key in (("confidence_*.json", "confidence"),
                         ("affinity_*.json", "affinity")):
        hits = sorted(out.rglob(pattern))
        if hits:
            found["files"][key] = str(hits[0])
            found["files"][f"all_{key}"] = [str(h) for h in hits]
            try:
                found[key] = json.loads(hits[0].read_text())
                if len(hits) > 1:
                    found[f"{key}_all"] = [json.loads(h.read_text()) for h in hits]
            except json.JSONDecodeError:
                found[key] = {"error": "unparseable JSON"}
    for pattern, key in (("pae_*.npz", "pae"), ("plddt_*.npz", "plddt")):
        hits = sorted(out.rglob(pattern))
        if hits:
            found["files"][key] = str(hits[0])
    return found


# --------------------------------------------------------------------------- #
# AlphaFold DB
# --------------------------------------------------------------------------- #

def fetch_alphafold_db(accession: str, out_dir: str | Path) -> dict[str, Any]:
    """Retrieve a real AlphaFold 2 prediction. No GPU, no weights, no licence key.

    This is retrieval, not prediction: it only works for proteins already in the database,
    which excludes every designed sequence. Useful for the receptor half of a complex, and
    for validating that the parser handles genuine output.
    """
    import ssl
    import urllib.request
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    api = f"https://alphafold.ebi.ac.uk/api/prediction/{accession}"
    with urllib.request.urlopen(api, timeout=90, context=ctx) as fh:
        meta = json.loads(fh.read())
    if not meta:
        raise BackendUnavailable(
            f"No AlphaFold DB entry for {accession}. The database covers natural proteins "
            "with a UniProt accession; a designed sequence will never be present.")
    entry = meta[0]
    files: dict[str, str] = {}
    for key, name in (("cifUrl", f"AF-{accession}.cif"),
                      ("paeDocUrl", f"AF-{accession}-predicted_aligned_error.json")):
        url = entry.get(key)
        if not url:
            continue
        dest = out / name
        with urllib.request.urlopen(url, timeout=180, context=ctx) as fh:
            dest.write_bytes(fh.read())
        files[key] = str(dest)
    return {
        "backend": "alphafold-db",
        "version": entry.get("latestVersion", "unknown"),
        "model": entry.get("modelCreatedDate", ""),
        "uniprot": accession,
        "licence": "CC-BY-4.0",
        "citation": "Varadi et al., Nucleic Acids Res (2022, 2024)",
        "files": files,
    }


def describe() -> str:
    """Human-readable statement of what can and cannot be run here."""
    lines = ["Structure prediction backends:"]
    for b in available_backends():
        mark = "available" if b.available else "UNAVAILABLE"
        lines.append(f"  [{mark}] {b.name} ({b.version}) — {b.licence}")
        if b.reason:
            lines.append(f"      {b.reason}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
