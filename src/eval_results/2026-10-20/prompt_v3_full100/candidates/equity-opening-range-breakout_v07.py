from AlgorithmImports import *


class OpeningRangeBreakoutAlgorithm(QCAlgorithm):
    """
    Intraday opening-range breakout reference on SPY for Sep-Dec 2024.
    Single trade per session, both directions, flat before close.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # Track state
        self._traded_today = False
        self._current_date = None
        self._opening_high = None
        self._opening_low = None
        self._opening_range_minutes = 15  # 15-minute opening range

        # Schedule: check for new day at market open, and manage exit before close
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(9, 30),
            self._on_market_open
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.before_market_close(self.spy, 5),
            self._before_close
        )

    def _on_market_open(self):
        """Reset daily state at market open."""
        today = self.spy.home_time.date
        if self._current_date != today:
            self._current_date = today
            self._traded_today = False
            self._opening_high = None
            self._opening_low = None

    def on_data(self, data: Slice):
        if not self.spy.has_data:
            return

        bar = data[self.spy]
        if bar is None:
            return

        today = self.spy.home_time.date
        if self._current_date != today:
            self._current_date = today
            self._traded_today = False
            self._opening_high = None
            self._opening_low = None

        # Only trade during regular market hours
        if not self.spy.is_tradable:
            return

        # Build opening range during first 15 minutes
        if self._opening_high is None or self._opening_low is None:
            minutes_since_open = (bar.end_time - self.spy.home_time.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60.0
            if minutes_since_open <= self._opening_range_minutes:
                if self._opening_high is None:
                    self._opening_high = bar.high
                    self._opening_low = bar.low
                else:
                    self._opening_high = max(self._opening_high, bar.high)
                    self._opening_low = min(self._opening_low, bar.low)
                return

        # Opening range not yet complete
        if self._opening_high is None or self._opening_low is None:
            return

        # If already traded today, just manage exit
        if self._traded_today:
            return

        # Check for breakout
        price = bar.close
        if price > self._opening_high:
            # Breakout above opening range - go long
            self._traded_today = True
            self.set_holdings(self.spy, 1.0)
            self.Log(f"Long breakout at {price:.2f}, OR high: {self._opening_high:.2f}")
        elif price < self._opening_low:
            # Breakout below opening range - go short
            self._traded_today = True
            self.set_holdings(self.spy, -1.0)
            self.Log(f"Short breakout at {price:.2f}, OR low: {self._opening_low:.2f}")

    def _before_close(self):
        """Liquidate any position before market close."""
        if self.portfolio[self.spy].quantity != 0:
            self.liquidate(self.spy)
            self.Log(f"Flattened position before close. Price: {self.securities[self.spy].price:.2f}")
        self._traded_today = False
