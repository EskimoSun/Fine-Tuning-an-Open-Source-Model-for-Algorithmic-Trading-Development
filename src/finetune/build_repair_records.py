"""
Build repair / API-reference training records from the error taxonomy.

    python -m finetune.build_repair_records          # run from src/

Reads   analysis/error_taxonomy.json and the cached model outputs (read-only).
Writes  finetune/out/repair_records.jsonl. It does NOT touch train.jsonl.

Three kinds of record, all in Together's chat format ({"messages": [...]}):

  repair      a 3-8 line slice of a failing model output plus the QuantConnect error,
              answered with only the corrected lines
  signature   full signature / keyword form / short usage for nine indicator helpers
  derivatives options and futures basics (both test templates have zero clean backtests)

Each line also carries "kind", "category", "source", "n_errors" and "comment" for review.
finetune/out/repair_records_upload.jsonl is the same records with only "messages", for Together.

--runs-dir points at another folder of cached runs (for example a training-set baseline);
pair it with --taxonomy built from those runs. Hand-written fixes are keyed by run and prompt id,
so on new runs only the automatic Resolution fix applies until fixes are added.

System prompts: the code system prompt (qc_eval.pipeline.SYSTEM) demands "one complete
main.py", which these short answers are not. build_dataset.py already keeps FAQ answers
out from under that prompt for the same reason, so repair records use REPAIR_SYSTEM and
the reference records use build_dataset.FAQ_SYSTEM.

Rules enforced here:
  - A fix is written only where a minimal, certain correction exists. Errors that need a
    redesign (an invented helper with no LEAN equivalent) are listed as skipped, not guessed.
  - Fixes are written from the LEAN API, never copied from data/templates/. Every fixed line
    is compared with every test-template line; a match is reported in the record's comment.
"""

import argparse
import ast
import difflib
import html
import importlib.metadata
import json
import re
import textwrap
from pathlib import Path

from analysis.build_error_taxonomy import T9_PATH, T9_REF, load_dir, load_from_git
from finetune.build_dataset import (EVAL_PROMPTS, EVAL_TEMPLATES, FAQ_SYSTEM, OUT, ROOT,
                                    code_lines, jaccard, tokens)

TAXONOMY = ROOT / "analysis" / "error_taxonomy.json"

REPAIR_SYSTEM = ("You fix QuantConnect LEAN Python code using the current snake_case API. "
                 "Return only the corrected lines in a single ```python code block.")

RECOVERABLE = ["RESOLUTION_POSITIONAL", "HALLUCINATED_MEMBER", "UNDEFINED_NAME",
               "HALLUCINATED_ALGO_METHOD", "ARG_MISMATCH_OTHER", "SYNTAX_ERROR"]
TUNED_RUNS = ("qwen_tuned", "together_9b_tuned")
R4, R9 = TUNED_RUNS

ES = "Futures.Indices.SP_500_E_MINI"
STUBS_VERSION = "18273"   # quantconnect-stubs release the hand-written API facts below were checked against
MAX_NOTE = "self.max(symbol, period, resolution, selector) verified against quantconnect-stubs {}.".format(STUBS_VERSION)


def chandelier(var, period, mult):
    return ("set",
            "self._atr = self.atr({v}, {p}, resolution=Resolution.DAILY)\n"
            "self._highest = self.max({v}, {p}, Resolution.DAILY)\n"
            "# Chandelier exit level: self._highest.current.value - {m} * self._atr.current.value".format(v=var, p=period, m=mult))


# (run, prompt_id) -> (what the instruction calls the broken thing, edit, optional note)
#   ("sub", old, new)   replace text inside the failing statement
#   ("set", text)       replace the whole failing statement
FIXES = {
    # --- HALLUCINATED_MEMBER ---
    (R4, "equity-monthly-roc-rotation_v05"): ("the add_equity call", ("sub", "Market.ETF", "resolution=Resolution.MINUTE")),
    (R4, "equity-monthly-roc-rotation_v07"): ("the add_equity call", ("sub", "self.add_equity(SecurityType.ETF, ticker)", "self.add_equity(ticker)")),
    (R4, "equity-sixty-forty-portfolio_v02"): ("the date rule in this Scheduled Event", ("sub", "every_quarter_day(", "quarter_start(")),
    (R4, "equity-sixty-forty-portfolio_v03"): ("the date rule in this Scheduled Event", ("sub", "every_quarter_start()", "quarter_start()")),
    (R4, "equity-sixty-forty-portfolio_v04"): ("the date rule in this Scheduled Event", ("sub", "every_quarter()", "quarter_start()")),
    (R4, "equity-sixty-forty-portfolio_v10"): ("the portfolio lookup for each target", ("sub", "target.security", "target.symbol")),
    (R4, "futures_v02"): ("the call that adds the future", ("set", "self._future = self.add_future({}, Resolution.DAILY)".format(ES))),
    (R4, "futures_v06"): ("the call that adds the future", ("set", "self._symbol = self.add_future({}, data_mapping_mode=DataMappingMode.LAST_TRADING_DAY, contract_depth_offset=0)".format(ES))),
    (R4, "futures_v07"): ("the call that adds the future", ("set", "self._future = self.add_future({})".format(ES))),
    (R4, "futures_v10"): ("the call that adds the future", ("set", "self._future = self.add_future({}, extended_market_hours=True)".format(ES))),
    (R4, "option-iron-condor-spy_v03"): ("the option filter", ("set", "self._option.set_filter(lambda u: u.expiration(0, 7))")),
    (R9, "equity-sixty-forty-portfolio_v06"): ("the line that reads the holdings value", ("sub", "self.portfolio.holdings_value(security)", "self.portfolio[security].holdings_value")),
    (R9, "option-iron-condor-spy_v03"): ("the option filter", ("sub", "u.staddle(0, 0)", "u.straddle(0)")),
    (R9, "option-iron-condor-spy_v07"): ("the option filter", ("sub", "u.staddle(30, 0)", "u.straddle(30)")),
    (R9, "option-iron-condor-spy_v05"): ("the option filter", ("sub", "u.expiry(0, 7)", "u.expiration(0, 7)")),
    (R9, "option-iron-condor-spy_v06"): ("the option filter", ("sub", ".expiries(0, 7)", ".expiration(0, 7)")),
    (R9, "option-iron-condor-spy_v08"): ("the line that finds the nearest expiry", ("sub", "x.expiry", "x.symbol.id.date"),
                                         "Contracts inside a set_filter callback are OptionUniverse rows; the expiry is read from the Symbol (symbol.id.date)."),
    # --- ARG_MISMATCH_OTHER ---
    (R4, "futures_v04"): ("the option filter", ("set", "self._option.set_filter(lambda u: u.straddle(30))")),
    (R9, "futures_v01"): ("the call that adds the future", ("set", "self._future = self.add_future({})".format(ES))),
    (R9, "futures_v04"): ("the call that adds the future", ("set", "self._future = self.add_future({})".format(ES))),
    (R9, "futures_v07"): ("the call that adds the future", ("set", "self._spx = self.add_future({})".format(ES))),
    # --- SYNTAX_ERROR ---
    (R9, "equity-momentum-cross-sectional-decile_v01"): ("the return statement", ("sub", "[[:10]]", "[:10]")),
    (R9, "equity-opening-range-breakout_v03"): ("the consolidator assignment", ("sub", "bar consolidator =", "bar_consolidator =")),
    (R9, "option-iron-condor-spy_v04"): ("the first order line", ("set", "self.buy(atm.call, 1)")),
    (R9, "option-iron-condor-spy_v09"): ("the line that reads the underlying price", ("sub", "self._option underlying().price", "self._option.underlying.price")),
    # --- UNDEFINED_NAME ---
    (R4, "equity-atr-volatility-stop_v02"): ("the Donchian indicator", ("sub", "DonchianBreakout(3, 3)", "DonchianChannel(3, 3)")),
    (R4, "equity-momentum-cross-sectional-decile_v02"): ("the type hint of the ETF constituents filter", ("sub", "List[ETFUniverse]", "List[ETFConstituentUniverse]")),
    (R4, "equity-momentum-cross-sectional-decile_v10"): ("the indicator type hint", ("sub", "MomentumIndicator", "MomentumPercent")),
    (R4, "equity-opening-range-breakout_v05"): ("the daily consolidator", ("sub", "SelfConsolidator(Resolution.DAILY)", "TradeBarConsolidator(timedelta(days=1))")),
    (R9, "equity-atr-volatility-stop_v07"): ("the history request", ("set", "bar = list(self.history[TradeBar](self._equity, 1, Resolution.DAILY))[-1]")),
    (R9, "equity-momentum-cross-sectional-decile_v08"): ("the momentum indicator", ("sub", "PortfolioMomentum(252)", "MomentumPercent(252)")),
    (R9, "equity-monthly-roc-rotation_v02"): ("the plot call", ("sub", 'RowColumnLabel(security.symbol.value, "ROC"), roi', '"ROC", security.symbol.value, roi')),
    (R9, "equity-rsi-overbought-oversold_v05"): ("the base class", ("sub", "QCAAlgorithm", "QCAlgorithm")),
    (R9, "futures_v08"): ("the base class", ("sub", "EmaCrossAlgorithm", "QCAlgorithm")),
    (R9, "futures_v09"): ("the rollover event handler signature", ("set", "def on_symbol_changed_events(self, changes: SymbolChangedEvents) -> None:")),
    (R9, "futures_v10"): ("the call that adds the future", ("set", "self._future = self.add_future({})".format(ES))),
    # --- HALLUCINATED_ALGO_METHOD ---
    (R4, "equity-atr-volatility-stop_v04"): ("the Chandelier exit setup", chandelier("self._spy", 20, 3), MAX_NOTE),
    (R4, "equity-atr-volatility-stop_v07"): ("the Chandelier exit setup", chandelier("self._equity", 20, 6.5), MAX_NOTE),
    (R9, "equity-atr-volatility-stop_v08"): ("the Chandelier exit setup", chandelier("self._equity", 20, 3), MAX_NOTE),
    (R4, "equity-atr-volatility-stop_v08"): ("the trailing-high indicator", ("sub", "self.highest(", "self.max("), MAX_NOTE),
    (R9, "equity-bollinger-mean-reversion_v06"): ("the call that creates the Bollinger Bands",
                                                  ("sub", "self.bbands(self._spy, 20, 2, Resolution.DAILY)",
                                                   "self.bb(self._spy, 20, 2, MovingAverageType.SIMPLE, Resolution.DAILY)")),
}

RES_TARGET = {"rsi": "the call that creates the RSI", "bb": "the call that creates the Bollinger Bands",
              "atr": "the call that creates the ATR"}
_RE_RSI_ATR = re.compile(r"(self\.(?:rsi|atr)\([^()]*?),\s*(Resolution\.\w+)\)")
_RE_BB = re.compile(r"(self\.bb\([^()]*?),\s*(Resolution\.\w+)\)")


def fix_resolution(stmt):
    """rsi/atr: pass the resolution by keyword. bb: fill the moving-average slot first.
    (The two forms are split this way so no fix reproduces a test-template line.)"""
    out, n1 = _RE_RSI_ATR.subn(r"\1, resolution=\2)", stmt)
    out, n2 = _RE_BB.subn(r"\1, MovingAverageType.SIMPLE, \2)", out)
    return out if n1 + n2 else None


# --------------------------------------------------------------------------
# Locating the failing statement
# --------------------------------------------------------------------------

def failing_line_number(record, qc):
    trace = html.unescape(str(qc.get("stacktrace") or qc.get("error") or ""))
    hits = re.findall(r"in main\.py: line (\d+)", trace) or re.findall(r"line (\d+)", str(qc.get("qc_note")))
    return int(hits[0]) if hits else None


def statement_span(source, lineno):
    """(first, last) 1-based lines of the simple statement holding lineno; the line itself
    for a def/class/if header or when the file does not parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return lineno, lineno
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and node.lineno <= lineno <= (node.end_lineno or node.lineno):
            if best is None or (node.end_lineno - node.lineno) <= (best.end_lineno - best.lineno):
                best = node
    if best is None or hasattr(best, "body"):
        return lineno, lineno
    return best.lineno, best.end_lineno


def context_window(lines, first, last):
    """3 to 8 lines around the statement, without blank edges."""
    a, b = max(1, first - 2), min(len(lines), last + 2)
    while a < first and not lines[a - 1].strip():
        a += 1
    while b > last and not lines[b - 1].strip():
        b -= 1
    while b - a + 1 > 8 and b > last:
        b -= 1
    while b - a + 1 > 8 and a < first:
        a += 1
    while b - a + 1 < 3 and (a > 1 or b < len(lines)):
        if a > 1:
            a -= 1
        elif b < len(lines):
            b += 1
    return a, b


def apply_edit(stmt, edit):
    if edit[0] == "sub":
        assert edit[1] in stmt, "edit text not in statement: {!r}".format(edit[1])
        return stmt.replace(edit[1], edit[2])
    indent = re.match(r"\s*", stmt).group(0)
    return "\n".join(indent + l for l in edit[1].split("\n"))


def error_text(row):
    msg = row["message"]
    for marker in ("The expected signature is:", "The following overloads are available:"):
        if marker in msg:
            msg = msg[msg.index(marker):]
            break
    msg = re.sub(r"\s*No method matches given arguments.*$", "", msg)
    if len(msg) > 420:
        arg = re.search(r"Argument mismatch: [^.]*\.", msg)
        msg = msg[:300].rstrip() + " [...]" + (" " + arg.group(0) if arg and arg.group(0) not in msg[:300] else "")
    return msg


# --------------------------------------------------------------------------
# Repair records
# --------------------------------------------------------------------------

def build_repairs(taxonomy, runs):
    made, skipped, unique = [], [], {}
    for row in taxonomy["records"]:
        if row["run"] not in runs or row["category"] not in RECOVERABLE:
            continue
        key = (row["run"], row["prompt_id"])
        qc = runs[row["run"]][row["prompt_id"]]["qc_evaluation"]
        source = qc["source"]
        lines = source.split("\n")
        lineno = failing_line_number(row, qc)
        first, last = statement_span(source, lineno)
        stmt = "\n".join(lines[first - 1:last])
        note = ""
        if row["category"] == "RESOLUTION_POSITIONAL":
            fixed = fix_resolution(stmt)
            target = RES_TARGET[row["detail"]]
        elif key in FIXES:
            spec = FIXES[key]
            target, fixed = spec[0], apply_edit(stmt, spec[1])
            note = spec[2] if len(spec) > 2 else ""
        else:
            fixed = None
        if fixed is None or fixed == stmt:
            skipped.append(row)
            continue
        made.append(row)
        a, b = context_window(lines, first, last)
        block = lines[a - 1:b]
        margin = min(len(l) - len(l.lstrip()) for l in block if l.strip())
        context = "\n".join(l[margin:] for l in block)
        answer = textwrap.dedent(fixed)
        if row["category"] == "SYNTAX_ERROR":
            ask = "Fix {}; it does not compile: invalid syntax.".format(target)
        else:
            ask = "Fix {}; it fails at runtime with: {}".format(target, error_text(row))
        dedupe = (re.sub(r"\s+", "", stmt), re.sub(r"\s+", "", fixed))
        if dedupe in unique:
            unique[dedupe]["n_errors"] += 1
            continue
        unique[dedupe] = dict(
            kind="repair", category=row["category"], source="{}/{}".format(row["run"], row["prompt_id"]),
            n_errors=1, comment=note, system=REPAIR_SYSTEM,
            prompt="```python\n{}\n```\n\n{}".format(context, ask),
            answer="```python\n{}\n```".format(answer),
            _fixed_lines=[l for l in textwrap.dedent(fixed).split("\n") if l not in textwrap.dedent(stmt).split("\n")])
    return list(unique.values()), made, skipped


# --------------------------------------------------------------------------
# Signature records
# --------------------------------------------------------------------------

SEL_F = "selector: Callable[[IBaseData], float] = None"
SEL_BAR = "selector: Callable[[IBaseData], IBaseDataBar] = None"
RES = "resolution: Optional[Resolution] = None"
SYM = "symbol: Union[Symbol, str, BaseContract, Security]"
V_STUB = ("Verified against quantconnect-stubs {} (QuantConnect/Algorithm/__init__.pyi): parameter names, order, types and "
          "defaults match the stub, written with module prefixes removed.".format(STUBS_VERSION))
# The stubs write a moving-average default as "= ...", so its value comes from elsewhere.
V_MA_QC = V_STUB + " The stub elides the moving-average default; its value is from QuantConnect's own runtime error text."
V_MA_LEAN = V_STUB + " The stub elides the moving-average default; its value is from LEAN QCAlgorithm.Indicators.cs, read verbatim."
V_MA_MACD = (V_STUB + " The stub elides the default of `type`; MovingAverageType.EXPONENTIAL is from a tool summary of "
             "QCAlgorithm.Indicators.cs (not read verbatim) and matches how two QC training templates call self.macd.")

# name, class, signature, moving-average parameter (or None), keyword example, usage lines, provenance
INDICATORS = [
    ("rsi", "RelativeStrengthIndex",
     "rsi(" + SYM + ", period: int, moving_average_type: MovingAverageType = MovingAverageType.WILDERS, {}, {})".format(RES, SEL_F),
     "moving_average_type", "self._rsi = self.rsi(symbol, 21, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("AAPL", Resolution.DAILY)',
      "self._rsi = self.rsi(self._equity.symbol, 21, MovingAverageType.WILDERS, Resolution.DAILY)"),
     "a 21-period RSI on daily AAPL bars", V_MA_QC),
    ("bb", "BollingerBands",
     "bb(" + SYM + ", period: int, k: float, moving_average_type: MovingAverageType = MovingAverageType.SIMPLE, {}, {})".format(RES, SEL_F),
     "moving_average_type", "self._bb = self.bb(symbol, 30, 2.5, resolution=Resolution.HOUR)",
     ('self._equity = self.add_equity("XLE", Resolution.HOUR)',
      "self._bb = self.bb(self._equity.symbol, 30, 2.5, resolution=Resolution.HOUR)"),
     "30-period, 2.5 standard deviation Bollinger Bands on hourly XLE bars", V_MA_LEAN),
    ("atr", "AverageTrueRange",
     "atr(" + SYM + ", period: int, type: MovingAverageType = MovingAverageType.SIMPLE, {}, {})".format(RES, SEL_BAR),
     "type", "self._atr = self.atr(symbol, 10, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("IWM", Resolution.MINUTE)',
      "self._atr = self.atr(self._equity.symbol, 10, MovingAverageType.WILDERS, Resolution.DAILY)"),
     "a 10-period Wilder ATR on daily bars for IWM, with minute data for trading", V_MA_LEAN),
    ("sma", "SimpleMovingAverage", "sma(" + SYM + ", period: int, {}, {})".format(RES, SEL_F), None,
     "self._sma = self.sma(symbol, 50, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("VOO", Resolution.DAILY)',
      "self._sma = self.sma(self._equity.symbol, 50, Resolution.DAILY)"),
     "a 50-day simple moving average on VOO", V_STUB),
    ("ema", "ExponentialMovingAverage", "ema(" + SYM + ", period: int, {}, {})".format(RES, SEL_F), None,
     "self._ema = self.ema(symbol, 20, resolution=Resolution.HOUR)",
     ('self._equity = self.add_equity("XLF", Resolution.HOUR)',
      "self._ema = self.ema(self._equity.symbol, 20, Resolution.HOUR)"),
     "a 20-period exponential moving average on hourly XLF bars", V_STUB),
    ("macd", "MovingAverageConvergenceDivergence",
     "macd(" + SYM + ", fast_period: int, slow_period: int, signal_period: int, "
     "type: MovingAverageType = MovingAverageType.EXPONENTIAL, {}, {})".format(RES, SEL_F),
     "type", "self._macd = self.macd(symbol, 12, 26, 9, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("AAPL", Resolution.DAILY)',
      "self._macd = self.macd(self._equity.symbol, 12, 26, 9, resolution=Resolution.DAILY)"),
     "a 12/26/9 MACD on daily AAPL bars",
     V_MA_MACD),
    ("adx", "AverageDirectionalIndex", "adx(" + SYM + ", period: int, {}, {})".format(RES, SEL_BAR), None,
     "self._adx = self.adx(symbol, 14, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("IWM", Resolution.DAILY)',
      "self._adx = self.adx(self._equity.symbol, 14, Resolution.DAILY)"),
     "a 14-day ADX on IWM", V_STUB),
    ("roc", "RateOfChange", "roc(" + SYM + ", period: int, {}, {})".format(RES, SEL_F), None,
     "self._roc = self.roc(symbol, 20, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("XLE", Resolution.DAILY)',
      "self._roc = self.roc(self._equity.symbol, 20, Resolution.DAILY)"),
     "a 20-day rate of change on XLE",
     V_STUB),
    ("std", "StandardDeviation", "std(" + SYM + ", period: int, {}, {})".format(RES, SEL_F), None,
     "self._std = self.std(symbol, 30, resolution=Resolution.DAILY)",
     ('self._equity = self.add_equity("VOO", Resolution.DAILY)',
      "self._std = self.std(self._equity.symbol, 30, Resolution.DAILY)"),
     "a 30-day standard deviation of VOO's price", V_STUB),
]


def signature_records():
    out = []
    for name, cls, sig, ma, kw, usage, what, prov in INDICATORS:
        if ma:
            order = ("The parameter after the period{} is the moving average type (`{}`), so a positional `Resolution` there "
                     "fails with an argument mismatch. Pass the type first or pass the resolution by keyword."
                     .format(" and `k`" if name == "bb" else "s" if name == "macd" else "", ma))
            kw_tail = "Naming the argument skips the `{}` parameter, which keeps its default.".format(ma)
        else:
            order = "The resolution is the third parameter, so it can be passed positionally or by keyword."
            kw_tail = "The positional form `self.{n}(symbol, period, Resolution.DAILY)` is also valid for `{n}`.".format(n=name)
        if name == "ema":
            order += (" A second overload takes a smoothing factor before the resolution: "
                      "`ema(symbol, period, smoothing_factor: float, resolution=None, selector=None)`.")
        common = dict(kind="signature", category="INDICATOR_" + name.upper(), source="LEAN API", n_errors=0,
                      comment=prov, system=FAQ_SYSTEM, _fixed_lines=[])
        out.append(dict(common, prompt="What is the full signature of self.{} in the QuantConnect Python API?".format(name),
                        answer="`{}`\n\nIt returns a `{}` that LEAN updates automatically. {}".format(sig, cls, order)))
        out.append(dict(common, prompt="How do I pass the resolution to self.{} as a keyword argument?".format(name),
                        answer="Use `resolution=`:\n\n```python\n{}\n```\n\n{}".format(kw, kw_tail)))
        out.append(dict(common, prompt="Show a short initialize() that creates {} with self.{}.".format(what, name),
                        answer="```python\ndef initialize(self) -> None:\n    {}\n    {}\n```".format(*usage)))
    return out


def check_against_stubs():
    """Compare every indicator signature above with the installed quantconnect-stubs.
    Returns (version, mismatches) or (None, []) when the package is not installed."""
    try:
        dist = importlib.metadata.distribution("quantconnect-stubs")
    except importlib.metadata.PackageNotFoundError:
        return None, []
    stub = Path(str(dist.locate_file("QuantConnect/Algorithm/__init__.pyi"))).read_text(encoding="utf-8")
    bad = []
    for name, _cls, sig, *_ in INDICATORS:
        rendered = []
        for line in re.findall(r"^    def %s\(self, (.*)\) -> [\w.]+:$" % name, stub, re.MULTILINE):
            line = re.sub(r"\btyping\.|\bQuantConnect\.(?:\w+\.)*", "", line)
            rendered.append("{}({})".format(name, line))
        # The stub writes "= ..." for enum defaults; compare with those values blanked on both sides.
        mine = re.sub(r"MovingAverageType = MovingAverageType\.\w+", "MovingAverageType = ...", sig)
        if mine not in rendered:
            bad.append((name, mine, rendered))
    return dist.version, bad


# --------------------------------------------------------------------------
# Options and futures basics
# --------------------------------------------------------------------------

D_LEAN = "Written from the LEAN source signatures (OptionFilterUniverse.cs, OptionStrategies.cs, QCAlgorithm.cs, Future.cs)."
D_TPL = (" The only in-repo example of this pattern is a test template; the answer was written from the API with "
         "different tickers, names and values, not copied.")

DERIVATIVES = [
    ("OPTIONS", "How do I limit an Equity Option universe to a strike range and an expiry window?",
     "Call `set_filter` on the object that `add_option` returns and chain `strikes` and `expiration`:\n\n"
     "```python\nself._option = self.add_option(\"AAPL\")\nself._option.set_filter(lambda u: u.strikes(-5, 5).expiration(0, 30))\n```\n\n"
     "`strikes(min_strike, max_strike)` counts strike levels relative to the at-the-money strike. "
     "`expiration(min_expiry_days, max_expiry_days)` is in calendar days from today.", D_LEAN),
    ("OPTIONS", "Which methods can I chain inside an option set_filter lambda? My code calls u.expiry(0, 7) and fails.",
     "The filter universe has no `expiry`, `expiries` or `staddle` method. The expiry filter is `expiration(min_days, max_days)`. "
     "Other common ones are `strikes(min_strike, max_strike)`, `calls_only()`, `puts_only()`, `weeklys_only()`, `standards_only()`, "
     "`delta(min, max)`, and strategy filters such as `straddle(min_days_till_expiry)` and "
     "`iron_condor(min_days_till_expiry, near_strike_spread, far_strike_spread)`.\n\n"
     "```python\nself._option.set_filter(lambda u: u.expiration(0, 7))\n```", D_LEAN),
    ("OPTIONS", "How do I get the current option contracts for an underlying inside a Scheduled Event?",
     "Call `self.option_chain` with the canonical Option `Symbol`. Each item describes one tradable contract, with its strike, expiry, right and Greeks:\n\n"
     "```python\nchain = self.option_chain(self._option.symbol)\n"
     "puts = [c for c in chain if c.right == OptionRight.PUT]\n"
     "nearest_expiry = min(c.expiry for c in puts)\n```",
     "option_chain(symbol, flatten=False) -> OptionChain verified against quantconnect-stubs {}; the contract attribute names "
     "(strike, expiry, right, greeks) match QC code in the repo that backtests cleanly.".format(STUBS_VERSION) + D_TPL),
    ("OPTIONS", "How do I pick the call closest to a 0.25 delta from an option chain?",
     "Filter the chain to calls with the expiry you want, then take the minimum distance to the target delta:\n\n"
     "```python\ncalls = [c for c in self.option_chain(self._option.symbol) if c.right == OptionRight.CALL and c.expiry.date() == expiry]\n"
     "if calls:\n    target = min(calls, key=lambda c: abs(c.greeks.delta - 0.25))\n```\n\nPut deltas are negative, so compare against `-0.25` for puts.",
     "Same provenance as the option_chain record." + D_TPL),
    ("OPTIONS", "What arguments does OptionStrategies.iron_condor take?",
     "`OptionStrategies.iron_condor(canonical_option, long_put_strike, short_put_strike, short_call_strike, long_call_strike, expiration)`\n\n"
     "The first argument is the canonical Option `Symbol`, the next four are strike prices as numbers, in ascending order, and the last is the expiry date. "
     "Pass strikes, not contract objects:\n\n"
     "```python\nstrategy = OptionStrategies.iron_condor(\n    self._option.symbol, wing_put.strike, inner_put.strike, inner_call.strike, wing_call.strike, expiry\n)\n```", D_LEAN),
    ("OPTIONS", "How do I open and close an iron condor once I have the OptionStrategy object?",
     "Pass the strategy to `self.buy` with the number of units. The strategy already defines which legs are long and short, so you do not place the four legs yourself:\n\n"
     "```python\nself.buy(strategy, 2)\n```\n\nTo close it, call `self.sell(strategy, 2)` or `self.liquidate()`.", D_LEAN),
    ("OPTIONS", "How do I read the underlying price from the object that add_option returns?",
     "`add_option` returns an `Option` security. Its `symbol` is the canonical Option Symbol and its `underlying` is the underlying security:\n\n"
     "```python\nself._option = self.add_option(\"IWM\")\nspot = self._option.underlying.price\n```\n\n"
     "A `Symbol` has no `price`; read prices from a security object or from `self.securities[symbol].price`.",
     "Option.underlying -> Security verified against quantconnect-stubs {}.".format(STUBS_VERSION)),
    ("FUTURES", "What is the signature of self.add_future?",
     "`add_future(ticker: str, resolution: Optional[Resolution] = None, market: str = None, fill_forward: Optional[bool] = None, "
     "leverage: float = 0, extended_market_hours: Optional[bool] = None, data_mapping_mode: Optional[DataMappingMode] = None, "
     "data_normalization_mode: Optional[DataNormalizationMode] = None, contract_depth_offset: int = 0)`\n\n"
     "The second positional parameter is the resolution, so pass everything after the ticker by keyword. It returns a `Future` for the continuous contract.",
     "Signature as printed by QuantConnect in a cached runtime error; names, order and types also match quantconnect-stubs {} "
     "(the stub elides the leverage default).".format(STUBS_VERSION)),
    ("FUTURES", "How do I add a continuous futures contract and choose how it rolls and how prices are adjusted?",
     "Pass `data_mapping_mode`, `data_normalization_mode` and `contract_depth_offset` to `add_future`:\n\n"
     "```python\nself._gold = self.add_future(\n    Futures.Metals.GOLD,\n    data_mapping_mode=DataMappingMode.OPEN_INTEREST,\n"
     "    data_normalization_mode=DataNormalizationMode.BACKWARDS_PANAMA_CANAL,\n    contract_depth_offset=0,\n)\n```\n\n"
     "`data_mapping_mode` decides when the continuous contract switches to the next contract, `data_normalization_mode` decides how past prices are "
     "adjusted across rolls, and `contract_depth_offset=0` selects the front contract.",
     D_LEAN + " Futures.Metals.GOLD, DataMappingMode.OPEN_INTEREST and DataNormalizationMode.BACKWARDS_PANAMA_CANAL verified against "
     "quantconnect-stubs {}.".format(STUBS_VERSION) + D_TPL),
    ("FUTURES", "How do I subscribe to the individual futures contracts, not just the continuous one?",
     "Call `set_filter` on the `Future` object with a range of days to expiry:\n\n"
     "```python\nself._gold.set_filter(0, 120)\n```\n\n"
     "The overloads are `set_filter(min_expiry_days, max_expiry_days)`, `set_filter(min_expiry, max_expiry)` with `timedelta` values, and "
     "`set_filter(universe_func)`. `set_filter` is a method of the `Future` object, not of the algorithm.", D_LEAN),
    ("FUTURES", "Which symbol do I send futures orders to?",
     "Orders go to the contract the continuous future currently maps to, which is the `mapped` property of the `Future` object. It is a `Symbol`:\n\n"
     "```python\ncontract = self._gold.mapped\nif contract is not None and not self.portfolio[contract].invested:\n    self.market_order(contract, 2)\n```\n\n"
     "The continuous `self._gold.symbol` is not tradable; use it for indicators and history.", D_LEAN + D_TPL),
    ("FUTURES", "Which event handler tells me that a continuous futures contract rolled to a new contract?",
     "Define `on_symbol_changed_events(self, symbols_changed: SymbolChangedEvents)`. LEAN does not call `on_contract_changed`, "
     "`on_data_mapping_changed` or `on_symbol_changed`, and `SymbolChangedEventList`, `FuturesMapping` and `DataMapping` are not LEAN types.\n\n"
     "```python\ndef on_symbol_changed_events(self, symbols_changed: SymbolChangedEvents) -> None:\n"
     "    for event in symbols_changed.values():\n        self.log(f\"{event.old_symbol} rolled to {event.new_symbol}\")\n```",
     "on_symbol_changed_events(self, symbols_changed: SymbolChangedEvents) and SymbolChangedEvent.old_symbol / new_symbol (both str) "
     "verified against quantconnect-stubs {}.".format(STUBS_VERSION) + D_TPL),
    ("FUTURES", "How do I move my position to the new contract when a futures contract rolls?",
     "In `on_symbol_changed_events`, close the position in the expiring contract and open the same quantity in the new one:\n\n"
     "```python\ndef on_symbol_changed_events(self, symbols_changed: SymbolChangedEvents) -> None:\n"
     "    for event in symbols_changed.values():\n"
     "        expiring = self.symbol(event.old_symbol)\n"
     "        held = self.portfolio[expiring].quantity\n"
     "        if held == 0:\n            continue\n"
     "        self.liquidate(expiring, tag=\"roll\")\n"
     "        self.market_order(self.symbol(event.new_symbol), held, tag=\"roll\")\n```",
     "The roll logic is dictated by the API, so it necessarily resembles the test template 'futures'; it was rewritten with different "
     "names and structure. The handler signature, old_symbol / new_symbol (str), self.symbol(ticker: str) and Future.mapped "
     "verified against quantconnect-stubs {}.".format(STUBS_VERSION)),
]


def derivatives_records():
    return [dict(kind="derivatives", category=cat, source="LEAN API", n_errors=0, comment=note, system=FAQ_SYSTEM,
                 prompt=q, answer=a, _fixed_lines=[]) for cat, q, a, note in DERIVATIVES]


# --------------------------------------------------------------------------
# Leakage checks
# --------------------------------------------------------------------------

def answer_code(answer):
    blocks = re.findall(r"```python\n(.*?)```", answer, re.DOTALL)
    return "\n".join(blocks)


def leakage_checks(records):
    eval_prompts = [tokens(json.loads(l)["prompt"]) for l in EVAL_PROMPTS.read_text().splitlines() if l.strip()]
    gold = {p.parent.name: code_lines(p.read_text(encoding="utf-8")) for p in EVAL_TEMPLATES.glob("*/main.py")}
    for r in records:
        r["max_prompt_sim"] = round(max(jaccard(tokens(r["prompt"]), e) for e in eval_prompts), 3)
        ans = code_lines(answer_code(r["answer"]))
        r["max_code_sim"] = round(max(difflib.SequenceMatcher(None, ans, g).ratio() for g in gold.values()), 3) if ans else 0.0
        # New lines the record teaches: fixed lines for repairs, every code line otherwise.
        new = code_lines("\n".join(r["_fixed_lines"])) if r["kind"] == "repair" else ans
        # Ignore boilerplate that any LEAN file shares (short lines, the initialize header).
        new = [l for l in new if len(l) >= 25 and not l.startswith("definitialize(")]
        hits = sorted({name for line in new for name, g in gold.items() if line in g})
        r["template_line_match"] = hits
        if hits:
            if r["kind"] == "repair":
                why = ("NOTE: the corrected line is identical to a line in test template(s) {}. It was produced by the smallest edit "
                       "to the model's own line and is the only correct form of this call.").format(", ".join(hits))
            else:
                why = "NOTE: a code line here is identical to a line in test template(s) {}.".format(", ".join(hits))
            r["comment"] = (r["comment"] + " " + why).strip()
    return records


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT / "repair_records.jsonl"))
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"),
                    help="folder with one sub-folder of cached records per run (default: src/runs)")
    ap.add_argument("--taxonomy", default=str(TAXONOMY),
                    help="error_taxonomy.json built from the same runs (default: analysis/error_taxonomy.json)")
    ap.add_argument("--skip-runs", default="qwen_base", help="comma-separated run names to leave out")
    ap.add_argument("--tuned9-ref", default=T9_REF)
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args(argv)

    taxonomy = json.loads(Path(args.taxonomy).read_text())
    runs_dir, skip = Path(args.runs_dir), set(filter(None, args.skip_runs.split(",")))
    runs = {}
    for name in dict.fromkeys(r["run"] for r in taxonomy["records"]):
        if name in skip:
            continue
        if (runs_dir / name).is_dir():
            runs[name] = load_dir(runs_dir / name)
        elif name == R9:
            # The tuned 9B run lives on a teammate's branch, not under runs/.
            local9 = ROOT.parent / T9_PATH
            runs[name] = load_dir(local9) if local9.is_dir() else load_from_git(args.tuned9_ref, T9_PATH)
        else:
            print("run {} is in the taxonomy but not under {}; skipped".format(name, runs_dir))

    version, mismatches = check_against_stubs()
    if version is None:
        print("quantconnect-stubs is not installed; signatures were last checked against {}\n".format(STUBS_VERSION))
    elif mismatches:
        for name, mine, theirs in mismatches:
            print("SIGNATURE MISMATCH {}:\n  record: {}\n  stubs:  {}".format(name, mine, " | ".join(theirs)))
        raise SystemExit("indicator signatures differ from quantconnect-stubs {}".format(version))
    else:
        print("all {} indicator signatures match quantconnect-stubs {}{}\n".format(
            len(INDICATORS), version, "" if version == STUBS_VERSION else " (records cite {})".format(STUBS_VERSION)))

    repairs, made, skipped = build_repairs(taxonomy, runs)
    records = leakage_checks(repairs + signature_records() + derivatives_records())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({
                "messages": [{"role": "system", "content": r["system"]},
                             {"role": "user", "content": r["prompt"]},
                             {"role": "assistant", "content": r["answer"]}],
                "kind": r["kind"], "category": r["category"], "source": r["source"], "n_errors": r["n_errors"],
                "max_prompt_sim": r["max_prompt_sim"], "max_code_sim": r["max_code_sim"], "comment": r["comment"],
            }, ensure_ascii=False) + "\n")

    upload = out.with_name(out.stem + "_upload.jsonl")
    with open(upload, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({"messages": [{"role": "system", "content": r["system"]},
                                             {"role": "user", "content": r["prompt"]},
                                             {"role": "assistant", "content": r["answer"]}]}, ensure_ascii=False) + "\n")

    print("wrote {} records to {}\n  and the messages-only copy to {}\n".format(len(records), out, upload))
    print("Repair records per category (errors = tuned-run errors in the taxonomy)")
    print("{:26} {:>7} {:>10} {:>8} {:>8}".format("category", "errors", "with fix", "unique", "skipped"))
    for cat in RECOVERABLE:
        e = sum(1 for r in taxonomy["records"] if r["run"] in runs and r["category"] == cat)
        print("{:26} {:>7} {:>10} {:>8} {:>8}".format(
            cat, e, sum(r["category"] == cat for r in made), sum(r["category"] == cat for r in repairs),
            sum(r["category"] == cat for r in skipped)))
    print("{:26} {:>7} {:>10} {:>8} {:>8}".format(
        "total", len(made) + len(skipped), len(made), len(repairs), len(skipped)))
    print("\nOther records: signature {}, derivatives {}".format(
        sum(r["kind"] == "signature" for r in records), sum(r["kind"] == "derivatives" for r in records)))
    print("\nSkipped (no minimal certain fix; the invented API has no one-line LEAN equivalent):")
    for cat in RECOVERABLE:
        ids = ["{}:{}".format("4B" if r["run"] == R4 else "9B", r["prompt_id"].replace("equity-", "")) for r in skipped if r["category"] == cat]
        if ids:
            print("  {} ({}): {}".format(cat, len(ids), ", ".join(ids)))

    worst = max(records, key=lambda r: r["max_prompt_sim"])
    print("\nLeakage vs prompts_100.jsonl (token Jaccard, build_dataset threshold 0.6):")
    print("  max = {} ({} / {})".format(worst["max_prompt_sim"], worst["kind"], worst["source"]))
    for kind in ("repair", "signature", "derivatives"):
        part = [r for r in records if r["kind"] == kind]
        print("  {:12} max prompt sim {:.3f} | max answer-code sim vs test templates {:.3f}".format(
            kind, max(r["max_prompt_sim"] for r in part), max(r["max_code_sim"] for r in part)))
    matches = [r for r in records if r["template_line_match"]]
    print("  records whose new code has a line identical to a test-template line: {}".format(len(matches)))
    for r in matches:
        print("    {} {} -> {}".format(r["kind"], r["source"], ", ".join(r["template_line_match"])))

    picks, seen = [], set()
    for want in ("RESOLUTION_POSITIONAL", "HALLUCINATED_MEMBER", "HALLUCINATED_ALGO_METHOD", "INDICATOR_RSI", "FUTURES"):
        r = next((r for r in records if r["category"] == want and id(r) not in seen), None)
        if r:
            picks.append(r)
            seen.add(id(r))
    print("\n{} sample records".format(len(picks[:args.samples])))
    for i, r in enumerate(picks[:args.samples], 1):
        print("\n===== sample {}: {} / {} / {} =====".format(i, r["kind"], r["category"], r["source"]))
        print("[system] " + r["system"])
        print("[user]\n" + r["prompt"])
        print("[assistant]\n" + r["answer"])
        if r["comment"]:
            print("[comment] " + r["comment"])
    return records


if __name__ == "__main__":
    main()
