"""
Root-cause classifier for cached evaluation records (runs/<model>/<prompt>.json).

taxonomy.py says WHICH STAGE failed (RUNTIME_ERROR, COMPILE_ERROR, NO_CODE).
This module says WHY: it reads the QuantConnect error text, the stack trace
and the generated source, and assigns exactly one primary category per record.

Offline only: no network, no QuantConnect or model calls.

    from qc_eval.error_classifier import classify_record
    result = classify_record(record)   # record = one cached JSON, already loaded
    result["outcome"], result["category"], result["domain"], result["latent"]

Three outputs per record:
  category  one primary root cause (first failure only; rules are ordered,
            most specific first, so a record is counted once)
  domain    which part of the LEAN API the failing line touches (heuristic)
  latent    static tags found anywhere in the source, whether or not they
            caused the crash. A backtest stops at its first error, so these
            show problems the first error hides.
"""

from __future__ import annotations

import ast
import html
import re
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorCategory:
    code: str
    stage: str          # generation | syntax | import | runtime | infra | none
    title: str
    rule: str           # human-readable detection rule (regexes are below)


ERROR_CATEGORIES = {c.code: c for c in [
    ErrorCategory("CLEAN", "none", "Backtest completed",
                  "qc_evaluation.status == 'completed'"),

    # --- generation ---
    ErrorCategory("GEN_LOOP_TRUNCATED", "generation",
                  "Output looped or rambled until the token limit (no usable code)",
                  "non-empty output with no closed ```python block (has_code false), "
                  "or extracted source still starts with a ``` fence"),
    ErrorCategory("GEN_EMPTY_OUTPUT", "generation",
                  "Empty response (no text returned)",
                  "output is empty"),

    # --- syntax / compile ---
    ErrorCategory("SYNTAX_ERROR", "syntax", "Code is not valid Python",
                  "status in (syntax_error, compile_error) and source does not start with a fence"),

    # --- runtime: ordered, first match wins ---
    ErrorCategory("RESOLUTION_POSITIONAL", "runtime",
                  "Resolution passed positionally into an indicator's moving-average-type slot",
                  r"regex: expected MovingAverageType, got Resolution"),
    ErrorCategory("WRONG_IMPORT", "import",
                  "Wrong import / namespace model (no `from AlgorithmImports import *`)",
                  r"source lacks `from AlgorithmImports import *` AND (regex: cannot import name|No module named "
                  r"OR failure is at module load OR the message is a bare CLR namespace name such as 'Resolution')"),
    ErrorCategory("LEGACY_PASCALCASE", "runtime",
                  "Legacy PascalCase method called on the algorithm",
                  r"regex: object has no attribute '[A-Z]\w+' and the failing line calls self.<PascalCase>("),
    ErrorCategory("UNDEFINED_NAME", "runtime",
                  "Invented class, enum or helper name (NameError)",
                  r"regex: name '(\w+)' is not defined"),
    ErrorCategory("ARG_MISMATCH_OTHER", "runtime",
                  "Wrong argument types or order (other than the Resolution slot)",
                  r"regex: Trying to dynamically access a method that does not exist|No method matches given arguments "
                  r"(after RESOLUTION_POSITIONAL has been ruled out)"),
    ErrorCategory("HALLUCINATED_ALGO_METHOD", "runtime",
                  "Invented method on the algorithm (self.<method> that LEAN does not have)",
                  r"regex: '<AlgorithmClass>' object has no attribute '<name>' where <name> has no leading underscore"),
    ErrorCategory("UNDEFINED_SELF_STATE", "runtime",
                  "Uses its own self._attribute or self._method that it never defined",
                  r"regex: '<AlgorithmClass>' object has no attribute '_<name>'"),
    ErrorCategory("SYMBOL_SECURITY_CONFUSION", "runtime",
                  "Treats a Symbol as a Security (wrong return-type handling)",
                  r"regex: 'Symbol' object has no attribute"),
    ErrorCategory("HALLUCINATED_MEMBER", "runtime",
                  "Invented attribute or method on a real LEAN / pandas object",
                  r"regex: '<Type>' object has no attribute|type object '<Type>' has no attribute "
                  r"(Type is not the algorithm class and not Symbol)"),
    ErrorCategory("PYTHON_LOGIC_ERROR", "runtime",
                  "Plain Python logic error (division by zero, bad operand)",
                  r"regex: division by zero|bad operand type|argument must be a string"),
    ErrorCategory("OTHER_RUNTIME", "runtime", "Other runtime error",
                  "runtime_error not matched by any rule above"),

    # --- not the model's fault ---
    ErrorCategory("INFRA_TIMEOUT", "infra", "QuantConnect request timed out (not a model error)",
                  "status == 'infrastructure_error'"),
]}

# Latent (static, non-exclusive) tags.
LATENT_TAGS = {
    "RESOLUTION_POSITIONAL": "self.rsi / self.bb / self.atr called with Resolution.X as a positional "
                             "argument in the moving-average-type slot",
    "NO_ALGORITHM_IMPORTS": "source has no `from AlgorithmImports import *`",
    "LEGACY_PASCALCASE": "calls self.<PascalCase>( (static finding LEGACY_API)",
    "UNKNOWN_SELF_METHOD": "calls a self.<method> outside the known LEAN list (static finding UNKNOWN_API)",
    "MISSING_READY_CHECK": "creates indicators but never checks readiness (static finding MISSING_READY_CHECK)",
    "ADD_EQUITY_NO_RESOLUTION": "add_equity called with no Resolution at all (not an error by itself; LEAN falls back to its default)",
    "SYNTAX_ERROR": "source does not parse (static finding SYNTAX_ERROR)",
}

# Index of the moving-average-type parameter, read off the signatures that
# QuantConnect printed in the cached error messages:
#   rsi(symbol, period, moving_average_type, resolution, selector)
#   bb(symbol, period, k, moving_average_type, resolution, selector)
#   atr(symbol, period, type, resolution, selector)
# Other indicators may have the same shape; add them only once a QC message
# confirms the signature.
MA_TYPE_SLOT = {"rsi": 2, "bb": 3, "atr": 2}

DOMAIN_RULES = [
    ("scheduling", re.compile(r"schedule\.on|date_rules|time_rules|DateRules|TimeRules")),
    ("options", re.compile(r"[Oo]ption(?!al)|iron_condor|straddle|strike|expiry|InterestRate")),
    ("futures", re.compile(r"[Ff]uture|Indices|SP_500|data_mapping|SymbolChanged")),
    ("universe", re.compile(r"[Uu]niverse|[Cc]onstituent|_select_assets|dollar_volume|ETF\b|Market\.ETF|SecurityType\.ETF")),
    ("indicators", re.compile(
        r"self\.(rsi|bb|atr|roc|sma|ema|max|min|mom|momp|std|macd)\(|IndicatorExtensions|[Ii]ndicator|is_ready|"
        r"is_warming_up|warm_up|RollingWindow|Resolution\.|\.roc\b|[Rr]egression|consolidat")),
    ("portfolio/orders", re.compile(r"portfolio|[Pp]ortfolioTarget|set_holdings|holdings|invested|_order|Order|liquidate")),
]

_RE_RES_SLOT = re.compile(r"expected MovingAverageType, got Resolution")
_RE_IMPORT = re.compile(r"cannot import name|No module named")
_RE_NAME = re.compile(r"name '(\w+)' is not defined")
_RE_SIG = re.compile(r"Trying to dynamically access a method that does not exist|No method matches given arguments")
_RE_SIG_METHOD = re.compile(r"required by the ([\w.]+) method")
_RE_ARG = re.compile(r"Argument mismatch: ([^\n]*)")
_RE_OBJ_ATTR = re.compile(r"'(\w+(?:\[\w+\])?)' object has no attribute '(\w+)'")
_RE_TYPE_ATTR = re.compile(r"type object '(\w+)' has no attribute '(\w+)'")
_RE_LOGIC = re.compile(r"division by zero|bad operand type|argument must be a string")
_RE_LOADER = re.compile(r"^.*?AlgorithmPythonWrapper\(\): ", re.DOTALL)
_RE_FRAME = re.compile(r"\n\s+at ([\w<>]+)\n\s*([^\n]*)\n[^\n]*\n in ([\w.]+): line (\d+)")
_RE_DID_YOU_MEAN = re.compile(r"Did you mean.*$")
_RE_BARE_IDENT = re.compile(r"^\w+$")
_ALGO_IMPORT = "from AlgorithmImports import"


# --------------------------------------------------------------------------
# Text extraction
# --------------------------------------------------------------------------

def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = "\n".join(str(v) for v in value)
    return html.unescape(str(value))


def error_parts(record: dict) -> dict:
    """Pull the comparable pieces out of one cached record.

    message  the exception text with the LEAN loader boilerplate removed
    frame    the function the first stack frame is in ('initialize', '<module>', ...)
    line     the offending source line from the first stack frame
    """
    qc = record.get("qc_evaluation") or {}
    status = qc.get("status")
    trace = _as_text(qc.get("stacktrace")) or _as_text(qc.get("error"))
    if status in ("syntax_error", "compile_error"):
        errors = [e for e in _as_text(qc.get("error")).split("\n") if "Warning " not in e]
        trace = "\n".join(errors) or _as_text(qc.get("qc_note"))
    head = trace.split("\n  at ")[0].strip()
    message = _RE_LOADER.sub("", head).strip()
    # Prefer the first frame that is in the generated file, not in a library.
    frames = _RE_FRAME.findall(trace)
    own = [f for f in frames if f[2] == "main.py"]
    frame = (own or frames or [("", "", "", "")])[0]
    return {
        "status": status,
        "message": " ".join(message.split()),
        "frame": frame[0],
        "line": frame[1].strip(),
        "module_load": "Unable to import python module" in trace or frame[0] == "<module>",
        "trace": trace,
        "source": qc.get("source") or "",
    }


def outcome_of(record: dict) -> str:
    """clean | runtime_error | compile_error | no_code | unknown"""
    qc = record.get("qc_evaluation") or {}
    status = qc.get("status")
    if status == "completed":
        return "clean"
    if status == "runtime_error":
        return "runtime_error"
    if status in ("syntax_error", "compile_error"):
        return "compile_error"
    if not qc and not record.get("has_code"):
        return "no_code"
    return "unknown"


# --------------------------------------------------------------------------
# Primary category
# --------------------------------------------------------------------------

def _algo_class_names(source: str) -> set:
    return set(re.findall(r"^class\s+(\w+)\s*\(", source, re.MULTILINE))


def classify_runtime(parts: dict) -> tuple:
    """Return (category_code, detail, ambiguity_note) for a runtime error."""
    msg, line, source, trace = parts["message"], parts["line"], parts["source"], parts["trace"]
    no_algo_import = _ALGO_IMPORT not in source

    if _RE_RES_SLOT.search(trace):
        method = _RE_SIG_METHOD.search(trace)
        return "RESOLUTION_POSITIONAL", method.group(1) if method else "", ""

    if no_algo_import and (_RE_IMPORT.search(msg) or parts["module_load"] or _RE_BARE_IDENT.match(msg)):
        return "WRONG_IMPORT", msg[:80], ""

    obj = _RE_OBJ_ATTR.search(msg)
    if obj and obj.group(2)[0].isupper() and re.search(r"self\.[A-Z]\w*\(", line):
        note = "also WRONG_IMPORT: no AlgorithmImports line" if no_algo_import else ""
        return "LEGACY_PASCALCASE", obj.group(2), note

    name = _RE_NAME.search(msg)
    if name:
        note = "fails at module load (name used in a class body, base class or annotation)" \
            if parts["module_load"] else ""
        return "UNDEFINED_NAME", name.group(1), note

    if _RE_SIG.search(msg):
        method = _RE_SIG_METHOD.search(trace)
        arg = _RE_ARG.search(trace)
        detail = (method.group(1) if method else "") + (": " + arg.group(1) if arg else "")
        return "ARG_MISMATCH_OTHER", detail, ""

    if obj:
        owner, attr = obj.group(1), obj.group(2)
        if owner in _algo_class_names(source):
            if attr.startswith("_"):
                return "UNDEFINED_SELF_STATE", attr, ""
            return "HALLUCINATED_ALGO_METHOD", attr, ""
        if owner == "Symbol":
            return "SYMBOL_SECURITY_CONFUSION", "Symbol." + attr, "also fits HALLUCINATED_MEMBER; counted here (more specific)"
        return "HALLUCINATED_MEMBER", owner + "." + attr, ""

    typ = _RE_TYPE_ATTR.search(msg)
    if typ:
        return "HALLUCINATED_MEMBER", typ.group(1) + "." + typ.group(2), ""

    if _RE_LOGIC.search(msg):
        return "PYTHON_LOGIC_ERROR", msg[:80], ""

    return "OTHER_RUNTIME", msg[:80], ""


def domain_of(parts: dict) -> str:
    """Which part of the API the failing line touches. Heuristic keyword match."""
    text = parts["line"] + " " + _RE_DID_YOU_MEAN.sub("", parts["message"][:200])
    for name, pattern in DOMAIN_RULES:
        if pattern.search(text):
            return name
    return "other"


# --------------------------------------------------------------------------
# Latent static tags
# --------------------------------------------------------------------------

def positional_resolution_calls(source: str) -> list:
    """self.rsi/bb/atr calls that put Resolution.X in the moving-average slot."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return re.findall(r"self\.(?:rsi|atr)\([^()]*?,\s*\d+\s*,\s*Resolution\.\w+\)|"
                          r"self\.bb\([^()]*?,\s*\d+\s*,\s*[\d.]+\s*,\s*Resolution\.\w+\)", source)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        slot = MA_TYPE_SLOT.get(node.func.attr)
        target = node.func.value
        if slot is None or not (isinstance(target, ast.Name) and target.id == "self"):
            continue
        if len(node.args) > slot:
            arg = node.args[slot]
            if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "Resolution":
                hits.append("self.{}(..., Resolution.{}) line {}".format(node.func.attr, arg.attr, node.lineno))
    return hits


_RE_ADD_CALL = re.compile(r"self\.add_equity\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


def latent_tags(record: dict, source: str) -> list:
    tags = []
    if not source:
        return tags
    if positional_resolution_calls(source):
        tags.append("RESOLUTION_POSITIONAL")
    if _ALGO_IMPORT not in source:
        tags.append("NO_ALGORITHM_IMPORTS")
    static = {f.get("code") for f in record.get("static_findings") or []}
    for finding, tag in (("LEGACY_API", "LEGACY_PASCALCASE"), ("UNKNOWN_API", "UNKNOWN_SELF_METHOD"),
                         ("MISSING_READY_CHECK", "MISSING_READY_CHECK"), ("SYNTAX_ERROR", "SYNTAX_ERROR")):
        if finding in static:
            tags.append(tag)
    adds = _RE_ADD_CALL.findall(source)
    if adds and any("Resolution" not in a and "resolution" not in a for a in adds):
        tags.append("ADD_EQUITY_NO_RESOLUTION")
    return tags


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def classify_record(record: dict) -> dict:
    """Classify one cached record. Never raises on a well-formed record."""
    outcome = outcome_of(record)
    parts = error_parts(record)
    source = parts["source"]
    if not source and record.get("has_code"):
        from .static_checks import extract_code
        source = extract_code(record.get("output") or "") or ""

    category, detail, note, domain = "CLEAN", "", "", ""
    if outcome == "no_code":
        output = record.get("output") or ""
        if output.strip():
            lines = [l for l in output.strip().split("\n") if l.strip()]
            top = max(set(lines), key=lines.count) if lines else ""
            category = "GEN_LOOP_TRUNCATED"
            detail = "most repeated line x{}: {}".format(lines.count(top), top.strip()[:70])
        else:
            category, detail = "GEN_EMPTY_OUTPUT", "0 characters returned"
    elif outcome == "compile_error":
        if source.lstrip().startswith("```"):
            category = "GEN_LOOP_TRUNCATED"
            detail = "unclosed ``` fence; raw output was sent to QC"
            note = "QC reports a syntax error on line 1 (the fence); root cause is truncation"
        else:
            category, detail = "SYNTAX_ERROR", parts["message"][:120]
    elif outcome == "runtime_error":
        category, detail, note = classify_runtime(parts)
        domain = domain_of(parts)
    elif outcome == "unknown":
        category, detail = "INFRA_TIMEOUT", _as_text((record.get("qc_evaluation") or {}).get("qc_note"))[:120]

    return {
        "outcome": outcome,
        "category": category,
        "detail": detail,
        "domain": domain,
        "ambiguity": note,
        "message": parts["message"],
        "frame": parts["frame"],
        "line": parts["line"],
        "latent": latent_tags(record, source),
    }
