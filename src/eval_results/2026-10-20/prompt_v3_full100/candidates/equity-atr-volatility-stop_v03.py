from AlgorithmImports import *


class AtrTrailingStop(QCAlgorithm):
    """
    A trailing stop strategy for SPY using ATR.
    Buys SPY with all capital, tracks the highest close since entry,
    and sells if the close drops below (highest close - 3 * ATR).
    Re-enters on the next bar after a stop-out.
    """

    def initialize(self):
        # Set start, end, and cash
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY with minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # ATR indicator with 14 period
        self._atr = self.atr("SPY", 14, resolution=Resolution.MINUTE)

        # State variables
        self._highest_close = 0.0
        self._in_position = False
        self._stop_level = 0.0

        # Chart for plotting stop level and trailing high
        self._chart = self.add_chart("Stop")
        self._plot_stop = self._chart.plot("Stop Level")
        self._plot_high = self._chart.plot("Trailing High")

        # Schedule daily check at market open to handle re-entry logic
        # We'll use on_data for the main logic since we need minute-level closes

    def on_data(self, data: Slice):
        # Wait until ATR is ready
        if not self._atr.is_ready:
            return

        if "SPY" not in data:
            return

        bar = data["SPY"]
        close = bar.close
        atr_value = self._atr.current.value

        # If we are not in a position, try to buy
        if not self._in_position:
            # Buy SPY with all available capital
            self.set_holdings("SPY", 1.0)
            self._in_position = True
            self._highest_close = close
            self._stop_level = close - 3 * atr_value
            self.log(f"BUY SPY at {close:.2f}, ATR={atr_value:.2f}, Stop={self._stop_level:.2f}")
        else:
            # Update the highest close
            if close > self._highest_close:
                self._highest_close = close

            # Update the stop level
            self._stop_level = self._highest_close - 3 * atr_value

            # Check if close drops below the stop level
            if close < self._stop_level:
                self.log(f"STOP HIT: Close {close:.2f} < Stop {self._stop_level:.2f}. Selling SPY.")
                self.liquidate("SPY")
                self._in_position = False
                self._highest_close = 0.0
                self._stop_level = 0.0

        # Plot the stop level and trailing high
        if self._in_position:
            self._plot_stop(bar.time, self._stop_level)
            self._plot_high(bar.time, self._highest_close)
        else:
            # Plot zero or skip when not in position
            self._plot_stop(bar.time, 0)
            self._plot_high(bar.time, 0)
