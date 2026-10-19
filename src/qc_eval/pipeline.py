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
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import sheet
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

Score fidelity to the request from 1 to 5:
5 = every requested asset, indicator, parameter, entry/exit rule and date range is present and correct
4 = all key elements present; one minor detail off
3 = core idea right but one key element wrong or missing
2 = same strategy family, several key elements wrong
1 = does not implement the requested strategy
If the request is vague, judge whether the code is a sensible version of it; do not penalize choices the request left open.
Judge only what the code does, not style. Do not assume it runs.

Reply with JSON only: {{"score": <1-5>, "reason": "<one sentence>"}}"""


# ---------------------------------------------------------------- models
def call_fable(prompt, system=SYSTEM, max_tokens=4096):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                 "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": os.environ.get("FABLE_MODEL", "claude-fable-5-1"),
              "max_tokens": max_tokens, "temperature": 0, "system": system,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=300)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def call_openai_compatible(prompt, model, max_tokens=4096):
    r = requests.post(
        f"{os.environ['QWEN_BASE_URL'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['QWEN_API_KEY']}"},
        json={"model": model, "max_tokens": max_tokens, "temperature": 0,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": prompt}]},
        timeout=300)
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


def generate(model, prompt, mock=False):
    if mock:
        return mock_generate(prompt), "mock"
    if model == "fable":
        return call_fable(prompt), os.environ.get("FABLE_MODEL", "claude-fable-5-1")
    mid = os.environ["QWEN_BASE_MODEL" if model == "qwen_base" else "QWEN_TUNED_MODEL"]
    return call_openai_compatible(prompt, mid), mid


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


def run_on_qc(qc, project_id, code, name):
    qc.update_main(project_id, code)
    ok, compile_id, logs = qc.compile(project_id)
    if not ok:
        first = next((str(l) for l in logs if "error" in str(l).lower()), str(logs[:1]))
        return {"compile_errors": count_compile_errors(logs), "runtime_errors": None,
                "qc_note": f"compile: {first[:200]}"}
    bt = qc.backtest(project_id, compile_id, name)
    if bt["status"] == "completed":
        stats = bt.get("statistics", {})
        return {"compile_errors": 0, "runtime_errors": 0,
                "total_orders": stats.get("Total Orders"), "statistics": stats, "qc_note": ""}
    if bt["status"] == "timeout":
        return {"compile_errors": 0, "runtime_errors": 1, "qc_note": "backtest timed out"}
    return {"compile_errors": 0, "runtime_errors": 1,
            "qc_note": f"runtime: {str(bt.get('error'))[:200]}"}


# ---------------------------------------------------------------- main loop
def load_prompts():
    with open(PROMPTS) as f:
        return [json.loads(l) for l in f if l.strip()]


def process(model, p, args, qc, project_ids):
    path = RUNS / model / f"{p['id']}.json"
    rec = json.loads(path.read_text()) if path.exists() else {}

    if "output" not in rec or args.regenerate:
        out, model_id = generate(model, p["prompt"], mock=args.mock)
        rec = {"prompt_id": p["id"], "model": model, "model_id": model_id, "output": out,
               "generated_at": datetime.now(timezone.utc).isoformat()}

    code = extract_code(rec["output"])
    rec["has_code"] = code is not None
    findings = run_static_checks(code, p) if code else []
    rec["static_findings"] = [f.to_dict() for f in findings]

    if code is None:
        rec.update(compile_errors=None, runtime_errors=None, fidelity=1,
                   judge_reason="no code returned", qc_note="no code")
    else:
        if qc is not None and ("compile_errors" not in rec or args.regenerate or args.rerun_qc):
            if model not in project_ids:
                project_ids[model] = qc.create_project(f"eval-{model}-{int(time.time())}")
            rec.update(run_on_qc(qc, project_ids[model], code, p["id"]))
        if "fidelity" not in rec or args.regenerate or args.rejudge:
            rec["fidelity"], rec["judge_reason"] = judge(p["prompt"], code, mock=args.mock)

    warn = [f"{f.code}: {f.detail}" if f.detail else f.code for f in findings]
    rec["note"] = "; ".join(x for x in [rec.get("qc_note", ""), *warn] if x)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="fable,qwen_base")
    ap.add_argument("--limit", type=int, help="only the first N prompts")
    ap.add_argument("--no-qc", action="store_true", help="skip compile/backtest")
    ap.add_argument("--mock", action="store_true", help="offline: fake generations, no judge")
    ap.add_argument("--regenerate", action="store_true", help="ignore cached generations")
    ap.add_argument("--rerun-qc", action="store_true")
    ap.add_argument("--rejudge", action="store_true")
    ap.add_argument("--human-sample", type=int, default=10)
    args = ap.parse_args()

    prompts = load_prompts()
    todo = prompts[: args.limit] if args.limit else prompts
    models = [m.strip() for m in args.models.split(",")]

    qc = None
    if not args.no_qc and not args.mock:
        from .qc_client import QCClient
        qc = QCClient()
        assert qc.authenticate(), "QuantConnect auth failed: check QC_USER_ID / QC_API_TOKEN"

    if not SHEET.exists():
        sheet.build(prompts, SHEET)

    results, project_ids = {}, {}
    for model in models:
        results[model] = {}
        for i, p in enumerate(todo, 1):
            try:
                rec = process(model, p, args, qc, project_ids)
            except Exception as e:  # keep going; failures are recorded, not hidden
                print(f"[{model}] {p['id']}: ERROR {e}")
                continue
            results[model][p["id"]] = rec
            print(f"[{model}] {i}/{len(todo)} {p['id']}: compile={rec.get('compile_errors')} "
                  f"runtime={rec.get('runtime_errors')} fidelity={rec.get('fidelity')}")

    rng = random.Random(42)  # fixed seed so the human sample is the same every run
    human = rng.sample([p["id"] for p in todo], min(args.human_sample, len(todo)))
    sheet.fill(SHEET, prompts, results, human_rows=human)
    print(f"\nwrote {SHEET}")
    print("Open it in Excel or Sheets to recalculate the Summary tab.")


if __name__ == "__main__":
    main()
