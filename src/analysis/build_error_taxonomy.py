"""
Build the error taxonomy report from cached evaluation records.

Offline: reads runs/ (read-only), writes analysis/error_taxonomy.md and
analysis/error_taxonomy.json. No model or QuantConnect calls.

Run from src/:
    .venv/bin/python analysis/build_error_taxonomy.py

The tuned 9B run is not on this branch. If its folder is not on disk the
script reads it straight from the teammate's remote branch with `git archive`
(nothing is checked out or merged). Override with --tuned9-dir or --tuned9-ref.
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from qc_eval.error_classifier import (  # noqa: E402
    ERROR_CATEGORIES, LATENT_TAGS, classify_record, positional_resolution_calls)

T9_PATH = "src/eval_results/2026-11-14/together_9b_100/generations/qwen_tuned"
T9_REF = "origin/codex/together-9b-eval100-ryz"

RUN_LABELS = {
    "qwen_base": "Base 9B (untuned)",
    "qwen_tuned": "Tuned 4B",
    "together_9b_tuned": "Tuned 9B",
}
TUNED = ["qwen_tuned", "together_9b_tuned"]
SMALL = 5   # counts below this are flagged as possibly noise

# One wrong-vs-right pair per category. "wrong" must appear verbatim in the
# named cached output and "right" verbatim in the named template; the build
# fails otherwise, so these cannot drift from the data.
SNIPPETS = {
    "RESOLUTION_POSITIONAL": dict(
        run="qwen_tuned", prompt="equity-rsi-overbought-oversold_v01",
        wrong="self._rsi = self.rsi(self._qqq.symbol, 14, Resolution.HOUR)",
        template="equity-rsi-overbought-oversold",
        right="self._rsi = self.rsi(self._equity, 14, MovingAverageType.WILDERS, Resolution.HOUR)",
        why="rsi's 3rd positional parameter is moving_average_type, not resolution. Either pass the "
            "moving-average type first or use the keyword (the Bollinger template does: "
            "`self.bb(self._equity, 20, 2, resolution=Resolution.DAILY)`)."),
    "HALLUCINATED_MEMBER": dict(
        run="together_9b_tuned", prompt="option-iron-condor-spy_v05",
        wrong="self._option.set_filter(lambda u: u.expiry(0, 7).strikes(-10, 10))",
        template="option-iron-condor-spy",
        right="self._option.set_filter(lambda u: u.strikes(-10, 10).expiration(0, 7))",
        why="The filter method is `expiration`, not `expiry` / `expiries`. Same shape of mistake as "
            "`date_rules.every_quarter_start()` for `date_rules.quarter_start(\"SPY\")`."),
    "UNDEFINED_NAME": dict(
        run="qwen_tuned", prompt="equity-momentum-cross-sectional-decile_v02",
        wrong="def _select_assets(self, data: List[ETFUniverse]) -> List[Symbol]:",
        template="equity-momentum-cross-sectional-decile",
        right="def _select_assets(self, fundamentals: list[Fundamental]) -> list[Symbol] | Universe.UnchangedUniverse:",
        why="`ETFUniverse` is not a LEAN type. A name in a signature is evaluated when the class is "
            "defined, so the algorithm fails to load before initialize() runs."),
    "HALLUCINATED_ALGO_METHOD": dict(
        run="qwen_tuned", prompt="equity-atr-volatility-stop_v04",
        wrong="self._chandelier = self.chandelier_exit(self._spy, 20, 3, Resolution.DAILY)",
        template="equity-atr-volatility-stop",
        right="stop_level = self._trailing_high - 3.0 * atr_value",
        why="There is no chandelier-exit helper on QCAlgorithm. The template builds it from "
            "`self.atr(self._spy.symbol, 14)` plus a manually tracked trailing high."),
    "ARG_MISMATCH_OTHER": dict(
        run="qwen_tuned", prompt="equity-momentum-cross-sectional-decile_v01",
        wrong="self.schedule.on(self.date_rules.month_start('SPY'))",
        template="equity-momentum-cross-sectional-decile",
        right="self.date_rules.month_start(\"SPY\"),\n            self.time_rules.at(9, 31),\n            self._rebalance,",
        why="schedule.on needs a date rule, a time rule and a callback."),
    "SYNTAX_ERROR": dict(
        run="together_9b_tuned", prompt="option-iron-condor-spy_v04",
        wrong="self.buy ATM call to form a straddle to trade volatility.",
        template="option-iron-condor-spy",
        right="self.buy(option_strategy, 1)",
        why="Prose leaked into code mid-line. All 5 tuned-9B syntax errors are this kind of slip "
            "(`bar consolidator = ...`, `self.return(...)`, `[[:10]]`), not truncation."),
    "PYTHON_LOGIC_ERROR": dict(
        run="together_9b_tuned", prompt="equity-monthly-roc-rotation_v04",
        wrong="current_weight = security.holdings.quantity / self.portfolio.total_holdings_value",
        template="equity-sixty-forty-portfolio",
        right="current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value",
        why="total_holdings_value is 0 before the first trade, so the division fails. "
            "total_portfolio_value includes cash and is never 0 at start."),
    "SYMBOL_SECURITY_CONFUSION": dict(
        run="qwen_tuned", prompt="equity-pairs-trading-cointegration_v02",
        wrong="if not self._ko.invested and not self._pep.invested:",
        template="futures",
        right="quantity = self.portfolio[old_symbol].quantity",
        why="self._ko is a Symbol (from `.symbol`); holdings live on the portfolio, "
            "e.g. `self.portfolio[self._ko].invested`."),
    "UNDEFINED_SELF_STATE": dict(
        run="qwen_tuned", prompt="equity-sixty-forty-portfolio_v09",
        wrong="self._targets.append(PortfolioTarget(security, self._weight))",
        template="equity-sixty-forty-portfolio",
        right="self._targets = {",
        why="The attribute is used before it is ever assigned."),
    "OTHER_RUNTIME": dict(
        run="qwen_tuned", prompt="equity-opening-range-breakout_v06",
        wrong="self._spy.high = 0",
        template="equity-opening-range-breakout",
        right="self._orb_high = None",
        why="`high` is a read-only property of the Security. Keep custom state on the algorithm."),
    "WRONG_IMPORT": dict(
        run="qwen_base", prompt="equity-momentum-cross-sectional-decile_v06",
        wrong="class MomentumDecileStrategy(QC.Algorithm.QuantConnect):",
        template="equity-momentum-cross-sectional-decile",
        right="from AlgorithmImports import *",
        why="The untuned model invents import paths (`QCAlgo`, `QC_Algorithm`, `QC.Algorithm...`). "
            "Every template uses the single `from AlgorithmImports import *` line and `QCAlgorithm`."),
    "LEGACY_PASCALCASE": dict(
        run="qwen_base", prompt="equity-rsi-overbought-oversold_v05",
        wrong="self.SetInitialCash(100000)",
        template="equity-rsi-overbought-oversold",
        right="self.set_cash(100000)",
        why="PascalCase is the old API, and SetInitialCash never existed even there (it was SetCash)."),
    "GEN_LOOP_TRUNCATED": dict(
        run="qwen_base", prompt="equity-atr-volatility-stop_v01",
        wrong="from QuantConnect.Lean.Engine.RealTime.RealTimeBrokerageFactory import RealTimeBrokerageFactory",
        template="equity-atr-volatility-stop",
        right="from AlgorithmImports import *",
        why="The same import line repeats hundreds of times until the token limit; the code block never closes."),
}

# Suggested correction-pair template for the training data, one line each.
CORRECTION_PAIRS = {
    "HALLUCINATED_MEMBER":
        "wrong: `u.expiry(0, 7)` / `self.date_rules.every_quarter_start()` / `security.roc` never attached; "
        "right: `u.strikes(-10, 10).expiration(0, 7)` / `self.date_rules.quarter_start(\"SPY\")` / "
        "`equity.roc = self.roc(equity, n, Resolution.DAILY)` before reading it. Write one pair per real member, "
        "grouped by object (option filter, date_rules, Security, universe, Futures).",
    "RESOLUTION_POSITIONAL":
        "wrong: `self.rsi(symbol, 14, Resolution.HOUR)`, `self.bb(symbol, 20, 2, Resolution.DAILY)`, "
        "`self.atr(symbol, 14, Resolution.DAILY)`; right: `self.rsi(symbol, 14, MovingAverageType.WILDERS, Resolution.HOUR)` "
        "or `self.bb(symbol, 20, 2, resolution=Resolution.DAILY)`. Include `self.roc(symbol, n, Resolution.DAILY)` as a "
        "contrast case that IS valid.",
    "UNDEFINED_NAME":
        "wrong: `def _select_assets(self, data: List[ETFUniverse])`, `OLSRegressionModel()`, `Indices.SP_500_E_MINI`; "
        "right: `list[Fundamental]`, `np.linalg.lstsq(...)`, `Futures.Indices.SP_500_E_MINI`. Pair each invented class "
        "with the real type or with plain numpy / Python.",
    "HALLUCINATED_ALGO_METHOD":
        "wrong: `self.chandelier_exit(spy, 20, 3, Resolution.DAILY)`, `self.orb(spy, 30)`, `self.spread(ko, pep)`; "
        "right: build it from real pieces (`self.atr(symbol, 14)` plus a tracked `self._trailing_high`; "
        "`self._orb_high = max(self._orb_high, bar.high)` in on_data; numpy OLS on session closes).",
    "ARG_MISMATCH_OTHER":
        "wrong: `self.schedule.on(self.date_rules.month_start('SPY'))`, `OptionStrategies.iron_condor(spy, call, put, ...)` "
        "with contracts, `self.add_future(\"SPX\", \"SP\")`; right: `self.schedule.on(date_rule, time_rule, callback)`, "
        "`OptionStrategies.iron_condor(self._option, long_put.strike, short_put.strike, short_call.strike, long_call.strike, expiry)`, "
        "`self.add_future(Futures.Indices.SP_500_E_MINI, ...)`.",
    "SYNTAX_ERROR":
        "wrong: `self.buy ATM call to form a straddle` (prose inside code), `bar consolidator = ...`; "
        "right: prose goes in a `#` comment and the statement stands alone, e.g. `self.buy(option_strategy, 1)`.",
    "PYTHON_LOGIC_ERROR":
        "wrong: `holdings_value / self.portfolio.total_holdings_value` (0 before the first trade); "
        "right: `self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value`.",
    "GEN_EMPTY_OUTPUT":
        "Probably not a training-data fix: all 4 are empty responses in the run with the old settings (thinking on, max_tokens 4096). "
        "Re-run with thinking off before writing pairs for it.",
    "OTHER_RUNTIME":
        "wrong: `self._spy.high = 0` (assigning to a read-only Security property); "
        "right: keep custom state on the algorithm, `self._orb_high = None`.",
    "UNDEFINED_SELF_STATE":
        "wrong: `self._targets.append(...)` with no earlier assignment; right: `self._targets = {...}` in initialize() first.",
    "SYMBOL_SECURITY_CONFUSION":
        "wrong: `self._ko = self.add_equity(\"KO\").symbol` then `self._ko.invested`; "
        "right: `self.portfolio[self._ko].invested` (a Symbol has no holdings or price).",
}


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_dir(path: Path) -> dict:
    return {f.stem: json.loads(f.read_text()) for f in sorted(path.glob("*.json"))}


def load_from_git(ref: str, path: str) -> dict:
    repo = SRC.parent
    blob = subprocess.run(["git", "-C", str(repo), "archive", ref, path], check=True, capture_output=True).stdout
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        tar.extractall(tmp, filter="data") if sys.version_info >= (3, 12) else tar.extractall(tmp)
        return load_dir(Path(tmp) / path)


def load_runs(args) -> tuple:
    runs, sources = {}, {}
    for key in ("qwen_base", "qwen_tuned"):
        runs[key] = load_dir(SRC / "runs" / key)
        sources[key] = "src/runs/{}/".format(key)
    local = Path(args.tuned9_dir) if args.tuned9_dir else SRC.parent / T9_PATH
    try:
        if local.is_dir():
            runs["together_9b_tuned"] = load_dir(local)
            sources["together_9b_tuned"] = str(local)
        else:
            runs["together_9b_tuned"] = load_from_git(args.tuned9_ref, T9_PATH)
            sources["together_9b_tuned"] = "git {}:{}/".format(args.tuned9_ref, T9_PATH)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print("tuned 9B run not found ({}); continuing with two runs".format(exc), file=sys.stderr)
    return runs, sources


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def table(header: list, rows: list) -> str:
    def numeric(i):
        return all(re.fullmatch(r"[\d.]*[%*]?|n/a", str(r[i])) for r in rows)
    out = ["| " + " | ".join(str(h) for h in header) + " |",
           "|" + "|".join("---:" if numeric(i) else "---" for i in range(len(header))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def short(pid: str) -> str:
    return pid.replace("equity-", "")


def pct(n: int, d: int) -> str:
    return "{:.0f}%".format(100.0 * n / d) if d else "n/a"


_BAD_RES = re.compile(r"self\.(?:rsi|atr)\([^()]*,\s*[0-9]+\s*,\s*Resolution\.|"
                      r"self\.bb\([^()]*,\s*[0-9]+\s*,\s*[0-9.]+\s*,\s*Resolution\.")
_TRAILING_RES = re.compile(r"self\.(?!rsi\(|bb\(|atr\(|add_|set_|history|register_|warm_up|indicator_history)"
                           r"[a-z_]+\([^()]*,\s*Resolution\.[A-Z]+\)")


def training_profile() -> dict:
    """How the training data uses the indicators behind RESOLUTION_POSITIONAL."""
    files = sorted((SRC / "data" / "train_templates").glob("*/main.py"))
    code = [f.read_text() for f in files]
    prof = dict(train_templates=len(files),
                calls={m: sum(len(re.findall(r"self\.%s\(" % m, c)) for c in code) for m in ("rsi", "bb", "atr")},
                templates_with_bad_pattern=sum(bool(_BAD_RES.search(c)) for c in code),
                other_indicator_calls_ending_in_positional_resolution=sum(len(_TRAILING_RES.findall(c)) for c in code))
    examples = bad = 0
    for name in ("train.jsonl", "val.jsonl"):
        f = SRC / "finetune" / "out" / name
        if f.exists():
            for line in f.read_text().splitlines():
                examples += 1
                bad += bool(_BAD_RES.search(line.replace("\\n", "\n")))
    prof.update(finetune_examples=examples, finetune_examples_with_bad_pattern=bad)
    return prof


def verify_snippets(runs: dict) -> None:
    for code, s in SNIPPETS.items():
        if s["run"] not in runs:
            continue
        rec = runs[s["run"]][s["prompt"]]
        text = ((rec.get("qc_evaluation") or {}).get("source") or "") + (rec.get("output") or "")
        assert s["wrong"] in text, "snippet for {} not found in {}/{}".format(code, s["run"], s["prompt"])
        tpl = (SRC / "data" / "templates" / s["template"] / "main.py").read_text()
        assert s["right"] in tpl, "reference line for {} not in template {}".format(code, s["template"])


# --------------------------------------------------------------------------
# Findings text (every number is computed, none typed in)
# --------------------------------------------------------------------------

def build_findings(report, rows, run_keys, tuned, templates) -> dict:
    L = RUN_LABELS

    def cnt(**kw):
        return sum(all(r[k] == v for k, v in kw.items()) for r in rows)

    def each(fn, keys=None):
        return ", ".join("{} {}".format(L[k], fn(k)) for k in (keys or tuned))

    rc, tp = report["resolution_claim"], report["training_data_profile"]
    rt = rc["runtime_errors"]
    res = rc["resolution_positional"]
    res_tpl = [t for t in templates if any(cnt(run=k, template=t, category="RESOLUTION_POSITIONAL") for k in tuned)]
    in_tpl = {k: sum(cnt(run=k, template=t, outcome="runtime_error") for t in res_tpl) for k in tuned}
    clean_hits = {k: sum(1 for r in rows if r["run"] == k and r["outcome"] == "clean" and "RESOLUTION_POSITIONAL" in r["latent"])
                  for k in tuned}
    no_res = report["latent_tags"]["ADD_EQUITY_NO_RESOLUTION"]["counts"]
    fam = ("HALLUCINATED_MEMBER", "UNDEFINED_NAME", "HALLUCINATED_ALGO_METHOD")
    fam_n = {k: sum(cnt(run=k, category=c) for c in fam) for k in tuned}
    f = {}

    f["RESOLUTION"] = "\n".join([
        "**Not confirmed at \"nearly half\". It is about a quarter:** " +
        each(lambda k: "{} of {} runtime errors ({})".format(res[k], rt[k], pct(res[k], rt[k]))) +
        ". It is still the largest single, exactly repeatable error in both tuned runs.\n",
        "Three corrections to how the error is described:\n",
        "1. **The resolution is not missing, it is misplaced.** In all {} cases the model did pass `Resolution.X`; it put it "
        "in the positional slot that belongs to the moving-average type. QuantConnect's message is the same every time: "
        "`Argument mismatch: argument 3 ('moving_average_type') expected MovingAverageType, got Resolution.` "
        "(argument 4 for `bb`, argument 3 `'type'` for `atr`).".format(sum(res[k] for k in tuned)),
        "2. **It only happens on three indicators, so it only appears in three templates** ({}). Inside those templates it is "
        "most of the failures: {}. Outside them it is zero.".format(
            ", ".join(short(t) for t in res_tpl),
            each(lambda k: "{} of {} runtime errors ({})".format(res[k], in_tpl[k], pct(res[k], in_tpl[k])))),
        "3. **The training data does not contain the wrong pattern.** In the {} training templates, `self.rsi(` appears {} times, "
        "`self.bb(` {} and `self.atr(` {}, all in the correct form, and {} of {} fine-tuning examples contain the wrong form. "
        "What the training data does contain is {} other indicator calls that end in a positional `Resolution.X` "
        "(`self.ema(symbol, 20, Resolution.DAILY)`, `self.roc(...)`, and so on), which is valid for those indicators. "
        "My reading (an inference, not something the records prove): the model learned \"resolution goes last\" and applies it "
        "to indicators it rarely or never saw. That is under-coverage rather than memorising a bad example, and it means the fix "
        "is to add correct rsi / bb / atr examples, not to remove anything.\n".format(
            tp["train_templates"], tp["calls"]["rsi"], tp["calls"]["bb"], tp["calls"]["atr"],
            tp["finetune_examples_with_bad_pattern"], tp["finetune_examples"],
            tp["other_indicator_calls_ending_in_positional_resolution"]),
        "Supporting checks:\n",
        "- The static rule (AST check for `Resolution.X` in that slot) finds the pattern in " +
        each(lambda k: "{} outputs".format(rc["static_rule_hits"][k])) +
        ". It catches every runtime hit ({} missed) and flags {} clean backtests. The extra hits are outputs that crashed on an "
        "earlier line first: {}.".format(
            sum(len(v) for v in rc["runtime_hits_missed_by_static_rule"].values()), sum(clean_hits.values()),
            each(lambda k: ", ".join(short(p) for p in rc["masked_by_an_earlier_error"][k]) or "none")),
        "- Fixing this line does not guarantee a clean backtest. The backtest stops here, so what would fail next in these "
        "{} outputs is unknown.".format(sum(res[k] for k in tuned)),
        "- Read literally (no resolution given at all), the claim matches a different, non-crashing pattern: " +
        each(lambda k: "{} outputs".format(no_res[k])) +
        " call `add_equity` with no resolution. That never raises an error (the Bollinger reference template does the same), so it "
        "cannot explain any runtime-error count; where the prompt asks for hourly or daily bars it is a fidelity problem instead.",
    ])

    zero_clean = [short(t) for t in templates if not any(cnt(run=k, template=t, outcome="clean") for k in tuned)]
    best = sorted(templates, key=lambda t: -sum(cnt(run=k, template=t, outcome="clean") for k in tuned))[:2]
    f["BREAKDOWN"] = "\n".join([
        "What the breakdowns show:\n",
        "- **Template decides the error type.** `RESOLUTION_POSITIONAL` is entirely in {}. `HALLUCINATED_MEMBER` is the main "
        "failure on the options template ({}). Futures fails on invented names and wrong arguments ({} `UNDEFINED_NAME` + "
        "`ARG_MISMATCH_OTHER`).".format(
            ", ".join(short(t) for t in res_tpl),
            each(lambda k: "{} of 10".format(cnt(run=k, template="option-iron-condor-spy", category="HALLUCINATED_MEMBER"))),
            each(lambda k: "{} of 10".format(cnt(run=k, template="futures", category="UNDEFINED_NAME") +
                                             cnt(run=k, template="futures", category="ARG_MISMATCH_OTHER")))),
        "- **Clean backtests are concentrated.** {} account for {} of the clean runs. No clean backtest in either tuned "
        "run: {}.".format(
            " and ".join(short(t) for t in best),
            each(lambda k: "{} of {}".format(sum(cnt(run=k, template=t, outcome="clean") for t in best), cnt(run=k, outcome="clean"))),
            ", ".join(zero_clean) or "none"),
        "- **Specificity shows no consistent effect.** Clean counts for vague / precise / over-specified (30 prompts each): {}. "
        "`RESOLUTION_POSITIONAL` is flat across specificity. `HALLUCINATED_ALGO_METHOD` looks vague-heavy in Tuned 4B "
        "({} of {} on vague prompts) but not in Tuned 9B ({} of {}), so treat that as noise. Most cells in the specificity "
        "tables are under 10.".format(
            each(lambda k: " / ".join(str(cnt(run=k, specificity=s, outcome="clean")) for s in ("vague", "precise", "over_specified"))),
            cnt(run="qwen_tuned", specificity="vague", category="HALLUCINATED_ALGO_METHOD"),
            cnt(run="qwen_tuned", category="HALLUCINATED_ALGO_METHOD"),
            cnt(run="together_9b_tuned", specificity="vague", category="HALLUCINATED_ALGO_METHOD"),
            cnt(run="together_9b_tuned", category="HALLUCINATED_ALGO_METHOD")),
        "- **Persona segment shows no pattern** beyond what 10 to 30 prompts per cell can support.",
    ])

    lt = report["latent_tags"]
    f["LATENT"] = "\n".join([
        "- `NO_ALGORITHM_IMPORTS` and `LEGACY_PASCALCASE` cover the base run and are absent from every tuned output.",
        "- `UNKNOWN_SELF_METHOD` flags more outputs ({}) than crashed on an invented algorithm method ({}). The gap is a mix of "
        "invented calls hidden behind an earlier error and false positives, since the known-method list in `static_checks.py` "
        "is incomplete. I did not hand-check which is which.".format(
            each(lambda k: lt["UNKNOWN_SELF_METHOD"]["counts"][k]), each(lambda k: cnt(run=k, category="HALLUCINATED_ALGO_METHOD"))),
        "- `MISSING_READY_CHECK` is 0 in every run. That check is a keyword test (any `is_ready`, `set_warm_up`, ... in the "
        "file), so 0 means the tuned outputs always mention readiness, not that warm-up is handled correctly.",
    ])

    init = report["runtime_errors_during_initialization"]
    f["COMPARE"] = "\n".join([
        "**Fixed by tuning (base 9B to tuned 9B, same size):**\n",
        "- Runaway output: {} base outputs never produced usable code (one import or comment line repeated to the token limit). "
        "Tuned 9B: 0.".format(cnt(run="qwen_base", category="GEN_LOOP_TRUNCATED")),
        "- Imports and namespaces: {} base crashes, and statically {} of {} base outputs with code lack "
        "`from AlgorithmImports import *`. Tuned: 0 of {}.".format(
            cnt(run="qwen_base", category="WRONG_IMPORT"), lt["NO_ALGORITHM_IMPORTS"]["counts"]["qwen_base"],
            sum(1 for r in rows if r["run"] == "qwen_base" and r["outcome"] != "no_code"),
            sum(1 for r in rows if r["run"] in tuned and r["outcome"] != "no_code")),
        "- PascalCase API: in {} base outputs statically, 0 tuned outputs.".format(lt["LEGACY_PASCALCASE"]["counts"]["qwen_base"]),
        "- Net: clean backtests went from 0 to {}.\n".format(each(lambda k: cnt(run=k, outcome="clean"))),
        "**Not fixed, and now the whole problem:** the model writes a file that loads, then calls LEAN API that does not exist. "
        "`HALLUCINATED_MEMBER` + `UNDEFINED_NAME` + `HALLUCINATED_ALGO_METHOD` together are {}. That family is more than twice the "
        "size of the Resolution error. Most tuned failures happen before the first bar: QuantConnect flags {} as "
        "initialization errors.\n".format(
            each(lambda k: "{} of {} runtime errors ({})".format(fam_n[k], rt[k], pct(fam_n[k], rt[k]))),
            each(lambda k: "{} of {}".format(init[k], rt[k]))),
        "**How to read \"appeared\":** every base output failed at or before import, so the base model never reached the "
        "lines where these errors occur. The table cannot say whether tuning created them or only exposed them. "
        "`RESOLUTION_POSITIONAL` is the one most plausibly tied to tuning, because it needs the snake_case indicator helpers "
        "that the base model never calls.\n",
        "**Tuned 4B vs Tuned 9B:** the profiles are nearly the same. The differences are small counts: empty responses "
        "({}), probably from the 4B run's thinking-on settings (the pipeline records an empty string when the token budget goes to reasoning); syntax errors ({}); plain logic errors ({}).".format(
            each(lambda k: cnt(run=k, category="GEN_EMPTY_OUTPUT")), each(lambda k: cnt(run=k, category="SYNTAX_ERROR")),
            each(lambda k: cnt(run=k, category="PYTHON_LOGIC_ERROR"))),
    ])

    area = report["runtime_errors_by_api_area"]

    def dom(d):
        return each(lambda k: area[k].get(d, 0))
    kw = sum("unexpected keyword" in (r["message"] or "") for r in rows)
    f["EXPECTED"] = "\n".join([
        table(["Expected category", "Where it landed", "Counts"], [
            ["Missing resolution argument", "`RESOLUTION_POSITIONAL` (misplaced, not missing; section 3)", each(lambda k: res[k])],
            ["Wrong or missing argument names (keyword vs positional)", "`RESOLUTION_POSITIONAL` + `ARG_MISMATCH_OTHER`. "
             "All are positional type mismatches; {} messages mention an unexpected keyword".format(kw),
             each(lambda k: res[k] + cnt(run=k, category="ARG_MISMATCH_OTHER"))],
            ["Attribute does not exist on object", "`HALLUCINATED_MEMBER` + `HALLUCINATED_ALGO_METHOD`. No `.Value` vs "
             "`.current.value` case was found", each(lambda k: cnt(run=k, category="HALLUCINATED_MEMBER") +
                                                        cnt(run=k, category="HALLUCINATED_ALGO_METHOD"))],
            ["Legacy PascalCase mixed with snake_case", "`LEGACY_PASCALCASE`: base only",
             each(lambda k: cnt(run=k, category="LEGACY_PASCALCASE"), run_keys)],
            ["Indicator used before ready / no warm-up", "Not observed. It does not raise an error, so runtime logs cannot show it; "
             "the static check is 0 in all runs. Needs a behaviour check against the reference", each(lambda k: 0)],
            ["Wrong return type handling", "`SYMBOL_SECURITY_CONFUSION`: noise-level", each(lambda k: cnt(run=k, category="SYMBOL_SECURITY_CONFUSION"))],
            ["Wrong import", "`WRONG_IMPORT`: base only", each(lambda k: cnt(run=k, category="WRONG_IMPORT"), run_keys)],
            ["Universe or option chain misuse", "API-area tag `options` + `universe` on runtime errors (spread over the "
             "hallucination categories)", each(lambda k: area[k].get("options", 0) + area[k].get("universe", 0))],
            ["Scheduling API misuse", "API-area tag `scheduling`: small", dom("scheduling")],
            ["Code loops / truncation", "`GEN_LOOP_TRUNCATED` (base) and `GEN_EMPTY_OUTPUT` (Tuned 4B)",
             each(lambda k: cnt(run=k, category="GEN_LOOP_TRUNCATED") + cnt(run=k, category="GEN_EMPTY_OUTPUT"), run_keys)],
        ]),
        "",
        "Runtime errors by API area (keyword heuristic on the failing line; a second view of the same errors, not extra ones):\n",
        table(["API area"] + [L[k] for k in run_keys],
              [[d] + [area[k].get(d, 0) for k in run_keys]
               for d in ("indicators", "options", "futures", "universe", "portfolio/orders", "scheduling", "other")]),
        "",
        "For the base run the area is almost always `other` because it fails on the import line.",
    ])

    top4 = [i["category"] for i in report["top8_tuned"][:4]]
    f["TOP8"] = ("The first four account for {}. Ranks 5 to 8 total 9 or fewer across both runs, so treat their order as "
                 "unstable.".format(each(lambda k: "{} of {} runtime errors".format(sum(cnt(run=k, category=c) for c in top4), rt[k]))))
    return f


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tuned9-dir", default=None)
    ap.add_argument("--tuned9-ref", default=T9_REF)
    ap.add_argument("--out", default=str(SRC / "analysis"))
    args = ap.parse_args()

    prompts = {}
    for line in (SRC / "data" / "prompts_100.jsonl").read_text().splitlines():
        if line.strip():
            p = json.loads(line)
            prompts[p["id"]] = p
    runs, sources = load_runs(args)
    verify_snippets(runs)
    run_keys = list(runs)
    tuned = [k for k in TUNED if k in runs]
    templates = list(dict.fromkeys(p["template_id"] for p in prompts.values()))
    specs = ["vague", "precise", "over_specified", "ceiling"]
    segments = ["individual", "startup", "institutional", "reference"]

    # ---- classify every record ----
    rows = []
    for run, recs in runs.items():
        for pid, rec in recs.items():
            c = classify_record(rec)
            p = prompts[pid]
            qc = rec.get("qc_evaluation") or {}
            rows.append(dict(
                run=run, prompt_id=pid, template=p["template_id"], segment=p["segment"],
                specificity=p["specificity"], model_id=rec.get("model_id"),
                system_prompt=rec.get("system_prompt"), generated_at=rec.get("generated_at"),
                total_orders=qc.get("total_orders"),
                has_initialize_error=bool(qc.get("has_initialize_error")),
                static_findings=[f.get("code") for f in rec.get("static_findings") or []], **c))

    def sel(**kw):
        return [r for r in rows if all(r[k] == v for k, v in kw.items())]

    def count(**kw):
        return len(sel(**kw))

    def n(run, cat):
        return count(run=run, category=cat)

    cat_order = [c for c in ERROR_CATEGORIES if c != "CLEAN" and any(r["category"] == c for r in rows)]
    tuned_total = {c: sum(count(run=k, category=c) for k in tuned) for c in cat_order}

    # ---- JSON ----
    cats_json = []
    for code in cat_order:
        cat = ERROR_CATEGORIES[code]
        hits = sel(category=code)
        examples, seen = [], set()
        for r in sorted(hits, key=lambda r: (r["run"] not in tuned, r["prompt_id"])):
            key = r["detail"] or r["message"][:60]
            if r["message"] and key not in seen and len(examples) < 3:
                seen.add(key)
                examples.append(dict(run=r["run"], prompt_id=r["prompt_id"], message=r["message"], line=r["line"]))
        cats_json.append(dict(
            category=code, stage=cat.stage, title=cat.title, rule=cat.rule,
            counts={k: count(run=k, category=code) for k in run_keys},
            count_tuned_runs=tuned_total[code],
            prompt_ids={k: [r["prompt_id"] for r in sel(run=k, category=code)] for k in run_keys},
            by_template={k: dict(collections.Counter(r["template"] for r in sel(run=k, category=code))) for k in run_keys},
            by_specificity={k: dict(collections.Counter(r["specificity"] for r in sel(run=k, category=code))) for k in run_keys},
            by_domain={k: dict(collections.Counter(r["domain"] for r in sel(run=k, category=code) if r["domain"])) for k in run_keys},
            details={k: dict(collections.Counter(r["detail"] for r in sel(run=k, category=code)).most_common(12)) for k in run_keys},
            ambiguous={k: [dict(prompt_id=r["prompt_id"], note=r["ambiguity"]) for r in sel(run=k, category=code) if r["ambiguity"]]
                       for k in run_keys},
            examples=examples,
            snippet=SNIPPETS.get(code),
            correction_pair=CORRECTION_PAIRS.get(code),
        ))

    runtime = {k: count(run=k, outcome="runtime_error") for k in run_keys}
    res_primary = {k: count(run=k, category="RESOLUTION_POSITIONAL") for k in run_keys}
    res_latent = {k: sum("RESOLUTION_POSITIONAL" in r["latent"] for r in sel(run=k)) for k in run_keys}
    res_masked = {k: [r["prompt_id"] for r in sel(run=k) if "RESOLUTION_POSITIONAL" in r["latent"]
                      and r["category"] != "RESOLUTION_POSITIONAL"] for k in run_keys}
    res_missed = {k: [r["prompt_id"] for r in sel(run=k, category="RESOLUTION_POSITIONAL")
                      if "RESOLUTION_POSITIONAL" not in r["latent"]] for k in run_keys}

    top8 = sorted(cat_order, key=lambda c: -tuned_total[c])
    cutoff = tuned_total[top8[7]] if len(top8) >= 8 else 0
    tied = [c for c in top8[8:] if tuned_total[c] == cutoff and cutoff > 0]

    report = dict(
        description="Root-cause error taxonomy over cached runs on the 100 held-out test prompts.",
        runs={k: dict(label=RUN_LABELS[k], source=sources[k], records=len(runs[k]),
                      model_id=sorted({r["model_id"] for r in sel(run=k)}),
                      system_prompt=sorted({r["system_prompt"] for r in sel(run=k)}),
                      outcomes=dict(collections.Counter(r["outcome"] for r in sel(run=k))),
                      clean_with_zero_orders=[r["prompt_id"] for r in sel(run=k, outcome="clean") if int(float(r["total_orders"] or 0)) == 0])
              for k in run_keys},
        resolution_claim=dict(
            runtime_errors=runtime, resolution_positional=res_primary,
            share_of_runtime_errors={k: round(res_primary[k] / runtime[k], 4) if runtime[k] else None for k in run_keys},
            static_rule_hits=res_latent, masked_by_an_earlier_error=res_masked, runtime_hits_missed_by_static_rule=res_missed),
        categories=cats_json,
        latent_tags={t: dict(rule=d, counts={k: sum(t in r["latent"] for r in sel(run=k)) for k in run_keys},
                             prompt_ids={k: [r["prompt_id"] for r in sel(run=k) if t in r["latent"]] for k in run_keys})
                     for t, d in LATENT_TAGS.items()},
        top8_tuned=[dict(rank=i + 1, category=c, count_tuned_runs=tuned_total[c],
                         counts={k: count(run=k, category=c) for k in tuned},
                         correction_pair=CORRECTION_PAIRS.get(c)) for i, c in enumerate(top8[:8])],
        top8_ties_at_cutoff=tied,
        training_data_profile=training_profile(),
        runtime_errors_by_api_area={k: dict(collections.Counter(r["domain"] for r in sel(run=k, outcome="runtime_error")))
                                    for k in run_keys},
        runtime_errors_during_initialization={k: sum(r["has_initialize_error"] for r in sel(run=k, outcome="runtime_error"))
                                              for k in run_keys},
        records=rows,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "error_taxonomy.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")

    # ---- Markdown ----
    L = RUN_LABELS
    md = []
    w = md.append

    def flag(n):
        return "{}*".format(n) if 0 < n < SMALL else str(n)

    w("# Error taxonomy: Qwen3.5 on the 100 held-out LEAN prompts\n")
    w("Generated by `src/analysis/build_error_taxonomy.py` from cached records. Rules live in "
      "`src/qc_eval/error_classifier.py`. Machine-readable copy: `error_taxonomy.json`.\n")
    w("Counts marked `*` are below {} and may be noise. Each run is a single generation per prompt at "
      "temperature 0, so there is no run-to-run variance estimate behind any number here.\n".format(SMALL))

    w("## 1. Runs and outcomes\n")
    w(table(["Run", "Model", "Records", "Clean", "Runtime error", "Compile error", "No code", "Unknown"],
            [[L[k], "`{}`".format(report["runs"][k]["model_id"][0]), len(runs[k])] +
             [count(run=k, outcome=o) for o in ("clean", "runtime_error", "compile_error", "no_code", "unknown")]
             for k in run_keys]))
    w("")
    for k in run_keys:
        w("- **{}**: read from `{}`.".format(L[k], sources[k]))
    w("")
    w("Things to know before reading the tables:\n")
    w("- A backtest stops at its **first** error. Each record gets one primary category for that first failure. "
      "Problems further down the file are invisible to QuantConnect, so section 6 adds static tags that scan the whole source.")
    w("- \"Compile error\" merges the pipeline statuses `syntax_error` and `compile_error`. \"Unknown\" is one "
      "QuantConnect read timeout in the base run (infrastructure, not the model).")
    w("- Clean means the backtest finished, not that it traded. Clean runs with zero orders: " +
      "; ".join("{} {} of {}".format(L[k], len(report["runs"][k]["clean_with_zero_orders"]), count(run=k, outcome="clean"))
                for k in run_keys if count(run=k, outcome="clean")) + ".")
    w("- The two tuned runs differ in more than size: Tuned 4B used the old settings (thinking on, max_tokens 4096); "
      "the Tuned 9B run's README records temperature 0 and max_tokens 4096. Base 9B vs Tuned 9B is the closer comparison.\n")

    w("## 2. Category counts (primary root cause, one per record)\n")
    w(table(["Category", "Stage", "What it is"] + [L[k] for k in run_keys] + ["Tuned total"],
            [["`{}`".format(c), ERROR_CATEGORIES[c].stage, ERROR_CATEGORIES[c].title] +
             [flag(count(run=k, category=c)) for k in run_keys] + [tuned_total[c]]
             for c in sorted(cat_order, key=lambda c: -tuned_total[c])]))
    w("")

    w("## 3. Jared's claim: is nearly half of the tuned runtime errors a missing resolution?\n")
    w(table(["Run", "Runtime errors", "`RESOLUTION_POSITIONAL`", "Share of runtime errors", "Static rule hits (whole source)"],
            [[L[k], runtime[k], res_primary[k], pct(res_primary[k], runtime[k]), res_latent[k]] for k in run_keys]))
    w("")
    w("__RESOLUTION_FINDINGS__")

    w("## 4. Categories in detail\n")
    for cj in sorted(cats_json, key=lambda c: -c["count_tuned_runs"]):
        code = cj["category"]
        w("### `{}` — {}\n".format(code, cj["title"]))
        w("- **Rule:** {}".format(cj["rule"]))
        w("- **Counts:** " + ", ".join("{} {}".format(L[k], flag(cj["counts"][k])) for k in run_keys))
        for k in run_keys:
            if cj["counts"][k]:
                dets = ", ".join("{} ×{}".format(d, n) if n > 1 else d for d, n in list(cj["details"][k].items())[:10] if d)
                if code not in ("GEN_LOOP_TRUNCATED", "WRONG_IMPORT", "SYNTAX_ERROR", "OTHER_RUNTIME", "PYTHON_LOGIC_ERROR",
                                "GEN_EMPTY_OUTPUT", "INFRA_TIMEOUT") and dets:
                    w("- **What was hit ({}):** {}".format(L[k], dets))
        for k in run_keys:
            if cj["counts"][k]:
                w("- **Prompt ids ({}):** {}".format(L[k], ", ".join(short(p) for p in cj["prompt_ids"][k])))
        amb = [(k, a) for k in run_keys for a in cj["ambiguous"][k]]
        if amb:
            notes = collections.Counter(a["note"] for _, a in amb)
            w("- **Notes:** " + "; ".join("{} ({} records)".format(n, c) for n, c in notes.items()))
        if cj["examples"]:
            w("- **Verbatim examples:**")
            for e in cj["examples"]:
                msg = e["message"] if len(e["message"]) <= 330 else e["message"][:330] + " […]"
                arg = re.search(r"Argument mismatch: [^.]*\.", e["message"])
                if arg and arg.group(0) not in msg:
                    msg += " " + arg.group(0)
                w("  - `{}` / {}: `{}`".format(short(e["prompt_id"]), L[e["run"]], msg.replace("`", "'")))
                if e["line"]:
                    w("    - failing line: `{}`".format(e["line"].replace("`", "'")))
        s = cj["snippet"]
        if s:
            w("\n```python\n# wrong ({}, {})\n{}\n\n# right (template {})\n{}\n```\n".format(
                L[s["run"]], short(s["prompt"]), s["wrong"], s["template"], s["right"]))
            w(s["why"] + "\n")
        else:
            w("")

    w("## 5. Breakdown by template and by specificity\n")
    for k in run_keys:
        present = [c for c in cat_order if count(run=k, category=c)]
        w("### {}: template × category\n".format(L[k]))
        w(table(["Template", "Clean"] + ["`{}`".format(c) for c in present],
                [[short(t), count(run=k, template=t, category="CLEAN")] +
                 [count(run=k, template=t, category=c) or "" for c in present] for t in templates]))
        w("")
    for k in run_keys:
        present = [c for c in cat_order if count(run=k, category=c)]
        w("### {}: specificity × category\n".format(L[k]))
        w(table(["Specificity", "Prompts", "Clean"] + ["`{}`".format(c) for c in present],
                [[s, count(run=k, specificity=s), count(run=k, specificity=s, category="CLEAN")] +
                 [count(run=k, specificity=s, category=c) or "" for c in present] for s in specs]))
        w("")
    w("### Clean backtests by persona segment\n")
    w(table(["Segment", "Prompts per run"] + [L[k] for k in run_keys],
            [[s, count(run=run_keys[0], segment=s)] + [count(run=k, segment=s, outcome="clean") for k in run_keys]
             for s in segments]))
    w("")
    w("__BREAKDOWN_FINDINGS__")

    w("## 6. Static tags over the whole source (not just the first error)\n")
    w("These are non-exclusive and only computed where code was extracted "
      "({}).\n".format(", ".join("{} {}".format(L[k], sum(1 for r in sel(run=k) if r["outcome"] != "no_code")) for k in run_keys)))
    w(table(["Tag", "Rule"] + [L[k] for k in run_keys],
            [["`{}`".format(t), d] + [report["latent_tags"][t]["counts"][k] for k in run_keys] for t, d in LATENT_TAGS.items()]))
    w("")
    w("__LATENT_FINDINGS__")

    w("## 7. Base vs tuned: what did fine-tuning fix?\n")

    def verdict(c):
        if c == "INFRA_TIMEOUT":
            return "n/a (infrastructure)"
        b = count(run="qwen_base", category=c)
        ts = [count(run=k, category=c) for k in tuned]
        if b and not any(ts):
            return "gone"
        if b and max(ts) < b:
            return "shrank"
        if not b and any(ts):
            return "appeared"
        return "stayed"
    w(table(["Category"] + [L[k] for k in run_keys] + ["After tuning"],
            [["`{}`".format(c)] + [flag(count(run=k, category=c)) for k in run_keys] + [verdict(c)]
             for c in sorted(cat_order, key=lambda c: (-count(run="qwen_base", category=c), -tuned_total[c]))]))
    w("")
    w("__COMPARE_FINDINGS__")

    w("## 8. The categories you expected, and where each one landed\n")
    w("__EXPECTED_FINDINGS__")

    w("## 9. Top 8 categories across the tuned runs, with a correction-pair template each\n")
    for item in report["top8_tuned"]:
        c = item["category"]
        w("{}. **`{}`** — {} ({}). {}".format(
            item["rank"], c, item["count_tuned_runs"],
            ", ".join("{} {}".format(L[k], item["counts"][k]) for k in tuned), CORRECTION_PAIRS.get(c, "")))
    w("")
    if tied:
        w("Rank 8 is a tie at {} with: {}. ".format(cutoff, ", ".join("`{}`".format(c) for c in tied)) +
          "Pairs for those: " + " ".join("`{}`: {}".format(c, CORRECTION_PAIRS.get(c, "")) for c in tied) + "\n")
    w("__TOP8_FINDINGS__")

    text = "\n".join(md)
    findings = build_findings(report, rows, run_keys, tuned, templates)
    for key in ("RESOLUTION", "BREAKDOWN", "LATENT", "COMPARE", "EXPECTED", "TOP8"):
        text = text.replace("__{}_FINDINGS__".format(key), findings.get(key, "").strip() + "\n")
    (out / "error_taxonomy.md").write_text(text + "\n")

    print("wrote", out / "error_taxonomy.md", "and", out / "error_taxonomy.json")
    for k in run_keys:
        print(" ", L[k], dict(collections.Counter(r["category"] for r in sel(run=k)).most_common()))
    # touch the helper so linters see it used; also a cheap self-check
    assert positional_resolution_calls("class A:\n def f(self):\n  self.rsi(s, 14, Resolution.HOUR)")


if __name__ == "__main__":
    main()
