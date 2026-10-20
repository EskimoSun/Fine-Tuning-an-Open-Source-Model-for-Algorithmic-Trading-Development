"""Console evidence for real generation and cloud execution; never prints credentials."""

import html
import json
import time


def print_model_output(model, prompt_id, model_id, output, source):
    print("\n=== MODEL OUTPUT {} / {} ===".format(model, prompt_id), flush=True)
    print("model_id={} source={} mock={}".format(model_id, source, model_id == "mock"), flush=True)
    print(output, flush=True)
    print("=== END MODEL OUTPUT ===\n", flush=True)


class QCProgressPrinter:
    def __init__(self, name):
        self.name = name
        self.last_marker = None
        self.last_printed = 0

    def __call__(self, result):
        backtest = result.get("raw_backtest", {}).get("backtest", {})
        progress = backtest.get("progress")
        percent = round(float(progress) * 100, 1) if progress is not None else None
        marker = (result.get("stage"), result.get("status"),
                  result.get("compilation", {}).get("state"), backtest.get("status"), percent)
        now = time.monotonic()
        if marker == self.last_marker and now - self.last_printed < 30:
            return
        self.last_marker, self.last_printed = marker, now
        print("[QC {}] stage={} status={} compile={} cloud={} progress={} project={} backtest={}".format(
            self.name, result.get("stage", "collect_evidence"), result.get("status"),
            marker[2], marker[3], str(percent) + "%" if percent is not None else "pending",
            result.get("project_id"), result.get("backtest_id")), flush=True)


def print_execution(name, result):
    keys = ("status", "stage", "project_id", "compile_id", "backtest_id",
            "compile_errors", "runtime_errors", "total_orders", "statistics", "trade_statistics",
            "orders_fetch_error", "equity_chart_fetch_error", "error", "qc_note")
    print("\n=== QC RESULT {} ===".format(name), flush=True)
    print(html.unescape(json.dumps({k: result[k] for k in keys if k in result},
                                  indent=2, ensure_ascii=False)), flush=True)
    for field in ("compile_logs", "logs"):
        lines = result.get(field, [])
        if lines:
            print("{} (last 20 of {}):".format(field, len(lines)), flush=True)
            for line in lines[-20:]:
                print(html.unescape(str(line)), flush=True)
    print("=== END QC RESULT ===\n", flush=True)
