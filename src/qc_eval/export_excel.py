"""Export a published evaluation snapshot into the agreed Excel workbook.

Run from src: python -m qc_eval.export_excel --snapshot eval_results/2026-10-19
Requires Node.js and @oai/artifact-tool. Does not call model or QC APIs.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "QC_Eval_Prompt_Error_Sheet.xlsx"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_report(snapshot):
    snapshot = Path(snapshot)
    prompts = [json.loads(line) for line in (ROOT / "data/prompts_100.jsonl").read_text().splitlines() if line.strip()]
    known = {p["id"]: p for p in prompts}
    baseline = []
    for row in read(snapshot / "baseline_random10/qc_summary.json")["rows"]:
        pid = row["prompt_id"]
        if pid not in known:
            raise ValueError("Unknown prompt: " + pid)
        saved_path = snapshot / "baseline_random10/scoring" / (pid + ".json")
        saved = read(saved_path) if saved_path.exists() else {}
        fidelity = None
        if (saved.get("intervention", "none") == "none" and
                saved.get("candidate_sha256") == row.get("candidate_source_sha256")):
            fidelity = saved.get("fidelity", {}).get("score")
        baseline.append({"prompt_id": pid, "compile_errors": row.get("compile_errors"),
                         "runtime_errors": row.get("runtime_errors"), "fidelity": fidelity,
                         "note": "Original Qwen baseline. {}. {}".format(
                             row["candidate_status"], " ".join(row.get("error", "").split()))[:400]})
    feedback, behavior, details, reasons = [], [], [], []
    labels = {"equity-rsi-overbought-oversold_v04": "QQQ hourly RSI",
              "equity-monthly-roc-rotation_v06": "Monthly ROC rotation", "futures_v05": "ES continuous futures"}
    judge_rows = read(snapshot / "judge_trial3/judge_summary.json")["rows"]
    for summary in judge_rows:
        pid = summary["prompt_id"]
        result = read(snapshot / "judge_trial3/scoring/qwen_qc_feedback_trial" / (pid + ".json"))
        history = read(snapshot / "repairs" / pid / "history.json")
        latest = history["attempts"][-1]
        code = (snapshot / "repairs" / pid / ("attempt_{:02d}.py".format(latest["round"]))).read_text()
        if hashlib.sha256(code.encode()).hexdigest() != result["candidate_sha256"]:
            raise ValueError("Judgment does not match final candidate source: " + pid)
        run = latest["execution"]
        fidelity = result["fidelity"]
        analyst_review = pid == "equity-monthly-roc-rotation_v06"
        feedback.append([pid, latest["model_id"], latest["round"], run.get("compile_errors"),
                         run.get("runtime_errors"), fidelity.get("score"), run["status"],
                         "Y" if fidelity.get("needs_human_review") or analyst_review else "N"])
        b = result.get("behavior", {})
        comparable = b.get("status") == "available"
        counts = b.get("trade_count", {})
        closed = b.get("closed_trades", {})
        note = "; ".join(b.get("errors", []))
        if b.get("status") == "partial":
            note += ". Counts cover different date windows; similarity metrics are withheld."
        behavior.append([pid, counts.get("candidate", {}).get("filled_orders"),
                         counts.get("reference", {}).get("filled_orders"), closed.get("candidate"),
                         closed.get("reference"), b.get("trade_matching", {}).get("f1") if comparable else None,
                         b.get("intervals", {}).get("quantile_mae_seconds") if comparable else None,
                         b.get("equity", {}).get("dtw_distance") if comparable else None,
                         b.get("position_direction_agreement") if comparable else None,
                         b.get("status", "unavailable"), note])
        review = "Judge flagged this candidate." if fidelity.get("needs_human_review") else ""
        if analyst_review:
            review = "Analyst review: unanchored month_start() misses some trading-month starts. Judge marked schedule as met; the original 4/5 is unchanged."
        reasons.append([pid, labels.get(pid, pid), fidelity.get("reason", ""), review,
                        str(run.get("project_id", "")), run.get("backtest_id", "")])
        for dimension, assessment in fidelity.get("dimensions", {}).items():
            details.append([pid, dimension, assessment.get("requested") or "Not specified",
                            assessment.get("status"), assessment.get("evidence"),
                            "judge_trial3/scoring/qwen_qc_feedback_trial/" + pid + ".json"])
    return {"prompts": prompts, "baseline": baseline, "feedback": feedback, "behavior": behavior,
            "details": details, "reasons": reasons, "snapshot": str(snapshot),
            "judge_model": "claude-opus-5-5", "generator_model": "qwen/qwen3.8-27b"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=SHEET)
    parser.add_argument("--template", type=Path, default=SHEET)
    parser.add_argument("--node", default=os.environ.get("NODE_BINARY") or shutil.which("node"))
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.js is required. Set NODE_BINARY or pass --node.")
    payload = ROOT / "runs/excel_report.json"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(json.dumps(build_report(args.snapshot), ensure_ascii=False, indent=2))
    command = [args.node, str(Path(__file__).with_name("export_excel.mjs")),
               str(args.template.resolve()), str(payload.resolve()), str(args.output.resolve())]
    if args.preview_dir:
        command.append(str(args.preview_dir.resolve()))
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
