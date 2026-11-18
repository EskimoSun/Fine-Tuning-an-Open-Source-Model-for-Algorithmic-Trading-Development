"""Contract checks for reviewed repairs; these do not simulate LEAN execution."""

import hashlib
import json
import runpy
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from qc_eval.pipeline import ROOT
from qc_eval.prepare_repairs import prepare


REPAIRS = ROOT / "repairs/qwen_base"


class Bars(dict):
    def contains_key(self, symbol):
        return symbol in self


class TradeBar:
    pass


class History:
    def __init__(self):
        self.closes = []

    def __getitem__(self, data_type):
        if data_type is not TradeBar:
            raise AssertionError("Expected typed TradeBar history")
        return lambda symbol, count, resolution: [types.SimpleNamespace(close=c) for c in self.closes[-count:]]


class QCContract:
    """Expose only the documented API surface used by these three repairs."""
    def __init__(self):
        self.is_warming_up = False
        self.actions = []
        self.history = History()

    def symbol(self, ticker):
        return ticker

    def set_start_date(self, *date):
        self.start_date = date

    def set_end_date(self, *date):
        self.end_date = date

    def set_cash(self, cash):
        self.cash = cash

    def add_equity(self, ticker, resolution):
        if resolution != "hour":
            raise AssertionError("Expected hourly data")
        return types.SimpleNamespace(symbol=ticker)

    def rsi(self, symbol, period, average, resolution):
        self.rsi_arguments = (symbol, period, average, resolution)
        return types.SimpleNamespace(is_ready=True, current=types.SimpleNamespace(value=50))

    def set_warm_up(self, count, resolution):
        self.warm_up = (count, resolution)

    def liquidate(self, symbol=None):
        self.actions.append(("liquidate", symbol))

    def set_holdings(self, symbol, weight):
        self.actions.append(("hold", symbol, weight))


def load_repair(version):
    module = types.ModuleType("AlgorithmImports")
    module.QCAlgorithm = QCContract
    module.Resolution = types.SimpleNamespace(HOUR="hour")
    module.MovingAverageType = types.SimpleNamespace(WILDERS="wilders")
    module.Slice = object
    module.TradeBar = TradeBar
    path = REPAIRS / "equity-rsi-overbought-oversold_v{:02d}.py".format(version)
    with patch.dict("sys.modules", {"AlgorithmImports": module}):
        namespace = runpy.run_path(str(path))
    cls = next(value for value in namespace.values()
               if isinstance(value, type) and value is not QCContract and issubclass(value, QCContract))
    algorithm = cls()
    algorithm.initialize()
    return algorithm


class RepairStrategyTests(unittest.TestCase):
    def test_initialization_uses_current_api_without_shadowing_methods(self):
        expected_dates = {1: (2024, 7, 1), 2: (2024, 9, 1), 4: (2024, 10, 1)}
        for version in (1, 2, 4):
            with self.subTest(version=version):
                algo = load_repair(version)
                self.assertTrue(callable(algo.rsi))
                self.assertTrue(callable(algo.symbol))
                self.assertEqual(algo.start_date, expected_dates[version])
                self.assertEqual(algo.end_date, (2024, 12, 31))
                self.assertEqual(algo.cash, 100000)
                if version != 4:
                    self.assertEqual(algo.rsi_arguments, ("QQQ", 14, "wilders", "hour"))

    def test_v01_retains_extreme_exits_and_same_bar_reversals(self):
        algo = load_repair(1)
        data = types.SimpleNamespace(bars=Bars(QQQ=object()))
        for value in (20, 50, 80, 50, 20):
            algo._rsi.current.value = value
            algo.on_data(data)
        self.assertEqual([a[2] for a in algo.actions if a[0] == "hold"], [1.0, -1.0, 1.0])
        self.assertEqual(sum(a[0] == "liquidate" for a in algo.actions), 2)

    def test_v02_midline_exits_and_no_same_bar_reentry(self):
        algo = load_repair(2)
        data = types.SimpleNamespace(bars=Bars(QQQ=object()))
        for value, expected in ((20, 1), (55, 0), (80, -1), (45, 0)):
            algo._rsi.current.value = value
            algo.on_data(data)
            self.assertEqual(algo._position, expected)
        self.assertEqual([a[2] for a in algo.actions if a[0] == "hold"], [1.0, -1.0])

    def test_warmup_missing_data_and_unready_indicators_do_not_trade(self):
        for version in (1, 2):
            algo = load_repair(version)
            algo._rsi.current.value = 20
            algo.on_data(types.SimpleNamespace(bars=Bars()))
            algo.is_warming_up = True
            algo.on_data(types.SimpleNamespace(bars=Bars(QQQ=object())))
            algo.is_warming_up = False
            algo._rsi.is_ready = False
            algo.on_data(types.SimpleNamespace(bars=Bars(QQQ=object())))
            self.assertEqual(algo.actions, [])

    def test_v04_hourly_history_and_simple_rsi_rule_transitions(self):
        algo = load_repair(4)
        data = types.SimpleNamespace(bars=Bars(QQQ=object()))
        for closes in (list(range(15, 0, -1)), [i % 2 for i in range(15)],
                       list(range(15)), [i % 2 for i in range(15)]):
            algo.history.closes = closes
            algo.on_data(data)
        self.assertFalse(algo._in_position)
        self.assertEqual([a[2] for a in algo.actions if a[0] == "hold"], [1.0, -1.0])
        self.assertEqual(sum(a[0] == "liquidate" for a in algo.actions), 2)
        self.assertIsNone(algo._calculate_rsi([], 14))


class RepairPackagingTests(unittest.TestCase):
    def test_original_is_preserved_and_provenance_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_code = "class Original(QCAlgorithm):\n    pass\n"
            source = root / "runs/qwen_base/prompt.json"
            source.parent.mkdir(parents=True)
            original = {"model_id": "real-model", "generated_at": "original-time", "output": original_code}
            source.write_text(json.dumps(original))
            repaired = root / "repair.py"
            repaired.write_text("class Repaired(QCAlgorithm):\n    pass\n")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"source_model": "qwen_base", "target_model": "qwen_repaired",
                "intervention": "manual_code_repair", "repairs": [{"prompt_id": "prompt",
                "source_sha256": hashlib.sha256(original_code.encode()).hexdigest(),
                "file": "repair.py", "changes": ["test repair"]}]}))
            before = source.read_bytes()
            paths = prepare(manifest, root / "runs")
            self.assertEqual(source.read_bytes(), before)
            record = json.loads(paths[0].read_text())
            self.assertEqual(record["intervention"], "manual_code_repair")
            self.assertEqual(record["repair"]["source_model"], "qwen_base")
            source.write_text(json.dumps(dict(original, output=original_code + "# changed")))
            with self.assertRaisesRegex(ValueError, "Source changed"):
                prepare(manifest, root / "runs")


if __name__ == "__main__":
    unittest.main()
