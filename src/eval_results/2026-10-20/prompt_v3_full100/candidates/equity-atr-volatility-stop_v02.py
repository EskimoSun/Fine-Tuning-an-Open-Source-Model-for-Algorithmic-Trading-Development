from AlgorithmImports import *


class AtrTrailingStopAlgorithm(QCAlgorithm):
    """
    Buy and hold SPY with all capital. Track the highest close since entry.
    Use a 14-period ATR. If the close drops below (highest close - 3 * ATR),
    liquidate everything. On the next bar, re-enter and reset the high tracker.
    """

    def initialize(self):
        # Set start, end, and cash
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY with minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # 14-period ATR on SPY
        self._atr = self.atr("SPY", 14, resolution=Resolution.MINUTE)

        # State variables
        self._highest_close = 0.0
        self._in_position = False
        self._should_reenter = False

    def on_data(self, data: Slice):
        # Wait until ATR is ready
        if not self._atr.is_ready:
            return

        if "SPY" not in data:
            return

        bar = data["SPY"]
        close = bar.close
        atr_value = self._atr.current.value

        # If we are not in a position and we are waiting to re-enter, buy now
        if not self._in_position and self._should_reenter:
            self.set_holdings("SPY", 1.0)
            self._in_position = True
            self._should_reenter = False
            # Initialize the highest close tracker with the current close
            self._highest_close = close
            return

        # If we are in a position, update the highest close
        if self._in_position:
            if close > self._highest_close:
                self._highest_close = close

            # Check trailing stop condition
            stop_level = self._highest_close - 3.0 * atr_value
            if close < stop_level:
                # Sell everything
                self.liquidate("SPY")
                self._in_position = False
                self._should_reenter = True
                # Reset highest close; will be set on re-entry
                self._highest_close = 0.0
