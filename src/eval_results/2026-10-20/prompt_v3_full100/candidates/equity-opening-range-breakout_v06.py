from AlgorithmImports import *


class OpeningRangeBreakoutAlgorithm(QCAlgorithm):
    """
    Opening Range Breakout strategy for SPY.

    - Defines the opening range as the high/low of minute bars in [09:30, 10:00).
    - After 10:00, if close > range high -> 100% long; if close < range low -> 100% short.
    - Only one trade per day; clears the range after a trade.
    - Liquidates at 15:55 and resets the range.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # State attributes
        self._range_high = None
        self._range_low = None
        self._traded_today = False
        self._current_date = None

        # Seed initial prices for plotting
        self._plot_range_high = []
        self._plot_range_low = []
        self._plot_direction = []
        self._plot_times = []

        # Schedule daily liquidation and range reset at 15:55
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(15, 55),
            self._on_daily_liquidate
        )

    def on_data(self, data: Slice):
        if not self.spy in data:
            return

        bar = data[self.spy.symbol]
        current_time = bar.end_time
        current_date = current_time.date()

        # Reset daily state if new trading day
        if self._current_date != current_date:
            self._current_date = current_date
            self._traded_today = False
            self._range_high = None
            self._range_low = None

        # Build opening range during [09:30, 10:00)
        if current_time.hour == 9 and current_time.minute >= 30:
            if self._range_high is None:
                self._range_high = bar.high
                self._range_low = bar.low
            else:
                self._range_high = max(self._range_high, bar.high)
                self._range_low = min(self._range_low, bar.low)

        # After 10:00, check for breakout
        if current_time.hour >= 10 and not self._traded_today and self._range_high is not None:
            if bar.close > self._range_high:
                self.set_holdings(self.spy.symbol, 1.0)
                self._traded_today = True
                self._record_plot(current_time, 1)
            elif bar.close < self._range_low:
                self.set_holdings(self.spy.symbol, -1.0)
                self._traded_today = True
                self._record_plot(current_time, -1)

        # Record range for plotting (only after range is established)
        if self._range_high is not None and current_time.hour >= 10:
            self._record_range_plot(current_time)

    def _on_daily_liquidate(self):
        """Liquidate all positions and reset range at 15:55."""
        self.liquidate(self.spy.symbol)
        self._range_high = None
        self._range_low = None
        self._traded_today = False

    def _record_plot(self, time, direction):
        """Record direction for plotting."""
        self._plot_times.append(time)
        self._plot_direction.append(direction)

    def _record_range_plot(self, time):
        """Record range high/low for plotting."""
        self._plot_times.append(time)
        self._plot_range_high.append(self._range_high)
        self._plot_range_low.append(self._range_low)

    def on_end(self):
        """Plot the range and direction at the end of the algorithm."""
        if self._plot_times:
            self.plot("Range High", self._plot_times, self._plot_range_high)
            self.plot("Range Low", self._plot_times, self._plot_range_low)
            self.plot("Direction", self._plot_times, self._plot_direction)
