from AlgorithmImports import *

class TrailingStopStrategy(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        self._atr = self.atr("SPY", 14, resolution=Resolution.MINUTE)

        self._trailing_high = None
        self._in_position = False

    def on_data(self, data: Slice):
        if not self._atr.is_ready:
            return

        if "SPY" not in data:
            return

        bar = data["SPY"]
        if bar.is_trade:
            return

        price = bar.close
        atr_value = self._atr.current.value

        if not self._in_position:
            # Re-enter 100%
            self.set_holdings("SPY", 1.0)
            self._in_position = True
            self._trailing_high = price
            return

        # Update trailing high
        if price > self._trailing_high:
            self._trailing_high = price

        stop = self._trailing_high - 3 * atr_value

        if price < stop:
            self.liquidate("SPY")
            self._in_position = False
            self._trailing_high = None
