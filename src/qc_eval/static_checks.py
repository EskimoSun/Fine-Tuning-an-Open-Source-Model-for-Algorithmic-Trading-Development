"""
Static checks: everything we can verify about generated LEAN code
WITHOUT QuantConnect access. Pure Python, no network.

Entry point: run_static_checks(code, prompt_spec) -> list[Finding]
"""

from __future__ import annotations

import ast
import re

from .taxonomy import Finding

# A starter list of current (snake_case) LEAN Python methods on QCAlgorithm.
# It is NOT complete. Anything outside it is only flagged as a warning.
# Grow this list from the LEAN docs as false positives show up.
KNOWN_API = {
    # setup
    "set_start_date", "set_end_date", "set_cash", "set_benchmark",
    "set_warm_up", "set_brokerage_model", "set_time_zone", "set_security_initializer",
    "set_universe_selection", "set_alpha", "set_portfolio_construction",
    "set_execution", "set_risk_management", "settings", "universe_settings",
    # adding data
    "add_equity", "add_forex", "add_crypto", "add_future", "add_option",
    "add_index", "add_index_option", "add_future_option", "add_cfd", "add_data",
    "add_universe", "add_universe_selection", "add_security",
    # indicators
    "sma", "ema", "rsi", "macd", "bb", "atr", "adx", "roc", "momp", "mom",
    "std", "max", "min", "aroon", "cci", "stoch", "vwap", "obv", "lwma",
    "kama", "dch", "kch", "willr", "register_indicator", "warm_up_indicator",
    "indicator_history",
    # orders
    "market_order", "limit_order", "stop_market_order", "stop_limit_order",
    "market_on_open_order", "market_on_close_order", "set_holdings",
    "liquidate", "order", "combo_market_order", "combo_limit_order",
    "transactions", "calculate_order_quantity", "buy", "sell",
    "set_filter", "plot_indicator", "option_chain", "future_chain",
    # data access / state
    "history", "securities", "portfolio", "time", "utc_time", "is_warming_up",
    "symbol", "current_slice", "object_store", "live_mode",
    # scheduling / logging / charting
    "schedule", "date_rules", "time_rules", "train",
    "log", "debug", "error", "quit", "plot", "plot_indicator",
    "set_runtime_statistic", "notify",
    # consolidators
    "consolidate", "subscription_manager",
    # options / futures helpers
    "option_chain", "future_chain", "option_chain_provider", "future_chain_provider",
}

# Old PascalCase methods that the snake_case API replaced.
LEGACY_PATTERN = re.compile(r"self\.([A-Z][A-Za-z]+)\s*\(")

TRADE_METHODS = {
    "market_order", "limit_order", "stop_market_order", "stop_limit_order",
    "set_holdings", "liquidate", "order", "market_on_open_order",
    "market_on_close_order", "combo_market_order", "combo_limit_order",
}
INDICATOR_METHODS = {
    "sma", "ema", "rsi", "macd", "bb", "atr", "adx", "roc", "mom", "momp",
    "std", "aroon", "cci", "stoch", "vwap", "obv", "lwma", "kama", "dch",
    "kch", "willr",
}


def extract_code(model_output: str) -> str | None:
    """Pull the Python code out of a model response.
    Prefers a ```python fenced block; falls back to the raw text if it
    looks like code."""
    fence = re.search(r"```(?:python|py)?\s*\n(.*?)```", model_output, re.DOTALL)
    if fence:
        return fence.group(1)
    if "class " in model_output and "QCAlgorithm" in model_output:
        return model_output
    return None


def _self_method_calls(tree: ast.AST) -> set[str]:
    """Names of every self.<name>(...) call in the code."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if isinstance(target, ast.Name) and target.id == "self":
                names.add(node.func.attr)
    return names


def _algorithm_classes(tree: ast.AST) -> list[ast.ClassDef]:
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [ast.dump(b) for b in node.bases]
            if any("QCAlgorithm" in b for b in bases):
                classes.append(node)
    return classes


def run_static_checks(code: str, prompt_spec: dict | None = None) -> list[Finding]:
    """Run every static check. prompt_spec is one entry from prompts.jsonl
    (used for the prompt-adherence checks); pass None to skip those."""
    findings: list[Finding] = []

    # 1. Does it parse?
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [Finding("SYNTAX_ERROR", f"line {e.lineno}: {e.msg}")]

    # 2. Is there an algorithm class with initialize()?
    algo_classes = _algorithm_classes(tree)
    if not algo_classes:
        findings.append(Finding("NO_ALGORITHM_CLASS"))
    else:
        methods = {
            n.name for c in algo_classes for n in c.body
            if isinstance(n, ast.FunctionDef)
        }
        if "initialize" not in methods and "Initialize" not in methods:
            findings.append(Finding("NO_INITIALIZE"))

    # 3. Legacy PascalCase API
    legacy = sorted(set(LEGACY_PATTERN.findall(code)))
    if legacy:
        findings.append(Finding("LEGACY_API", ", ".join(legacy[:10])))

    # 4. Unknown self.<method> calls (possible hallucinations)
    defined_here = {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
    }
    calls = _self_method_calls(tree)
    unknown = sorted(
        c for c in calls
        if c not in KNOWN_API and c not in defined_here and not c[0].isupper()
    )
    if unknown:
        findings.append(Finding("UNKNOWN_API", ", ".join(unknown)))

    # 5. Indicators created but never checked for readiness
    uses_indicators = bool(calls & INDICATOR_METHODS)
    warms_up = "set_warm_up" in calls or "warm_up_indicator" in calls
    checks_ready = any(k in code for k in ("is_ready", "IsReady", "is_warming_up", "automatic_indicator_warm_up"))
    if uses_indicators and not (checks_ready or warms_up):
        findings.append(Finding("MISSING_READY_CHECK"))

    # 6. Lookahead heuristics
    if re.search(r"\.shift\(\s*-\s*\d+", code):
        findings.append(Finding("LOOKAHEAD_SUSPECT", "pandas .shift(-n) reads future rows"))

    # 7. Prompt adherence
    if prompt_spec:
        # treat legacy PascalCase calls (SetHoldings) as their snake_case form
        normalized = {re.sub(r"(?<!^)(?=[A-Z])", "_", c).lower() for c in calls}
        if prompt_spec.get("expects_orders", True) and not (normalized & TRADE_METHODS):
            findings.append(Finding("NO_ORDERS"))
        lowered = code.lower()
        for req in prompt_spec.get("must_contain", []):
            # each requirement is a list of acceptable alternatives
            options = req if isinstance(req, list) else [req]
            if not any(opt.lower() in lowered for opt in options):
                findings.append(Finding("PROMPT_MISS", " / ".join(options)))

    return findings
