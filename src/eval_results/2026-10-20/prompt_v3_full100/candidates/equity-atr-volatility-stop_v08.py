from AlgorithmImports import *


class AtrChandelierStopAlgorithm(QCAlgorithm):
    """ATR chandelier stop reference strategy on SPY."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        self._atr = self.atr("SPY", 14, resolution=Resolution.MINUTE)

        self._trailing_high = None
        self._stop_level = None
        self._pending_reentry = False

    def on_data(self, data: Slice):
        if not self._atr.is_ready:
            return

        if "SPY" not in data:
            return

        bar = data["SPY"]
        close = bar.close
        atr_value = self._atr.current.value

        if atr_value is None or atr_value <= 0:
            return

        if self._pending_reentry:
            self._pending_reentry = False
            self.set_holdings("SPY", 1.0)
            self._trailing_high = close
            self._stop_level = close - 3.0 * atr_value
            return

        if self.portfolio["SPY"].quantity == 0:
            self.set_holdings("SPY", 1.0)
            self._trailing_high = close
            self._stop_level = close - 3.0 * atr_value
            return

        if close > self._trailing_high:
            self._trailing_high = close

        self._stop_level = self._trailing_high - 3.0 * atr_value

        if close < self._stop_level:
            self.liquidate("SPY")
            self._trailing_high = None
            self._stop_level = None
            self._pending_reentry = True
