"""
End-to-end eval pipeline: generate -> compile/backtest on QC -> judge -> spreadsheet.

    python -m qc_eval.pipeline --models fable,qwen_base          # baseline
    python -m qc_eval.pipeline --models qwen_tuned               # after fine-tuning
    python -m qc_eval.pipeline --models fable --limit 5          # quick test
    python -m qc_eval.pipeline --mock --limit 10 --no-qc         # offline plumbing test

Environment variables:
    ANTHROPIC_API_KEY            Fable (reference + judge)
    FABLE_MODEL                  default claude-fable-5-1
    QWEN_BASE_URL                OpenAI-compatible endpoint, e.g. https://api.together.xyz/v1
    QWEN_API_KEY
    QWEN_BASE_MODEL              e.g. Qwen/Qwen3-4B-Instruct-2507 (the untuned model)
    QWEN_TUNED_MODEL             the fine-tuned model id on the same endpoint
    QC_USER_ID, QC_API_TOKEN     QuantConnect (QC_ORG_ID optional)

Every generation and score is cached under runs/<model>/<prompt_id>.json.
Reruns reuse the cache unless you pass --regenerate, so the sheet always
reflects outputs you can point to on disk.
"""

import argparse
import ast
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import sheet
from .config import load_env
from .rubric import FIDELITY_RUBRIC
from .reporting import QCProgressPrinter, print_model_output
from .static_checks import extract_code, run_static_checks

ROOT = Path(__file__).resolve().parent.parent

PROMPTS = ROOT / "data" / "prompts_100.jsonl"
RUNS = ROOT / "runs"
SHEET = ROOT / "QC_Eval_Prompt_Error_Sheet.xlsx"

SYSTEM = (
    "You write QuantConnect LEAN algorithms in Python using the current snake_case API. "
    "Return one complete main.py in a single ```python code block. "
    "If the request cannot be done with QuantConnect data, say so instead of inventing an API."
)

JUDGE = """You are grading whether a QuantConnect algorithm implements a user's request.

Request:
<prompt>
{prompt}
</prompt>

Code:
<code>
{code}
</code>

""" + FIDELITY_RUBRIC + """

Reply with JSON only: {{"score": <1-5>, "reason": "<one sentence>"}}"""


# ---------------------------------------------------------------- models
def call_fable(prompt, system=SYSTEM, max_tokens=4096):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": os.environ.get("FABLE_MODEL", "claude-fable-5-1"),
              "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=300)
    r.raise_for_status()
    response = r.json()
    if response.get("stop_reason") == "max_tokens":
        raise RuntimeError("Anthropic response reached max_tokens (thinking and text share this budget); no complete judgment was returned")
    return "".join(b.get("text", "") for b in response["content"] if b.get("type") == "text")


def call_openai_compatible(prompt, model, max_tokens=4096, system=SYSTEM):
    for attempt in range(3):
        r = requests.post(
            f"{os.environ['QWEN_BASE_URL'].rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['QWEN_API_KEY']}"},
            json={"model": model, "max_tokens": max_tokens, "temperature": 0,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]},
            timeout=300)
        if r.status_code not in (429, 503) or attempt == 2:
            break
        try:
            delay = max(1, float(r.headers.get("Retry-After", 2 ** (attempt + 1))))
        except ValueError:
            delay = 2 ** (attempt + 1)
        if delay > 30:
            # A daily quota or long wait needs a later resumed command, not
            # unlimited retries. No successful generation is ever resampled.
            break
        print("[{}] HTTP {}; retrying the failed request in {}s ({}/2)".format(
            model, r.status_code, delay, attempt + 1), flush=True)
        time.sleep(delay)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def mock_generate(prompt):
    """Offline stand-in that returns a fixed SPY SMA algorithm."""
    return ('```python\nfrom AlgorithmImports import *\n\nclass Mock(QCAlgorithm):\n'
            '    def initialize(self):\n        self.set_start_date(2020, 1, 1)\n'
            '        self.set_cash(100000)\n        self.spy = self.add_equity("SPY").symbol\n'
            '        self.fast = self.sma(self.spy, 50)\n        self.slow = self.sma(self.spy, 200)\n'
            '        self.set_warm_up(200)\n\n    def on_data(self, data):\n'
            '        if self.is_warming_up:\n            return\n'
            '        if self.fast.current.value > self.slow.current.value:\n'
            '            self.set_holdings(self.spy, 1)\n        else:\n            self.liquidate()\n```')


def generate(model, prompt, mock=False, system=SYSTEM):
    if mock:
        return mock_generate(prompt), "mock"
    if model == "fable":
        return call_fable(prompt, system=system), os.environ.get("FABLE_MODEL", "claude-fable-5-1")
    mid = os.environ["QWEN_BASE_MODEL" if model == "qwen_base" else "QWEN_TUNED_MODEL"]
    return call_openai_compatible(prompt, mid, system=system), mid


def judge(prompt, code, mock=False):
    if mock:
        return None, "mock: not judged"
    text = call_fable(JUDGE.format(prompt=prompt, code=code), system="You are a strict code reviewer.", max_tokens=300)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        obj = json.loads(m.group(0))
        score = int(obj["score"])
        return (score if 1 <= score <= 5 else None), obj.get("reason", "")
    except Exception:
        return None, f"unparsed judge reply: {text[:120]}"


# ---------------------------------------------------------------- QC
def count_compile_errors(logs):
    lines = [str(x) for x in logs]
    n = sum(1 for l in lines if re.search(r"\berror\b", l, re.IGNORECASE))
    return max(n, 1)  # a failed build has at least one error


def run_on_qc(qc, project_id, code, name, on_progress=None):
    """Keep full QC evidence while exposing concise spreadsheet counters.

    Runtime errors count failed executions (0/1), not individual log lines.
    Compilation counts are diagnostic-line estimates, with at least one for
    a failed build. Unknown outcomes (timeouts/infrastructure) remain None.
    """
    result = {"status": "running", "stage": "syntax",
              "source": code, "source_sha256": hashlib.sha256(code.encode()).hexdigest(),
              "started_at": datetime.now(timezone.utc).isoformat(),
              "compile_errors": None, "runtime_errors": None,
              "statistics": {}, "runtime_statistics": {}, "logs": [], "qc_note": ""}

    def progress(update):
        result.update(update)
        if on_progress:
            on_progress(result)

    try:
        progress({})
        try:
            ast.parse(code, filename="main.py")
        except SyntaxError as exc:
            progress({"status": "syntax_error", "error": str(exc),
                      "line": exc.lineno, "offset": exc.offset, "compile_errors": 1,
                      "qc_note": f"syntax: {str(exc)[:200]}"})
            return result

        if project_id is None:
            progress({"stage": "create_project"})
            project_id = qc.create_project(f"llm-eval-{name}-{time.time_ns()}")
        progress({"project_id": project_id, "stage": "upload"})
        qc.update_main(project_id, code)
        progress({"stage": "compile"})
        ok, compile_id, logs = qc.compile(project_id, on_progress=progress)
        progress({"compile_id": compile_id, "compile_logs": logs})
        if not ok:
            first = next((str(l) for l in logs if "error" in str(l).lower()), str(logs[:1]))
            progress({"status": "compile_error", "error": logs,
                      "compile_errors": count_compile_errors(logs),
                      "qc_note": f"compile: {first[:200]}"})
            return result

        progress({"compile_errors": 0, "stage": "backtest"})
        bt = qc.backtest(project_id, compile_id, name, on_progress=progress)
        progress({key: value for key, value in bt.items() if key != "raw"})
        failed = bt["status"] == "runtime_error"
        runtime_detail = bt.get("error") or bt.get("stacktrace") or "runtime or initialization failed"
        progress({"runtime_errors": int(failed),
                  "qc_note": f"runtime: {str(runtime_detail)[:200]}" if failed else "",
                  "stage": "logs"})
        try:
            qc.read_logs(project_id, result["backtest_id"], on_progress=progress)
        except Exception as exc:
            # Log availability must not erase the actual execution outcome.
            progress({"log_fetch_error": str(exc)})
        progress({"stage": "finished"})
    except TimeoutError as exc:
        progress({"status": "timeout", "error": str(exc), "qc_note": str(exc)})
    except KeyboardInterrupt:
        progress({"status": "interrupted", "error": "Stopped locally; cloud job may still run",
                  "qc_note": "QC evaluation interrupted"})
        raise
    except Exception as exc:
        update = {"status": "infrastructure_error", "error": str(exc),
                  "error_type": type(exc).__name__, "qc_note": f"infrastructure: {str(exc)[:200]}"}
        if hasattr(exc, "endpoint") and hasattr(exc, "response"):
            update["api_error"] = {"endpoint": exc.endpoint, "response": exc.response}
        progress(update)
    finally:
        progress({"finished_at": datetime.now(timezone.utc).isoformat()})
    return result


def save_record(path, rec):
    """Atomic checkpoints keep a stopped run inspectable and valid JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    temporary.replace(path)


# ---------------------------------------------------------------- main loop
def load_prompts():
    with open(PROMPTS) as f:
        return [json.loads(l) for l in f if l.strip()]


def process(model, p, args, qc):
    path = RUNS / model / f"{p['id']}.json"
    rec = json.loads(path.read_text()) if path.exists() else {}

    replace_mock = not args.mock and rec.get("model_id") == "mock"
    needs_generation = "output" not in rec or args.regenerate or replace_mock
    if needs_generation:
        print("[{}] {}: requesting {} model output".format(
            model, p["id"], "mock" if args.mock else "REAL"), flush=True)
        out, model_id = generate(model, p["prompt"], mock=args.mock)
        rec = {"prompt_id": p["id"], "model": model, "model_id": model_id, "output": out,
               "generated_at": datetime.now(timezone.utc).isoformat()}
    if getattr(args, "print_output", False):
        print_model_output(model, p["id"], rec.get("model_id"), rec["output"],
                           "fresh_generation" if needs_generation else "saved_generation")

    code = extract_code(rec["output"])
    rec["has_code"] = code is not None
    findings = run_static_checks(code, p) if code else []
    rec["static_findings"] = [f.to_dict() for f in findings]

    if code is None:
        rec.update(compile_errors=None, runtime_errors=None, fidelity=1,
                   judge_reason="no code returned", qc_note="no code")
    else:
        if qc is not None and ("compile_errors" not in rec or args.regenerate or args.rerun_qc):
            # Replace the QC subrecord on rerun so old errors/stats cannot leak.
            for key in ("compile_errors", "runtime_errors", "total_orders", "statistics", "qc_note"):
                rec.pop(key, None)

            reporter = QCProgressPrinter(model + "/" + p["id"]) if getattr(args, "verbose", False) else None

            def checkpoint(qc_result):
                rec["qc_evaluation"] = dict(qc_result)
                for key in ("compile_errors", "runtime_errors", "total_orders", "statistics", "qc_note"):
                    if key in qc_result:
                        rec[key] = qc_result[key]
                rec["note"] = rec.get("qc_note", "")
                save_record(path, rec)
                if reporter:
                    reporter(qc_result)

            run_on_qc(qc, None, code, p["id"], on_progress=checkpoint)
        if not args.skip_judge and ("fidelity" not in rec or "judge_error" in rec or args.regenerate or args.rejudge):
            try:
                rec["fidelity"], rec["judge_reason"] = judge(p["prompt"], code, mock=args.mock)
            except Exception as exc:
                rec["fidelity"] = None
                rec["judge_error"] = str(exc)
                rec["judge_reason"] = f"judge failed: {exc}"
            else:
                rec.pop("judge_error", None)

    warn = [f"{f.code}: {f.detail}" if f.detail else f.code for f in findings]
    rec["note"] = "; ".join(x for x in [rec.get("qc_note", ""), *warn] if x)
    save_record(path, rec)
    return rec


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="fable,qwen_base")
    ap.add_argument("--limit", type=int, help="only the first N prompts")
    ap.add_argument("--no-qc", action="store_true", help="skip compile/backtest")
    ap.add_argument("--mock", action="store_true", help="offline: fake generations, no judge")
    ap.add_argument("--regenerate", action="store_true", help="ignore cached generations")
    ap.add_argument("--rerun-qc", action="store_true")
    ap.add_argument("--rejudge", action="store_true")
    ap.add_argument("--skip-judge", action="store_true", help="generate/evaluate only; use qc_eval.score for detailed judging later")
    ap.add_argument("--human-sample", type=int, default=10)
    ap.add_argument("--print-output", action="store_true", help="print raw model output, actual model ID and cache provenance")
    ap.add_argument("--verbose", action="store_true", help="print QC cloud stage/progress while waiting")
    ap.add_argument("--prompt-id", action="append", help="select a prompt ID (repeatable)")
    ap.add_argument("--repair-attempts", type=int, default=0,
                    help="enable real QC -> model repair feedback, with this many repair attempts (1-5)")
    args = ap.parse_args()

    prompts = load_prompts()
    todo = prompts
    if args.prompt_id:
        unknown = set(args.prompt_id) - {p["id"] for p in prompts}
        if unknown:
            ap.error("Unknown prompt IDs: " + ", ".join(sorted(unknown)))
        todo = [p for p in prompts if p["id"] in args.prompt_id]
    todo = todo[: args.limit] if args.limit else todo
    models = [m.strip() for m in args.models.split(",")]

    if args.repair_attempts:
        if not 1 <= args.repair_attempts <= 5 or args.mock or args.no_qc:
            ap.error("--repair-attempts requires real QC and a value from 1 to 5")
        from .auto_repair import run_batch
        run_batch(todo, models, args.repair_attempts, args.verbose, args.print_output)
        return

    qc = None
    if not args.no_qc and not args.mock:
        from .qc_client import QCClient
        qc = QCClient()
        assert qc.authenticate(), "QuantConnect auth failed: check QC_USER_ID / QC_API_TOKEN"

    if not SHEET.exists():
        sheet.build(prompts, SHEET)

    results = {}
    for model in models:
        results[model] = {}
        for i, p in enumerate(todo, 1):
            try:
                rec = process(model, p, args, qc)
            except Exception as e:  # QC failures are checkpointed inside run_on_qc
                print(f"[{model}] {p['id']}: ERROR {e}")
                continue
            results[model][p["id"]] = rec
            print(f"[{model}] {i}/{len(todo)} {p['id']}: compile={rec.get('compile_errors')} "
                  f"runtime={rec.get('runtime_errors')} fidelity={rec.get('fidelity')} "
                  f"model_id={rec.get('model_id')} mock={rec.get('model_id') == 'mock'}", flush=True)

    rng = random.Random(42)  # fixed seed so the human sample is the same every run
    human = rng.sample([p["id"] for p in todo], min(args.human_sample, len(todo)))
    sheet.fill(SHEET, prompts, results, human_rows=human)
    print(f"\nwrote {SHEET}")
    print("Open it in Excel or Sheets to recalculate the Summary tab.")


if __name__ == "__main__":
    main()
