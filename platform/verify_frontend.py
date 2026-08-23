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
import shutil
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
    # node is an undeclared prerequisite: on a clean checkout that follows the README exactly
    # this raised FileNotFoundError and took down the whole suite with a stack trace, so the
    # documented "run everything" command did not run on a machine set up by the documented
    # install. Absence is now reported as a named skip, not a crash.
    if shutil.which("node") is None:
        print("  SKIP  app.js parses -- node is not installed "
              "(needed only for this syntax check; see README prerequisites)")
    else:
        r = subprocess.run(["node", "--check", str(APP)], capture_output=True, text=True)
        check("app.js parses", r.returncode == 0, r.stderr.strip()[:200])

    print("\n[DOM contract] every id app.js touches exists in index.html")
    # app.js reaches most ids through the setText()/stats() helpers, not getElementById, and
    # both helpers swallow a miss (`if (el) ...`). Matching only the direct call left 7 ids
    # unchecked while the module docstring claimed every id was verified, so a renamed id
    # produced a silently blank panel and a green suite.
    # A literal immediately followed by `+` is a PREFIX for a constructed id, not an id.
    ids = {m.group(1) for m in
           re.finditer(r"(?:getElementById|setText|stats)\(\s*['\"]([\w-]+)['\"]\s*(?![\s]*\+)", app)}
    html_ids = set(re.findall(r'id="([\w-]+)"', html))
    missing = sorted(ids - html_ids)
    check(f"{len(ids)} referenced ids all present", not missing,
          f"missing: {missing}" if missing else "")

    # Constructed ids are verified by expanding them: every data-tab value in the HTML must
    # have a matching tab-<value> element, which is what app.js:154 builds at runtime.
    prefixes = {m.group(1) for m in
                re.finditer(r"getElementById\(\s*['\"]([\w-]+)['\"]\s*\+", app)}
    built_missing = []
    for pre in prefixes:
        vals = re.findall(r'data-%s="([\w-]+)"' % pre.rstrip("-"), html)
        built_missing += [f"{pre}{v}" for v in vals if f'id="{pre}{v}"' not in html]
    check(f"constructed ids resolve ({sorted(prefixes)} x data-* values)",
          not built_missing, str(built_missing))

    print("\n[data contract] every dataset field app.js reads is present")
    # Checking ds["candidates"][0] only inspected 1 of 25 records: deleting `sequence` from
    # another candidate left the suite green while the UI would render undefined. Every record
    # in both collections is checked, and the offending code is reported.
    cand = ds["candidates"][0]
    prod = ds["natural_products"][0]
    needed_top = ["disclosure", "natural_products", "candidates", "schema_version",
                  "built", "git_sha"]
    for k in needed_top:
        check(f"dataset.{k}", k in ds)
    CAND_KEYS = ["code", "sequence", "valid", "binding_free_energy",
                 "dissociation_constant", "plddt", "liabilities"]
    NP_KEYS = ["name", "class", "validation", "binding_residues_text"]
    miss_c = [(c.get("code", "?"), k) for c in ds["candidates"] for k in CAND_KEYS if k not in c]
    miss_p = [(n.get("name", "?"), k) for n in ds["natural_products"] for k in NP_KEYS if k not in n]
    check(f"all {len(ds['candidates'])} candidates carry every field app.js reads",
          not miss_c, str(miss_c[:4]))
    check(f"all {len(ds['natural_products'])} natural products carry every field app.js reads",
          not miss_p, str(miss_p[:4]))

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

    # "At least one is invalid" survived flipping three of the four invalid candidates to
    # valid, including one whose sequence carries the ambiguity code B and one whose sequence
    # field holds prose. The flag is re-derived per candidate instead.
    sys.path.insert(0, str(REPO / "platform"))
    from cbc import peptide as _pep
    disagree = []
    for c in ds["candidates"]:
        want = _pep.analyze(c.get("code", "?"), c.get("sequence", "")).valid
        if bool(c.get("valid")) != bool(want):
            disagree.append((c.get("code"), c.get("valid"), want))
    check("every candidate's valid flag equals what peptide.analyze derives",
          not disagree, str(disagree[:4]))
    n_valid = sum(1 for c in ds["candidates"] if c["valid"])
    check("some candidates are invalid, as the legacy data requires",
          n_valid < len(ds["candidates"]), f"{len(ds['candidates']) - n_valid} invalid")
    # Same stale-state problem as the README phrase check above: asserting that nothing is
    # ever predicted was correct only while nothing had been. The property is that a value
    # is never shown without a provenance the UI can render honestly.
    st = {c["plddt"]["provenance"]["status"] for c in ds["candidates"]}
    check("every pLDDT status is not_computed or predicted",
          st <= {"not_computed", "predicted"}, str(st))
    check("predicted pLDDTs name their model",
          all(c["plddt"]["provenance"].get("software", "").startswith("Boltz")
              for c in ds["candidates"]
              if c["plddt"]["provenance"]["status"] == "predicted"))
    check("the UI renders 'predicted' with a badge",
          "predicted" in app and "badge" in app)
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

    # The disclosure must EXIST and must not assert something the artefacts contradict.
    # Pinning this to a fixed sentence made it certify a claim that went false the moment
    # runs/ filled up; it now checks presence plus the absence of retracted statements.
    check("index.html carries a visible disclosure block", 'class="disclosure"' in html)
    stale = [t for t in ("No structure prediction has been run",
                         "no structure prediction has been run") if t in html]
    check("the disclosure makes no claim the artefacts contradict", not stale, str(stale))

    # The page's "It does not" list denied two capabilities the repository demonstrably has,
    # fifty lines above the disclosure block that asserts them. The phrase-pinned check above
    # could not see it, because the false claim was worded differently from the retired one.
    # This checks the property instead: nothing in the denial list may contradict a capability
    # the shipped disclosure claims. Pairs are (regex that would appear in a denial, regex
    # that would appear in the disclosure asserting the same capability).
    denials = re.search(r'It does not.*?</ul>', html, re.S)
    denial_text = denials.group(0) if denials else ""
    disclosure = json.dumps(ds.get("disclosure", {})) + html
    CONTRADICTIONS = {
        "denies running any structure predictor while the disclosure claims one ran":
            (r"any structure predictor", r"Boltz-2[^\"]{0,80}(runs|produced)"),
        "denies ADMET prediction outright while the disclosure claims ADMET-AI runs":
            (r"<li>\s*Perform ADMET", r"ADMET[- ]AI"),
    }
    for label, (den, cap) in CONTRADICTIONS.items():
        contradicts = (re.search(den, denial_text, re.I) is not None
                       and re.search(cap, disclosure, re.I) is not None)
        check(f"the 'It does not' list never {label}", not contradicts)
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
        # This used to accept the literal phrase "not de novo designs", which was false:
        # motif_provenance records one segment as a de novo amphipathic helix. The property
        # is that the README states how the sequences were made AND points at the
        # per-segment record, so the qualification travels with the claim.
        # Match against a whitespace-normalised copy. Markdown is hard-wrapped at ~96
        # columns, so re-wrapping a paragraph moves a line break into the middle of a phrase
        # and broke this check without changing a word of the content. A guard that fails on
        # reflow trains its reader to ignore it.
        flat = " ".join(rd.split())
        check("README states the sequence provenance and cites the per-segment record",
              "motif_provenance" in flat and "unattributed segments" in flat)
        # This checked ONE of the three numbers in that paragraph, and the two it did not
        # check were both wrong for as long as it passed: the README claimed "16 attributed
        # motifs" when only 7 of the 16 entries carry a UniProt accession, and "14 of 35"
        # candidates when 31 of 35 carry an unattributed fragment. A guard that covers a
        # third of a sentence certifies the sentence.
        ds_json = json.loads((REPO / "data" / "dataset.json").read_text())
        counts = (ds_json.get("disclosure") or {}).get("sequence_attribution_counts")
        check("the dataset publishes measured attribution counts", bool(counts))
        if counts:
            want = {
                "attributed motifs": counts["attributed_motifs"],
                "unattributed motif entries": counts["unattributed_motif_entries"],
                "unattributed segments": counts["unattributed_segments"],
                "unattributed fragments": counts["distinct_unattributed_fragments"],
                "candidates carrying one": counts["candidates_carrying_one"],
            }
            absent = [f"{k}={v}" for k, v in want.items() if str(v) not in flat]
            check(f"all {len(want)} attribution counts appear in the README", not absent,
                  str(absent))
            # And the discredited pair must not come back.
            stale = [t for t in ("16 attributed motifs", "14 of 35 candidates")
                     if t in flat]
            check("the README no longer states the retracted attribution counts", not stale,
                  str(stale))
            derived = counts["attributed_motifs"] + counts["unattributed_motif_entries"]
            record = len((ds_json.get("motif_provenance") or {}).get("motifs") or [])
            check("the attributed/unattributed split accounts for every motif entry",
                  derived == record, f"{derived} vs {record} in motif_provenance")
        check("README names the structure backend and its licence",
              "Boltz-2" in rd and "MIT" in rd)
        # "A 12-discipline expert panel" reads as human peer review. It was a multi-agent LLM
        # review -- reviews/panel_raw.json keys every reviewer as a `reviewer_persona` string
        # -- and the project's own internal audit flagged the wording (LIC-08) without the fix
        # being applied. Provenance for the review process must be held to the standard the
        # rest of the document claims for its numbers.
        panel = any(t in flat for t in ("multi-agent LLM review", "multi-agent LLM"))
        check("the README discloses that the review panel was LLM-based", panel)
        check("the README says plainly it was not human peer review",
              "not human peer review" in flat)
        check("no wording presents the panel as human experts",
              "12-discipline expert panel" not in flat)

        # The NOTICE said AlphaFold was referred to "only to describe what this project does
        # NOT do". That became false when AlphaFold DB became a live dependency.
        notice = " ".join((REPO / "NOTICE").read_text().split())
        check("NOTICE does not claim AlphaFold is only mentioned negatively",
              "referred to only to describe what this project does NOT do" not in notice)
        # The repository redistributes data under five licences and one of them, ChEMBL's
        # CC BY-SA 3.0, is share-alike. A metadata file that names only Apache-2.0 tells a
        # reuser they have fewer obligations than they do -- the same class of understatement
        # as an overclaimed result, one field over.
        import yaml as _yaml
        cff = _yaml.safe_load((REPO / "CITATION.cff").read_text())
        lic = cff["license"] if isinstance(cff["license"], list) else [cff["license"]]
        # The page renders identifiers from dataset.citation. If that block ever stops being
        # a copy of CITATION.cff, the page and the registries start telling a reader two
        # different things about how to cite the same release.
        cit = ds.get("citation")
        check("the dataset carries a citation block read from CITATION.cff", bool(cit))
        if cit:
            want = {(i["type"], i["value"]) for i in (cff.get("identifiers") or [])}
            have = {(i["type"], i["value"]) for i in cit["identifiers"]}
            check(f"all {len(want)} identifiers on the page match CITATION.cff", want == have,
                  f"page {sorted(have)} vs cff {sorted(want)}")
            check("the page states the version CITATION.cff states",
                  cit["version"] == cff.get("version"),
                  f"{cit['version']} vs {cff.get('version')}")
            check("the citation block warns against citing it as a positive result",
                  "negative" in (cit.get("note") or ""))
            check("index.html hosts the citation block", 'id="citation-block"' in html)

        check("CITATION.cff lists every licence the deposit carries",
              {"Apache-2.0", "CC-BY-4.0", "CC-BY-SA-3.0", "CC0-1.0", "MIT"} <= set(lic),
              f"lists {lic}")
        for name in ("CITATION.cff", "codemeta.json", ".zenodo.json", "biotools.json",
                     "docs/REGISTRATION.md"):
            body = (REPO / name).read_text()
            check(f"{name} discloses the share-alike obligation",
                  "BY-SA" in body or "BY SA" in body)

        for token, what in (("AlphaFold DB IS used", "AlphaFold DB is used"),
                            ("AlphaFold 3 is NOT run", "AlphaFold 3 is not run"),
                            ("AlphaFold SERVER is NOT used", "AlphaFold Server is not used")):
            check(f"NOTICE states that {what}", token in notice)

    print("\n[data-load failure] the error card names the cause that actually applies")
    check("the file:// case is detected explicitly",
          "location.protocol === 'file:'" in app)
    # Isolate the two template literals of the ternary, so the assertion is about the message
    # the reader actually sees and not about the comment above it.
    _tern = re.search(r"isFile\s*\n?\s*\?\s*(`[\s\S]*?`)\s*:\s*(`[\s\S]*?`)\);", app)
    check("the data-load error card branches on the scheme", _tern is not None)
    if _tern:
        file_msg, served_msg = _tern.group(1), _tern.group(2)
        check("the file:// message does not tell the reader to rebuild existing data",
              "build_dataset.py" not in file_msg, file_msg[:80])
        check("the served-but-missing message does name build_dataset.py",
              "build_dataset.py" in served_msg)
    check("the file:// message names the real mechanism",
          "cross-origin" in app and "http.server" in app)

    print("\n[file-scheme shim] the script twin cannot drift from the JSON")
    # Every generated shim, not just the first two. The slate and structure indices were
    # added later and inherited the same file:-scheme problem; leaving them out of this loop
    # would have let either drift from its JSON twin with nothing to notice.
    SHIMS = (("dataset.json", "dataset.js", "__CBC_DATASET__"),
             ("validation_gate.json", "validation_gate.js", "__CBC_GATE__"),
             ("slate.json", "slate.js", "__CBC_SLATE__"),
             ("structures.json", "structures.js", "__CBC_STRUCTURES__"))
    for jsonf, jsf, glob_name in SHIMS:
        jp, sp = REPO / "data" / jsonf, REPO / "data" / jsf
        check(f"data/{jsf} exists", sp.exists())
        # The .json was only tested implicitly, by `continue`. Deleting data/validation_gate
        # .json left the whole suite exiting 0 while the served page 404s on it.
        check(f"data/{jsonf} exists", jp.exists())
        if not (jp.exists() and sp.exists()):
            continue
        body = sp.read_text()
        check(f"data/{jsf} assigns window.{glob_name}", f"window.{glob_name} = " in body)
        try:
            shim = json.loads(body.split(" = ", 1)[1].rstrip().rstrip(";"))
            same = shim == json.loads(jp.read_text())
        except (ValueError, IndexError):
            shim, same = None, False
        check(f"data/{jsf} carries exactly the same object as data/{jsonf}", same)
        both = body + jp.read_text()
        bad = [t for t in ("NaN", "Infinity", "-Infinity")
               if re.search(r"(?<![\w\"])" + re.escape(t) + r"(?![\w\"])", both)]
        check(f"data/{jsonf} holds no value the browser's JSON.parse rejects", not bad,
              str(bad))
    def tag_pos(src: str) -> int:
        m = re.search(rf'<script[^>]*src="{re.escape(src)}"', html)
        return m.start() if m else -1
    app_at = tag_pos("app.js")
    # Matching the bare path let a mention inside an HTML comment satisfy the ordering, so
    # the position is taken from the <script> tag itself.
    late = [jsf for _j, jsf, _g in SHIMS
            if tag_pos(f"data/{jsf}") < 0 or tag_pos(f"data/{jsf}") > app_at]
    check(f"index.html loads all {len(SHIMS)} shims before app.js", not late, str(late))
    # The fetch itself moved behind a helper, so matching the literal fetch(...) call stopped
    # proving anything about three of the four files. What matters is the PAIR: each file is
    # requested over the network somewhere, and each has a window.__CBC_* fallback when that
    # request cannot be made.
    unpaired = [jsonf for jsonf, _js, g in SHIMS
                if not re.search(rf"""['"]data/{re.escape(jsonf)}['"]""", app)
                or f"window.{g}" not in app]
    check("every shim is both fetched and fallen back to in app.js", not unpaired,
          str(unpaired))

    print("\n[gallery] the repository's own structures are actually reachable")
    # The page could display a prediction for a year without ever being able to show one of
    # the repository's own -- the viewer only took a file the reader dragged in. These checks
    # pin the path that closed that gap, because it is invisible to every other suite: a
    # broken cif path or a dropped renderer would leave the page silently empty.
    sidx = REPO / "data" / "structures.json"
    check("data/structures.json exists", sidx.exists())
    if sidx.exists():
        idx = json.loads(sidx.read_text())
        ents = idx["entries"]
        missing = [e["id"] for e in ents if not (REPO / e["cif"]).exists()]
        check(f"all {len(ents)} indexed structures point at a file that exists",
              not missing, str(missing[:5]))
        bad_pae = [e["id"] for e in ents if e.get("pae") and not (REPO / e["pae"]).exists()]
        check("every indexed PAE file exists", not bad_pae, str(bad_pae[:5]))
        for g in ("complex", "peptide_monomer", "receptor_afdb"):
            check(f"the gallery holds at least one {g}",
                  any(e["group"] == g for e in ents))
        # A single-chain model has no interface. Boltz emits iptm: 0.0 for one, and publishing
        # that zero beside a peptide reads as the worst possible binding result rather than as
        # an absence -- the exact confusion this repository exists to remove.
        mono = [e["id"] for e in ents
                if len(e["chains"]) < 2 and any("iptm" in k for k in (e.get("metrics") or {}))]
        check("no single-chain entry publishes an ipTM", not mono, str(mono[:5]))
        # Decoys outscore several natives. A picker that offered them would invite exactly the
        # cherry-picking the composition-matched null was built to prevent. Matching "decoy"
        # in the entry id was WRONG and said so on the first run: the candidate
        # HippoNrf-KeapDecoy-X3 is a designed sequence whose name contains the word. The
        # question is what a fold IS, so ask the run manifest which job produced it.
        job_of = {}
        for r in json.loads((REPO / "runs" / "manifest.json").read_text())["runs"]:
            job_of[r["path"]] = r["job"]
        decoys = [e["id"] for e in ents
                  if re.search(r"_decoy\d+$", job_of.get((e.get("provenance") or {}).get("run", ""), ""))]
        check("no decoy fold is offered in the picker", not decoys, str(decoys[:5]))
        cpx = [e for e in ents if e["group"] == "complex"]
        check("every complex carries the screen numbers that judge it",
              all(e.get("screen", {}).get("decoy_max") is not None for e in cpx))
        # The index picks a run by evidence, and more than one retained run can hold the same
        # model. Picking the wrong one would put a DIFFERENT fold's confidence on the page
        # under the right candidate's name -- a stale-artefact failure wearing a new hat, and
        # invisible unless the two are compared directly.
        msa = json.loads((REPO / "data" / "study_msa_specificity.json").read_text())
        native = {r["code"]: r for r in msa["rows"] if r.get("kind") == "native"}
        drift = []
        for e in cpx:
            r = native.get(e["code"])
            if r is None:
                drift.append(f"{e['code']}: no native row")
                continue
            for k in ("iptm", "ptm", "complex_plddt"):
                a, b = (e.get("metrics") or {}).get(k), r.get(k)
                if a is None or b is None or abs(a - b) > 5e-5:
                    drift.append(f"{e['code']}.{k}: index {a} vs study {b}")
        check(f"all {len(cpx)} complexes report the study's own confidences", not drift,
              str(drift[:4]))
        iface = [e for e in cpx if e.get("interface_pae")]
        check("interface PAE is labelled descriptive, not a study result",
              all("not a pre-registered quantity" in e["interface_pae"]["note"]
                  for e in iface))
        # A PAE block sliced at the wrong offset still produces a plausible number, so check
        # the count of residue pairs equals 2 x nA x nB for every complex that has one.
        wrong = []
        for e in iface:
            # Resolve the chains the entry NAMES rather than assuming the first two: the
            # positional form passed when chain_pair was edited to "A-Z", and would index
            # out of range on a one-chain entry.
            want = (e["interface_pae"].get("chain_pair") or "").split("-")
            lens = {c["id"]: c["length"] for c in e["chains"]}
            if len(want) != 2 or any(x not in lens for x in want):
                wrong.append(f"{e['id']}: names {want}, has {sorted(lens)}")
                continue
            if e["interface_pae"]["n_pairs"] != 2 * lens[want[0]] * lens[want[1]]:
                wrong.append(f"{e['id']}: {e['interface_pae']['n_pairs']} pairs")
        check("every interface PAE covers exactly the two chains it names", not wrong,
              str(wrong[:4]))
        # D8: without this the two checks above go vacuously true if the feature is dropped.
        # Two pLDDT scales live in one entry; both must say which they are.
        unscaled = [e["id"] for e in ents
                    if any(c.get("mean_plddt") is not None and not c.get("mean_plddt_scale")
                           for c in e["chains"])
                    or ((e.get("metrics") or {}) and "scale" not in (e.get("metrics") or {}))]
        check("every published pLDDT says which scale it is on", not unscaled,
              str(unscaled[:4]))
        check(f"all {len(cpx)} complexes carry an interface PAE", len(iface) == len(cpx),
              f"{len(iface)} of {len(cpx)}")
        check("app.js can load an indexed structure",
              "function loadIndexedStructure(" in app and "data-structure" in app)
        check("the gallery names the file:// limitation rather than failing silently",
              "loadIndexedStructure" in app
              and "file:" in app.split("function loadIndexedStructure")[1][:2000])

    hosts = re.findall(r"\['([a-z-]+)',\s*render[A-Za-z]+\]", app)
    missing_hosts = [h for h in hosts if f'id="{h}"' not in html]
    check(f"all {len(hosts)} per-section error hosts exist in index.html",
          not missing_hosts, str(missing_hosts))
    check("the section table covers every renderer that loadData runs", len(hosts) >= 9,
          f"found {len(hosts)}")
    # The host-id check above passed while the table referenced a renderer that did not exist.
    # `['citation-block', renderCitation]` evaluates the identifier when the array is built, so
    # an undefined name is a ReferenceError thrown before the per-section try/catch can catch
    # anything -- it takes down every renderer on the page, not one. node --check does not see
    # it either, because it is a runtime error and not a syntax error. Check the definitions.
    named = re.findall(r"\['[a-z-]+',\s*(render[A-Za-z]+)\]", app)
    undefined = [n for n in named if f"function {n}(" not in app]
    check(f"all {len(named)} renderers in the section table are defined", not undefined,
          str(undefined))

    print("\n[slate] every study on the page traces to a registered plan")
    slp = REPO / "data" / "slate.json"
    check("data/slate.json exists", slp.exists())
    if slp.exists():
        sl = json.loads(slp.read_text())
        orphan = [st["study_id"] for st in sl["studies"]
                  if not (REPO / st["plan_file"]).exists()
                  or not (REPO / st["artefact"]).exists()]
        check(f"all {len(sl['studies'])} studies cite a plan and artefact that exist",
              not orphan, str(orphan))
        # The join is on the artefact's OWN plan hash, so a stale README section loses its
        # number instead of mislabelling a result. Assert the hash really is the artefact's.
        wrong = []
        for st in sl["studies"]:
            body = json.loads((REPO / st["artefact"]).read_text())
            a = body.get("analysis") or body
            if (a.get("prespec_hash") or "")[:12] != st["plan_hash"]:
                wrong.append(st["study_id"])
        check("every study's plan hash is the one its artefact records", not wrong, str(wrong))
        # Verdicts are copied, never recomputed here; confirm they match the artefact.
        drift = []
        for st in sl["studies"]:
            body = json.loads((REPO / st["artefact"]).read_text())
            a = body.get("analysis") or body
            v = a.get("verdicts") or {}
            for h in st["hypotheses"]:
                if h["verdict"] and v.get(h["name"]) != h["verdict"]:
                    drift.append(f"{st['study_id']}:{h['name']}")
        check("no verdict on the page differs from its artefact", not drift, str(drift[:5]))
        # counts read from the same file they are meant to police proves nothing, and the
        # whole block passed with studies:[] because every loop then had nothing to iterate.
        derived = [h for st in sl["studies"] for h in st["hypotheses"] if h["verdict"]]
        check("the published counts are derived from the published studies",
              sl["counts"]["hypotheses"] == len(derived)
              and sl["counts"]["falsified"] == sum(1 for h in derived
                                                   if h["verdict"] == "FALSIFIED")
              and sl["counts"]["confirmed"] == sum(1 for h in derived
                                                   if h["verdict"] == "CONFIRMED"),
              f"counts say {sl['counts']['hypotheses']}, studies hold {len(derived)}")
        check("falsified hypotheses are published, not dropped",
              sum(1 for h in derived if h["verdict"] == "FALSIFIED") > 0)
        # ARTEFACT -> PAGE. Everything above walks the page and asks whether the artefact
        # agrees; nothing asked the reverse, so a verdict the page never rendered was
        # undetectable. Exactly one had gone missing -- study #6's Fisher test, the one that
        # refuses the criterion beside it -- and losses like that are never symmetric.
        lost = []
        for st in sl["studies"]:
            body = json.loads((REPO / st["artefact"]).read_text())
            av = (body.get("analysis") or body).get("verdicts") or {}
            shown = {h["name"] for h in st["hypotheses"]}
            lost += [f"{st['study_id']}:{n}" for n in av if n not in shown]
        check("every verdict in every artefact reaches the page", not lost, str(lost[:5]))
        blank = [f"{st['study_id']}:{h['name']}" for st in sl["studies"]
                 for h in st["hypotheses"] if h["verdict"] is None]
        check("no hypothesis is published with its verdict blanked", not blank, str(blank[:5]))
        # A study whose plan and artefact disagree about how a hypothesis was decided must
        # say so rather than pick a side: #2's equivalence rule names a t-test but the study
        # filed it as a criterion, and #6's Fisher verdict has no rule at all.
        unresolved = [f"{st['study_id']}:{h['name']}" for st in sl["studies"]
                      for h in st["hypotheses"]
                      if h.get("rule_cites_a_test_statistic") and h["kind"] != "test"
                      and "threshold_embeds_a_test" not in h]
        check("a threshold whose rule names a test statistic says so", not unresolved,
              str(unresolved))
        # `decided by` must range over hypotheses that were decided.
        dec = [h for st in sl["studies"] for h in st["hypotheses"]
               if h["verdict"] in ("CONFIRMED", "FALSIFIED")]
        cc = sl["counts"]
        check("the decided-by buckets sum to the decided count",
              cc["decided_by_a_test"] + cc["decided_by_a_threshold"]
              + cc["decided_by_neither"] == cc["decided"] == len(dec),
              f"{cc['decided_by_a_test']}+{cc['decided_by_a_threshold']}"
              f"+{cc['decided_by_neither']} vs decided {cc['decided']} vs {len(dec)}")
        # A failure counted twice makes n_planned - n_failures disagree with n_observed.
        dbl = [st["study_id"] for st in sl["studies"]
               if st.get("n_failures_detail")
               and st["n_failures"] > st["n_failures_detail"]["distinct"]]
        check("no study double-counts a technical failure", not dbl, str(dbl))
        # CUSTODY. The workbench's promise is that a number on the page traces to a file a
        # reader can open, and study #12 breaks it: 160 of its 176 rows name fold outputs
        # under runs/interface-null-positive-control/, which is deliberately not committed.
        # That was true from the day the study shipped and the README said so; slate.json had
        # no field for it and the page rendered #12 with the same fields as eight studies
        # whose coordinates are here. Recomputed from the artefacts and the manifest, not
        # read back out of the file it is checking -- and against the MANIFEST, never against
        # the filesystem, because all 176 paths resolve on the machine that built slate.json.
        man = REPO / "runs" / "manifest.json"
        check("runs/manifest.json exists", man.exists())
        if man.exists():
            mf = json.loads(man.read_text())
            held = {f"{r['path']}/{f['file']}" for r in mf.get("runs", [])
                    for f in r.get("files", [])}
            wrong, quiet = [], []
            for st in sl["studies"]:
                cu = st.get("custody")
                if not cu:
                    wrong.append(f"{st['study_id']}: no custody block")
                    continue
                arts = [st["artefact"], *(st.get("companion_artefacts") or [])]
                n_rows = n_cite = n_held = n_short = 0
                for art in arts:
                    for r in (json.loads((REPO / art).read_text()).get("rows") or []):
                        if not isinstance(r, dict):
                            continue
                        n_rows += 1
                        ps = [v for v in r.values()
                              if isinstance(v, str) and v.startswith("runs/")]
                        if not ps:
                            continue
                        n_cite += 1
                        if all(q in held for q in ps):
                            n_held += 1
                        else:
                            n_short += 1
                if (cu["rows"], cu["rows_citing_a_fold_output"],
                        cu["rows_whose_bytes_this_repository_holds"],
                        cu["rows_whose_bytes_this_repository_does_not_hold"]) != (
                        n_rows, n_cite, n_held, n_short):
                    wrong.append(f"{st['study_id']}: page says "
                                 f"{cu['rows_whose_bytes_this_repository_holds']}"
                                 f"/{cu['rows_citing_a_fold_output']} of {cu['rows']}, "
                                 f"artefacts+manifest say {n_held}/{n_cite} of {n_rows}")
                if n_short and cu.get("complete") is not False:
                    quiet.append(st["study_id"])
            check("every study's custody count is what its rows and the manifest say",
                  not wrong, str(wrong[:3]))
            check("a study missing fold bytes is marked incomplete, not silent",
                  not quiet, str(quiet))
            gap = [st["study_id"] for st in sl["studies"]
                   if st["custody"]["complete"] is False]
            # The point of the field is that it is not always empty. If study #12's folds are
            # ever committed this check should be retired deliberately, not pass by drift.
            check("the study whose folds are not carried here says so on the page",
                  gap == ["interface-null-positive-control-v1"], str(gap))
            check("the page renders the custody shortfall rather than only storing it",
                  "renderCustody" in app and "custody" in app)
            cc = sl["counts"]
            check("the custody tally matches the studies it counts",
                  cc["studies_with_an_incomplete_custody_record"] == len(gap)
                  and cc["studies_whose_fold_bytes_are_all_in_this_repository"]
                  == sum(1 for st in sl["studies"] if st["custody"]["complete"] is True),
                  f"{cc['studies_with_an_incomplete_custody_record']} vs {len(gap)}")

        # A generated file stamped with a bare commit claims a clean-tree reproduction.
        # The same exclusion the generators use. Without it this check fails structurally the
        # moment a generator runs: writing its own output dirties the tree and invalidates the
        # stamp it just wrote. See cbc.provenance.GENERATED_ARTEFACTS.
        sys.path.insert(0, str(REPO / "platform"))
        from cbc.provenance import _tree_is_dirty
        dirty = _tree_is_dirty(REPO)
        stamps = {n: json.loads((REPO / "data" / n).read_text()).get("git_sha")
                  for n in ("slate.json", "structures.json",
                            "alphafold_db_comparison.json", "dataset.json")
                  if (REPO / "data" / n).exists()}
        bad_stamp = [n for n, v in stamps.items()
                     if v and v != "unknown" and bool(dirty) != v.endswith("-dirty")]
        check("every generated file's git stamp matches the tree state", not bad_stamp,
              f"tree {'dirty' if dirty else 'clean'}, stamps {stamps}")
        check("a confirmed threshold is not presented as a test",
              sl["counts"]["decided_by_a_threshold"] > 0
              and "not a score" in sl["reading_note"])
        # The #slate-confirmatory notice used to open with a hand-written bold sentence --
        # "Not one study in this slate is confirmatory." -- printed directly above the
        # generated paragraph that names #12 as the exception, and directly below a stat
        # card reading "1 confirmatory - see below". Nothing checked it because nothing
        # checked app.js for a claim about a count at all. Both lines of the notice are
        # generated now; these two checks are what keep them generated.
        check("the confirmatory notice's heading is read from the artefact",
              "confirmatory_headline" in sl
              and "sl.confirmatory_headline" in app
              and "confirmatory.</strong>" not in app,
              sl.get("confirmatory_headline", "<absent>"))
        denies = re.search(r"not\s+one\s+(?:of\s+the\s+\d+\s+)?stud(?:y|ies)",
                           sl.get("confirmatory_headline", ""), re.I)
        check("the heading denies a confirmatory study only when there is none",
              bool(denies) == (sl["counts"]["studies_confirmatory"] == 0),
              f"{sl['counts']['studies_confirmatory']} confirmatory · "
              f"{sl.get('confirmatory_headline', '<absent>')!r}")

    print("\n[alphafold] the comparison states what it cannot support")
    afp = REPO / "data" / "alphafold_db_comparison.json"
    check("data/alphafold_db_comparison.json exists", afp.exists())
    if afp.exists():
        af = json.loads(afp.read_text())
        check("the artefact is labelled exploratory", af["status"].startswith("EXPLORATORY"))
        gen = REPO / af.get("generator", "nonexistent")
        check("it names a generator file that exists", gen.exists())
        # `exists()` was checked under the name "committed", which is a different claim. A
        # generator git is told to IGNORE can never be committed, and an artefact that names
        # one is not reproducible from a clone whatever the working tree looks like.
        if gen.exists():
            ig = subprocess.run(["git", "check-ignore", "-q", str(gen)], cwd=REPO)
            check("the generator is not excluded from version control", ig.returncode != 0)
        check("it records the AlphaFold Server restriction",
              "prohibit" in af["source"]["note"].lower())
        check("it states its licence", af["source"]["licence"] == "CC BY 4.0")
        check("it enumerates its confounds", len(af["confounds"]) >= 3)
        # `for k in arm` iterates the arm dict's own keys, and every r lives one level down
        # in arm["rows"]. A p_value written beside a correlation -- the only place one would
        # realistically appear -- was invisible to this check. Serialise and search.
        blob = json.dumps(af["arms"])
        check("no p-value is attached to a within-protein correlation",
              "p_value" not in blob and "pearson_p" not in blob)
        for name, arm in af["arms"].items():
            total = arm["n_compared"] + len(arm["not_compared"])
            check(f"arm {name} accounts for every downloaded target",
                  total == af["coverage"]["downloaded"],
                  "" if total == af["coverage"]["downloaded"]
                  else f"{arm['n_compared']} compared + {len(arm['not_compared'])} skipped "
                       f"= {total}, but {af['coverage']['downloaded']} were downloaded")

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
