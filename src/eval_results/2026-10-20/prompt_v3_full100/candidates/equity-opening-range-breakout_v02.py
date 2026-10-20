from AlgorithmImports import *


class OpeningRangeBreakoutAlgorithm(QCAlgorithm):
    """
    Opening Range Breakout strategy for SPY.
    Tracks the high and low from 9:30 to 10:00 AM.
    After 10:00, if a bar closes above the high, buy with everything.
    If a bar closes below the low, short with everything.
    Only one trade per day. Close everything at 3:55 PM and reset.
    """

    def initialize(self):
        # Set start, end, and cash
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity with minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # State variables
        self._session_high = None
        self._session_low = None
        self._traded_today = False
        self._current_date = None

        # Schedule:
        # 1. At 9:30 AM, reset the session high/low and traded flag
        # 2. At 10:00 AM, start checking for breakout
        # 3. At 3:55 PM, close all positions and reset

        # Reset at market open (9:30)
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(9, 30),
            self._on_session_start
        )

        # Check for breakout after 10:00 (every minute from 10:00 to 3:54)
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(10, 0),
            self._on_breakout_check_start
        )

        # Close everything at 3:55 PM
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(15, 55),
            self._on_close_positions
        )

    def _on_session_start(self):
        """Reset session state at 9:30 AM."""
        self._session_high = None
        self._session_low = None
        self._traded_today = False
        self._current_date = self.now.date

    def _on_breakout_check_start(self):
        """
        This is called once at 10:00 AM. We need to check every minute after 10:00.
        Since we can't easily schedule every minute from 10:00 to 3:54 with a single rule,
        we'll use on_data to handle the minute-by-minute checks after 10:00.
        This method just marks that we're in the breakout checking phase.
        """
        # The actual checking happens in on_data for bars after 10:00
        pass

    def on_data(self, data: Slice):
        """
        Process minute bars for SPY.
        - From 9:30 to 10:00: track high and low
        - After 10:00: check for breakout (only if not yet traded today)
        """
        if self.spy not in data:
            return

        bar = data[self.spy]
        if bar is None:
            return

        # Get the current time
        current_time = bar.end_time
        current_date = current_time.date

        # If it's a new day, reset state (safety check)
        if self._current_date != current_date:
            self._current_date = current_date
            self._session_high = None
            self._session_low = None
            self._traded_today = False

        # Only process during market hours (9:30 AM to 4:00 PM)
        if current_time.hour < 9 or (current_time.hour == 9 and current_time.minute < 30):
            return
        if current_time.hour >= 16:
            return

        # Phase 1: 9:30 AM to 10:00 AM - Track high and low
        if current_time.hour == 9 and current_time.minute >= 30:
            # 9:30 to 9:59
            if self._session_high is None:
                self._session_high = bar.high
                self._session_low = bar.low
            else:
                self._session_high = max(self._session_high, bar.high)
                self._session_low = min(self._session_low, bar.low)
            return

        if current_time.hour == 10 and current_time.minute == 0:
            # The 10:00 bar itself - include it in the range? 
            # The problem says "from 9:30 to 10:00", which typically means up to but not including 10:00,
            # or including the 10:00 bar. Let's include bars from 9:30 to 9:59 (the 30-minute opening range).
            # The 10:00 bar is the first bar we check for breakout.
            # So we do NOT include the 10:00 bar in the range tracking.
            pass

        # Phase 2: After 10:00 AM - Check for breakout
        if current_time.hour > 10 or (current_time.hour == 10 and current_time.minute > 0):
            if self._traded_today:
                return
            if self._session_high is None or self._session_low is None:
                return

            # Check if bar closed above the high
            if bar.close > self._session_high:
                # Buy with everything
                self.set_holdings(self.spy, 1.0)
                self._traded_today = True
                self.log(f"BUY signal at {current_time}: close {bar.close} > high {self._session_high}")
                return

            # Check if bar closed below the low
            if bar.close < self._session_low:
                # Short with everything
                self.set_holdings(self.spy, -1.0)
                self._traded_today = True
                self.log(f"SHORT signal at {current_time}: close {bar.close} < low {self._session_low}")
                return

    def _on_close_positions(self):
        """Close all positions at 3:55 PM and reset state."""
        if self.portfolio[self.spy].quantity != 0:
            self.liquidate(self.spy)
            self.log(f"Closed all positions at {self.now}")
        
        # Reset state
        self._session_high = None
        self._session_low = None
        self._traded_today = False
