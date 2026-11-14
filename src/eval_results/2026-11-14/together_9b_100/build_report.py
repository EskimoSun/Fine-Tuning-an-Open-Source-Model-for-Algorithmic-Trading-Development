"""Build English report inputs from the full 100-prompt evaluation evidence."""
import hashlib
import html
import json
import csv
from collections import Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SRC = next(parent for parent in HERE.parents if (parent / "qc_eval/pipeline.py").exists())
sys.path.insert(0, str(SRC))
from qc_eval.behavior import normalize_orders


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def error_text(value):
    return html.unescape(value if isinstance(value, str) else json.dumps(value)) if value else ""


def fill_count(run):
    if run.get("status") != "completed" or "orders" not in run:
        return None
    try:
        return normalize_orders(run["orders"])["filled_orders"]
    except (KeyError, ValueError, TypeError):
        return None


manifest = read(HERE / "manifest.json")
prompts = manifest["prompts"]
assert len(prompts) == 100
rows, qc_rows, behavior_rows, reason_rows, dimension_rows, sections = [], [], [], [], [], []
for spec in prompts:
    pid = spec["id"]
    generation = read(HERE / "generations/qwen_tuned" / (pid + ".json"))
    result_path = HERE / "scoring/together_9b_tuned" / (pid + ".json")
    result = read(result_path)
    if not result:
        raise RuntimeError("Evaluation not complete: " + pid)
    assert generation.get("model_id") == manifest["model_id"]
    run = read(HERE / "scoring/evaluations/together_9b_tuned" / (pid + ".json"))
    gold = read(HERE / "scoring/evaluations/gold" / (spec["template_id"] + ".json"))
    if result.get("candidate_sha256"):
        code_path = HERE / "candidates" / (pid + ".py")
        assert hashlib.sha256(code_path.read_bytes()).hexdigest() == result["candidate_sha256"]
        english = code_path.read_text().replace("buy\u655e\u53e3", "buy exposure")
        english_dir = HERE / "candidates_english"
        english_dir.mkdir(exist_ok=True)
        (english_dir / code_path.name).write_text(english)
    fidelity = result.get("fidelity", {})
    behavior = result.get("behavior", {})
    row = {"prompt_id": pid, "model_id": generation["model_id"], "template_id": spec["template_id"],
           "compile_errors": run.get("compile_errors"), "runtime_errors": run.get("runtime_errors"),
           "qc_status": run.get("status", "no_code" if result.get("status") == "no_code" else "not_run"),
           "judge_status": fidelity.get("status", "not_judged"), "fidelity": fidelity.get("score"),
           "reason": fidelity.get("reason") or fidelity.get("error") or "No valid judgment",
           "project_id": run.get("project_id"), "backtest_id": run.get("backtest_id"),
           "source_sha256": result.get("candidate_sha256"), "error": error_text(run.get("error")),
           "behavior_status": behavior.get("status", "unavailable"),
           "needs_human_review": fidelity.get("needs_human_review", False),
           "gold_status": gold.get("status", "not_run")}
    rows.append(row)
    qc_rows.append([pid, generation["model_id"], 0, row["compile_errors"], row["runtime_errors"],
                    row["fidelity"], row["qc_status"], "Y" if row["needs_human_review"] else "N"])
    trade_count = behavior.get("trade_count", {})
    behavior_rows.append([pid,
        trade_count.get("candidate", {}).get("filled_orders", fill_count(run)),
        trade_count.get("reference", {}).get("filled_orders", fill_count(gold)),
        behavior.get("closed_trades", {}).get("candidate", run.get("trade_statistics", {}).get("totalNumberOfTrades") if run.get("status") == "completed" else None),
        behavior.get("closed_trades", {}).get("reference", gold.get("trade_statistics", {}).get("totalNumberOfTrades") if gold.get("status") == "completed" else None),
        behavior.get("trade_matching", {}).get("f1"),
        behavior.get("intervals", {}).get("quantile_mae_seconds"),
        behavior.get("equity", {}).get("dtw_distance"), behavior.get("position_direction_agreement"),
        row["behavior_status"], "; ".join(behavior.get("errors", [])) or behavior.get("interpretation", "")])
    reason_rows.append([pid, row["reason"], "Judge flagged review." if row["needs_human_review"] else "",
                        str(row["project_id"] or ""), row["backtest_id"] or ""])
    for name, dimension in fidelity.get("dimensions", {}).items():
        dimension_rows.append([pid, name, dimension.get("requested") or "Not specified", dimension["status"],
                               dimension["evidence"], str(result_path.relative_to(HERE))])
    sections.extend(["## " + pid, "", "Prompt: " + spec["prompt"], "",
        "QC: {}. Claude fidelity: {}. Judge: {}. Behavior: {}.".format(row["qc_status"], row["fidelity"], row["judge_status"], row["behavior_status"]),
        "", row["reason"], "", "[English code view](candidates_english/{}.py) | [Original evaluated source](candidates/{}.py) | [Judgment](scoring/together_9b_tuned/{}.json)".format(pid, pid, pid), ""])
    if row["error"]:
        sections.extend(["QC error:", "", "```text", row["error"], "```", ""])

scores = [row["fidelity"] for row in rows if row["fidelity"] is not None]
summary = {"model_id": manifest["model_id"], "system_prompt": "v1", "automatic_repairs": False,
           "selected_prompts": len(rows), "completed_backtests": sum(r["qc_status"] == "completed" for r in rows),
           "judged_candidates": sum(r["judge_status"] == "judged" for r in rows),
           "mean_fidelity": sum(scores) / len(scores) if scores else None,
           "fidelity_distribution": dict(Counter(scores)),
           "qc_statuses": dict(Counter(r["qc_status"] for r in rows)),
           "judge_statuses": dict(Counter(r["judge_status"] for r in rows)),
           "behavior_statuses": dict(Counter(r["behavior_status"] for r in rows)), "rows": rows}
(HERE / "results_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n")
with (HERE / "results.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
payload = {"manifest": manifest, "prompts": prompts, "rows": rows, "qc_rows": qc_rows,
           "behavior_rows": behavior_rows, "reason_rows": reason_rows, "dimension_rows": dimension_rows}
(HERE / "workbook_data.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
lines = ["# Together 9B: full 100-prompt evaluation", "", "Model: `{}`. System prompt: `v1`. Temperature: 0. Maximum output tokens: 4096.".format(manifest["model_id"]), "",
         "All 100 held-out prompts across 10 strategy templates. The 870 training prompts are excluded. Three previously evaluated 9B outputs are reused. Original generations are preserved, with no repairs or mock outputs.", "",
         "All original generations were saved before QC and judge processing. Together inference is no longer required for this run.", "",
         "Candidate execution and 1-5 prompt adherence are separate results. Missing behavior metrics remain blank. Template similarity is diagnostic and does not penalize unspecified prompt choices.", "",
         "Gold evidence is reused only when its exact source hash matches. Some Gold runs are historical and use an older QC engine. Candidate run engine versions and exact evidence remain in the JSON files.", "",
         "Original provider outputs can contain language-instruction violations. They are retained unchanged as evaluation evidence. The report and derived summaries are in English.", "",
         "English code views translate one non-English comment fragment from the reused third smoke-test output. These display copies are separate from the exact original code used by QC and Claude. No trading logic is changed.", "",
         "| Metric | Value |", "|---|---:|", "| Requested prompts | 100 |",
         "| Completed candidate backtests | {} |".format(summary["completed_backtests"]),
         "| Valid Claude judgments | {} |".format(summary["judged_candidates"]),
         "| Mean fidelity | {} |".format(summary["mean_fidelity"]), "",
         "[Full terminal log](evaluation.log) | [Machine-readable summary](results_summary.json)", ""]
(HERE / "README.md").write_text("\n".join(lines + sections) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
