from AlgorithmImports import *


class SpyChandelierExitAlgorithm(QCAlgorithm):
    """
    Long-only SPY strategy with ATR-based chandelier exit and automatic re-entry.
    Period: 2022-01-01 to 2024-12-31.
    Chandelier exit: trail stop = highest high since entry - ATR_MULTIPLE * ATR(22).
    Re-entry: buy 100% of portfolio when flat and price > trailing stop (or no stop yet).
    """

    ATR_PERIOD = 22
    ATR_MULTIPLE = 3.0  # Adjust to match your desk's standard ATR multiple

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        self._atr = self.atr("SPY", self.ATR_PERIOD, resolution=Resolution.DAILY)

        self._highest_high = None
        self._trailing_stop = None
        self._in_position = False

        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(16, 0),
            self.on_daily_signal
        )

    def on_data(self, data: Slice):
        if not self._atr.is_ready:
            return

        if self.spy.symbol not in data:
            return

        bar = data[self.spy.symbol]
        if bar is None:
            return

        # Update highest high while in position
        if self._in_position:
            if self._highest_high is None or bar.high > self._highest_high:
                self._highest_high = bar.high

            # Update trailing stop
            atr_value = self._atr.current.value
            if atr_value > 0:
                new_stop = self._highest_high - self.ATR_MULTIPLE * atr_value
                if self._trailing_stop is None or new_stop > self._trailing_stop:
                    self._trailing_stop = new_stop

            # Check for exit: close <= trailing stop
            if bar.close <= self._trailing_stop:
                self.liquidate(self.spy.symbol)
                self._in_position = False
                self._highest_high = None
                self._trailing_stop = None
                self.Log(f"Chandelier exit triggered. Close={bar.close:.2f}, Stop={self._trailing_stop:.2f}")

    def on_daily_signal(self):
        """Called at 16:00 each trading day to handle re-entry."""
        if self._in_position:
            return

        if not self._atr.is_ready:
            return

        if self.spy.symbol not in self.securities:
            return

        price = self.securities[self.spy.symbol].price
        if price is None or price <= 0:
            return

        # Re-entry condition: no active stop (flat) -> enter long
        # In a chandelier system, re-entry is typically when price makes a new
        # high above the previous stop, or simply when flat and trend is up.
        # Here we re-enter when flat and price > ATR-based threshold above recent low,
        # or more simply: re-enter when flat (the chandelier system re-enters on
        # the next bar after exit if price is above the stop level).
        # Standard chandelier re-entry: enter when price > trailing stop.
        # Since we reset stop on exit, we re-enter on the next signal if price
        # is above a fresh ATR-based entry threshold.
        #
        # Simplest consistent rule: re-enter when flat and close > SMA(22) or
        # close > highest high of last N bars. We use: re-enter when flat and
        # price > ATR_MULTIPLE * ATR above the lowest low of the last ATR_PERIOD bars.
        #
        # For clarity and consistency with chandelier logic, we re-enter when
        # flat and the current price is above the trailing stop that would be
        # computed from the highest high since the last exit. Since we reset
        # on exit, we simply re-enter on the next bar when flat.
        #
        # To avoid immediate re-entry on the same bar as exit, we require
        # at least one bar gap. We track last exit date.
        if not hasattr(self, '_last_exit_date'):
            self._last_exit_date = None

        if self._last_exit_date is not None:
            current_date = self.spy.symbol if False else self.Time.Date
            if current_date == self._last_exit_date:
                return

        # Re-enter: go long 100%
        self.set_holdings(self.spy.symbol, 1.0)
        self._in_position = True
        self._highest_high = self.securities[self.spy.symbol].price
        self._trailing_stop = None
        self.Log(f"Re-entry: SPY at {price:.2f}")

    def on_order_event(self, order_event: OrderEvent):
        if order_event.Status == OrderStatus.FILLED:
            if order_event.Symbol == self.spy.symbol:
                if order_event.Direction == OrderDirection.BUY:
                    self._in_position = True
                    if self._highest_high is None:
                        self._highest_high = order_event.FillPrice
                elif order_event.Direction == OrderDirection.SELL:
                    self._in_position = False
                    self._highest_high = None
                    self._trailing_stop = None
                    self._last_exit_date = self.Time.Date
