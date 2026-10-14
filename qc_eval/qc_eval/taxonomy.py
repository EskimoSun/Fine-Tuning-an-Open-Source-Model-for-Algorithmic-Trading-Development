"""
Error taxonomy for generated QuantConnect (LEAN) algorithms.

Every check in the harness reports findings using one of these categories,
so results from different models can be counted and compared the same way.

Severity:
  "fail"    - the output is wrong (it would not run, or would run incorrectly)
  "warning" - the output is suspicious and worth a human look, but a
              heuristic flagged it, so it may be a false positive
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    code: str
    stage: str        # static | compile | runtime | behavior | meta
    severity: str     # fail | warning
    description: str


CATEGORIES = {c.code: c for c in [
    # --- Static checks (no QuantConnect access needed) ---
    Category("SYNTAX_ERROR", "static", "fail",
             "Code does not parse as Python."),
    Category("NO_ALGORITHM_CLASS", "static", "fail",
             "No class inheriting from QCAlgorithm."),
    Category("NO_INITIALIZE", "static", "fail",
             "Algorithm class has no initialize() method."),
    Category("LEGACY_API", "static", "warning",
             "Uses old PascalCase API (e.g. self.SetStartDate) instead of the current snake_case API."),
    Category("UNKNOWN_API", "static", "warning",
             "Calls a self.<method> that is not in the known LEAN API list and not defined in the class. "
             "Possible hallucination; the known list is incomplete, so check by hand."),
    Category("MISSING_READY_CHECK", "static", "warning",
             "Creates indicators but never checks .is_ready, so it may trade on unwarmed values."),
    Category("LOOKAHEAD_SUSPECT", "static", "warning",
             "Pattern that often reads future data (e.g. pandas .shift(-n))."),
    Category("NO_ORDERS", "static", "fail",
             "Prompt asks for trading but the code never places an order."),
    Category("PROMPT_MISS", "static", "fail",
             "A required element from the prompt (asset, indicator, rule) is missing from the code."),

    # --- QuantConnect cloud stages (need API keys) ---
    Category("COMPILE_ERROR", "compile", "fail",
             "LEAN build failed."),
    Category("RUNTIME_ERROR", "runtime", "fail",
             "Backtest started but crashed."),
    Category("TIMEOUT", "runtime", "fail",
             "Backtest did not finish within the time limit."),

    # --- Behavioral checks (need a reference implementation) ---
    Category("NO_TRADES", "behavior", "fail",
             "Backtest completed but placed zero trades when the strategy should trade."),
    Category("BEHAVIOR_MISMATCH", "behavior", "fail",
             "Trades or key statistics differ from the reference beyond the agreed tolerance."),

    # --- Meta ---
    Category("ABSTAINED", "meta", "warning",
             "Model declined or said it was unsure instead of producing code."),
    Category("NO_CODE", "meta", "fail",
             "No Python code block found in the model output."),
]}


@dataclass
class Finding:
    code: str
    detail: str = ""

    @property
    def category(self) -> Category:
        return CATEGORIES[self.code]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "stage": self.category.stage,
            "severity": self.category.severity,
            "detail": self.detail,
        }
