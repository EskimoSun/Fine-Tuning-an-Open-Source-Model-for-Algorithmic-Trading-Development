from AlgorithmImports import *


class OpeningRangeBreakoutAlgorithm(QCAlgorithm):
    """Opening-range breakout reference on SPY (2024-09-01 to 2024-12-31)."""

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        self._range_high = None
        self._range_low = None
        self._entered_today = False
        self._current_day = None

        # Collect the 09:30-10:00 range and evaluate the breakout after 10:00.
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(9, 30),
            self._start_range_window,
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(10, 0),
            self._evaluate_breakout,
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(15, 55),
            self._exit_position,
        )

    def _start_range_window(self):
        """Reset the daily range and entry flag at 09:30."""
        self._range_high = None
        self._range_low = None
        self._entered_today = False
        self._current_day = self.now.date

    def on_data(self, data: Slice):
        if self.spy.symbol not in data:
            return

        bar = data[self.spy.symbol]
        if not bar.is_traded:
            return

        # Accumulate the opening range from 09:30 (inclusive) to 10:00 (exclusive).
        if self._current_day is not None and bar.end_time.date == self._current_day:
            if bar.end_time.hour == 9 and bar.end_time.minute >= 30:
                if self._range_high is None or bar.high > self._range_high:
                    self._range_high = bar.high
                if self._range_low is None or bar.low < self._range_low:
                    self._range_low = bar.low

    def _evaluate_breakout(self):
        """After 10:00, enter on the first close outside the opening range."""
        if self._entered_today:
            return
        if self._range_high is None or self._range_low is None:
            return

        price = self.securities[self.spy.symbol].price
        if price > self._range_high:
            self.set_holdings(self.spy.symbol, 1.0)
            self._entered_today = True
            self.log(f"Long entry at {price:.2f} above range high {self._range_high:.2f}")
        elif price < self._range_low:
            self.set_holdings(self.spy.symbol, -1.0)
            self._entered_today = True
            self.log(f"Short entry at {price:.2f} below range low {self._range_low:.2f}")

    def _exit_position(self):
        """Liquidate at 15:55 and reset the daily state."""
        if self.portfolio[self.spy.symbol].quantity != 0:
            self.liquidate(self.spy.symbol)
            self.log(f"Exiting position at {self.securities[self.spy.symbol].price:.2f}")
        self._range_high = None
        self._range_low = None
        self._entered_today = False
        self._current_day = None
