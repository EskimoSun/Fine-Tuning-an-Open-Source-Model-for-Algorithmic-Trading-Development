from AlgorithmImports import *


class Sp500OpeningRangeBreakout(QCAlgorithm):
    """
    SPY minute-level opening range breakout strategy.

    - Range is defined as the high/low of the 09:30-10:00 ET bars.
    - After 10:00 ET, if a bar closes above the range high, go 100% long.
    - If a bar closes below the range low, go 100% short.
    - Only one trade per day; after a trade, the range is cleared.
    - Liquidate at 15:55 ET and reset for the next day.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # State variables
        self._range_high = None
        self._range_low = None
        self._traded_today = False
        self._current_date = None

        # Schedule:
        # 1. At 09:30 ET, start collecting the opening range (we'll do this in on_data)
        # 2. At 10:00 ET, finalize the range
        # 3. At 15:55 ET, liquidate and reset

        # We'll handle range collection and breakout logic in on_data for precision.
        # Schedule the liquidation at 15:55 ET.
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(15, 55),
            self._liquidate_and_reset
        )

    def on_data(self, data: Slice):
        if not self.spy in data:
            return

        bar = data[self.spy]
        if not bar.is_traded:
            return

        current_time = bar.end_time
        current_date = current_time.date()

        # Reset daily state if new day
        if self._current_date != current_date:
            self._current_date = current_date
            self._range_high = None
            self._range_low = None
            self._traded_today = False

        # Collect opening range: 09:30 to 10:00 ET
        # Bars are labeled by end time, so:
        # - The bar ending at 09:31 covers 09:30-09:31
        # - The bar ending at 10:00 covers 09:59-10:00
        # We want bars with end_time in (09:30, 10:00] i.e., 09:31 through 10:00
        if current_time.hour == 9 and current_time.minute >= 31:
            # Still in the opening range window (09:31 to 09:59)
            if self._range_high is None:
                self._range_high = bar.high
                self._range_low = bar.low
            else:
                self._range_high = max(self._range_high, bar.high)
                self._range_low = min(self._range_low, bar.low)
        elif current_time.hour == 10 and current_time.minute == 0:
            # The 10:00 bar (covers 09:59-10:00) is the last bar of the range
            if self._range_high is None:
                self._range_high = bar.high
                self._range_low = bar.low
            else:
                self._range_high = max(self._range_high, bar.high)
                self._range_low = min(self._range_low, bar.low)

            # Range is now complete. Log it.
            self.log(f"{current_date}: Opening range high={self._range_high:.2f}, low={self._range_low:.2f}")

        # After 10:00, check for breakout (only if we haven't traded today)
        if self._traded_today:
            return

        if self._range_high is None or self._range_low is None:
            return

        # Only check after 10:00 ET
        if current_time.hour > 10 or (current_time.hour == 10 and current_time.minute > 0):
            if bar.close > self._range_high:
                self.log(f"{current_date}: Breakout above range high {self._range_high:.2f}, close={bar.close:.2f}. Going long.")
                self.set_holdings(self.spy, 1.0)
                self._traded_today = True
                # Clear range after trade
                self._range_high = None
                self._range_low = None
            elif bar.close < self._range_low:
                self.log(f"{current_date}: Breakout below range low {self._range_low:.2f}, close={bar.close:.2f}. Going short.")
                self.set_holdings(self.spy, -1.0)
                self._traded_today = True
                # Clear range after trade
                self._range_high = None
                self._range_low = None

    def _liquidate_and_reset(self):
        """Liquidate all positions and reset daily state."""
        if self.portfolio[self.spy].quantity != 0:
            self.log(f"Liquidating SPY position at 15:55 ET.")
            self.liquidate(self.spy)

        self._range_high = None
        self._range_low = None
        self._traded_today = False
