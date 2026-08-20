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
"""

from __future__ import annotations

import json
import re
import sys

from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def build() -> int:
    by_hash = plans()
    sections = readme_sections()
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
            "supersedes_reason": c.get("supersedes_reason"),
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
            "hypotheses": hyps,
            "metrics": metrics,
            "exploratory_metrics": exploratory,
            "prespec_audit": audit,
            "confirmatory": audit.get("confirmatory"),
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
        "confirmatory_note": "Every study in this slate deviated from its registered plan in "
                             "at least one respect, so every study's own audit records "
                             "confirmatory = false. The deviations are machine-detected and "
                             "listed per study; results affected by them are exploratory, not "
                             "confirmatory. Pre-registration did not make these results "
                             "confirmatory -- it made the deviations visible.",
        # A reader scanning #1, #2, #6...#11 under a tile reading "8 Studies" cannot tell an
        # infrastructure section from a suppressed negative. The gap is explained in the
        # README and was explained nowhere on the page.
        "numbering_note": (
            "The slate runs " + ", ".join(
                f"#{s['slate_number']}" for s in studies if s["slate_number"]) + ". "
            "#4 is the target-construct registry, which has no hypothesis and no plan hash, "
            "so it has no entry here. #3 and #5 were allocated to studies that were never "
            "registered and never run, and the numbers were not reused so that every citation "
            "keeps pointing at the same thing. Nothing has been withdrawn: prespec/ holds "
            f"{len(by_hash)} registered plans and every study family in it appears above."),
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
        print(f"  {n:>4s} {s['study_id']:28s} {s['plan_hash']}  {v:8s} "
              f"fail={s['n_failures']}  {s['title'][:38]}")
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
