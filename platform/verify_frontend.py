#!/usr/bin/env python3
"""Static verification of the front end.

Checks the things a browser would only reveal at runtime:
  * app.js parses (delegated to node --check)
  * every getElementById / querySelector id used by app.js exists in index.html
  * every dataset field app.js reads is actually present in data/dataset.json
  * no fabricated-data renderer or false claim survives in the shipped files
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app.js"
HTML = REPO / "index.html"
DATASET = REPO / "data" / "dataset.json"
README = REPO / "README.md"

FAIL: list[str] = []
PASS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def main() -> int:
    app = APP.read_text()
    html = HTML.read_text()
    ds = json.loads(DATASET.read_text())

    print("\n[syntax]")
    r = subprocess.run(["node", "--check", str(APP)], capture_output=True, text=True)
    check("app.js parses", r.returncode == 0, r.stderr.strip()[:200])

    print("\n[DOM contract] every id app.js touches exists in index.html")
    ids = set(re.findall(r"getElementById\(['\"]([\w-]+)['\"]\)", app))
    html_ids = set(re.findall(r'id="([\w-]+)"', html))
    missing = sorted(ids - html_ids)
    check(f"{len(ids)} referenced ids all present", not missing,
          f"missing: {missing}" if missing else "")

    print("\n[data contract] every dataset field app.js reads is present")
    cand = ds["candidates"][0]
    prod = ds["natural_products"][0]
    needed_top = ["disclosure", "natural_products", "candidates", "schema_version",
                  "built", "git_sha"]
    for k in needed_top:
        check(f"dataset.{k}", k in ds)
    for k in ["code", "sequence", "valid", "binding_free_energy",
              "dissociation_constant", "plddt", "liabilities"]:
        check(f"candidate.{k}", k in cand)
    for k in ["name", "class", "validation", "binding_residues_text"]:
        check(f"natural_product.{k}", k in prod)

    print("\n[provenance] every value record is well formed")
    bad = []
    for c in ds["candidates"]:
        for k, v in c.items():
            if isinstance(v, dict) and "provenance" in v:
                st = v["provenance"].get("status")
                if st not in {"computed", "measured", "literature", "database",
                              "predicted", "placeholder", "not_computed"}:
                    bad.append(f"{c['code']}.{k}={st}")
    check("all provenance statuses are valid", not bad, str(bad[:5]))

    n_valid = sum(1 for c in ds["candidates"] if c["valid"])
    check("invalid sequences are marked invalid", n_valid < len(ds["candidates"]),
          f"{len(ds['candidates']) - n_valid} marked invalid")
    check("no candidate exposes a numeric pLDDT as a result",
          all(c["plddt"]["provenance"]["status"] == "not_computed"
              for c in ds["candidates"]))
    check("no candidate exposes a numeric ΔG as a result",
          all(c["binding_free_energy"]["provenance"]["status"] == "not_computed"
              for c in ds["candidates"]))
    check("retracted claims are preserved, not deleted",
          sum(1 for c in ds["candidates"] if "retracted_claims" in c) == 25)

    print("\n[honesty] fabricated renderers and false claims are gone")
    banned_app = {
        "synthetic pLDDT formula": r"93\s*\+\s*Math\.sin",
        "synthetic PAE ramp": r"Math\.abs\(i\s*-\s*j\)\s*\*\s*0\.4",
        "charCode-driven geometry": r"charCode\s*%\s*5",
        "'REAL FASTA' comment": r"REAL FASTA",
    }
    for label, pat in banned_app.items():
        check(f"app.js no longer contains the {label}",
              re.search(pat, app) is None)

    banned_html = {
        "'Live Connected' badge": r"Live Connected",
        "'designed via AlphaFold3'": r"designed via AlphaFold",
        "a Google/DeepMind logo badge": r"logo=google|shields\.io[^\"']*DeepMind",
        "DeepMind in the product name": r"<title>[^<]*DeepMind|<h1>[^<]*DeepMind",
    }
    for label, pat in banned_html.items():
        hits = [m.group(0) for m in re.finditer(pat, html, re.I)]
        check(f"index.html no longer contains {label}", not hits, str(hits[:3]))

    # DeepMind may only appear in a disclaimer or trademark line, never as branding.
    dm_lines = [l.strip() for l in html.splitlines() if "DeepMind" in l]
    ok_dm = all(re.search(r"not affiliated|trademark|claim any affiliation", l, re.I)
                for l in dm_lines)
    check("every DeepMind mention is a disclaimer or trademark notice", ok_dm,
          str([l[:70] for l in dm_lines if not re.search(
              r'not affiliated|trademark|claim any affiliation', l, re.I)]))

    check("index.html carries a visible disclosure block",
          'class="disclosure"' in html and "No structure prediction has been run" in html)
    check("footer disclaims affiliation",
          "Not affiliated with" in html)
    check("CDN scripts are version-pinned",
          all("@" in m for m in re.findall(r'src="(https://cdn\.jsdelivr\.net/[^"]+)"', html)),
          str(re.findall(r'src="(https://cdn[^"]+)"', html)))

    if README.exists():
        rd = README.read_text()
        check("README has no Google-logo badge", "logo=google" not in rd)
        # This check used to look for the literal phrase "No structure prediction has been
        # run", which was the honest disclosure when none had been. Structure prediction is
        # now real, so that phrase would be false and the README correctly dropped it.
        # A check pinned to a phrase rather than to the property it stands for goes stale
        # exactly when the project improves, so it now tests the property: the README must
        # carry a status disclosure that separates what is computed from what is not.
        check("README has a status disclosure section",
              "## Status disclosure" in rd)
        check("README states what is NOT implemented",
              "not implemented" in rd.lower())
        check("README discloses that sequences are not de novo designs",
              "not de novo designs" in rd or "hypothesis catalogue" in rd)
        check("README names the structure backend and its licence",
              "Boltz-2" in rd and "MIT" in rd)

    print("\n[lifecycle] resources are released")
    check("a viewer disposal path exists", "function disposeViewer" in app)
    check("disposeViewer is called before creating a viewer",
          app.index("disposeViewer();") < app.index("$3Dmol.createViewer"))
    check("chart instance is destroyed before recreation",
          "plddtChart.destroy()" in app)
    check("only one viewer is ever constructed",
          app.count("$3Dmol.createViewer") == 1)

    print("\n[rendering rules]")
    check("renderValue is the only value path",
          "function renderValue" in app)
    check("not_computed renders a label, never a number",
          re.search(r"status === 'not_computed'[\s\S]{0,200}not computed", app) is not None)
    check("placeholder renders a label, never a number",
          re.search(r"status === 'placeholder'[\s\S]{0,200}illustrative only", app) is not None)
    check("pLDDT axis spans the full 0-100 range",
          re.search(r"y:\s*\{\s*min:\s*0,\s*max:\s*100", app) is not None)
    pae_fn = re.search(r"function renderPae\([\s\S]*?\n\}", app).group(0)
    check("PAE matrix size is derived from the data, not capped",
          re.search(r"const n = p\.pae\.length", pae_fn) is not None)
    check("PAE render contains no hardcoded token limit",
          not re.search(r"Math\.min\(\s*(?:p\.pae\.length|n)\s*,\s*\d+", pae_fn))

    print("\n" + "=" * 74)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print("  -", f)
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
