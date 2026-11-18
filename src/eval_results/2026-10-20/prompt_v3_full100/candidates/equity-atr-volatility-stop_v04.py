from AlgorithmImports import *

class ChandelierStopSPY(QCAlgorithm):
    """
    Long-only SPY strategy using a Chandelier Exit stop (ATR(14) * 3).
    Immediate re-entry when price crosses back above the stop.
    Backtest period: 2022-01-01 to 2024-12-31.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity at daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # ATR(14) for Chandelier Exit
        self._atr = self.atr("SPY", 14, resolution=Resolution.DAILY)

        # Track state
        self._in_position = False
        self._chandelier_stop = 0.0
        self._highest_since_entry = 0.0

        # Schedule daily check after market close
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.at(16, 30),
            self.on_daily_check
        )

    def on_data(self, data: Slice):
        if not self._atr.is_ready:
            return

        if "SPY" not in data:
            return

        price = data["SPY"].price
        atr_value = self._atr.current.value

        if not self._in_position:
            # No position: check if we should enter
            # Enter when price is above the previous day's close (simple momentum trigger)
            # For immediate re-entry logic, we enter when price > stop (if stop exists) or on first bar
            if self._chandelier_stop > 0 and price > self._chandelier_stop:
                self._enter_position(price)
            elif self._chandelier_stop == 0:
                # First entry: just go long
                self._enter_position(price)
        else:
            # In position: update highest since entry and chandelier stop
            if price > self._highest_since_entry:
                self._highest_since_entry = price

            # Chandelier Exit: highest high since entry - ATR * 3
            new_stop = self._highest_since_entry - 3.0 * atr_value
            # Stop should only ratchet up, never down
            if new_stop > self._chandelier_stop:
                self._chandelier_stop = new_stop

            # Check if price fell below the stop
            if price < self._chandelier_stop:
                self._exit_position(price)

    def on_daily_check(self):
        """
        End-of-day check to ensure stop is updated and position state is consistent.
        This is a safety net; the main logic runs in on_data.
        """
        if not self._atr.is_ready:
            return

        if "SPY" not in self.securities:
            return

        price = self.securities["SPY"].price
        atr_value = self._atr.current.value

        if self._in_position:
            # Update highest and stop
            if price > self._highest_since_entry:
                self._highest_since_entry = price
            new_stop = self._highest_since_entry - 3.0 * atr_value
            if new_stop > self._chandelier_stop:
                self._chandelier_stop = new_stop

            # If price is below stop, exit
            if price < self._chandelier_stop:
                self._exit_position(price)
        else:
            # If not in position and price is above stop, re-enter
            if self._chandelier_stop > 0 and price > self._chandelier_stop:
                self._enter_position(price)

    def _enter_position(self, price: float):
        """Enter long position with all available capital."""
        if self._in_position:
            return
        self.set_holdings("SPY", 1.0)
        self._in_position = True
        self._highest_since_entry = price
        self._chandelier_stop = 0.0  # Will be set on next bar
        self.log(f"ENTER LONG SPY at {price:.2f}")

    def _exit_position(self, price: float):
        """Exit long position."""
        if not self._in_position:
            return
        self.liquidate("SPY")
        self._in_position = False
        self._highest_since_entry = 0.0
        # Keep the stop level so we can re-enter when price crosses back above
        self.log(f"EXIT LONG SPY at {price:.2f}, stop was {self._chandelier_stop:.2f}")
