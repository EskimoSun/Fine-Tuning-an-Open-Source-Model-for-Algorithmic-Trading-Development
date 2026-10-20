from AlgorithmImports import *


class SpyMorningBreakout(QCAlgorithm):
    """
    Day-trading backtest for SPY that trades the morning breakout.

    Strategy:
      - Watch the first N minutes of the trading session (default 30).
      - Track the high and low of that window.
      - Go long if price breaks above the window high.
      - Go short if price breaks below the window low.
      - Only one position at a time; no re-entry after the first trigger.
      - Flatten the position before the market close.
    """

    def initialize(self):
        # Use minute data for intraday precision.
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # Parameters
        self.watch_minutes = 30          # length of the opening window to observe
        self.position_fraction = 0.95    # fraction of portfolio to use per trade
        self.close_before_minutes = 5    # flatten this many minutes before close

        # State
        self._window_high = None
        self._window_low = None
        self._window_end = None
        self._triggered = False
        self._position_side = None       # "long" or "short"

        # Schedule the flatten task before market close.
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.before_market_close(self.spy, self.close_before_minutes),
            self._flatten_before_close
        )

    def on_data(self, data: Slice):
        if not self.is_warm_up_complete:
            return

        if self.spy not in data:
            return

        bar = data[self.spy]
        if bar.is_trade:
            return

        now = self.time

        # Determine the end of the observation window for today.
        if self._window_end is None or self._window_end.date() != now.date():
            # Market open is 9:30 ET for SPY.
            market_open = self.spy.exchange.hours.get_market_open_time(now)
            self._window_end = market_open + timedelta(minutes=self.watch_minutes)
            self._window_high = None
            self._window_low = None
            self._triggered = False
            self._position_side = None

        # While inside the observation window, track high/low.
        if now <= self._window_end:
            if self._window_high is None or bar.high > self._window_high:
                self._window_high = bar.high
            if self._window_low is None or bar.low < self._window_low:
                self._window_low = bar.low
            return

        # After the window, look for a breakout (only once per day).
        if self._triggered:
            return

        if self._window_high is None or self._window_low is None:
            return

        # Long breakout: price closes above the window high.
        if bar.close > self._window_high:
            self._triggered = True
            self._position_side = "long"
            self.set_holdings(self.spy, self.position_fraction)
            self.Log(f"LONG breakout at {now}: close={bar.close:.2f} > high={self._window_high:.2f}")
            return

        # Short breakout: price closes below the window low.
        if bar.close < self._window_low:
            self._triggered = True
            self._position_side = "short"
            self.set_holdings(self.spy, -self.position_fraction)
            self.Log(f"SHORT breakout at {now}: close={bar.close:.2f} < low={self._window_low:.2f}")

    def _flatten_before_close(self):
        """Flatten any open position before the market closes."""
        if self.spy in self.portfolio and self.portfolio[self.spy].quantity != 0:
            self.liquidate(self.spy)
            self.Log(f"Flattened position before close at {self.time}")
        self._triggered = False
        self._position_side = None
