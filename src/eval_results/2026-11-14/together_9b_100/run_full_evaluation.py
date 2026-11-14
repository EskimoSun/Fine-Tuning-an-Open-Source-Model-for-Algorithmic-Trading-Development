"""Evaluate 100 original Together outputs; finish generation before cloud scoring."""
import argparse
import hashlib
import json
import os
import shutil
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SRC = next(parent for parent in Path(__file__).resolve().parents
           if (parent / "qc_eval/pipeline.py").exists())
sys.path.insert(0, str(SRC))
from qc_eval import pipeline
from qc_eval import score as score_module
from qc_eval.config import load_env
from qc_eval.qc_client import QCClient, QCAPIError
from qc_eval.score import ensure_evaluation, format_progress, score_one, summarize
from qc_eval.static_checks import extract_code

HERE = Path(__file__).resolve().parent
SMOKE = HERE.parent / "together_9b_smoke_20261114"
MODEL = "jared-309b/Qwen-9B-finetune"
LABEL = "together_9b_tuned"
GEN = HERE / "generations/qwen_tuned"
SCORING = HERE / "scoring"
PATH_LOCKS = {}
LOCKS_GUARD = threading.Lock()


def atomic_save(path, record):
    """Concurrent readers see complete JSON; writers never share a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temporary.replace(path)


pipeline.save_record = atomic_save
score_module.save_record = atomic_save
original_ensure_evaluation = ensure_evaluation


def locked_evaluation(code, path, *args, **kwargs):
    """Gold templates are shared across prompt variants and need a path lock."""
    with LOCKS_GUARD:
        lock = PATH_LOCKS.setdefault(str(path), threading.RLock())
    with lock:
        return original_ensure_evaluation(code, path, *args, **kwargs)


score_module.ensure_evaluation = locked_evaluation


class PacedQC(QCClient):
    """One shared submission gate across workers, with rate-limit backoff."""
    def __init__(self):
        super().__init__()
        self.submit_gate = threading.Lock()
        self.last_submit = 0
        self.worker_project = threading.local()

    def create_project(self, name):
        # Each QC worker runs sequentially and reuses only its own evaluation
        # project. Full runs therefore create at most three cloud projects.
        project_id = getattr(self.worker_project, "project_id", None)
        if project_id is None:
            project_id = super().create_project(name)
            self.worker_project.project_id = project_id
        return project_id

    def _post(self, path, payload=None):
        if path != "backtests/create":
            return super()._post(path, payload)
        with self.submit_gate:
            for attempt in range(3):
                deadline = self.last_submit + 65
                while time.monotonic() < deadline:
                    time.sleep(max(0, min(30, deadline - time.monotonic())))
                self.last_submit = time.monotonic()
                try:
                    return super()._post(path, payload)
                except QCAPIError as exc:
                    if "too many backtest requests" not in json.dumps(exc.response).lower() or attempt == 2:
                        raise
                    wait_until = time.monotonic() + 300 * (attempt + 1)
                    emit("QC rate limit: waiting before another submission")
                    while time.monotonic() < wait_until:
                        time.sleep(max(0, min(30, wait_until - time.monotonic())))


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(message):
    print("[{}] {}".format(now(), message), flush=True)


def initialize(prompts):
    for spec in prompts:
        name = spec["id"] + ".json"
        for source, destination in (
            (SMOKE / "generations/qwen_tuned" / name, GEN / name),
            (SMOKE / "scoring" / LABEL / name, SCORING / LABEL / name),
            (SMOKE / "scoring/evaluations" / LABEL / name, SCORING / "evaluations" / LABEL / name),
        ):
            if source.exists() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    for folder in (SMOKE / "scoring/evaluations/gold", SRC / "runs/scoring/evaluations/gold"):
        for source in folder.glob("*.json"):
            cached = json.loads(source.read_text())
            destination = SCORING / "evaluations/gold" / source.name
            if cached.get("status") == "completed" and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    manifest = HERE / "manifest.json"
    identity = {"model_id": MODEL, "model_label": LABEL, "system_prompt": "v1",
                "intervention": "none", "automatic_repairs": False, "prompts": prompts}
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        assert all(previous[k] == v for k, v in identity.items()), "Experiment identity changed"
    else:
        pipeline.save_record(manifest, dict(identity, started_at=now(),
            generation_workers=4, seed_experiment=str(SMOKE.relative_to(SRC)),
            generation_max_tokens=4096, temperature=0))


def generate_one(spec):
    path = GEN / (spec["id"] + ".json")
    existing = json.loads(path.read_text()) if path.exists() else {}
    if "output" in existing:
        assert existing.get("model_id") == MODEL, "Unexpected cached model"
        return spec["id"], 0, True
    args = SimpleNamespace(system="v1", mock=False, regenerate=False,
        rerun_qc=False, rejudge=False, skip_judge=True, verbose=False, print_output=True)
    started = time.monotonic()
    record = pipeline.process("qwen_tuned", spec, args, None)
    assert record.get("model_id") == MODEL and "output" in record
    elapsed = time.monotonic() - started
    record["generation_elapsed_seconds"] = elapsed
    pipeline.save_record(path, record)
    code = extract_code(record["output"])
    if code is not None:
        (HERE / "candidates").mkdir(exist_ok=True)
        (HERE / "candidates" / (spec["id"] + ".py")).write_text(code)
    return spec["id"], elapsed, False


def generate_all(prompts):
    started = time.monotonic()
    errors, durations = {}, []
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = {executor.submit(generate_one, spec): spec for spec in prompts}
        for number, job in enumerate(as_completed(jobs), 1):
            spec = jobs[job]
            try:
                pid, elapsed, cached = job.result()
                if not cached:
                    durations.append(elapsed)
                emit("GENERATION {}/100 {} cached={} elapsed={:.1f}s".format(number, pid, cached, elapsed))
            except Exception as exc:
                errors[spec["id"]] = str(exc)
                emit("GENERATION ERROR {}: {}".format(spec["id"], exc))
            pipeline.save_record(HERE / "generation_progress.json", {
                "updated_at": now(), "processed": number, "total": len(prompts),
                "elapsed_seconds": time.monotonic() - started,
                "median_new_request_seconds": statistics.median(durations) if durations else None,
                "errors": errors, "together_required": True})
    missing = []
    for spec in prompts:
        path = GEN / (spec["id"] + ".json")
        if not path.exists():
            missing.append(spec["id"])
            continue
        record = json.loads(path.read_text())
        if record.get("model_id") != MODEL or "output" not in record:
            missing.append(spec["id"])
        code = extract_code(record.get("output", ""))
        if code is not None:
            (HERE / "candidates").mkdir(exist_ok=True)
            (HERE / "candidates" / (spec["id"] + ".py")).write_text(code)
    if missing:
        raise RuntimeError("Generation incomplete; keep Together available. Missing IDs: " + ", ".join(missing))
    pipeline.save_record(HERE / "generation_complete.json", {
        "completed_at": now(), "total": len(prompts), "model_id": MODEL,
        "original_generations_saved": len(prompts), "together_required": False,
        "elapsed_seconds": time.monotonic() - started,
        "median_new_request_seconds": statistics.median(durations) if durations else None})
    emit("ALL 100 ORIGINAL GENERATIONS SAVED. Together endpoint is no longer needed for QC or judge.")


def score_args():
    return SimpleNamespace(output_dir=SCORING, rerun_qc=False, gold_refreshed=set(),
        verbose=True, print_output=False, time_tolerance_seconds=60,
        dtw_window=1, judge=True, rejudge=False)


def judge_one(spec, record):
    result = score_one(LABEL, spec, record, score_args(), None)
    emit(format_progress(result))
    return result


def score_all(prompts):
    qc = PacedQC()
    if not qc.authenticate():
        raise RuntimeError("QC authentication failed; generation files remain safely cached")
    emit("QC authenticated. Three QC workers share a 65-second submission gate; two independent judge workers.")
    started = time.monotonic()
    jobs, prepared = [], []
    def prepare(spec):
            worker_qc = qc
            record = json.loads((GEN / (spec["id"] + ".json")).read_text())
            assert record.get("model_id") == MODEL
            emit("QC START " + spec["id"])
            code = extract_code(record["output"])
            if code is not None:
                reference = (SRC / spec["reference_path"]).read_text()
                locked_evaluation(reference, SCORING / "evaluations/gold" / (spec["template_id"] + ".json"),
                    "gold-" + spec["template_id"], worker_qc, verbose=True)
                candidate = locked_evaluation(code, SCORING / "evaluations" / LABEL / (spec["id"] + ".json"),
                    LABEL + "-" + spec["id"], worker_qc, seed=record.get("qc_evaluation"), verbose=True)
                record["qc_evaluation"] = candidate
                for field in ("compile_errors", "runtime_errors", "statistics", "total_orders", "qc_note"):
                    if field in candidate:
                        record[field] = candidate[field]
                pipeline.save_record(GEN / (spec["id"] + ".json"), record)
            return spec, record
    with ThreadPoolExecutor(max_workers=3) as qc_executor, ThreadPoolExecutor(max_workers=2) as judge_executor:
        qc_jobs = [qc_executor.submit(prepare, spec) for spec in prompts]
        for job in as_completed(qc_jobs):
            spec, record = job.result()
            prepared.append(spec["id"])
            emit("QC PREPARED {}/100 {}".format(len(prepared), spec["id"]))
            jobs.append(judge_executor.submit(judge_one, spec, record))
            completed = [job.result() for job in jobs if job.done()]
            pipeline.save_record(HERE / "summary.json", summarize(completed))
            pipeline.save_record(HERE / "evaluation_progress.json", {
                "updated_at": now(), "qc_processed": len(prepared), "judge_finished": len(completed),
                "total": len(prompts), "elapsed_seconds": time.monotonic() - started,
                "together_required": False, "qc_workers": 3, "judge_workers": 2})
        results = [job.result() for job in jobs]
    pipeline.save_record(HERE / "summary.json", summarize(results))
    pipeline.save_record(HERE / "evaluation_complete.json", {
        "completed_at": now(), "total": len(results), "elapsed_seconds": time.monotonic() - started})
    emit("FULL EVALUATION FINISHED\n" + json.dumps(summarize(results)["all"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "generate", "score"), default="all")
    args = parser.parse_args()
    load_env()
    assert os.environ.get("QWEN_TUNED_MODEL") == MODEL, "Wrong deployed model"
    assert os.environ.get("QWEN_BASE_URL", "").rstrip("/") == "https://api-inference.together.ai/v1", "Wrong generation endpoint"
    prompts = pipeline.load_prompts()
    assert len(prompts) == 100 and len({p["id"] for p in prompts}) == 100
    initialize(prompts)
    pipeline.RUNS = HERE / "generations"
    if args.stage in ("all", "generate"):
        generate_all(prompts)
    if args.stage in ("all", "score"):
        if not (HERE / "generation_complete.json").exists():
            raise RuntimeError("Finish all original generations before scoring")
        score_all(prompts)


if __name__ == "__main__":
    main()
