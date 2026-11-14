"""Resume deferred/rate-limited QC jobs at most once per 65 seconds.

Original source and original failed API evidence are preserved. No Together calls.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SRC = next(parent for parent in HERE.parents if (parent / "qc_eval/pipeline.py").exists())
sys.path.insert(0, str(SRC))
from qc_eval import pipeline, score as scoring
from qc_eval.config import load_env
from qc_eval.qc_client import QCClient, QCAPIError
from qc_eval.static_checks import extract_code
from run_full_evaluation import atomic_save

scoring.save_record = atomic_save
pipeline.save_record = atomic_save
TERMINAL = {"completed", "runtime_error", "compile_error", "syntax_error"}
PROGRESS = HERE / "qc_recovery_progress.json"
state = {"stage": "cooldown", "together_required": False, "minimum_submit_interval_seconds": 65}
POOL_PROJECT = int(sys.argv[sys.argv.index("--reuse-project") + 1]) if "--reuse-project" in sys.argv else None


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(message):
    print("[{}] {}".format(now(), message), flush=True)


def checkpoint(**updates):
    state.update(updates, updated_at=now())
    atomic_save(PROGRESS, state)


def wait_for(seconds, reason):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        remaining = until - time.monotonic()
        checkpoint(stage="waiting", wait_reason=reason, wait_seconds_remaining=round(remaining))
        time.sleep(max(0, min(30, remaining)))


class ThrottledQC(QCClient):
    def __init__(self):
        super().__init__()
        self.last_submit = 0

    def _post(self, path, payload=None):
        if path != "backtests/create":
            return super()._post(path, payload)
        for attempt in range(3):
            remaining = 65 - (time.monotonic() - self.last_submit)
            if remaining > 0:
                wait_for(remaining, "Space QC backtest submissions by at least 65 seconds")
            self.last_submit = time.monotonic()
            try:
                result = super()._post(path, payload)
                emit("QC accepted backtest submission")
                return result
            except QCAPIError as exc:
                if "too many backtest requests" not in json.dumps(exc.response).lower() or attempt == 2:
                    raise
                delay = 300 * (attempt + 1)
                emit("QC still rate-limited. Backing off for {} seconds before retry.".format(delay))
                wait_for(delay, "QC rejected a backtest submission due to rate limiting")


def recover(qc, code, path, name):
    old = json.loads(path.read_text()) if path.exists() else {}
    if old.get("status") in TERMINAL:
        return old
    if old:
        backup = HERE / "qc_initial_evidence" / path.relative_to(HERE / "scoring/evaluations")
        if not backup.exists():
            atomic_save(backup, old)
    emit("QC recovery: " + name)
    checkpoint(stage="executing", current=name)
    if POOL_PROJECT is not None:
        # Sequential jobs reuse an evaluation project. Every compilation,
        # backtest ID and exact source remains in its own evidence record.
        def save_progress(update):
            atomic_save(path, dict(update, shared_evaluation_project=POOL_PROJECT))
        result = pipeline.run_on_qc(qc, POOL_PROJECT, code, name, on_progress=save_progress)
        result["shared_evaluation_project"] = POOL_PROJECT
        atomic_save(path, result)
        return result
    return scoring.ensure_evaluation(code, path, name, qc, rerun=True, verbose=True)


def main():
    load_env()
    prompts = json.loads((HERE / "manifest.json").read_text())["prompts"]
    assert len(prompts) == 100 and (HERE / "generation_complete.json").exists()
    progress = json.loads((HERE / "evaluation_progress.json").read_text())
    assert progress["qc_processed"] == 100, "Wait until original QC submissions have stopped"
    if POOL_PROJECT is None:
        emit("Waiting five minutes before resuming QC at one submission per 65 seconds.")
        wait_for(300, "Initial QC rate-limit cooldown")
    else:
        emit("Reusing existing evaluation project {}; submissions remain spaced by 65 seconds.".format(POOL_PROJECT))
        checkpoint(stage="resuming", shared_evaluation_project=POOL_PROJECT)
    qc = ThrottledQC()
    if not qc.authenticate():
        raise RuntimeError("QC authentication failed")
    gold_done = set()
    refreshed, unresolved = [], []
    for index, spec in enumerate(prompts, 1):
        record_path = HERE / "generations/qwen_tuned" / (spec["id"] + ".json")
        record = json.loads(record_path.read_text())
        assert record["model_id"] == "jared-309b/Qwen-9B-finetune"
        code = extract_code(record["output"])
        assert code is not None
        if spec["template_id"] not in gold_done:
            gold_path = HERE / "scoring/evaluations/gold" / (spec["template_id"] + ".json")
            reference = (SRC / spec["reference_path"]).read_text()
            recover(qc, reference, gold_path, "gold-" + spec["template_id"])
            gold_done.add(spec["template_id"])
        path = HERE / "scoring/evaluations/together_9b_tuned" / (spec["id"] + ".json")
        old = json.loads(path.read_text()) if path.exists() else {}
        if old.get("status") not in TERMINAL:
            result = recover(qc, code, path, "together_9b_tuned-" + spec["id"])
            record["qc_evaluation"] = result
            for field in ("compile_errors", "runtime_errors", "statistics", "total_orders", "qc_note"):
                record.pop(field, None)
                if field in result:
                    record[field] = result[field]
            atomic_save(record_path, record)
            refreshed.append(spec["id"])
            if result.get("status") not in TERMINAL:
                unresolved.append({"prompt_id": spec["id"], "status": result.get("status")})
        checkpoint(stage="progress", checked=index, total=100, refreshed=len(refreshed), unresolved=unresolved)
    while not (HERE / "evaluation_complete.json").exists():
        wait_for(30, "Wait for original Claude judge tasks to finish")
    args = SimpleNamespace(output_dir=HERE / "scoring", rerun_qc=False, gold_refreshed=set(),
        verbose=False, print_output=False, time_tolerance_seconds=60, dtw_window=1, judge=False, rejudge=False)
    results = []
    for spec in prompts:
        path = HERE / "scoring/together_9b_tuned" / (spec["id"] + ".json")
        previous = json.loads(path.read_text())
        record = json.loads((HERE / "generations/qwen_tuned" / (spec["id"] + ".json")).read_text())
        result = scoring.score_one("together_9b_tuned", spec, record, args, None)
        assert result["judge_input_sha256"] == previous["judge_input_sha256"], "Judge input changed"
        result["fidelity"] = previous["fidelity"]
        atomic_save(path, result)
        results.append(result)
    atomic_save(HERE / "summary.json", scoring.summarize(results))
    atomic_save(HERE / "qc_recovery_complete.json", {"completed_at": now(), "refreshed": refreshed, "unresolved": unresolved})
    checkpoint(stage="finished", checked=100, refreshed=len(refreshed), unresolved=unresolved)
    emit("QC recovery finished\n" + json.dumps(scoring.summarize(results)["all"], indent=2))


def refresh_cached(fetch=False):
    """Recover cached terminal outcomes and optionally download missing evidence."""
    load_env()
    prompts = json.loads((HERE / "manifest.json").read_text())["prompts"]
    qc = QCClient() if fetch else None
    if qc and not qc.authenticate():
        raise RuntimeError("QC authentication failed")
    items, gold_seen = [], set()
    for spec in prompts:
        if spec["template_id"] not in gold_seen:
            items.append((HERE / "scoring/evaluations/gold" / (spec["template_id"] + ".json"),
                          (SRC / spec["reference_path"]).read_text(), None))
            gold_seen.add(spec["template_id"])
        record_path = HERE / "generations/qwen_tuned" / (spec["id"] + ".json")
        record = json.loads(record_path.read_text())
        items.append((HERE / "scoring/evaluations/together_9b_tuned" / (spec["id"] + ".json"),
                      extract_code(record["output"]), record_path))
    repaired = []
    for path, code, record_path in items:
        if not path.exists():
            continue
        result = json.loads(path.read_text())
        assert result.get("source_sha256") == scoring.digest(code)
        bt = (result.get("raw_backtest") or {}).get("backtest") or {}
        if result.get("status") == "infrastructure_error" and "NoneType" in str(result.get("error")) and (bt.get("completed") or QCClient._runtime_failed(bt)):
            backup = HERE / "qc_parser_originals" / path.relative_to(HERE / "scoring/evaluations")
            if not backup.exists():
                atomic_save(backup, result)
            previous_error = result["error"]
            failed = QCClient._runtime_failed(bt)
            result.update(status="runtime_error" if failed else "completed", stage="finished",
                error=bt.get("error"), stacktrace=bt.get("stacktrace"), runtime_errors=int(failed),
                statistics=bt.get("statistics") or {}, runtime_statistics=bt.get("runtimeStatistics") or {},
                trade_statistics=(bt.get("totalPerformance") or {}).get("tradeStatistics") or {},
                total_orders=(bt.get("statistics") or {}).get("Total Orders"),
                qc_note="runtime: " + str(bt.get("error"))[:200] if failed else "",
                parser_repair={"reason": "Recovered terminal status from the original cloud response; null statistics remain unavailable.",
                               "original_client_error": previous_error, "new_cloud_run": False})
            atomic_save(path, result)
            repaired.append(str(path.relative_to(HERE)))
        if qc and result.get("status") == "completed":
            if result.get("parser_repair"):
                response = qc._post("backtests/read", {"projectId": result["project_id"], "backtestId": result["backtest_id"]})
                latest = response["backtest"]
                assert latest.get("completed") or QCClient._runtime_failed(latest)
                failed = QCClient._runtime_failed(latest)
                result.update(raw_backtest=response, status="runtime_error" if failed else "completed",
                    error=latest.get("error"), runtime_errors=int(failed), statistics=latest.get("statistics") or {},
                    trade_statistics=(latest.get("totalPerformance") or {}).get("tradeStatistics") or {},
                    total_orders=(latest.get("statistics") or {}).get("Total Orders"))
                atomic_save(path, result)
            result = scoring.ensure_evaluation(code, path, "evidence-" + path.stem, qc)
        if record_path and result.get("status") in TERMINAL:
            record = json.loads(record_path.read_text())
            record["qc_evaluation"] = result
            for key in ("compile_errors", "runtime_errors", "statistics", "total_orders", "qc_note"):
                record.pop(key, None)
                if key in result:
                    record[key] = result[key]
            atomic_save(record_path, record)
    args = SimpleNamespace(output_dir=HERE / "scoring", rerun_qc=False, gold_refreshed=set(),
        verbose=False, print_output=False, time_tolerance_seconds=60, dtw_window=1, judge=False, rejudge=False)
    results = []
    for spec in prompts:
        path = HERE / "scoring/together_9b_tuned" / (spec["id"] + ".json")
        previous = json.loads(path.read_text())
        record = json.loads((HERE / "generations/qwen_tuned" / path.name).read_text())
        result = scoring.score_one("together_9b_tuned", spec, record, args, None)
        assert previous["judge_input_sha256"] == result["judge_input_sha256"]
        result["fidelity"] = previous["fidelity"]
        atomic_save(path, result)
        results.append(result)
    atomic_save(HERE / "summary.json", scoring.summarize(results))
    atomic_save(HERE / "qc_evidence_refresh.json", {"updated_at": now(), "fetched_missing_evidence": fetch, "parser_repairs": repaired})
    print(json.dumps({"parser_repairs": repaired, "summary": scoring.summarize(results)["all"]}, indent=2))


if __name__ == "__main__":
    if "--refresh-evidence" in sys.argv:
        refresh_cached(fetch=True)
    elif "--repair-cached" in sys.argv:
        refresh_cached(fetch=False)
    else:
        main()
