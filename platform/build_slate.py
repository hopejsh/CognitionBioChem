"""Build data/slate.json: the pre-registered studies, assembled from plans and artefacts.

The README carries the study sections and the page carried none. A reader arriving at the
workbench saw a validation gate and a file dropzone, and nothing at all about the experiments
the repository exists to report -- including the two whose answer is negative. That asymmetry
flatters the project: the page showed the machinery and hid the results.

NOTHING HERE IS TYPED BY HAND. Each study contributes three files and this script joins them:

  prespec/<study>-v<N>.<hash>.json   the plan -- question, hypotheses, thresholds, confounds,
                                     hashed and registered BEFORE the run
  data/study_<name>.json             the artefact -- what the run measured and the verdicts
  README.md                          the slate number and section title

VERDICTS ARE COPIED, NOT RECOMPUTED. This script has no statistics in it, so it cannot
disagree with the study that produced them.

FOUR THINGS THIS FILE LEARNED THE HARD WAY, each from a defect that shipped:

1. ITERATE THE ARTEFACT'S VERDICTS, NOT THE PLAN'S HYPOTHESES. The first version walked the
   plan's hypothesis list, so any verdict the analysis produced under a name the plan did not
   contain was dropped in silence. Exactly one existed and it was the worst possible one:
   study #6's `H2_interpolation_premium_fisher`, FALSIFIED at p = 0.59, the test that refuses
   the criterion `H2_interpolation_premium` confirms on the same data. The README says of that
   pair "That is not a positive result, and the report no longer lets it read as one." The
   page let it read as one. Losses of this kind are never symmetric; they land on the
   inconvenient half.

2. A HYPOTHESIS IS A TEST ONLY IF ITS OWN DECISION RULE SAYS SO. Membership of `p_holm` was
   used as the signal, and `p_holm` contains whatever the study put in its correction family.
   The ache study's H3 -- "the Huperzine A absolute error lies within 2 SD of the mean" -- has
   no p-value anywhere in its rule, yet carried a Holm-adjusted 0.814 and was rendered as
   `test / p = 0.814 / CONFIRMED`. A reader saw a hypothesis confirmed at p = 0.814. The rule
   text decides now; a p-value reported beside a threshold is reported as exactly that.

3. `observed` IS NOT ALWAYS A NUMBER. Three of them are a dict or a list, and the page called
   String() on them: study #2's equivalence claim rendered as `[object Object]`, and study
   #8's falsification rendered its rho and its bootstrap CI as one unlabelled comma list. The
   generator normalises the shape, once, here -- the same fix `known_confounds` needed.

4. A JOIN THAT CAN SILENTLY PICK THE WRONG SECTION IS WORSE THAN NO JOIN. `next(...)` over
   sections took the first `##` block whose text contained the 12-character hash anywhere, so
   one prose cross-reference of the form "study #6 (`8457830a2c5e`)" placed inside an earlier
   section would relabel that study with the earlier section's number and title, exit 0. The
   join now requires exactly one match and reports a conflict rather than choosing.

5. A REGISTERED STATEMENT REPUBLISHED IS A LIVE CLAIM, NOT A RECORD. This script copies each
   plan's hypothesis `statement` verbatim onto the front page beside a verdict pill. Study #7
   registered `H2_iptm_calibration` as "ipTM predicts whether the interface is right, so it
   can be used as a screening filter", and study #12 later falsified exactly that use -- 4 of
   16 X-ray-established binders beat all ten permutations of themselves against a threshold
   of 5 registered in advance. The plan is hash-locked and is never rewritten, so the page
   went on publishing the superseded sentence under a green CONFIRMED, which is a licence to
   use the instrument the way #12 proved it cannot be used. The registered statement still
   renders exactly as registered; what changed is that it can no longer render ALONE. Every
   hypothesis is joined against `retractions.jsonl` here, and the withdrawal is emitted into
   the same object. `platform/check_retractions.py` verifies the result independently of this
   file, so deleting the join fails the build rather than quietly un-retracting the claim.

6. A STUDY WHOSE BYTES ARE NOT HERE MUST NOT RENDER LIKE ONE WHOSE BYTES ARE. Every study
   entry carried the same fields, so the page drew study #12 -- +0.0895, Holm p = 0.0148,
   4 of 16, 176 rows -- in the same card as eight studies whose numbers re-derive from
   coordinates a clone can open. 160 of #12's 176 rows name outputs under
   `runs/interface-null-positive-control/`, a tree that is deliberately not committed, and
   the README says so plainly while `slate.json` had no field to carry it and `app.js` had
   nothing to render. This is the one place the repository was claiming STRONGER provenance
   than it has, and the promise it broke is the workbench's central one. `custody` is now
   computed for every study against `runs/manifest.json` -- the record of which fold bytes
   this repository actually took custody of, not what happens to sit on the author's disk --
   and the page prints the shortfall beside the numbers it qualifies. Nothing here is typed:
   the counts come from the artefact's own rows, the regeneration cost is the measured
   compute the artefact recorded, and the module to re-run is found by its STUDY_ID.
"""

from __future__ import annotations

import ast
import json
import re
import sys

from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retractions as R                                             # noqa: E402
from cbc.provenance import git_sha                                   # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "slate.json"
OUT_JS = REPO / "data" / "slate.js"
README = REPO / "README.md"

#: A decision rule that mentions any of these is decided by a test statistic. Anything else is
#: a threshold comparison on a descriptive quantity, whatever the study filed it under.
_TEST_RULE = re.compile(r"\bp\s*[<>=]|\bp-value|\bp\s+<|Holm-adjusted p|permutation p|"
                        r"\bfisher\b.*\bp\b|\bt-test\b", re.I)


def sha() -> str | None:
    """Delegates to cbc.provenance.git_sha, which marks a dirty tree. See its docstring."""
    return git_sha(REPO)


def readme_sections() -> list[dict]:
    """Every `##` and `###` heading as its own section.

    Splitting on `##` alone swallowed `### The first pre-registered study`, so the ache study
    inherited the title of the methodology section it happens to sit inside and appeared on
    the page as a study called "Pre-registration".
    """
    text = README.read_text()
    heads = [(m.start(), len(m.group(1)), m.group(2))
             for m in re.finditer(r"^(#{2,3}) (.+)$", text, re.M)]
    out = []
    for i, (pos, level, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        # En-dash and colon are as plausible as the em-dash actually used; accepting only one
        # separator meant a heading typed with another silently lost its number.
        num = re.match(r"Slate #(\d+)\s*[—–:-]?\s*(.*)", title)
        out.append({"title": title, "level": level, "body": text[pos:end],
                    "number": int(num.group(1)) if num else None,
                    "short": num.group(2).strip() if num and num.group(2).strip() else title})
    return out


def plans() -> dict[str, dict]:
    """Registered plans keyed by full hash. Artefacts cite the full hash; only the README
    search uses the 12-character prefix."""
    out = {}
    for f in sorted((REPO / "prespec").glob("*.json")):
        d = json.loads(f.read_text())
        out[d["hash"]] = {"file": str(f.relative_to(REPO)), **d}
    return out


def _slate_name(s: dict) -> str:
    return f"#{s['slate_number']}" if s["slate_number"] else s["study_id"]


def _confirmatory_headline(studies: list[dict]) -> str:
    """The one-sentence form of counts.studies_confirmatory, for use as a heading.

    `confirmatory_note` below is a paragraph, and a paragraph is not what a panel headline
    or a slide bullet wants -- so four surfaces wrote their own heading by hand instead of
    reading it, and all four still said "Not one study in this slate is confirmatory" [SLATE-COUNT-HISTORICAL]
    after
    #12's audit came back with an empty deviation list. On the Pre-registered studies tab
    that sentence sat in bold directly above the derived paragraph that contradicted it and
    directly below a stat card reading "1 confirmatory". The heading is a claim about a
    count, so it is generated from the count.
    """
    clean = [s for s in studies if s["confirmatory"] is True]
    if not clean:
        return f"Not one of the {len(studies)} studies in this slate is confirmatory."
    noun = "confirmatory study" if len(clean) == 1 else "confirmatory studies"
    return (f"{len(clean)} {noun} of {len(studies)} — "
            + ", ".join(_slate_name(s) for s in clean)
            + f"; the other {len(studies) - len(clean)} deviated from their registered plan.")


def _confirmatory_note(studies: list[dict]) -> str:
    """The prose form of counts.studies_confirmatory, derived from the same audits.

    A hand-typed universal ("every study deviated") is a claim about all future studies
    written before they exist. verify_all.py already carries the version of this lesson
    that cost something: hand-maintained counts "will eventually lie".
    """
    name = _slate_name

    deviated = [s for s in studies if s["confirmatory"] is not True]
    clean = [s for s in studies if s["confirmatory"] is True]
    tail = ("The deviations are machine-detected and listed per study; results affected by "
            "them are exploratory, not confirmatory. Pre-registration did not make those "
            "results confirmatory -- it made the deviations visible.")
    if not clean:
        return ("Every study in this slate deviated from its registered plan in at least one "
                "respect, so every study's own audit records confirmatory = false. " + tail)
    return (f"{len(deviated)} of the {len(studies)} studies in this slate deviated from their "
            f"registered plan in at least one respect, so their audits record "
            f"confirmatory = false. " + tail + " The exception is "
            + ", ".join(name(s) for s in clean)
            + f", whose audit records no deviation at all and confirmatory = true"
            + (" -- the first study in this slate to do so." if len(clean) == 1 else "."))


def anchor_for(title: str) -> str:
    return "#" + re.sub(r"[^a-z0-9\s-]", "", title.lower()).strip().replace(" ", "-")


def label_from_metrics(v, metrics: dict) -> str | None:
    """Name a bare numeric pair by finding those values in the study's own metrics.

    Study #8's H3 observed `[1.0471, 0.4445]` and rendered as "1.0471, 0.4445" -- two
    unlabelled numbers under a threshold that names two different quantities, so a reader
    could not tell which was the model error and which the inter-laboratory dispersion. The
    labels are not typed here: they are the metric keys whose values these are.
    """
    if not isinstance(v, list) or not v or not all(isinstance(x, (int, float)) for x in v):
        return None
    named = []
    for x in v:
        hit = next((k for k, y in metrics.items()
                    if isinstance(y, (int, float)) and abs(y - x) < 1e-9), None)
        if hit is None:
            return None
        named.append(f"{hit.replace('_', ' ')} = {x:g}")
    return ", ".join(named)


def interval_straddles_threshold(crit: dict, metrics: dict) -> dict | None:
    """A criterion whose own confidence interval contains the line it was decided against.

    Study #11's H1 is CONFIRMED because the discrimination ratio 1.40 is below its 2.0
    threshold -- but the study's own bootstrap interval for that ratio is [0.96, 3.84], which
    contains 2.0. The verdict is real and the interval is real and they say different things,
    and the page showed the first in green with the second three cards away. Nothing here
    decides between them; the point is that a reader must not have to notice the tension
    unaided. Both numbers come from the artefact, and the threshold is parsed out of the
    study's own threshold string rather than typed.
    """
    obs, thr = crit.get("observed"), crit.get("threshold")
    if not isinstance(obs, (int, float)) or not isinstance(thr, str):
        return None
    nums = re.findall(r"-?\d+(?:\.\d+)?", thr)
    if not nums:
        return None
    line = float(nums[-1])
    for key, v in metrics.items():
        if "ci95" not in key or not (isinstance(v, list) and len(v) == 2):
            continue
        lo, hi = v
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))):
            continue
        # Only the interval belonging to THIS quantity: it must contain the observed value.
        if lo <= obs <= hi and lo <= line <= hi:
            return {"interval_metric": key, "interval": [lo, hi], "threshold_value": line,
                    "note": (f"the verdict rests on {obs} falling on one side of {line}, but "
                             f"this study's own {key.replace('_', ' ')} is [{lo}, {hi}], "
                             f"which contains {line}. The criterion is met and the interval "
                             f"does not exclude the other side; both are reported.")}
    return None


def render_observed(v) -> str | None:
    """A one-line rendering the page can print without calling String() on a dict."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v:g}"
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return ", ".join(f"{k} = {render_observed(x)}" for k, x in v.items())
    if isinstance(v, list):
        # A [point, [lo, hi]] pair is the shape the bootstrap studies use, and flattening it
        # destroyed exactly the interval the falsification turns on.
        if len(v) == 2 and isinstance(v[1], list) and len(v[1]) == 2:
            return f"{render_observed(v[0])} (95% CI [{v[1][0]:g}, {v[1][1]:g}])"
        return ", ".join(render_observed(x) for x in v)
    return str(v)


# --------------------------------------------------------------------- custody ------ #
#: The record of which prediction bytes this repository actually took custody of.
#: `runs/` on the author's disk is NOT that record. All 176 of study #12's row paths resolve
#: with `Path.exists()` here, and 160 of them resolve for nobody else: they name
#: `runs/interface-null-positive-control/`, 805 files the study wrote straight into the tree
#: and that was never committed. A check built on `exists()` would have passed on the one
#: machine where the answer does not matter. `runs/manifest.json` is what
#: `platform/rescue_runs.py` writes when a run is taken into custody, and `cbc.provenance`
#: already leans on it for exactly this property -- "all 503 entries of runs/manifest.json
#: resolve to files the clone has". It is the honest authority, so it is the one used here.
MANIFEST = REPO / "runs" / "manifest.json"

#: The repository's own CLI convention for the two steps that produce fold bytes. These two
#: names are the only strings in this block that are not read out of an artefact, and they
#: are not trusted either: `module_cli()` returns the flags the module's argparse actually
#: defines, and a step this module names that the study module does not offer is reported
#: rather than printed as an instruction that would fail.
REGENERATION_STEPS = ("fetch", "run")


def files_under_custody() -> set[str]:
    """Every repository-relative path `runs/manifest.json` records bytes and a sha256 for."""
    if not MANIFEST.exists():
        return set()
    m = json.loads(MANIFEST.read_text())
    return {f"{r['path']}/{f['file']}" for r in m.get("runs", [])
            for f in r.get("files", []) if r.get("path") and f.get("file")}


def _loop_flag_names(tree: ast.AST, call: ast.Call) -> set[str]:
    """String constants of the `for f in ("register", "fetch", ...)` loop wrapping a call.

    The study modules define their flags in a loop over a tuple, so the argument to
    `add_argument` is `f"--{f}"` and reading the call alone yields the placeholder rather
    than the flags. Reading the loop is the difference between checking the CLI and
    pretending to.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, (ast.Tuple, ast.List)):
            if any(c is call for c in ast.walk(node)):
                names |= {e.value for e in node.iter.elts
                          if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return names


def module_cli(study_id: str) -> tuple[str | None, set[str], str | None]:
    """The module that owns a study, and the long flags its argparse defines.

    Found by its `STUDY_ID` assignment rather than by transforming the study id into a
    filename: the transformation is a guess that succeeds silently on the wrong file. More
    than one match is reported, never resolved -- the same rule the README join follows four
    functions up, and for the same reason.
    """
    hits = []
    for f in sorted((REPO / "platform" / "studies").glob("*.py")):
        src = f.read_text()
        if re.search(rf'^STUDY_ID\s*=\s*["\']{re.escape(study_id)}["\']', src, re.M):
            hits.append((f, src))
    if len(hits) != 1:
        return None, set(), (f"{len(hits)} modules in platform/studies/ declare "
                             f"STUDY_ID = {study_id!r}")
    f, src = hits[0]
    flags: set[str] = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value.lstrip("-"))
                elif isinstance(arg, ast.JoinedStr):
                    flags |= _loop_flag_names(tree, node)
    return str(f.relative_to(REPO)), flags, None


def custody_for(study_id: str, body: dict, a: dict, tracked: set[str]) -> dict:
    """Whether a clone can open the bytes behind this study's rows, counted from the rows.

    Every study entry used to carry the same fields, so the page drew study #12's numbers in
    the same card as eight studies whose numbers re-derive from coordinates the repository
    ships. It does not ship #12's: 160 of its 176 rows name a run tree that is deliberately
    untracked. The README states this in full and `slate.json` had nowhere to put it.

    A row is under custody when EVERY `runs/` path it names is in the manifest. Any path, not
    just `model`: study #11 names `structure` and study #8 names `pred_cif` and `ref_cif`,
    and a check that knew only the field name study #12 happens to use would report perfect
    custody for a study whose reference structures had gone missing.
    """
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    citing = held = short = 0
    trees: set[str] = set()
    for r in rows:
        paths = [v for v in r.values() if isinstance(v, str) and v.startswith("runs/")]
        if not paths:
            continue
        citing += 1
        absent = [q for q in paths if q not in tracked]
        if absent:
            short += 1
            trees |= {"runs/" + q.split("/")[1] + "/" for q in absent}
        else:
            held += 1

    # The sha256 over the study's own inputs is what makes a regeneration checkable rather
    # than merely repeatable, so it travels with the shortfall it answers.
    digests = {k: v for src in (body, a) for k, v in src.items()
               if "sha256" in k and isinstance(v, str)}

    out = {
        "rows": len(rows),
        "rows_citing_a_fold_output": citing,
        "rows_whose_bytes_this_repository_holds": held,
        "rows_whose_bytes_this_repository_does_not_hold": short,
        "complete": (short == 0) if citing else None,
        "checked_against": str(MANIFEST.relative_to(REPO)),
        "files_under_custody": len(tracked),
        "run_trees_not_in_this_repository": sorted(trees),
        "input_digests": digests,
        "basis": ("a row is under custody when every runs/ path it names appears in "
                  "runs/manifest.json with a sha256. Presence on the machine that built this "
                  "file is not the test: the untracked tree resolves there and nowhere else."),
    }
    if not citing:
        out["note"] = ("no row in this artefact names a path under runs/, so there is "
                       "nothing here for the manifest to resolve.")
        return out
    if not short:
        out["note"] = (f"all {held} rows that name a fold output name bytes this repository "
                       f"carries, so every number in this study re-derives from files a "
                       f"clone can open.")
        return out

    # -- the shortfall, and what it would cost to close it ---------------------------- #
    ru = body.get("reuse_accounting") or a.get("reuse_accounting") or {}
    computed = ru.get("cumulative_folds_computed_across_invocations")
    seconds = ru.get("cumulative_compute_seconds")
    rate = (ru.get("cumulative_mean_seconds_per_computed_fold")
            or ru.get("mean_seconds_per_computed_fold"))
    if seconds is not None and computed == short:
        # The artefact measured the wall clock of exactly these folds. Preferred over the
        # rate for the reason its own note gives: "Multiplying a rate by folds that were
        # never computed is how this project once overstated its compute by 6.5x."
        cost_seconds, cost_basis = seconds, (
            f"measured: reuse_accounting.cumulative_compute_seconds, the summed wall clock "
            f"of the {computed} folds this artefact computed, which is exactly the "
            f"{short} rows whose bytes are missing")
    elif rate:
        cost_seconds, cost_basis = round(rate * short, 1), (
            f"estimated: {short} folds at the artefact's measured "
            f"{rate} s per computed fold")
    else:
        cost_seconds, cost_basis = None, None

    module, flags, problem = module_cli(study_id)
    steps = [f"--{x}" for x in REGENERATION_STEPS if x in flags]
    missing_steps = [f"--{x}" for x in REGENERATION_STEPS if x not in flags]
    regen = {
        "module": module,
        "found_by": "the STUDY_ID declared in platform/studies/, not a guessed filename",
        "steps": steps,
        "command": (f"./.venv/bin/python {module} {' '.join(steps)}"
                    if module and steps else None),
        "compute_seconds": cost_seconds,
        "gpu_hours": round(cost_seconds / 3600, 2) if cost_seconds is not None else None,
        "compute_basis": cost_basis,
    }
    if problem:
        regen["problem"] = problem
    if missing_steps:
        regen["problem"] = (f"{module} does not define {', '.join(missing_steps)}; its CLI "
                            f"offers {sorted('--' + x for x in flags)}")
    out["regeneration"] = regen
    out["note"] = (
        f"{short} of this study's {len(rows)} rows name fold outputs under "
        + ", ".join(sorted(trees))
        + f" — a run tree this repository deliberately does not carry. Those "
        f"{short} confidence values are reproducible by re-running the study and are NOT "
        f"verifiable against stored bytes, unlike the "
        f"{held} rows whose folds are in runs/manifest.json. Everything needed to make the "
        f"folds again travels with the artefact"
        + (f" ({', '.join(sorted(digests))})" if digests else "")
        # Self-contained, because this sentence is republished into the report, the Korean
        # report and the deck as well as the page, and "the command above" is true on
        # exactly one of them. A note that only reads correctly beside the fields it was
        # written next to is the fan-out this whole block exists to stop.
        + (f"; regenerating them is {regen['command']}"
           # One decimal, the same rendering the tile and the README use. Two decimals here
           # and one there reads as two different measurements of the same thing.
           + (f", ≈ {regen['gpu_hours']:.1f} GPU-hours." if regen["gpu_hours"] else ".")
           if regen.get("command") else "."))
    return out


def build() -> int:
    by_hash = plans()
    sections = readme_sections()
    tracked = files_under_custody()
    studies: list[dict] = []
    problems: list[str] = []

    for f in sorted((REPO / "data").glob("study_*.json")):
        body = json.loads(f.read_text())
        a = body.get("analysis") or body
        h = a.get("prespec_hash")
        if not h:
            continue
        plan = by_hash.get(h)
        if plan is None:
            problems.append(f"{f.name} cites plan {h[:12]}, which is not in prespec/")
            continue
        c = plan["content"]
        short = h[:12]

        # -- README join: exactly one section, or none and a recorded conflict ------------ #
        matches = [s for s in sections if short in s["body"]]
        conflict = None
        if len(matches) == 1:
            sec = matches[0]
        else:
            sec = None
            if len(matches) > 1:
                conflict = [s["title"] for s in matches]
                problems.append(f"{c['study_id']}: plan {short} appears in "
                                f"{len(matches)} README sections {conflict}; refusing to "
                                "choose one")
            else:
                # Zero matches loses the number AND the title in silence, which is the same
                # asymmetric loss as the conflict case one direction over.
                conflict = []
                problems.append(f"{c['study_id']}: plan {short} appears in NO README "
                                "section, so the study is published without a number or a "
                                "title of its own")

        verdicts = a.get("verdicts") or {}
        crit = a.get("criteria") or {}
        holm = a.get("p_holm") or {}
        raw = a.get("p_raw") or {}
        registered = {x["name"]: x for x in c.get("hypotheses", [])}
        metrics = a.get("metrics") or {}
        withdrawn = R.load()

        # Walk the union, artefact first, so nothing the analysis decided can go missing.
        names = list(registered) + [n for n in verdicts if n not in registered]
        hyps = []
        for n in names:
            hyp = registered.get(n, {})
            rule = hyp.get("confirmed_if") or ""
            rule_cites_test = bool(_TEST_RULE.search(rule))
            # A hypothesis is a TEST only if a p-value both decided it and was corrected for
            # it. The rule text is necessary -- it is what stopped the ache study's 2-SD
            # check being rendered as "test / p = 0.814" -- but it is not sufficient: study
            # #2's equivalence claim names a t-test inside a threshold rule and the study
            # filed it under `criteria`, so calling it a test would misreport it in the other
            # direction. Where a threshold rule embeds a test statistic, that is recorded
            # rather than resolved, because it is a real property of the hypothesis.
            decided_by_test = bool(n in holm and (rule_cites_test or not rule))
            entry = {
                "name": n,
                "registered": n in registered,
                "statement": hyp.get("statement"),
                "confirmed_if": hyp.get("confirmed_if"),
                "verdict": verdicts.get(n),
                "kind": ("test" if decided_by_test
                         else "criterion" if (n in crit or rule) else "unknown"),
                "rule_cites_a_test_statistic": rule_cites_test,
            }
            # The registered sentence above is reproduced exactly as registered. If a later
            # study withdrew what it asserts, the withdrawal is attached here so the two can
            # never be separated by a renderer, a copy-paste, or a reader in a hurry.
            ret = R.for_hypothesis(withdrawn, c["study_id"], n, hyp.get("statement"))
            if ret is not None:
                entry["retraction"] = {
                    **ret.as_rendered(),
                    "applies_to": "the registered statement, not the verdict",
                    "note": ("the plan is hash-locked and is not edited; this withdrawal is "
                             "joined from retractions.jsonl at build time and travels with "
                             "the statement wherever it is republished"),
                }
            # A second and different join. Above, the SENTENCE was withdrawn. Here the
            # sentence and the verdict both stand and what is withdrawn is the reading the
            # DECISION RULE rests on -- #9's H1 and #10's H2 each ask whether one candidate
            # beat its own shuffles, which is the per-case reading study #12 falsified. A
            # green CONFIRMED reading "a candidate is confident and specific" is the worst
            # version of that: 2 of 13 cleared the threshold where 1.18 are expected by
            # chance. Striking those statements would print a falsehood, so this emits a
            # boundary instead of a withdrawal and the renderer keeps them apart.
            lim = R.reading_limit_for(withdrawn, c["study_id"], n)
            if lim is not None:
                entry["reading_limit"] = lim[0].as_reading_limit(lim[1])
            if rule_cites_test and not decided_by_test:
                entry["threshold_embeds_a_test"] = (
                    "the decision rule names a test statistic, but the study filed this "
                    "hypothesis as a threshold criterion and applied no multiplicity "
                    "correction to it; the test's value is inside the observed column")
            if not rule and decided_by_test:
                entry["kind_inferred_from"] = (
                    "the registered plan carries no decision rule for this name, so its kind "
                    "was taken from its membership of the correction family alone")
            if n not in registered:
                entry["unregistered_note"] = (
                    "decided by the analysis under a name the registered plan does not "
                    "contain, so it is reported here as the analysis reported it and is not "
                    "part of the pre-registered family")
            if n in holm:
                entry["p_holm"] = holm[n]
                entry["p_raw"] = raw.get(n)
                if not decided_by_test:
                    entry["p_is_incidental"] = (
                        "this hypothesis is decided by the threshold above; the study placed "
                        "it in the correction family, so a Holm-adjusted value exists, but no "
                        "p-value appears in its decision rule and none decided it")
            if n in crit:
                obs = crit[n].get("observed")
                entry["observed"] = obs
                entry["observed_text"] = (label_from_metrics(obs, metrics)
                                          or render_observed(obs))
                entry["threshold"] = crit[n].get("threshold")
                entry["confirmed_by_absence_note"] = crit[n].get("note")
                straddle = interval_straddles_threshold(crit[n], metrics)
                if straddle:
                    entry["interval_contains_the_threshold"] = straddle
            hyps.append(entry)

        rows = body.get("rows") or []
        # Three studies record a technical failure as `ok: false` on the row rather than in a
        # `failures` list, so counting the list alone printed "Technical failures 0" for a
        # study whose README paragraph is about the failure it reported. But the two records
        # OVERLAP -- study #6's 3X39 appears in both -- and adding them gave 4 for a study
        # whose own artefact says 16 planned and 13 observed. Count distinct units of work.
        def unit(x):
            """A key that identifies the unit of work, or the record itself if none applies.

            The first version keyed on five names and nothing else. Study #1's rows carry
            `chembl`/`name` and none of those five, so both of its failed rows collapsed to
            (None,)*5 and de-duplicated to ONE -- publishing "0 in the failures list, 2 rows
            marked not ok; they overlap, so 1 distinct", which is arithmetically impossible
            and contradicts the README's "two salts the affinity head rejected". A key that
            matches nothing must not silently merge records: fall back to the record.
            """
            k = tuple(x.get(n) for n in
                      ("pdb_id", "code", "job", "chembl", "name", "stratum", "seed"))
            return k if any(v is not None for v in k) else json.dumps(x, sort_keys=True)
        listed = a.get("failures") or []
        failed_rows = [r for r in rows if r.get("ok") is False]
        distinct = {unit(x) for x in listed} | {unit(r) for r in failed_rows}
        n_listed, n_failed_rows = len(listed), len(failed_rows)
        n_distinct = len(distinct)

        # The plan's lineage note is prose the plan happens to carry, not a hypothesis, so
        # it needs its own join: `for_hypothesis` walks verdicts and would never look at it.
        plan_field = R.plan_field_for(withdrawn, c["study_id"], "supersedes_reason")

        audit = a.get("prespec_audit") or {}
        mult = a.get("multiplicity") or {}
        # Metrics the audit itself flags as unregistered are the ones a reader most needs, and
        # #10's screen-level null lives here: it is the sentence that says two winners out of
        # thirteen is what chance looks like.
        exploratory = {}
        for k, v in metrics.items():
            if isinstance(v, dict) and "interpretation" in v:
                exploratory[k] = v

        studies.append({
            "slate_number": sec["number"] if sec else None,
            "title": sec["short"] if sec else c["study_id"],
            "readme_anchor": anchor_for(sec["title"]) if sec else None,
            "readme_join_conflict": conflict,
            "study_id": c["study_id"],
            "plan_hash": short,
            "plan_file": plan["file"],
            "registered_utc": plan.get("registered_utc"),
            "supersedes": c.get("supersedes"),
            # Copied from the plan byte for byte, and never rewritten on the way out. A
            # lineage note can outlive its own facts: msa-specificity-v9's says the screened
            # set gives "13 distinct designs", and the two screens have since derived 13
            # constructs over 12 distinct peptides from their own rows. Editing the string
            # here would break the one promise the plan directory makes. So the string ships
            # as registered and the correction ships beside it, joined from retractions.jsonl
            # against a `plan_field` anchor -- the same journey a withdrawn hypothesis
            # statement makes, one field over.
            "supersedes_reason": c.get("supersedes_reason"),
            "supersedes_reason_correction": (
                plan_field[0].as_plan_field_correction(plan_field[1])
                if plan_field else None),
            "artefact": str(f.relative_to(REPO)),
            "question": c.get("question"),
            "primary_metric": c.get("primary_metric"),
            "decision_threshold": c.get("decision_threshold"),
            "known_confounds": ([c["known_confounds"]]
                                if isinstance(c.get("known_confounds"), str)
                                else list(c.get("known_confounds") or [])),
            "multiplicity": mult,
            "excluded_from_correction": mult.get("excluded_from_correction") or [],
            "n_observed": a.get("n_observed"),
            "n_planned": c.get("n_planned"),
            # The page needs the number of CANDIDATES, not the number of folds: "2 of 13 beat
            # all their decoys" is a different denominator from "143 folds". Hard-coding it in
            # app.js is what this file exists to prevent.
            "n_candidates": (len(a["per_candidate"])
                             if isinstance(a.get("per_candidate"), list) else None),
            # And how many MOLECULES those constructs are. De-duplication in the screen is
            # applied on (peptide, target), so one peptide declared against two receptors is
            # screened twice and every mean and count downstream is taken over constructs.
            # The page said "13 distinct candidates" for exactly as long as nothing carried
            # the second number; it is 12, and it comes from the artefact, not from here.
            "peptide_multiplicity": a.get("peptide_multiplicity"),
            "n_distinct_peptides": (a.get("peptide_multiplicity") or {}).get(
                "n_distinct_peptides"),
            "hypotheses": hyps,
            # Hypothesis withdrawals AND any correction on a republished plan field. The
            # second belongs here rather than in a list of its own: the study really does
            # carry a withdrawn claim on the page, and it is the field's own enclosing object
            # that check_retractions.py asks for a `retraction` naming the record. Split the
            # two apart and the guard has nothing to accept the republished wording by.
            "retractions": sorted({h["retraction"]["id"] for h in hyps
                                   if "retraction" in h}
                                  | ({plan_field[0].id} if plan_field else set())),
            # Kept apart from `retractions` for the reason the two joins are kept apart: a
            # reader who sees a study listed under "retractions" concludes something was
            # withdrawn in it, and for #9 and #10 nothing was.
            "reading_limits": sorted({h["reading_limit"]["retraction"] for h in hyps
                                      if "reading_limit" in h}),
            # The artefact's own reading of its numbers. #9's is where this repository wrote
            # its central retraction down -- "This key previously ended: ... Study #12
            # falsified that clause and it is withdrawn" -- and until now it stopped at the
            # artefact and never reached the page, which is the audit's pattern exactly: the
            # correction was made, on a surface the reader is not looking at.
            "interpretation_key": a.get("interpretation_key"),
            "interpretation_key_states_a_withdrawal":
                R.states_a_withdrawal(a.get("interpretation_key")),
            "metrics": metrics,
            "exploratory_metrics": exploratory,
            "prespec_audit": audit,
            "confirmatory": audit.get("confirmatory"),
            # Whether a clone can open the bytes these numbers were read from. Eight studies
            # can say yes; #12 cannot, and until now the page did not let it say so.
            "custody": custody_for(c["study_id"], body, a, tracked),
            "n_failures": n_distinct,
            "n_failures_detail": {"listed_in_failures": n_listed,
                                  "rows_marked_not_ok": n_failed_rows,
                                  "distinct": n_distinct,
                                  "note": ("the two records overlap; distinct is the count "
                                           "of separate units of work that failed")},
        })

    # study_inference_variance.json is the raw fold log and ..._analysis.json is its analysis;
    # both cite the same plan. One study, one entry: prefer whichever decided the hypotheses.
    def _absorb(keep: dict, drop: dict) -> None:
        """Fold the companion in without losing anything it decided.

        The merge previously kept only the richer artefact's hypothesis list. Nothing is lost
        today because the raw fold log decides nothing, but a verdict living only in the
        dropped artefact would have disappeared in silence -- which is the exact failure this
        module was rewritten to close, one layer up.
        """
        keep.setdefault("companion_artefacts", []).extend(
            [drop["artefact"], *(drop.get("companion_artefacts") or [])])
        # The rows live in one artefact and the verdicts in the other. Study #6's fold log
        # holds all 87 rows and decides nothing, so it is always the one dropped -- and its
        # custody went with it, publishing "no row names a path under runs/" for the one
        # study in the slate whose every row does. Custody is a property of the study, so it
        # is summed across the artefacts the study is made of.
        kc, dc = keep.get("custody"), drop.get("custody")
        if kc and dc:
            kept_cited = kc["rows_citing_a_fold_output"]
            for k in ("rows", "rows_citing_a_fold_output",
                      "rows_whose_bytes_this_repository_holds",
                      "rows_whose_bytes_this_repository_does_not_hold"):
                kc[k] += dc[k]
            kc["run_trees_not_in_this_repository"] = sorted(
                set(kc["run_trees_not_in_this_repository"])
                | set(dc["run_trees_not_in_this_repository"]))
            kc["input_digests"] = {**dc["input_digests"], **kc["input_digests"]}
            kc["complete"] = ((kc["rows_whose_bytes_this_repository_does_not_hold"] == 0)
                              if kc["rows_citing_a_fold_output"] else None)
            # The note describes rows, so it comes from the artefact that has them.
            if not kept_cited and dc["rows_citing_a_fold_output"]:
                kc["note"] = dc["note"]
            if "regeneration" in dc and "regeneration" not in kc:
                kc["regeneration"] = dc["regeneration"]
        shown = {h["name"] for h in keep["hypotheses"]}
        for h in drop["hypotheses"]:
            if h["verdict"] and h["name"] not in shown:
                h["from_companion_artefact"] = drop["artefact"]
                keep["hypotheses"].append(h)

    merged: dict[str, dict] = {}
    for s in studies:
        key = s["study_id"]
        prev = merged.get(key)
        decided = sum(1 for x in s["hypotheses"] if x["verdict"])
        if prev is None:
            merged[key] = s
        elif decided > sum(1 for x in prev["hypotheses"] if x["verdict"]):
            _absorb(s, prev)
            merged[key] = s
        else:
            _absorb(prev, s)
    studies = list(merged.values())
    studies.sort(key=lambda s: (s["slate_number"] is None, s["slate_number"] or 0))

    # The one robustness claim the page makes about the headline, computed over every
    # retained version rather than asserted. An earlier hand-written version of this sentence
    # said "every correction made the separation smaller", which the superseded artefacts
    # refute: it ran -0.006, -0.015, -0.045, -0.041, -0.012, +0.001 across the screen's six
    # versions. What IS true of all of them is the verdict.
    versions = []
    for f in sorted(list((REPO / "data" / "superseded").glob("study_*.json"))
                    + [REPO / "data" / "study_candidate_screen.json",
                       REPO / "data" / "study_msa_specificity.json"]):
        b = json.loads(f.read_text())
        av = (b.get("analysis") or b).get("verdicts") or {}
        h1 = next((k for k in av if k.startswith("H1")), None)
        if h1 and ("candidate_screen" in f.name or "msa_specificity" in f.name):
            versions.append({"artefact": str(f.relative_to(REPO)),
                             "hypothesis": h1, "verdict": av[h1],
                             "n_candidates": len((b.get("analysis") or b).get(
                                 "per_candidate") or [])})
    separation_versions = {
        "note": "every retained version of the two screening studies, oldest first",
        "n_versions": len(versions),
        "all_falsified": all(v["verdict"] == "FALSIFIED" for v in versions),
        "versions": versions,
    }

    hyps_all = [h for s in studies for h in s["hypotheses"] if h["verdict"]]
    confirmed = sum(1 for h in hyps_all if h["verdict"] == "CONFIRMED")
    falsified = sum(1 for h in hyps_all if h["verdict"] == "FALSIFIED")
    other = len(hyps_all) - confirmed - falsified
    # "Decided by" must range over hypotheses that were DECIDED. Counting NOT_TESTED under
    # `decided_by_a_threshold` filed a hypothesis that was never decided under how it was
    # decided, and made the two identities in this block use different denominators under the
    # same word.
    decided_h = [h for h in hyps_all if h["verdict"] in ("CONFIRMED", "FALSIFIED")]
    by_test = sum(1 for h in decided_h if h["kind"] == "test")
    by_thresh = sum(1 for h in decided_h if h["kind"] == "criterion")
    unknown = len(decided_h) - by_test - by_thresh

    index = {
        "schema_version": "1.2",
        "built": date.today().isoformat(),
        "git_sha": sha(),
        "note": "Assembled by platform/build_slate.py from the registered plans, the study "
                "artefacts and the README. No verdict, threshold or p-value is computed here "
                "-- all are copied from the artefact that produced them.",
        "counts": {
            "studies": len(studies),
            "hypotheses": len(hyps_all),
            "confirmed": confirmed,
            "falsified": falsified,
            "not_tested": other,
            "decided": confirmed + falsified,
            "decided_by_a_test": by_test,
            "decided_by_a_threshold": by_thresh,
            "decided_by_neither": unknown,
            "unregistered": sum(1 for h in hyps_all if not h["registered"]),
            "studies_confirmatory": sum(1 for s in studies if s["confirmatory"] is True),
            # A tile that counts studies without counting which of them a reader can check
            # is the tile that let #12 sit in the slate looking like the other eight.
            "studies_whose_fold_bytes_are_all_in_this_repository":
                sum(1 for s in studies if s["custody"]["complete"] is True),
            "studies_with_an_incomplete_custody_record":
                sum(1 for s in studies if s["custody"]["complete"] is False),
        },
        "reading_note": "A CONFIRMED criterion is not a test result. Most hypotheses here are "
                        "pre-specified threshold comparisons on a descriptive statistic, "
                        "decided by looking at a number against a line drawn in advance, and "
                        "the count of confirmations is not a score. A few of those rules name "
                        "a test statistic inside them and are flagged with "
                        "`threshold_embeds_a_test`; where they do, the value is in the "
                        "observed column and no multiplicity correction was applied to it. "
                        "Several confirmations are confirmations of unwelcome statements -- "
                        "that a method does not discriminate, or that candidates fall in a "
                        "failed band.",
        # This sentence used to read "Every study in this slate deviated from its
        # registered plan in at least one respect". It was typed by hand and it stopped
        # being true the moment a study registered a plan and ran it without deviating,
        # while the counts block three lines up already said studies_confirmatory = 1.
        # It is now derived from the same audits the count is derived from, so the two
        # cannot disagree again.
        # The bold line above that paragraph on the page, and the bullet the deck and both
        # report editions print. Four hand-written copies of it survived #12 and had to be
        # corrected one surface at a time; there is now one string and four readers of it.
        "confirmatory_headline": _confirmatory_headline(studies),
        "confirmatory_note": _confirmatory_note(studies),
        # A reader scanning #1, #2, #6...#11 under a tile reading "8 Studies" cannot tell an
        # infrastructure section from a suppressed negative. The gap is explained in the
        # README and was explained nowhere on the page.
        "numbering_note": (
            "The slate runs " + ", ".join(
                f"#{s['slate_number']}" for s in studies if s["slate_number"]) + ". "
            "#4 is the target-construct registry, which has no hypothesis and no plan hash, "
            "so it has no entry here. #3 and #5 were allocated to studies that were never "
            "registered and never run, and the numbers were not reused so that every citation "
            "keeps pointing at the same thing. NO SLATE NUMBER HAS BEEN WITHDRAWN: prespec/ "
            f"holds {len(by_hash)} registered plans and every study family in it appears "
            "above. That is a statement about numbering and not about findings — this "
            "project has withdrawn claims, and each withdrawal is recorded in "
            "retractions.jsonl and shown beside the claim it retracts."),
        "separation_across_versions": separation_versions,
        "studies": studies,
    }
    OUT.write_text(json.dumps(index, indent=2) + "\n")
    OUT_JS.write_text("// GENERATED by platform/build_slate.py -- do not edit.\n"
                      "// Byte-for-byte the same object as data/slate.json; this form exists\n"
                      "// only so the page still works when opened from a file: URL.\n"
                      "window.__CBC_SLATE__ = " + json.dumps(index, indent=2) + ";\n")
    print(f"wrote {OUT.relative_to(REPO)} and {OUT_JS.relative_to(REPO)}")
    for s in studies:
        n = f"#{s['slate_number']}" if s["slate_number"] else "  —"
        v = " ".join(("*" if not h["registered"] else "") + h["verdict"][0]
                     for h in s["hypotheses"] if h["verdict"])
        cu = s["custody"]
        cust = ("" if cu["complete"] is not False else
                f" CUSTODY {cu['rows_whose_bytes_this_repository_does_not_hold']}"
                f"/{cu['rows']} rows missing")
        print(f"  {n:>4s} {s['study_id']:28s} {s['plan_hash']}  {v:8s} "
              f"fail={s['n_failures']}  {s['title'][:38]}{cust}")
    c = index["counts"]
    print(f"  {c['confirmed']}C / {c['falsified']}F / {c['not_tested']}NT over "
          f"{c['hypotheses']} hypotheses ({c['unregistered']} unregistered, marked *)")
    print(f"  kinds: {c['decided_by_a_test']} test + {c['decided_by_a_threshold']} threshold "
          f"+ {c['decided_by_neither']} neither = {c['decided']} decided")
    unnumbered = [s["study_id"] for s in studies if s["slate_number"] is None]
    if unnumbered:
        print(f"  no numbered README section: {unnumbered}")
    if problems:
        print("\n  PROBLEMS:")
        for p in problems:
            print("   -", p)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
