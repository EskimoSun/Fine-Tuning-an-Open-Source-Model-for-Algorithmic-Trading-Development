"""Score existing generations against prompts and their human-written templates.

Offline by default. --qc explicitly enables cloud compile/backtest/evidence
requests; --judge enables paid model judging. Never generates new Qwen code.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .behavior import compare_behavior
from .fidelity import judge_fidelity, judge_request
from .pipeline import ROOT, RUNS, load_prompts, run_on_qc, save_record
from .static_checks import extract_code, run_static_checks

SCORING_VERSION = 1
OUTPUT = RUNS / "scoring"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_evaluation(code, path, name, qc=None, seed=None, rerun=False):
    """Reuse only evidence bound to this exact source; failed runs need explicit retry."""
    source_hash = digest(code)
    cached = json.loads(path.read_text()) if path.exists() else {}
    result = next((r for r in (cached, seed or {})
                   if r.get("source_sha256") == source_hash), None)
    if result is None or rerun:
        if qc is None:
            return {"status": "not_run", "source_sha256": source_hash}
        result = run_on_qc(qc, None, code, name,
                           on_progress=lambda r: save_record(path, r))
    if result.get("status") == "completed" and qc is not None:
        for field, method in (("orders", qc.read_orders), ("equity_chart", qc.read_equity_chart)):
            if field not in result:
                try:
                    result[field] = method(result["project_id"], result["backtest_id"])
                    result.pop(field + "_fetch_error", None)
                except Exception as exc:
                    result[field + "_fetch_error"] = str(exc)
                save_record(path, result)
        result["evidence_note"] = "Equity chart requests up to 10000 observations; daily diagnostics are not intraday rule proofs."
    save_record(path, result)
    return result


def _reference_path(spec):
    path = (ROOT / spec["reference_path"]).resolve()
    templates = (ROOT / "data/templates").resolve()
    if templates not in path.parents:
        raise ValueError("Reference path is outside data/templates")
    return path


def score_one(model, spec, record, args, qc):
    output_path = args.output_dir / model / (spec["id"] + ".json")
    previous = json.loads(output_path.read_text()) if output_path.exists() else {}
    result = {"scoring_version": SCORING_VERSION, "prompt_id": spec["id"],
              "model": model, "model_id": record.get("model_id"),
              "template_id": spec["template_id"], "prompt": spec["prompt"],
              "specificity": spec.get("specificity"), "segment": spec.get("segment"),
              "scored_at": datetime.now(timezone.utc).isoformat(),
              "prompt_sha256": digest(spec["prompt"])}
    if record.get("model_id") == "mock":
        result.update(status="mock_generation", fidelity={"score": None},
                      note="Run the generation pipeline with --regenerate and real model credentials first.")
        save_record(output_path, result)
        return result
    code = extract_code(record["output"])
    if code is None:
        result.update(status="no_code", fidelity={"score": 1, "status": "no_code",
                      "reason": "No algorithm was returned for this trading prompt.",
                      "needs_human_review": True})
        save_record(output_path, result)
        return result
    reference = _reference_path(spec).read_text(encoding="utf-8")
    result.update(candidate_sha256=digest(code), reference_sha256=digest(reference),
                  reference_path=spec["reference_path"],
                  static_findings=[f.to_dict() for f in run_static_checks(code, spec)])
    gold_path = args.output_dir / "evaluations/gold" / (spec["template_id"] + ".json")
    candidate_path = args.output_dir / "evaluations" / model / (spec["id"] + ".json")
    # Gold is cached once per template/source hash, not once per prompt variant.
    gold = ensure_evaluation(reference, gold_path, "gold-" + spec["template_id"], qc,
                             rerun=args.rerun_qc and spec["template_id"] not in args.gold_refreshed)
    args.gold_refreshed.add(spec["template_id"])
    candidate = ensure_evaluation(code, candidate_path, model + "-" + spec["id"], qc,
                                  seed=record.get("qc_evaluation"), rerun=args.rerun_qc)
    result["execution"] = {"reference": {k: gold.get(k) for k in ("status", "project_id", "backtest_id", "qc_note")},
                           "candidate": {k: candidate.get(k) for k in ("status", "project_id", "backtest_id", "qc_note")}}
    result["behavior"] = compare_behavior(gold, candidate, args.time_tolerance_seconds, args.dtw_window)
    result["behavior"]["interpretation"] = (
        "Template similarity is diagnostic only; unspecified prompt choices must not lower fidelity."
        if spec.get("specificity") == "vague" else
        "Check explicit prompt requirements and prompt/template conflicts before interpreting template similarity.")
    request = judge_request(spec, code, reference)
    judge_model = os.environ.get("FABLE_MODEL") or previous.get("judge_model")
    judge_hash = digest(request + "\njudge_model=" + str(judge_model))
    result["judge_input_sha256"] = judge_hash
    result["judge_model"] = judge_model
    result["judge_request"] = request
    if (not args.rejudge and previous.get("judge_input_sha256") == judge_hash
            and previous.get("fidelity", {}).get("status") == "judged"):
        result["fidelity"] = previous["fidelity"]
    elif args.judge:
        try:
            result["fidelity"] = judge_fidelity(request)
        except Exception as exc:
            result["fidelity"] = {"status": "judge_error", "score": None,
                                  "error": str(exc), "needs_human_review": True}
    else:
        result["fidelity"] = {"status": "not_judged", "score": None,
                              "reason": "Pass --judge to score the code with the 1-5 rubric."}
    result["status"] = "scored"
    save_record(output_path, result)
    return result


def summarize(results):
    """Denominators include missing/failed rows; no missing score becomes zero."""
    def group(rows):
        scores = [r["fidelity"]["score"] for r in rows if r.get("fidelity", {}).get("score") is not None]
        return {"requested_rows": len(rows), "rows_with_fidelity": len(scores),
                "fidelity_mean": sum(scores) / len(scores) if scores else None,
                "fidelity_distribution": dict(Counter(scores)),
                "statuses": dict(Counter(r["status"] for r in rows)),
                "judge_statuses": dict(Counter(r.get("fidelity", {}).get("status", "not_judged") for r in rows)),
                "behavior_available": sum(r.get("behavior", {}).get("status") == "available" for r in rows),
                "human_review_rows": [r["prompt_id"] for r in rows if r.get("fidelity", {}).get("needs_human_review")]}
    summary = {"all": group(results), "by_model": {}, "by_specificity": {}}
    for field, key in (("model", "by_model"), ("specificity", "by_specificity")):
        for value in sorted({r.get(field, "unknown") or "unknown" for r in results}):
            summary[key][value] = group([r for r in results if (r.get(field) or "unknown") == value])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="qwen_base", help="comma-separated saved generation model labels")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prompt-id", action="append", help="score only this prompt ID (repeatable)")
    parser.add_argument("--generations", type=Path, help="optional JSONL with prompt_id, model, output, and optional qc_evaluation")
    parser.add_argument("--qc", action="store_true", help="enable real cloud runs and evidence collection")
    parser.add_argument("--judge", action="store_true", help="enable paid prompt-fidelity judging")
    parser.add_argument("--rerun-qc", action="store_true", help="with --qc, replace cached cloud evaluations")
    parser.add_argument("--rejudge", action="store_true", help="with --judge, replace cached fidelity judgments")
    parser.add_argument("--time-tolerance-seconds", type=float, default=60)
    parser.add_argument("--dtw-window", type=int, default=1, help="maximum DTW shift in daily observations; 0 disables warping")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.time_tolerance_seconds < 0 or args.dtw_window < 0 or (args.limit is not None and args.limit <= 0):
        parser.error("Use nonnegative tolerances and a positive --limit")
    if args.rerun_qc and not args.qc:
        parser.error("--rerun-qc requires --qc")
    if args.rejudge and not args.judge:
        parser.error("--rejudge requires --judge")
    if args.judge and not all(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "FABLE_MODEL")):
        parser.error("--judge requires ANTHROPIC_API_KEY and an explicitly configured valid FABLE_MODEL")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models or any(Path(m).name != m or m in (".", "..", "evaluations") for m in models):
        parser.error("Model labels must be simple directory names")
    prompts = load_prompts()
    if args.prompt_id:
        unknown = set(args.prompt_id) - {p["id"] for p in prompts}
        if unknown:
            parser.error("Unknown prompt IDs: " + ", ".join(sorted(unknown)))
        prompts = [p for p in prompts if p["id"] in args.prompt_id]
    if args.limit:
        prompts = prompts[:args.limit]
    supplied = {}
    if args.generations:
        for line in args.generations.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                key = (record["model"], record["prompt_id"])
                if key in supplied:
                    parser.error("Duplicate generation: " + str(key))
                supplied[key] = record
    qc = None
    if args.qc:
        from .qc_client import QCClient
        qc = QCClient()
        if not qc.authenticate():
            parser.error("QuantConnect authentication failed")
    args.gold_refreshed = set()
    results = []
    for model in models:
        for spec in prompts:
            try:
                path = RUNS / model / (spec["id"] + ".json")
                if args.generations:
                    record = supplied.get((model, spec["id"]))
                else:
                    record = json.loads(path.read_text()) if path.exists() else None
                if record is None:
                    result = {"prompt_id": spec["id"], "model": model, "specificity": spec.get("specificity"),
                              "status": "missing_generation", "fidelity": {"score": None}}
                    save_record(args.output_dir / model / (spec["id"] + ".json"), result)
                else:
                    result = score_one(model, spec, record, args, qc)
            except Exception as exc:
                result = {"prompt_id": spec["id"], "model": model, "specificity": spec.get("specificity"),
                          "status": "scoring_error", "error": str(exc), "fidelity": {"score": None}}
                save_record(args.output_dir / model / (spec["id"] + ".json"), result)
            results.append(result)
            print("[{}] {}: {} fidelity={} behavior={}".format(model, spec["id"], result["status"],
                  result.get("fidelity", {}).get("score"), result.get("behavior", {}).get("status")))
    summary = summarize(results)
    save_record(args.output_dir / "summary.json", summary)
    print("Reports: " + str(args.output_dir.resolve()))
    print(json.dumps(summary["all"], indent=2))


if __name__ == "__main__":
    main()
