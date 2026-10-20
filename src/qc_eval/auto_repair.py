"""Real model -> user's QC account -> error feedback -> bounded model repair.

Original generations remain unchanged. Each revision and execution is saved;
only a completed backtest is promoted to <source_model>_qc_repaired.
"""
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone

from .pipeline import RUNS, generate, save_record
from .reporting import print_model_output
from .score import ensure_evaluation
from .static_checks import extract_code, run_static_checks

REPAIR_SYSTEM = """You repair QuantConnect LEAN Python algorithms using real QC execution feedback.
An external runner submits your main.py to the user's authenticated QC Cloud API
and returns errors. You do not need credentials, HTTP requests, or local execution.
Return one complete main.py in one ```python block. Preserve the user's requested
assets, dates, indicators, parameters, entry/exit conditions, timing and sizing.
Fix all visible issues, including downstream issues; do not remove strategy rules
to obtain a successful backtest. Use current snake_case Python APIs and real imports.
Use from AlgorithmImports import *. Import datetime/timedelta explicitly if needed.
Known QC interfaces (use only those relevant to the request):
- Resolution.HOUR, Resolution.DAILY, Resolution.MINUTE.
- self.bb(symbol, 20, 2, resolution=Resolution.DAILY); read
  lower_band.current.value, middle_band.current.value, upper_band.current.value.
- self.rsi(symbol, 14, MovingAverageType.WILDERS, Resolution.HOUR).
- self.roc(symbol, 60, Resolution.DAILY); self.atr(symbol, 14).
- self.settings.automatic_indicator_warm_up = True before creating indicators;
  check indicator.is_ready. Indicator objects are not lists or raw numbers.
- self.schedule.on(self.date_rules.every_day(symbol), self.time_rules.at(8, 0),
  self.callback). Scheduled callbacks take no arguments besides self.
- self.date_rules.every(DayOfWeek.MONDAY), self.date_rules.month_start(symbol),
  self.time_rules.after_market_open(symbol, 1).
- BrokerageName.INTERACTIVE_BROKERS_BROKERAGE; do not add brokerage settings unless needed.
- self.add_future(Futures.Indices.SP_500_E_MINI, extended_market_hours=True,
  data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
  data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO, contract_depth_offset=0).
  Keep the Future object, set_filter(0, 92), trade its mapped property, handle
  on_symbol_changed_events. A continuous Symbol itself is not tradable.
- self.add_option("SPY", Resolution.MINUTE), option.set_filter(...).
  Read real option contracts and greeks from the option chain; never invent
  OrderOption, SetUniverseSelection, DateRules.Weekly, or self.Indicator.
  Use valid subscribed contract symbols for orders; do not approximate a requested
  delta with a fixed percentage price offset.
Use hourly on_data or consolidated hourly bars for hourly decisions, not one daily
scheduled call. self.history can return a DataFrame; do not treat it as a Slice list.
Store indicators in fields like self._bb and self._rsi; do not shadow helper methods.
Never include API keys or other credentials in algorithm code.
Use English for identifiers, comments, docstrings, log messages, and response text.
"""


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact(text):
    text = str(text)
    for key, value in os.environ.items():
        if any(marker in key.upper() for marker in ("TOKEN", "API_KEY", "SECRET", "PASSWORD")) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    return re.sub(r"gsk_[A-Za-z0-9]{20,}", "[REDACTED]", text)


def feedback_request(spec, output, execution):
    # Explicitly select execution evidence; never forward client configuration,
    # request headers, API responses, account IDs or the .env to the model.
    evidence = {key: execution[key] for key in (
        "status", "error", "stacktrace", "compile_logs", "qc_note") if key in execution}
    evidence["logs_tail"] = execution.get("logs", [])[-12:]
    return redact("User request:\n{}\n\nCurrent candidate:\n{}\n\nActual QC execution feedback:\n{}\n\n"
                  "Return the corrected complete algorithm. A completed backtest proves execution only; "
                  "all requested trading behavior must still be preserved.".format(
                      spec["prompt"], output, html.unescape(json.dumps(evidence, ensure_ascii=False))[:18000]))


def repair_one(model, spec, qc, max_repairs=3, verbose=False, print_output=False):
    if not 1 <= max_repairs <= 5:
        raise ValueError("max_repairs must be between 1 and 5")
    source_path = RUNS / model / (spec["id"] + ".json")
    source = json.loads(source_path.read_text()) if source_path.exists() else {}
    if not source.get("output") or source.get("model_id") == "mock":
        output, model_id = generate(model, spec["prompt"])
        source = {"prompt_id": spec["id"], "model": model, "model_id": model_id,
                  "output": redact(output), "generated_at": datetime.now(timezone.utc).isoformat()}
        save_record(source_path, source)
    if not source.get("model_id") or source["model_id"] == "mock":
        raise ValueError("A real source model is required")
    root = RUNS / "qc_repair" / model / spec["id"]
    state_path = root / "state.json"
    source_hash = digest(source["output"])
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    identity = (source_hash, digest(spec["prompt"]), source["model_id"])
    if state and tuple(state.get(k) for k in ("source_output_sha256", "prompt_sha256", "model_id")) != identity:
        raise ValueError("Repair source or prompt changed; archive its existing qc_repair directory first")
    if not state:
        state = {"prompt_id": spec["id"], "source_model": model, "model_id": source["model_id"],
                 "source_output_sha256": source_hash, "prompt_sha256": identity[1],
                 "intervention": "model_qc_feedback_repair", "attempts": []}
    while True:
        index = len(state["attempts"])
        if index and state["attempts"][-1]["execution"]["status"] == "completed":
            break
        if index > max_repairs:
            break
        attempt_path = root / ("attempt_{:02d}.json".format(index))
        saved_attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else None
        if saved_attempt:
            output, model_id = saved_attempt["output"], saved_attempt["model_id"]
        elif index == 0:
            output, model_id = source["output"], source["model_id"]
        else:
            previous = state["attempts"][-1]
            if previous["execution"]["status"] not in ("compile_error", "syntax_error", "runtime_error", "no_code"):
                # Infrastructure, authentication and timeouts are not code errors.
                break
            request = feedback_request(spec, previous["output"], previous["execution"])
            save_record(root / ("attempt_{:02d}_request.json".format(index)),
                        {"system": REPAIR_SYSTEM, "request": request})
            print("[repair {}] requesting model correction {}/{}".format(spec["id"], index, max_repairs), flush=True)
            output, model_id = generate(model, request, system=REPAIR_SYSTEM)
            output = redact(output)
        code = extract_code(output)
        # Save a successful API response before QC calls; resume cannot resample it.
        if saved_attempt:
            attempt = saved_attempt
        else:
            attempt = {"round": index, "model_id": model_id, "output": output,
                       "source_sha256": digest(code) if code else None,
                       "generated_at": datetime.now(timezone.utc).isoformat()}
            save_record(attempt_path, attempt)
        if print_output:
            print_model_output(model + "_qc_repaired", spec["id"], model_id, output,
                               "original" if index == 0 else "qc_feedback_round_{}".format(index))
        if code:
            (root / ("attempt_{:02d}.py".format(index))).write_text(code, encoding="utf-8")
            seed = source.get("qc_evaluation") if index == 0 else None
            cached_path = RUNS / "scoring/evaluations" / model / (spec["id"] + ".json")
            if index == 0 and cached_path.exists():
                cached = json.loads(cached_path.read_text())
                if cached.get("source_sha256") == digest(code):
                    seed = cached
            execution_path = root / ("attempt_{:02d}_qc.json".format(index))
            saved_execution = json.loads(execution_path.read_text()) if execution_path.exists() else {}
            execution = ensure_evaluation(code, execution_path,
                                          "repair-{}-r{}".format(spec["id"], index), qc,
                                          seed=seed, verbose=verbose,
                                          rerun=saved_execution.get("status") in ("running", "interrupted"))
        else:
            execution = {"status": "no_code", "error": "No complete Python algorithm returned"}
        attempt["execution"] = execution
        save_record(attempt_path, attempt)
        state["attempts"].append(attempt)
        state["status"] = execution["status"]
        state["repairs_used"] = index
        save_record(state_path, state)
        print("[repair {}] round={} status={} backtest={}".format(
            spec["id"], index, execution["status"], execution.get("backtest_id")), flush=True)
    latest = state["attempts"][-1]
    if latest["execution"]["status"] == "completed":
        target = model + "_qc_repaired"
        record = {"prompt_id": spec["id"], "model": target, "model_id": latest["model_id"],
                  "output": latest["output"], "intervention": "model_qc_feedback_repair",
                  "repair": {"source_model": model, "source_sha256": digest(extract_code(source["output"]) or ""),
                             "rounds": latest["round"], "state_path": str(state_path)},
                  "qc_evaluation": latest["execution"],
                  "static_findings": [f.to_dict() for f in run_static_checks(extract_code(latest["output"]), spec)]}
        save_record(RUNS / target / (spec["id"] + ".json"), record)
    return state


def run_batch(prompts, models, max_repairs=3, verbose=False, print_output=False):
    from .config import load_env
    from .qc_client import QCClient
    load_env()
    qc = QCClient()
    if not qc.authenticate():
        raise RuntimeError("QC authentication failed; check local .env")
    print("QC authenticated; real cloud feedback repair enabled", flush=True)
    results = []
    for model in models:
        for spec in prompts:
            results.append(repair_one(model, spec, qc, max_repairs, verbose, print_output))
    summary = [{"model": r["source_model"], "prompt_id": r["prompt_id"], "status": r["status"],
                "repairs_used": r["repairs_used"]} for r in results]
    save_record(RUNS / "qc_repair/latest_summary.json", {"results": summary})
    print(json.dumps(summary, indent=2), flush=True)
    return results
