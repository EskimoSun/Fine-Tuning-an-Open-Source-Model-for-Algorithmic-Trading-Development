from AlgorithmImports import *

class AtrTrailingStopAlgorithm(QCAlgorithm):
    """A simple ATR-based trailing stop strategy for SPY."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.settings.automatic_indicator_warm_up = True

        spy = self.add_equity('SPY', resolution=Resolution.MINUTE)
        self._spy = spy

        self._atr = self.atr(spy.symbol, 14)

        self._trailing_high = 0.0
        self._waiting_to_reenter = False

    def on_data(self, data: Slice):
        if not self._atr.is_ready:
            return

        if self._spy.symbol not in data:
            return

        bar = data[self._spy.symbol]
        close = bar.close

        # Re-entry logic
        if self._waiting_to_reenter:
            self.set_holdings(self._spy.symbol, 1.0)
            self._trailing_high = close
            self._waiting_to_reenter = False
            return

        # Initial entry
        if self.portfolio[self._spy.symbol].invested == 0:
            self.set_holdings(self._spy.symbol, 1.0)
            self._trailing_high = close
            return

        # Update trailing high
        self._trailing_high = max(self._trailing_high, close)

        # Calculate stop
        stop = self._trailing_high - 3.0 * self._atr.current.value

        # Plot for visualization
        self.plot("Trailing High", self._trailing_high)
        self.plot("Stop", stop)

        # Check for stop-out
        if close < stop:
            self.liquidate(self._spy.symbol)
            self._waiting_to_reenter = True
            self._trailing_high = 0.0
