"""
Compile and backtest every training target on QuantConnect, reusing ONE project.

    python -m finetune.validate_qc                     # all training templates, resumes from cache
    python -m finetune.validate_qc --only futures --only forex
    python -m finetune.validate_qc --rerun             # ignore cached results

The eval pipeline creates a new QC project per backtest (100/day cap). Here we create a single
project once, store its id in finetune/qc_project.json, and overwrite main.py for each template,
so validation does not use the daily project quota.

Results go to finetune/qc_validation.json: {template: {status, error, total_orders, ...}}.
build_dataset --require-qc keeps only templates whose status is "completed".
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from qc_eval.qc_client import QCClient

from .build_dataset import QC_VALIDATION, load_template_codes

HERE = Path(__file__).resolve().parent
PROJECT_FILE = HERE / "qc_project.json"


def get_project(qc):
    if PROJECT_FILE.exists():
        return json.loads(PROJECT_FILE.read_text())["project_id"]
    pid = qc.create_project("finetune-validation-{:%Y%m%d}".format(datetime.now()))
    PROJECT_FILE.write_text(json.dumps({"project_id": pid}))
    return pid


def validate(qc, project_id, name, code, max_wait):
    qc.update_main(project_id, code)
    ok, compile_id, logs = qc.compile(project_id)
    if not ok:
        return {"status": "compile_error", "error": "\n".join(str(x) for x in logs)[-2000:]}
    bt = qc.backtest(project_id, compile_id, name, max_wait=max_wait)
    return {"status": bt["status"], "error": (bt.get("error") or bt.get("stacktrace") or "")[-2000:] or None,
            "backtest_id": bt["backtest_id"], "total_orders": bt.get("total_orders")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="template folder (repeatable)")
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--max-wait", type=float, default=1800, help="seconds to wait for one backtest")
    ap.add_argument("--pause", type=float, default=2, help="seconds between backtests")
    args = ap.parse_args(argv)

    codes = load_template_codes()
    names = args.only or sorted(codes)
    missing = [n for n in names if n not in codes]
    if missing:
        raise SystemExit("unknown or eval templates: {}".format(missing))
    results = json.loads(QC_VALIDATION.read_text()) if QC_VALIDATION.exists() else {}

    qc = QCClient()
    project_id = get_project(qc)
    for i, name in enumerate(names, 1):
        if name in results and not args.rerun and results[name]["status"] in ("completed", "compile_error", "runtime_error"):
            continue
        print("[{}/{}] {}".format(i, len(names), name), flush=True)
        try:
            rec = validate(qc, project_id, name, codes[name], args.max_wait)
        except Exception as exc:  # timeouts and API errors are retried on the next run
            rec = {"status": "error", "error": "{}: {}".format(type(exc).__name__, exc)[:2000]}
        rec["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        results[name] = rec
        QC_VALIDATION.write_text(json.dumps(results, indent=1, sort_keys=True))
        print("    ->", rec["status"], (rec.get("error") or "")[:160].replace("\n", " "), flush=True)
        time.sleep(args.pause)

    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("summary:", counts)


if __name__ == "__main__":
    main()
