"""Reproducible failure classification and cross-run aggregation for qc_summary.json files.

qc_summary.json rows already carry a hand-written `failure_kind`/`error_cause`,
but no script in this repo derives them - they were labeled once and pasted
into the committed output. `classify()` re-derives the same categories from
`candidate_status` and `error_cause`/`error` with fixed rules, so every future
run gets the breakdown automatically instead of someone re-reading error text.
"""

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

import re

RUNTIME_RULES = [
    ("null_reference", re.compile(r"Object reference not set to an instance of an object")),
    ("missing_attribute_or_api", re.compile(r"has no attribute")),
    ("api_argument_mismatch", re.compile(
        r"Argument mismatch|No method matches given arguments|unexpected keyword argument|"
        r"Trying to dynamically access a method that does not exist")),
    ("undefined_symbol", re.compile(r"name '[^']+' is not defined")),
    ("python_exception", re.compile(
        r"KeyError|was not found in the collection|throws a TypeError exception")),
]

BREAKDOWN_FIELDS = ("template_id", "specificity", "segment", "split")


def classify(row):
    """Failure kind for one qc_summary.json row, or None if it completed."""
    status = row.get("candidate_status")
    if status == "completed":
        return None
    if status == "not_generated":
        return "not_generated"
    if status == "no_code" or row.get("decline_text"):
        return "declined_no_code"
    if status == "infrastructure_error":
        return "pending_infrastructure_error"
    cause = row.get("error_cause") or row.get("error") or ""
    for kind, pattern in RUNTIME_RULES:
        if pattern.search(cause):
            return kind
    return "other_runtime_error"


def load_rows(paths):
    """Read every qc_summary.json matched by `paths`, tagging rows with their run."""
    rows = []
    seen = set()
    for pattern in paths:
        for match in sorted(glob.glob(pattern, recursive=True)):
            if match in seen:
                continue
            seen.add(match)
            data = json.loads(Path(match).read_text())
            run = data.get("run_label") or Path(match).parent.name
            for row in data.get("rows", []):
                rows.append(dict(row, run=run, source_file=match))
    return rows


def validate_against_recorded(rows):
    """Rows where the stored failure_kind disagrees with a fresh classify() call."""
    mismatches = []
    for row in rows:
        recorded = row.get("failure_kind")
        if recorded is None:
            continue
        derived = classify(row)
        if derived != recorded:
            mismatches.append({"run": row["run"], "prompt_id": row.get("prompt_id"),
                                "recorded": recorded, "derived": derived,
                                "error_cause": row.get("error_cause")})
    return mismatches


def _group_stats(rows):
    total = len(rows)
    completed = sum(1 for r in rows if r.get("candidate_status") == "completed")
    kinds = Counter(classify(r) for r in rows if classify(r) is not None)
    return {"total": total, "completed": completed,
            "completion_rate": round(completed / total, 3) if total else None,
            "failure_kinds": dict(kinds)}


def aggregate(rows):
    """Overall + per-dimension completion/failure breakdowns, by run."""
    by_run = {}
    for run in sorted({r["run"] for r in rows}):
        run_rows = [r for r in rows if r["run"] == run]
        by_run[run] = {"overall": _group_stats(run_rows),
                        "by": {field: {value: _group_stats([r for r in run_rows if r.get(field) == value])
                                       for value in sorted({r.get(field) for r in run_rows if r.get(field) is not None})}
                               for field in BREAKDOWN_FIELDS}}
    return {"overall": _group_stats(rows), "by_run": by_run}


def generalization_gap(run_summary):
    """Tuned-vs-held-out completion rates for one run's `by.split` breakdown."""
    split = run_summary["by"].get("split", {})
    tuned, held_out = split.get("tuned_on"), split.get("held_out")
    if not tuned or not held_out:
        return None
    return {"tuned_on_rate": tuned["completion_rate"], "held_out_rate": held_out["completion_rate"],
            "generalizes": held_out["completion_rate"] is not None and tuned["completion_rate"] is not None
            and held_out["completion_rate"] >= tuned["completion_rate"] * 0.75}


def render_markdown(agg):
    lines = ["# Error analysis", ""]
    lines.append("## Overall")
    lines.append("")
    o = agg["overall"]
    lines.append("- {}/{} completed ({})".format(o["completed"], o["total"], o["completion_rate"]))
    lines.append("")
    lines.append("| Failure kind | Count |")
    lines.append("|---|---:|")
    for kind, count in sorted(o["failure_kinds"].items(), key=lambda kv: -kv[1]):
        lines.append("| {} | {} |".format(kind, count))
    lines.append("")
    for run, summary in agg["by_run"].items():
        lines.append("## Run: {}".format(run))
        lines.append("")
        gap = generalization_gap(summary)
        if gap:
            verdict = "generalizes" if gap["generalizes"] else "does NOT generalize"
            lines.append("- tuned-on rate {}, held-out rate {} -> {}".format(
                gap["tuned_on_rate"], gap["held_out_rate"], verdict))
            lines.append("")
        for field in BREAKDOWN_FIELDS:
            values = summary["by"].get(field)
            if not values:
                continue
            lines.append("### By {}".format(field))
            lines.append("")
            lines.append("| {} | Completed/Total |".format(field))
            lines.append("|---|---:|")
            for value, stats in values.items():
                lines.append("| {} | {}/{} |".format(value, stats["completed"], stats["total"]))
            lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+",
                         help="qc_summary.json files or glob patterns, e.g. 'eval_results/**/qc_summary.json'")
    parser.add_argument("--validate", action="store_true",
                         help="print rows where classify() disagrees with the recorded failure_kind")
    parser.add_argument("--md-out", help="write the Markdown report to this path")
    parser.add_argument("--json-out", help="write the raw aggregation to this path")
    args = parser.parse_args()

    rows = load_rows(args.paths)
    if not rows:
        raise SystemExit("No rows found for: " + " ".join(args.paths))

    if args.validate:
        mismatches = validate_against_recorded(rows)
        print(json.dumps(mismatches, indent=2))
        print("{} mismatches out of {} labeled rows".format(
            len(mismatches), sum(1 for r in rows if r.get("failure_kind") is not None)))
        return

    agg = aggregate(rows)
    report = render_markdown(agg)
    print(report)
    if args.md_out:
        Path(args.md_out).write_text(report)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
