"""Build API training records from the installed quantconnect-stubs package.

    cd src && .venv/bin/python -m finetune.build_stub_records

Reads QuantConnect/Algorithm/__init__.pyi (class QCAlgorithm) with ast and writes
finetune/out/stub_records.jsonl (review copy: messages + kind/category/source/comment) and
finetune/out/stub_records_upload.jsonl (messages only, for Together).

Per method: a signature record and a usage record. Indicator helpers (every QCAlgorithm method
whose return type derives from IndicatorBase) get a third record on the resolution slot.
Signatures, slots, defaults and return types come from the stubs only. A default the stubs
write as "..." is reported as not shown, never filled in. Usage snippets are either generated
from the signature (indicators, date and time rules) or hand-written (HAND below); every
self.* call in every snippet is bound against the stub overloads before it is written out.

Nothing here calls QuantConnect or a model. Snippets are checked against the stubs, not backtested.
"""
import argparse
import ast
import collections
import importlib.metadata
import json
import re
import zlib
from pathlib import Path

from finetune.build_dataset import EVAL_PROMPTS, FAQ_SYSTEM, OUT, ROOT, jaccard, tokens
from finetune.build_repair_records import INDICATORS, V_STUB, leakage_checks

TRAIN_TEMPLATES = ROOT / "data" / "train_templates"
REPAIR_RECORDS = OUT / "repair_records.jsonl"
SNAKE = re.compile(r"[a-z][a-z0-9_]*\Z")
SYMBOL_UNION = "Union[Symbol, str, BaseContract, Security]"

# Step 2 of the task: methods that are always kept, whatever the cap.
COMMON = ["add_equity", "add_option", "add_future", "add_crypto", "add_forex", "history", "set_holdings",
          "market_order", "limit_order", "stop_market_order", "liquidate", "set_warm_up", "set_start_date",
          "set_end_date", "set_cash", "set_benchmark", "settings", "universe_settings", "add_universe",
          "on_data", "on_order_event", "on_securities_changed"]
# Members of other classes that the task names: (display prefix, module, class, member filter).
OTHER = [("self.schedule.", "Scheduling", "ScheduleManager", ["on"]),
         ("self.date_rules.", "Scheduling", "DateRules", None),
         ("self.time_rules.", "Scheduling", "TimeRules", None),
         ("option.", "Securities.Option", "Option", ["set_filter"])]
# Exceptions to "describe the overload whose first parameter is the Symbol union": display -> first parameter name.
# self.history(symbol, ...) returns a pandas DataFrame in Python, which is the `tickers` overload in the stubs;
# the Symbol-union overload is typed Sequence[TradeBar] and would contradict the usage record.
PREFER_FIRST_PARAM = {"self.history": "tickers"}
# Variables in snippets whose class is known, for the call check.
RECEIVERS = {"option": ("Securities.Option", "Option"), "future": ("Securities.Future", "Future")}


def verified_defaults():
    """Defaults the stubs elide ("= ...") that build_repair_records.py established from another source:
    {method: {parameter: (value, where it came from)}}."""
    known = {}
    for name, _cls, sig, *_rest, provenance in INDICATORS:
        for param, value in re.findall(r"(\w+): MovingAverageType = (MovingAverageType\.\w+)", sig):
            known.setdefault(name, {})[param] = (value, provenance.replace(V_STUB, "").strip())
    return known


def strip(text):
    """Module prefixes removed, same convention as build_repair_records.py."""
    text = re.sub(r"\btyping\.|\bQuantConnect\.(?:\w+\.)*|\bSystem\.(?:\w+\.)*|\bpandas\.", "", text)
    return re.sub(r"\bdatetime\.(?=datetime|timedelta|date\b)", "", text)


# --------------------------------------------------------------------------
# Stub index
# --------------------------------------------------------------------------

class Stubs:
    def __init__(self):
        dist = importlib.metadata.distribution("quantconnect-stubs")
        self.version = dist.version
        self.root = Path(str(dist.locate_file("QuantConnect")))
        self.classes = collections.defaultdict(list)       # bare name -> [(module, ClassDef)]
        for path in sorted(self.root.rglob("__init__.pyi")):
            module = ".".join(path.parent.relative_to(self.root).parts)
            self._index(ast.parse(path.read_text(encoding="utf-8")).body, module)
        system = self.root.parent / "System" / "__init__.pyi"
        if system.exists():
            self._index(ast.parse(system.read_text(encoding="utf-8")).body, "System")

    def _index(self, body, module):
        for node in body:
            if isinstance(node, ast.ClassDef):
                self.classes[node.name].append((module, node))
                self._index(node.body, module)

    def get(self, module, name):
        for mod, node in self.classes.get(name, []):
            if mod == module:
                return node
        raise KeyError((module, name))

    def from_annotation(self, annotation):
        """ClassDef for a dotted annotation such as QuantConnect.Scheduling.DateRules, or None."""
        m = re.fullmatch(r"QuantConnect\.((?:\w+\.)*)(\w+)", annotation or "")
        if not m:
            return None
        try:
            return self.get(m.group(1).rstrip("."), m.group(2))
        except KeyError:
            return None

    def members(self, node, seen=None):
        """Names defined on a class or inherited from stub base classes."""
        seen = seen or set()
        names = set()
        for n in node.body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                names.add(n.name)
            elif isinstance(n, ast.AnnAssign):
                names.add(ast.unparse(n.target))
            elif isinstance(n, ast.Assign):
                names.update(ast.unparse(t) for t in n.targets)
        for base in node.bases:
            bare = re.sub(r"\[.*", "", ast.unparse(base)).split(".")[-1]
            if bare not in seen:
                seen.add(bare)
                for _mod, b in self.classes.get(bare, []):
                    names |= self.members(b, seen)
        return names

    def has_member(self, class_name, member):
        return any(member in self.members(node) for _mod, node in self.classes.get(class_name, []))

    def derives_from(self, class_name, root, seen=()):
        if class_name == root:
            return True
        for _mod, node in self.classes.get(class_name, []):
            for base in node.bases:
                bare = re.sub(r"\[.*", "", ast.unparse(base)).split(".")[-1]
                if bare not in seen and self.derives_from(bare, root, seen + (class_name,)):
                    return True
        return False


def split_members(node):
    """(methods, properties, settable) of a class: name -> [FunctionDef], name -> node, set of names."""
    methods, props, settable = collections.defaultdict(list), {}, set()
    for n in node.body:
        if isinstance(n, ast.FunctionDef):
            decorators = [ast.unparse(d) for d in n.decorator_list]
            if "property" in decorators:
                props[n.name] = n
            elif any(d.endswith(".setter") for d in decorators):
                settable.add(n.name)
            else:
                methods[n.name].append(n)
        elif isinstance(n, ast.AnnAssign):
            props.setdefault(ast.unparse(n.target), n)
    return methods, props, settable


def params_of(fn):
    """[(name, stripped annotation, default text or None)] without self."""
    args = fn.args.args[1:]
    defaults = [None] * (len(args) - len(fn.args.defaults)) + list(fn.args.defaults)
    return [(a.arg, strip(ast.unparse(a.annotation)) if a.annotation else "Any",
             None if d is None else ast.unparse(d)) for a, d in zip(args, defaults)]


def render(name, fn):
    return "{}({})".format(name, ", ".join(
        "{}: {}{}".format(n, t, "" if d is None else " = " + d) for n, t, d in params_of(fn)))


def unique_overloads(fns):
    """One overload per parameter-name tuple; among twins keep the one whose first parameter is the
    Symbol union (the twins differ only in the symbol or number type)."""
    by_names = {}
    for fn in fns:
        ps = params_of(fn)
        key = tuple(p[0] for p in ps)
        if key not in by_names or (ps and ps[0][1] == SYMBOL_UNION and params_of(by_names[key])[0][1] != SYMBOL_UNION):
            by_names[key] = fn
    return list(by_names.values())


def doc_parts(fn):
    """(first sentence of the summary, {param: description}) from a stub docstring."""
    doc = ast.get_docstring(fn) or ""
    head = re.split(r"\n\s*\n|\n?:param|\n?:returns", doc, maxsplit=1)[0]
    head = " ".join(head.split())
    first = re.split(r"(?<=[.!?])\s", head, maxsplit=1)[0].rstrip(".")
    described = {}
    for m in re.finditer(r":param (\w+): (.*?)(?=\n:param|\n:returns|\Z)", doc, re.S):
        described[m.group(1)] = " ".join(m.group(2).split()).rstrip(".")
    return first, described


# --------------------------------------------------------------------------
# Checking snippets against the stubs
# --------------------------------------------------------------------------

def arg_fits(arg, annotation):
    """False only when a literal or enum member is clearly in the wrong slot."""
    if annotation in ("Any", "object") or "Callable" in annotation or annotation.startswith("QuantConnect_"):
        return True
    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id[:1].isupper() and arg.attr.isupper():
        return re.search(r"\b%s\b" % arg.value.id, annotation) is not None or "str" in annotation.split(", ")
    if isinstance(arg, ast.Constant) and isinstance(arg.value, bool):
        return "bool" in annotation
    if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
        return re.search(r"\b(int|float)\b", annotation) is not None
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return re.search(r"\bstr\b", annotation) is not None
    return True


def binds(call, fn):
    ps = params_of(fn)
    names = [p[0] for p in ps]
    if len(call.args) > len(ps) and not fn.args.vararg:
        return False
    given = set(names[:len(call.args)])
    for i, a in enumerate(call.args[:len(ps)]):
        if not arg_fits(a, ps[i][1]):
            return False
    for kw in call.keywords:
        if kw.arg not in names or kw.arg in given or not arg_fits(kw.value, ps[names.index(kw.arg)][1]):
            return False
        given.add(kw.arg)
    return all(n in given for n, _t, d in ps if d is None)


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ([node.id] + parts[::-1]) if isinstance(node, ast.Name) else None


class Checker:
    def __init__(self, stubs, algo):
        self.stubs = stubs
        self.methods, self.props, _ = split_members(algo)
        self.unverified = collections.Counter()

    def overloads(self, cls_node, name):
        """Overloads of a method, or of the __call__ of a callable property such as self.history."""
        methods, props, _ = split_members(cls_node)
        if name in methods:
            return methods[name]
        node = props.get(name)
        ann = ast.unparse(node.returns if isinstance(node, ast.FunctionDef) else node.annotation) if node is not None else ""
        target = self.stubs.from_annotation(ann)
        if target is not None:
            return split_members(target)[0].get("__call__", [])
        return []

    def prop_class(self, name):
        node = self.props.get(name)
        if node is None:
            return None
        return self.stubs.from_annotation(ast.unparse(node.returns if isinstance(node, ast.FunctionDef) else node.annotation))

    def check(self, code, algo_node):
        """Problems found in a snippet; empty when every checkable reference agrees with the stubs."""
        problems = []
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                path = dotted(node.func)
                if not path:
                    continue
                cls_node = None
                if path[0] == "self" and len(path) == 2 and not path[1].startswith("_"):
                    cls_node = algo_node
                elif path[0] == "self" and len(path) == 3 and self.prop_class(path[1]) is not None:
                    cls_node = self.prop_class(path[1])
                elif len(path) == 2 and path[0] in RECEIVERS:
                    cls_node = self.stubs.get(*RECEIVERS[path[0]])
                if cls_node is None:
                    continue
                fns = self.overloads(cls_node, path[-1])
                if not fns:
                    problems.append("{}: no such method in the stubs".format(".".join(path)))
                elif not any(binds(node, fn) for fn in fns):
                    problems.append("{}: no overload accepts {}".format(".".join(path), ast.unparse(node)))
            elif isinstance(node, ast.Attribute):
                path = dotted(node)
                if not path:
                    continue
                if path[0] == "self" and len(path) == 2 and not path[1].startswith("_"):
                    if path[1] not in self.methods and path[1] not in self.props:
                        problems.append("self.{}: not on QCAlgorithm in the stubs".format(path[1]))
                elif path[0] == "self" and len(path) == 3 and self.prop_class(path[1]) is not None:
                    if path[2] not in self.stubs.members(self.prop_class(path[1])):
                        problems.append("{}: no such member in the stubs".format(".".join(path)))
                elif path[0][:1].isupper() and path[-1].isupper() and len(path) >= 2:
                    owner = path[-2]
                    if owner not in self.stubs.classes:
                        self.unverified[".".join(path)] += 1
                    elif not self.stubs.has_member(owner, path[-1]):
                        problems.append("{}: no such member in the stubs".format(".".join(path)))
        return problems


# --------------------------------------------------------------------------
# Generated snippets
# --------------------------------------------------------------------------

PAIRS = [("SPY", "QQQ"), ("AAPL", "SPY"), ("QQQ", "IWM"), ("MSFT", "SPY"), ("IWM", "SPY"), ("XLF", "SPY"),
         ("TLT", "SPY"), ("GLD", "SPY"), ("XLE", "SPY"), ("NVDA", "QQQ"), ("EFA", "SPY"), ("VOO", "QQQ")]
INT_RULES = [("fast", 12), ("slow", 26), ("signal", 9), ("tenkan", 9), ("kijun", 26), ("senkou_a_period", 26),
             ("senkou_b_period", 52), ("delay", 26), ("order", 1), ("period_1", 7), ("period_2", 14), ("period_3", 28),
             ("smooth", 3), ("k_period", 3), ("d_period", 3), ("streak", 2), ("look_back", 100), ("stored", 10)]
FLOAT_RULES = [("in_phase", 0.635), ("quadrature", 0.338), ("confidence", 0.95), ("delta", 0.1), ("limit_move", 3.0),
               ("mult", 3.0), ("sensitivity", 0.05)]
ENUM_EXAMPLE = {"MovingAverageType": "MovingAverageType.SIMPLE", "SwissArmyKnifeTool": "SwissArmyKnifeTool.GAUSS",
                "Resolution": "Resolution.DAILY", "Optional[Resolution]": "Resolution.DAILY"}


def pick(name, choices):
    return choices[zlib.crc32(name.encode()) % len(choices)]


def example_value(method, pname, annotation, symbols):
    if annotation == SYMBOL_UNION:
        return symbols.pop(0) if symbols else None
    if annotation == "List[Symbol]":
        return "[{}]".format(", ".join(symbols))
    if annotation in ("int", "Optional[int]"):
        for key, value in INT_RULES:
            if key in pname:
                return str(value)
        return str(pick(method, [10, 14, 20, 30]))
    if annotation in ("float", "Optional[float]"):
        if pname == "k":
            return "2"
        for key, value in FLOAT_RULES:
            if key in pname:
                return str(value)
        return "2.0"
    return ENUM_EXAMPLE.get(annotation)


def words(camel):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", camel)


def indicator_snippet(name, fn, index):
    """(usage code, bare call text, resolution text) for an indicator helper, or None when a
    required argument has a type this generator has no example value for."""
    ps = params_of(fn)
    greek = any(p[0] == "mirror_option" for p in ps)
    a, b = PAIRS[index % len(PAIRS)]
    resolution = "Resolution.MINUTE" if greek else "Resolution.DAILY"
    symbols = ["option.symbol"] if greek else ["self._" + a.lower(), "self._" + b.lower()]
    two = (ps[0][1] == "List[Symbol]") or sum(1 for _n, t, d in ps if t == SYMBOL_UNION and d is None) > 1
    pool, args = list(symbols), []
    for pname, annotation, default in ps:
        if default is not None:
            break
        if pname == "resolution":
            args.append("resolution=" + resolution)     # required in this overload; still passed by name
            continue
        value = example_value(name, pname, annotation, pool)
        if value is None:
            return None
        args.append(value)
    has_resolution = any(p[0] == "resolution" and p[2] is not None for p in ps)
    call = "self.{}({}{})".format(name, ", ".join(args), ", resolution=" + resolution if has_resolution else "")
    var = "self._{}_indicator".format(name) if name in ("max", "min", "sum", "str", "t", "b", "c", "d", "g", "r", "v", "a") \
        else "self._" + name
    lines = ["def initialize(self) -> None:"]
    if greek:
        lines += ['    self._{t} = self.add_equity("{T}", Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW).symbol'
                  .format(t=a.lower(), T=a),
                  "    contract = min(self.option_chain(self._{}), key=lambda c: (c.expiry, c.strike))".format(a.lower()),
                  "    option = self.add_option_contract(contract.symbol, Resolution.MINUTE)"]
    else:
        lines.append('    self._{} = self.add_equity("{}", {}).symbol'.format(a.lower(), a, resolution))
        if two:
            lines.append('    self._{} = self.add_equity("{}", {}).symbol'.format(b.lower(), b, resolution))
    lines += ["    {} = {}".format(var, call), "",
              "def on_data(self, slice: Slice) -> None:",
              "    if {}.is_ready:".format(var),
              '        self.plot("{}", "value", {}.current.value)'.format(name, var)]
    return "\n".join(lines), "{} = {}".format(var, call), resolution


RULE_ARGS = {  # example call for each date/time rule member, written from the stub signatures
    "self.date_rules.today": "", "self.date_rules.tomorrow": "", "self.date_rules.every": "(DayOfWeek.MONDAY)",
    "self.date_rules.every_day": "({s})", "self.date_rules.month_end": "({s})", "self.date_rules.month_start": "({s}, 2)",
    "self.date_rules.on": "(2024, 3, 15)", "self.date_rules.quarter_end": "({s})", "self.date_rules.quarter_start": "({s})",
    "self.date_rules.week_end": "({s})", "self.date_rules.week_start": "({s}, 1)", "self.date_rules.year_end": "({s})",
    "self.date_rules.year_start": "({s})",
    "self.time_rules.now": "", "self.time_rules.midnight": "", "self.time_rules.noon": "",
    "self.time_rules.after_market_close": "({s}, 10)", "self.time_rules.after_market_open": "({s}, 30)",
    "self.time_rules.at": "(10, 30)", "self.time_rules.before_market_close": "({s}, 15)",
    "self.time_rules.before_market_open": "({s}, 30)", "self.time_rules.every": "(timedelta(hours=2))",
}
OTHER_RULE = ["self.time_rules.after_market_open({s}, 30)", "self.time_rules.at(11, 0)", "self.time_rules.before_market_close({s}, 20)",
              "self.date_rules.every_day({s})", "self.date_rules.week_start({s})", "self.date_rules.month_start({s})"]


def rule_snippet(display, index):
    ticker = PAIRS[index % len(PAIRS)][0]
    sym = "self._" + ticker.lower()
    mine = (display + RULE_ARGS[display]).format(s=sym)
    if display.startswith("self.date_rules"):
        date_rule, time_rule = mine, OTHER_RULE[index % 3].format(s=sym)
    else:
        date_rule, time_rule = OTHER_RULE[3 + index % 3].format(s=sym), mine
    resolution = "Resolution.MINUTE" if "market" in time_rule or "every(" in time_rule else "Resolution.DAILY"
    return "\n".join([
        "def initialize(self) -> None:",
        '    self._{} = self.add_equity("{}", {}).symbol'.format(ticker.lower(), ticker, resolution),
        "    self.schedule.on({},".format(date_rule),
        "                     {},".format(time_rule),
        "                     self._on_schedule)", "",
        "def _on_schedule(self) -> None:",
        "    self.set_holdings({}, 1)".format(sym)])


# --------------------------------------------------------------------------
# Hand-written snippets: display name -> (question, code). Checked against the stubs at build time.
# --------------------------------------------------------------------------

def init(*body):
    return "def initialize(self) -> None:\n" + "\n".join("    " + line for line in body)


def data(*body):
    return "def on_data(self, slice: Slice) -> None:\n" + "\n".join("    " + line for line in body)


SPY_D = 'self._spy = self.add_equity("SPY", Resolution.DAILY).symbol'
SPY_M = 'self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol'

HAND = {
    "self.add_equity": ("How do I subscribe to daily SPY bars and keep the Symbol for later orders?",
        init(SPY_D, "self.set_benchmark(self._spy)")),
    "self.add_option": ("How do I add the SPY option chain with a strike and expiry filter?",
        init('self.add_equity("SPY", Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW)',
             'option = self.add_option("SPY", Resolution.MINUTE)',
             "option.set_filter(-5, 5, 0, 30)",
             "self._option_symbol = option.symbol")),
    "self.add_future": ("How do I add a continuous E-mini S&P 500 future that rolls on open interest?",
        init("future = self.add_future(Futures.Indices.SP_500_E_MINI, Resolution.MINUTE,",
             "                         data_mapping_mode=DataMappingMode.OPEN_INTEREST,",
             "                         data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,",
             "                         contract_depth_offset=0)",
             "self._future = future.symbol")),
    "self.add_crypto": ("How do I add hourly BTCUSD from Coinbase with a cash account?",
        init("self.set_brokerage_model(BrokerageName.COINBASE, AccountType.CASH)",
             'self._btc = self.add_crypto("BTCUSD", Resolution.HOUR, Market.COINBASE).symbol')),
    "self.add_forex": ("How do I add hourly EURUSD from OANDA?",
        init("self.set_brokerage_model(BrokerageName.OANDA_BROKERAGE, AccountType.MARGIN)",
             'self._eurusd = self.add_forex("EURUSD", Resolution.HOUR, Market.OANDA).symbol')),
    "self.history": ("How do I request the last 30 daily bars for one symbol in initialize?",
        init(SPY_D, "bars = self.history(self._spy, 30, Resolution.DAILY)",
             "if not bars.empty:", '    self._mean_close = bars["close"].mean()')),
    "self.set_holdings": ("How do I hold 60% of the portfolio in one asset and 40% in another?",
        data("if not self.portfolio.invested:", "    self.set_holdings(self._spy, 0.6)", "    self.set_holdings(self._tlt, 0.4)")),
    "self.market_order": ("How do I buy 100 shares at market and log the order id?",
        data("if not self.portfolio.invested:", "    ticket = self.market_order(self._spy, 100)",
             '    self.debug(f"sent order {ticket.order_id}")')),
    "self.limit_order": ("How do I place a limit order 1% below the current price?",
        data("price = self.securities[self._spy].price", "if price > 0 and not self.portfolio.invested:",
             "    self._ticket = self.limit_order(self._spy, 100, round(price * 0.99, 2))")),
    "self.stop_market_order": ("How do I attach a 5% stop to a position as soon as the entry fills?",
        "def on_order_event(self, order_event: OrderEvent) -> None:\n"
        "    if order_event.status == OrderStatus.FILLED and order_event.fill_quantity > 0:\n"
        "        stop_price = round(order_event.fill_price * 0.95, 2)\n"
        "        self.stop_market_order(order_event.symbol, -order_event.fill_quantity, stop_price)"),
    "self.liquidate": ("How do I close one position and tag the order with the reason?",
        data("if self._rsi.is_ready and self._rsi.current.value > 70:", '    self.liquidate(self._spy, tag="RSI above 70")')),
    "self.set_warm_up": ("How do I warm up a 200-day moving average before trading starts?",
        init(SPY_D, "self._sma = self.sma(self._spy, 200, Resolution.DAILY)", "self.set_warm_up(200, Resolution.DAILY)")),
    "self.set_start_date": ("How do I start a backtest on 1 January 2021?",
        init("self.set_start_date(2021, 1, 1)", "self.set_cash(100000)", SPY_D)),
    "self.set_end_date": ("How do I stop a backtest at the end of June 2023?",
        init("self.set_start_date(2020, 7, 1)", "self.set_end_date(2023, 6, 30)", 'self._qqq = self.add_equity("QQQ", Resolution.DAILY).symbol')),
    "self.set_cash": ("How do I set the starting capital to 250,000 dollars?",
        init("self.set_start_date(2022, 1, 1)", "self.set_cash(250000)")),
    "self.set_benchmark": ("How do I benchmark the strategy against QQQ?",
        init('self._qqq = self.add_equity("QQQ", Resolution.DAILY).symbol', "self.set_benchmark(self._qqq)")),
    "self.settings": ("How do I turn on automatic indicator warm-up?",
        init("self.settings.automatic_indicator_warm_up = True", SPY_D, "self._ema = self.ema(self._spy, 50, Resolution.DAILY)")),
    "self.universe_settings": ("How do I make universe members daily and unadjusted?",
        init("self.universe_settings.resolution = Resolution.DAILY",
             "self.universe_settings.data_normalization_mode = DataNormalizationMode.RAW",
             'self._universe = self.add_universe(self.universe.etf("SPY"))')),
    "self.add_universe": ("How do I select the 10 most liquid US stocks each day?",
        "def initialize(self) -> None:\n"
        "    self.universe_settings.resolution = Resolution.DAILY\n"
        "    self._universe = self.add_universe(self._select)\n\n"
        "def _select(self, fundamental: List[Fundamental]) -> List[Symbol]:\n"
        "    liquid = sorted(fundamental, key=lambda f: f.dollar_volume, reverse=True)[:10]\n"
        "    return [f.symbol for f in liquid]"),
    "self.on_data": ("How do I read the latest bar for my symbol in on_data and enter when price is above its average?",
        data("bar = slice.bars.get(self._spy)", "if bar is None or not self._sma.is_ready:", "    return",
             "if bar.close > self._sma.current.value and not self.portfolio.invested:", "    self.set_holdings(self._spy, 1)")),
    "self.on_order_event": ("How do I log every fill?",
        "def on_order_event(self, order_event: OrderEvent) -> None:\n"
        "    if order_event.status == OrderStatus.FILLED:\n"
        '        self.debug(f"{order_event.symbol} filled {order_event.fill_quantity} at {order_event.fill_price}")'),
    "self.on_securities_changed": ("How do I sell what leaves the universe and buy what enters it?",
        "def on_securities_changed(self, changes: SecurityChanges) -> None:\n"
        "    for security in changes.removed_securities:\n"
        "        if security.invested:\n"
        "            self.liquidate(security.symbol)\n"
        "    for security in changes.added_securities:\n"
        "        self.set_holdings(security.symbol, 0.1)"),
    "self.schedule.on": ("How do I run a rebalance function 30 minutes after the open every trading day?",
        "def initialize(self) -> None:\n"
        "    " + SPY_M + "\n"
        "    self.schedule.on(self.date_rules.every_day(self._spy),\n"
        "                     self.time_rules.after_market_open(self._spy, 30),\n"
        "                     self._on_schedule)\n\n"
        "def _on_schedule(self) -> None:\n"
        "    self.set_holdings(self._spy, 1)"),
    "option.set_filter": ("How do I keep only weekly and monthly contracts within 5 strikes and 30 days?",
        init('option = self.add_option("QQQ", Resolution.MINUTE)',
             "option.set_filter(lambda u: u.include_weeklys().strikes(-5, 5).expiration(0, 30))",
             "self._option_symbol = option.symbol")),
    "self.date_rules.set_default_time_zone": ("How do I make date rules use New York time?",
        init("self.date_rules.set_default_time_zone(TimeZones.NEW_YORK)", SPY_D)),
    "self.time_rules.set_default_time_zone": ("How do I make time rules use Chicago time?",
        init("self.time_rules.set_default_time_zone(TimeZones.CHICAGO)",
             "self.schedule.on(self.date_rules.every_day(), self.time_rules.at(8, 30), self._on_schedule)")),
    # ---- members kept because the training templates use them
    "self.register_indicator": ("How do I feed a manually created RSI with daily bars?",
        init(SPY_M, "self._rsi = RelativeStrengthIndex(14)", "self.register_indicator(self._spy, self._rsi, Resolution.DAILY)")),
    "self.warm_up_indicator": ("How do I warm up an indicator I created by hand?",
        init(SPY_D, "self._sma = SimpleMovingAverage(50)", "self.register_indicator(self._spy, self._sma, Resolution.DAILY)",
             "self.warm_up_indicator(self._spy, self._sma, Resolution.DAILY)")),
    "self.plot": ("How do I chart an indicator next to the price?",
        data("if self._sma.is_ready:", '    self.plot("Trend", "sma", self._sma.current.value)',
             '    self.plot("Trend", "price", self.securities[self._spy].price)')),
    "self.plot_indicator": ("How do I chart an indicator automatically as it updates?",
        init(SPY_D, "self._rsi = self.rsi(self._spy, 14, resolution=Resolution.DAILY)", 'self.plot_indicator("RSI", self._rsi)')),
    "self.securities": ("How do I read the current price of a security I subscribed to?",
        data("security = self.securities[self._spy]", "if security.has_data and security.price > 0:",
             '    self.log(f"SPY price {security.price}")')),
    "self.portfolio": ("How do I check a holding and the total portfolio value?",
        data("holding = self.portfolio[self._spy]", "if holding.invested and holding.unrealized_profit_percent < -0.05:",
             "    self.liquidate(self._spy)", 'self.plot("Equity", "value", self.portfolio.total_portfolio_value)')),
    "self.time": ("How do I trade only on Mondays using the algorithm clock?",
        data("if self.time.weekday() == 0 and not self.portfolio.invested:", "    self.set_holdings(self._spy, 1)")),
    "self.log": ("How do I write the close of each bar to the log?",
        data("bar = slice.bars.get(self._spy)", "if bar is not None:", '    self.log(f"{self.time} close {bar.close}")')),
    "self.debug": ("How do I print a debug message when a position opens?",
        data("if not self.portfolio.invested:", "    self.set_holdings(self._spy, 1)", '    self.debug(f"entered SPY at {self.time}")')),
    "self.option_chain": ("How do I list today's put contracts for an underlying?",
        data("chain = self.option_chain(self._spy)", "puts = [c for c in chain if c.right == OptionRight.PUT]",
             "if puts:", "    self._nearest_put = min(puts, key=lambda c: c.expiry).symbol")),
    "self.add_option_contract": ("How do I subscribe to one specific option contract?",
        data("chain = self.option_chain(self._spy)", "calls = [c for c in chain if c.right == OptionRight.CALL]",
             "if calls and self._contract is None:", "    nearest = min(calls, key=lambda c: (c.expiry, c.strike))",
             "    self._contract = self.add_option_contract(nearest.symbol, Resolution.MINUTE).symbol")),
    "self.set_brokerage_model": ("How do I model an Interactive Brokers margin account?",
        init("self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)", SPY_D)),
    "self.is_warming_up": ("How do I skip trading while the algorithm is warming up?",
        data("if self.is_warming_up:", "    return", "if not self.portfolio.invested:", "    self.set_holdings(self._spy, 1)")),
    "self.calculate_order_quantity": ("How do I get the share count for a 50% target before ordering?",
        data("quantity = self.calculate_order_quantity(self._spy, 0.5)", "if quantity != 0:",
             "    self.market_order(self._spy, quantity)")),
    "self.universe": ("How do I trade the constituents of an ETF?",
        init("self.universe_settings.resolution = Resolution.DAILY", 'self._universe = self.add_universe(self.universe.etf("QQQ"))')),
    "self.buy": ("How do I buy a fixed number of shares?",
        data("if not self.portfolio.invested:", "    self.buy(self._spy, 10)")),
    "self.indicator_history": ("How do I get past values of an indicator?",
        init(SPY_D, "self._sma = self.sma(self._spy, 20, Resolution.DAILY)",
             "history = self.indicator_history(self._sma, self._spy, 60, Resolution.DAILY)",
             "self._sma_frame = history.data_frame")),
    "self.add_index": ("How do I subscribe to the SPX index?",
        init('self._spx = self.add_index("SPX", Resolution.MINUTE).symbol',
             "option = self.add_index_option(self._spx, Resolution.MINUTE)", "option.set_filter(-3, 3, 0, 30)")),
    "self.is_market_open": ("How do I check the exchange is open before ordering?",
        data("if self.is_market_open(self._spy) and not self.portfolio.invested:", "    self.market_order(self._spy, 10)")),
    "self.set_time_zone": ("How do I run the algorithm clock in Chicago time?",
        init("self.set_time_zone(TimeZones.CHICAGO)", SPY_M)),
    "self.consolidate": ("How do I build 30-minute bars from minute data?",
        "def initialize(self) -> None:\n"
        "    " + SPY_M + "\n"
        "    self.consolidate(self._spy, timedelta(minutes=30), self._on_bar)\n\n"
        "def _on_bar(self, bar: TradeBar) -> None:\n"
        '    self.log(f"30-minute close {bar.close}")'),
    "self.on_warmup_finished": ("How do I run code once when warm-up ends?",
        "def on_warmup_finished(self) -> None:\n"
        '    self.log(f"warm-up finished at {self.time}")\n'
        "    self.set_holdings(self._spy, 1)"),
    "self.schedule": ("How do I schedule a monthly rebalance?",
        "def initialize(self) -> None:\n"
        "    " + SPY_D + "\n"
        "    self.schedule.on(self.date_rules.month_start(self._spy), self.time_rules.noon, self._on_schedule)\n\n"
        "def _on_schedule(self) -> None:\n"
        "    self.set_holdings(self._spy, 0.9)"),
    "self.date_rules": ("How do I schedule something for the first trading day of each week?",
        init(SPY_M, "self.schedule.on(self.date_rules.week_start(self._spy),",
             "                 self.time_rules.after_market_open(self._spy, 5),", "                 self._on_schedule)")),
    "self.time_rules": ("How do I schedule something 15 minutes before the close?",
        init(SPY_M, "self.schedule.on(self.date_rules.every_day(self._spy),",
             "                 self.time_rules.before_market_close(self._spy, 15),", "                 self.liquidate)")),
}


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

class Entity:
    def __init__(self, display, name, group, fns=None, prop=None, settable=False, source=""):
        self.display, self.name, self.group = display, name, group
        self.fns, self.prop, self.settable, self.source = fns or [], prop, settable, source
        self.chosen = None


def choose_overload(entity, call_names, checker):
    """Unique overloads with the described one first: the one the snippet's call binds to, else the
    one whose first parameter is the Symbol union, else the first in the stub."""
    unique = unique_overloads(entity.fns)
    def rank(fn):
        ps = params_of(fn)
        return (0 if ps and ps[0][0] == PREFER_FIRST_PARAM.get(entity.display) else 1,
                0 if any(binds(c, fn) for c in call_names) else 1,
                0 if entity.group != "indicator" or any(p[0] == "resolution" for p in ps) else 1,
                0 if ps and ps[0][1] == SYMBOL_UNION else 1 if ps and ps[0][1].startswith("Union[Symbol") else 2)
    unique.sort(key=rank)
    return unique


def calls_to(code, display):
    target = display.split(".")
    found = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Call) and dotted(node.func) == target:
            found.append(node)
    return found


def signature_answer(entity, unique, known=None):
    """Answer text; `known` maps parameters whose "..." default is filled from build_repair_records.py."""
    known = known or {}
    fn = unique[0]
    ps = params_of(fn)
    summary, described = doc_parts(fn)
    returns = strip(ast.unparse(fn.returns)) if fn.returns else "None"
    slots = []
    for i, (n, _t, _d) in enumerate(ps[:10], 1):
        if i == 1:
            continue
        text = re.split(r"(?<=[a-z)])\.\s", described.get(n, ""), maxsplit=1)[0].strip()
        # A description that only repeats the parameter name adds nothing.
        trivial = set(re.findall(r"[a-z]+", text.lower())) <= set(n.split("_")) | {"the", "a", "of", "to", "use"}
        slots.append("{} `{}`".format(i, n) + ("" if trivial else " ({})".format(text[:1].lower() + text[1:] if not text[:2].isupper() else text)))
    sentence = "It returns `{}`".format(returns) if returns != "None" else "It returns nothing"
    if slots:
        sentence += "; the positional slots after the first are " + ", ".join(slots)
        if len(ps) > 10:
            sentence += ", then {} more".format(len(ps) - 10)
    sig = render(entity.name, fn)
    for n, t, d in ps:
        if d == "..." and n in known:
            sig = sig.replace("{}: {} = ...".format(n, t), "{}: {} = {}".format(n, t, known[n][0]))
    parts = ["`{}`".format(sig), sentence + "."]
    if summary:
        parts.insert(1, summary + ".")
    if entity.name.startswith("on_") and entity.display.startswith("self.on_"):
        parts.append("LEAN calls this event handler; define it on your algorithm class instead of calling it.")
    hidden = [n for n, _t, d in ps if d == "..." and n not in known]
    if hidden:
        parts.append("The stubs write the default of {} as `...`, so the default value is not shown in the stubs."
                     .format(", ".join("`{}`".format(n) for n in hidden)))
    others = ["({})".format(", ".join(p[0] for p in params_of(f))) for f in unique[1:]]
    if others:
        shown = "; ".join("`{}`".format(o) for o in others[:4])
        more = " and {} more".format(len(others) - 4) if len(others) > 4 else ""
        parts.append("The stubs list {} other overload{}: {}{}.".format(len(others), "s" if len(others) > 1 else "", shown, more))
    return "\n\n".join(parts)


def resolution_answer(entity, fn, call_line, resolution):
    ps = params_of(fn)
    names = [p[0] for p in ps]
    slot = names.index("resolution") + 1
    required = sum(1 for p in ps if p[2] is None)
    between = names[required:slot - 1]
    text = "`resolution` is positional slot {} of `self.{}`, after {}.".format(
        slot, entity.name, ", ".join("`{}`".format(n) for n in names[:slot - 1]))
    if between:
        landing = ps[required]
        text += (" Slot {} is `{}` ({}), so a `Resolution` passed right after the required arguments lands there and the call "
                 "fails with an argument mismatch. Pass the resolution by keyword and the skipped parameter{} keep{} the default:"
                 .format(required + 1, landing[0], landing[1], "s" if len(between) > 1 else "", "" if len(between) > 1 else "s"))
    else:
        text += (" Every slot before it is required, so the resolution can follow them positionally, but the keyword form is "
                 "the one that stays correct across indicators:")
        if ps[slot - 1][2] is None:
            text = text.replace(" Every slot", " It has no default in this overload, so it must be given. Every slot")
    return "{}\n\n```python\n{}\n```".format(text, call_line)


def property_answer(entity):
    node = entity.prop
    ann = strip(ast.unparse(node.returns if isinstance(node, ast.FunctionDef) else node.annotation))
    summary = doc_parts(node)[0] if isinstance(node, ast.FunctionDef) else ""
    access = "The stubs define a setter, so it can be assigned." if entity.settable else "The stubs define no setter for it."
    text = "`{}` is a property of type `{}`, read without parentheses. {}".format(entity.display, ann, access)
    return text + (" " + summary + "." if summary else "")


def count_lines(code):
    return sum(1 for line in code.splitlines() if line.strip())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT / "stub_records.jsonl"))
    ap.add_argument("--cap", type=int, default=600, help="approximate maximum number of records")
    ap.add_argument("--top", type=int, default=100, help="most-used QCAlgorithm members to add to the named set")
    ap.add_argument("--samples", type=int, default=3)
    args = ap.parse_args(argv)

    stubs = Stubs()
    algo = stubs.get("Algorithm", "QCAlgorithm")
    source = "quantconnect-stubs {} QuantConnect/Algorithm/__init__.pyi".format(stubs.version)
    methods, props, settable = split_members(algo)
    checker = Checker(stubs, algo)
    callable_props = {n for n in props if SNAKE.match(n) and n not in methods and checker.overloads(algo, n)}
    pub_methods = sorted(n for n in methods if SNAKE.match(n))
    pub_props = sorted(n for n in props if SNAKE.match(n) and n not in callable_props)
    skipped_names = sorted(n for n in list(methods) + list(props) if not SNAKE.match(n))

    def is_indicator(name):
        for fn in methods[name]:
            ret = ast.unparse(fn.returns) if fn.returns else ""
            if ret.startswith("QuantConnect.Indicators.") and stubs.derives_from(re.sub(r"\[.*", "", ret).split(".")[-1], "IndicatorBase"):
                return True
        return False
    indicators = [n for n in pub_methods if is_indicator(n)]

    print("quantconnect-stubs {}: QCAlgorithm has {} public snake_case methods ({} overload definitions), {} callable "
          "properties ({}) and {} plain properties; {} members in total.".format(
              stubs.version, len(pub_methods), sum(len(methods[n]) for n in pub_methods), len(callable_props),
              ", ".join(sorted(callable_props)), len(pub_props), len(pub_methods) + len(callable_props) + len(pub_props)))
    print("skipped as not snake_case or private: {}".format(", ".join(skipped_names)))
    print("indicator helpers (return type derives from IndicatorBase): {}\n".format(len(indicators)))

    def algo_entity(name, group):
        if name in methods or name in callable_props:
            return Entity("self." + name, name, group, fns=checker.overloads(algo, name), source=source)
        return Entity("self." + name, name, group, prop=props[name], settable=name in settable, source=source)

    entities = [algo_entity(n, "indicator") for n in indicators]
    entities += [algo_entity(n, "common") for n in COMMON]
    for prefix, module, cls_name, only in OTHER:
        cls = stubs.get(module, cls_name)
        m, p, s = split_members(cls)
        src = "quantconnect-stubs {} QuantConnect/{}/__init__.pyi class {}".format(stubs.version, module.replace(".", "/"), cls_name)
        for name in sorted(set(m) | set(p)):
            if SNAKE.match(name) and (only is None or name in only):
                entities.append(Entity(prefix + name, name, "common", fns=m.get(name), prop=p.get(name) if name not in m else None,
                                       settable=name in s, source=src))

    # Usage ranking over the training templates (test templates are a different folder and are not read).
    usage = collections.Counter()
    all_names = set(pub_methods) | callable_props | set(pub_props)
    for path in sorted(TRAIN_TEMPLATES.glob("*/main.py")):
        code = path.read_text(encoding="utf-8")
        usage.update(n for n in re.findall(r"\bself\.([a-z][a-z0-9_]*)\b", code) if n in all_names)
        usage.update(n for n in re.findall(r"^\s*def (on_[a-z0-9_]+)\(", code, re.M) if n in all_names)
    have = {e.display for e in entities}
    ranked = [(n, c) for n, c in usage.most_common() if "self." + n not in have]

    def build(top):
        return entities + [algo_entity(n, "usage") for n, _c in ranked[:top]]

    def n_records(ents):
        total = 0
        for e in ents:
            total += 1 + (1 if (e.group == "indicator" or e.display in HAND or e.display in RULE_ARGS) else 0) \
                     + (1 if e.group == "indicator" else 0)
        return total
    full = len(all_names) * 2 + len(indicators)
    top = min(args.top, len(ranked))
    while top > 0 and n_records(build(top)) > args.cap:
        top -= 1
    print("Full QCAlgorithm surface would be about {} records (two per member, three per indicator helper); cap is {}.".format(full, args.cap))
    print("Kept: {} indicator helpers + {} named members (step 2) + the {} most used other members in {} training templates."
          .format(len(indicators), len(entities) - len(indicators), top, len(list(TRAIN_TEMPLATES.glob("*/main.py")))))
    if top:
        print("  usage cutoff: rank {} is self.{} with {} occurrence(s); {} QCAlgorithm members appear in the templates at all, "
              "{} of them outside the named set{}.".format(
                  top, ranked[top - 1][0], ranked[top - 1][1], len(usage), len(ranked),
                  "" if top < len(ranked) else " (fewer than {}, so all were kept)".format(args.top)))
    print("  not covered: {} QCAlgorithm members that no training template uses.\n".format(
        len(all_names) - len({e.name for e in build(top) if e.display.startswith("self.") and e.display.count(".") == 1})))
    entities = build(top)

    records, problems, no_usage, sig_len = [], [], [], []
    defaults, filled = verified_defaults(), {}
    for index, e in enumerate(entities):
        category = e.display.upper().replace("SELF.", "").replace(".", "_")
        if e.group == "indicator":
            category = "INDICATOR_" + e.name.upper()
        base = dict(category=category, source=e.source, n_errors=0, system=FAQ_SYSTEM, _fixed_lines=[], group=e.group)
        question = code = None
        how = ""
        if e.display in HAND:
            question, code = HAND[e.display]
            how = "Hand-written snippet"
        elif e.display in RULE_ARGS:
            question = "How do I schedule a function with {}?".format(e.display)
            code = rule_snippet(e.display, index)
            how = "Snippet generated from the stub signature"

        if e.prop is not None and not e.fns:
            records.append(dict(base, kind="property", prompt="What is {} in the QuantConnect Python API?".format(e.display),
                                answer=property_answer(e), comment="Type and setter read from {}.".format(e.source)))
            unique = []
        else:
            unique = choose_overload(e, calls_to(code, e.display) if code else [], checker)
            fn = unique[0]
            call_line = None
            if e.group == "indicator":
                made = indicator_snippet(e.name, fn, index)
                if made:
                    code, call_line, resolution = made
                    cls_name = strip(ast.unparse(fn.returns))
                    question = "Show a short example that creates the {} indicator with self.{} and reads its value.".format(words(cls_name), e.name)
                    how = "Snippet generated from the stub signature; argument values are illustrative"
                else:
                    problems.append("{}: no example value for a required argument; usage and resolution records skipped".format(e.display))
            sig = render(e.name, fn)
            known = {n: v for n, v in defaults.get(e.name, {}).items()
                     if e.group == "indicator" and any(p[0] == n and p[2] == "..." for p in params_of(fn))}
            filled.update({e.display + "." + n: v[0] for n, v in known.items()})
            extra = "".join(" The stubs write the default of `{}` as `...`; `{}` was taken from the LEAN source check in "
                            "build_repair_records.py, which records: {}".format(n, v[0], v[1]) for n, v in known.items())
            sig_len.append((len(sig), e.display, sig, len(e.fns)))
            where = "self.{}".format(e.name) if e.display.startswith("self.") and e.display.count(".") == 1 else \
                    ("set_filter on the Option that self.add_option returns" if e.display == "option.set_filter" else e.display)
            records.append(dict(base, kind="signature",
                                prompt="What is the signature of {} in the QuantConnect Python API?".format(where),
                                answer=signature_answer(e, unique, known),
                                comment="Signature, return type and parameter notes read from {} ({} overload definition{} in the stub, "
                                        "{} after merging ones that differ only in argument type).".format(
                                            e.source, len(e.fns), "" if len(e.fns) == 1 else "s", len(unique)) + extra))
            if e.group == "indicator" and call_line and "resolution" in [p[0] for p in params_of(fn)]:
                records.append(dict(base, kind="resolution_slot",
                                    prompt="Which positional slot does the resolution go in for self.{}, and how do I pass it by keyword?".format(e.name),
                                    answer=resolution_answer(e, fn, call_line, resolution),
                                    comment="Slot number computed from {}.".format(e.source)))
            elif e.group == "indicator" and call_line:
                problems.append("{}: no resolution parameter in the stub; resolution record skipped".format(e.display))

        if code is None:
            no_usage.append(e.display)
            continue
        bad = checker.check(code, algo)
        if not 3 <= count_lines(code) <= 8:
            bad.append("snippet has {} lines".format(count_lines(code)))
        if unique and e.display in HAND and not e.name.startswith("on_") and not any(
                binds(c, unique[0]) for c in calls_to(code, e.display)):
            bad.append("snippet does not call the described overload")
        if bad:
            problems.append("{}: usage record dropped: {}".format(e.display, "; ".join(bad)))
            continue
        records.append(dict(base, kind="usage", prompt=question, answer="```python\n{}\n```".format(code),
                            comment="{}; every self.* call, property member and enum member in it was checked against "
                                    "quantconnect-stubs {}. Not backtested.".format(how, stubs.version)))

    # Dedupe inside the set, then against repair_records.jsonl.
    seen, kept = {}, []
    for r in records:
        key = (r["prompt"], r["answer"])
        if key in seen or r["prompt"] in {k[0] for k in seen}:
            problems.append("duplicate prompt dropped: {}".format(r["prompt"]))
            continue
        seen[key] = True
        kept.append(r)
    records = kept
    superseded = []
    if REPAIR_RECORDS.exists():
        mine = {r["category"] for r in records}
        prompts = [(tokens(r["prompt"]), r) for r in records]
        for line in REPAIR_RECORDS.read_text(encoding="utf-8").splitlines():
            old = json.loads(line)
            user = old["messages"][1]["content"]
            if old.get("kind") == "signature" and old.get("category") in mine:
                superseded.append((old["category"], user, "same indicator"))
            elif old.get("kind") != "repair":
                best = max(prompts, key=lambda p: jaccard(tokens(user), p[0]))
                if jaccard(tokens(user), best[0]) >= 0.6:
                    superseded.append((old["category"], user, "prompt Jaccard {:.2f} with: {}".format(
                        jaccard(tokens(user), best[0]), best[1]["prompt"])))
        note = {}
        for cat, user, _why in superseded:
            note.setdefault(cat, []).append(user)
        for r in records:
            if r["category"] in note and r["group"] == "indicator":
                r["comment"] += " Supersedes the hand-written {} records in repair_records.jsonl.".format(r["category"])

    leakage_checks(records)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    upload = out.with_name(out.stem + "_upload.jsonl")
    with open(out, "w", encoding="utf-8") as full_file, open(upload, "w", encoding="utf-8") as up_file:
        for r in records:
            messages = [{"role": "system", "content": r["system"]}, {"role": "user", "content": r["prompt"]},
                        {"role": "assistant", "content": r["answer"]}]
            full_file.write(json.dumps({"messages": messages, "kind": r["kind"], "category": r["category"], "source": r["source"],
                                        "max_prompt_sim": r["max_prompt_sim"], "max_code_sim": r["max_code_sim"],
                                        "comment": r["comment"]}, ensure_ascii=False) + "\n")
            up_file.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")

    kinds = collections.Counter(r["kind"] for r in records)
    groups = collections.Counter((r["group"], r["kind"]) for r in records)
    print("wrote {} records to {}\n  and the messages-only copy to {}\n".format(len(records), out, upload))
    print("Members covered: {} ({} indicator helpers, {} named, {} by usage)".format(
        len(entities), len(indicators), sum(e.group == "common" for e in entities), sum(e.group == "usage" for e in entities)))
    print("Records per kind: " + ", ".join("{} {}".format(k, v) for k, v in sorted(kinds.items())))
    for g in ("indicator", "common", "usage"):
        print("  {:<10}".format(g) + ", ".join("{} {}".format(k[1], v) for k, v in sorted(groups.items()) if k[0] == g))
    print("\nMembers with a signature or property record but no usage record ({}): {}".format(len(no_usage), ", ".join(no_usage)))
    print("\nDefaults filled from build_repair_records.py ({}): {}".format(
        len(filled), ", ".join("{} = {}".format(k, v) for k, v in sorted(filled.items()))))
    print("\nProblems ({}):".format(len(problems)))
    for p in problems:
        print("  " + p)
    if checker.unverified:
        print("Enum-style names whose class is not in the stubs (not checked): " + ", ".join(sorted(checker.unverified)))

    print("\nSuperseded records in repair_records.jsonl ({}; that file is not modified):".format(len(superseded)))
    for cat, n in sorted(collections.Counter(c for c, _u, _w in superseded).items()):
        print("  {:<18} {} record(s)".format(cat, n))
    for cat, user, why in superseded:
        if why != "same indicator":
            print("  {} | {} | {}".format(cat, user, why))

    print("\n10 longest signatures:")
    for length, display, sig, n in sorted(sig_len, reverse=True)[:10]:
        print("  [{} chars, {} overload definitions] {}\n    {}".format(length, n, display, sig))

    eval_prompts = [tokens(json.loads(l)["prompt"]) for l in EVAL_PROMPTS.read_text().splitlines() if l.strip()]
    worst = max(records, key=lambda r: r["max_prompt_sim"])
    print("\nLeakage vs prompts_100.jsonl ({} prompts, token Jaccard, build_dataset threshold 0.6):".format(len(eval_prompts)))
    print("  max = {} ({}: {})".format(worst["max_prompt_sim"], worst["kind"], worst["prompt"]))
    print("  max answer-code similarity vs test templates = {}".format(max(r["max_code_sim"] for r in records)))
    hits = [r for r in records if r["template_line_match"]]
    print("  records with a code line identical to a test-template line: {}".format(len(hits)))
    for r in hits:
        print("    {} {} -> {}".format(r["kind"], r["category"], ", ".join(r["template_line_match"])))

    print("\nSamples:")
    for kind, cat in (("signature", "INDICATOR_BB"), ("resolution_slot", "INDICATOR_BB"), ("usage", "INDICATOR_BB"),
                      ("signature", "HISTORY"))[:args.samples + 1]:
        for r in records:
            if r["kind"] == kind and r["category"] == cat:
                print("--- {} / {}\nQ: {}\nA: {}\n".format(kind, cat, r["prompt"], r["answer"]))


if __name__ == "__main__":
    main()
