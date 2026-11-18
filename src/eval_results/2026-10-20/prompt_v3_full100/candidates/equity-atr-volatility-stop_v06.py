from AlgorithmImports import *


class TrailingAtrStrategy(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        self.settings.automatic_indicator_warm_up = True
        self._atr = self.atr("SPY", 14, resolution=Resolution.MINUTE)

        self._trailing_high = 0.0
        self._stop = 0.0

        self.plot("Trailing High", "Trailing High", self._trailing_high)
        self.plot("Stop", "Stop", self._stop)

    def on_data(self, data: Slice):
        if not self._atr.is_ready:
            return

        if "SPY" not in data.bars:
            return

        bar = data.bars["SPY"]
        close = bar.close
        atr_value = self._atr.current.value

        if self.portfolio["SPY"].quantity == 0:
            self._trailing_high = close
            self._stop = close - 3 * atr_value
            self.set_holdings("SPY", 1.0)
            return

        if close > self._trailing_high:
            self._trailing_high = close

        self._stop = self._trailing_high - 3 * atr_value

        if close < self._stop:
            self.liquidate("SPY")
            self._trailing_high = close
            self._stop = close - 3 * atr_value
