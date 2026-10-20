from AlgorithmImports import *

class Spy30MinOrbAlgorithm(QCAlgorithm):
    """
    SPY 30-minute Opening Range Breakout (ORB) strategy.
    - Long/short breakout of the first 30-minute range.
    - One trade per day.
    - Flat by 15:55 ET.
    - Backtest period: Q4 2024 (Oct 1 - Dec 31, 2024).
    """

    def initialize(self):
        # Set backtest period: Q4 2024
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity with minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # Track state
        self._traded_today = False
        self._current_day = None
        self._orb_high = None
        self._orb_low = None
        self._orb_ready = False

        # Schedule: check for new day at market open
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(9, 30),
            self._on_new_day
        )

        # Schedule: flat by 15:55
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(15, 55),
            self._flatten_position
        )

    def _on_new_day(self):
        """Reset daily state at market open."""
        self._traded_today = False
        self._orb_high = None
        self._orb_low = None
        self._orb_ready = False
        self._current_day = self.now.date

    def on_data(self, slice):
        if self.spy not in slice:
            return

        bar = slice[self.spy]
        if bar is None:
            return

        # Check if we've already traded today
        if self._traded_today:
            return

        # Check if we're in the first 30 minutes (9:30 - 10:00 ET)
        # We need to collect the high and low of the first 30 minutes
        if not self._orb_ready:
            # Update ORB high/low with current bar
            if self._orb_high is None or bar.high > self._orb_high:
                self._orb_high = bar.high
            if self._orb_low is None or bar.low < self._orb_low:
                self._orb_low = bar.low

            # Check if 30 minutes have passed (10:00 ET)
            if self.now.hour == 10 and self.now.minute >= 0:
                self._orb_ready = True
                self.log(f"ORB established: High={self._orb_high:.2f}, Low={self._orb_low:.2f}")

        # If ORB is ready, check for breakout
        if self._orb_ready:
            # Long breakout: price breaks above ORB high
            if bar.close > self._orb_high:
                self.log(f"Long breakout detected: Close={bar.close:.2f} > ORB High={self._orb_high:.2f}")
                self.set_holdings(self.spy, 1.0)
                self._traded_today = True
                return

            # Short breakout: price breaks below ORB low
            if bar.close < self._orb_low:
                self.log(f"Short breakout detected: Close={bar.close:.2f} < ORB Low={self._orb_low:.2f}")
                self.set_holdings(self.spy, -1.0)
                self._traded_today = True
                return

    def _flatten_position(self):
        """Liquidate any open position by 15:55."""
        if self.portfolio[self.spy].quantity != 0:
            self.log(f"Flattening position at 15:55. Quantity: {self.portfolio[self.spy].quantity}")
            self.liquidate(self.spy)
