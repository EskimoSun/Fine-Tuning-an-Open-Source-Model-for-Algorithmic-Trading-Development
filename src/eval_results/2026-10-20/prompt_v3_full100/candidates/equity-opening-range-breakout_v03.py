from AlgorithmImports import *


class OpeningRangeBreakout(QCAlgorithm):
    """Opening Range Breakout strategy for SPY.

    Tracks the high and low of the first 30 minutes (9:30-10:00 ET).
    After 10:00, buys on a close above the range high or shorts on a close
    below the range low. Only one trade per day. Closes at 3:55 PM ET.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Seed starting prices so the algorithm can run without live data
        self.set_prices({
            "SPY": 550.0,
        })

        # Add SPY at minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # State variables
        self._range_high = None
        self._range_low = None
        self._traded_today = False
        self._current_day = None
        self._trade_direction = 0  # 1 = long, -1 = short, 0 = flat

        # Charts
        self._orb_chart = self.add_chart("ORB")
        self._orb_high_series = self._orb_chart.add_series("Range High", "#FF0000", "-", 1, 1)
        self._orb_low_series = self._orb_chart.add_series("Range Low", "#00FF00", "-", 1, 1)

        self._trades_chart = self.add_chart("Trades")
        self._trades_series = self._trades_chart.add_series("Direction", "#0000FF", "-", 1, 1)

        # Schedule: check for new day at 9:30, evaluate breakout after 10:00, close at 3:55
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(9, 30),
            self._on_new_day
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(10, 0),
            self._on_breakout_check
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(15, 55),
            self._on_close_position
        )

    def _on_new_day(self):
        """Reset daily state at 9:30 AM."""
        today = self.now.date()
        if self._current_day != today:
            self._current_day = today
            self._range_high = None
            self._range_low = None
            self._traded_today = False
            self._trade_direction = 0

    def on_data(self, data: Slice):
        if not self.spy.is_warm_up:
            return

        if "SPY" not in data:
            return

        bar = data["SPY"]
        current_time = self.now

        # Track the opening range from 9:30 to 10:00
        if self._current_day is None or current_time.date() != self._current_day:
            self._current_day = current_time.date()
            self._range_high = None
            self._range_low = None
            self._traded_today = False
            self._trade_direction = 0

        # Only track range during 9:30 - 10:00
        if current_time.hour == 9 and current_time.minute >= 30:
            if self._range_high is None or bar.high > self._range_high:
                self._range_high = bar.high
            if self._range_low is None or bar.low < self._range_low:
                self._range_low = bar.low

            # Plot the range on the ORB chart
            self._orb_high_series.plot(current_time, self._range_high)
            self._orb_low_series.plot(current_time, self._range_low)

        # After 10:00, check for breakout
        if current_time.hour >= 10 and not self._traded_today:
            if self._range_high is not None and self._range_low is not None:
                if bar.close > self._range_high:
                    # Buy with everything
                    self.set_holdings("SPY", 1.0)
                    self._traded_today = True
                    self._trade_direction = 1
                    self._trades_series.plot(current_time, 1)
                    self.log(f"Long breakout at {current_time}: close {bar.close:.2f} > high {self._range_high:.2f}")
                elif bar.close < self._range_low:
                    # Short with everything
                    self.set_holdings("SPY", -1.0)
                    self._traded_today = True
                    self._trade_direction = -1
                    self._trades_series.plot(current_time, -1)
                    self.log(f"Short breakout at {current_time}: close {bar.close:.2f} < low {self._range_low:.2f}")

    def _on_breakout_check(self):
        """Placeholder for scheduled breakout check (handled in on_data)."""
        pass

    def _on_close_position(self):
        """Close all positions at 3:55 PM."""
        if self.portfolio["SPY"].quantity != 0:
            self.liquidate("SPY")
            self.log(f"Closed position at {self.now}")
        self._traded_today = False
        self._trade_direction = 0
        self._trades_series.plot(self.now, 0)
