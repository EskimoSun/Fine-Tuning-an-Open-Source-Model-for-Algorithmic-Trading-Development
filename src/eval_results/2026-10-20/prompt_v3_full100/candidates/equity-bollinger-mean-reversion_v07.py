from AlgorithmImports import *


class SpyBollingerMeanReversion(QCAlgorithm):
    """
    Bollinger Band mean-reversion reference strategy on SPY.

    - Window: 2024-09-01 to 2024-12-31
    - Signal evaluation: daily (after market close)
    - Bands: 20-period SMA, 2 standard deviations
    - Entry: close below lower band -> long; close above upper band -> exit
    - Exit: close back above middle band (SMA)
    """

    def initialize(self):
        # Set start/end dates
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)

        # Standard paper account
        self.set_cash(100_000)

        # Add SPY equity at daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands: 20 period, 2 standard deviations
        self._bb = self.bb(self.spy.symbol, 20, 2, resolution=Resolution.DAILY)

        # Track position state
        self._in_position = False

        # Schedule daily signal evaluation after market close
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(16, 30),  # 4:30 PM ET, after close
            self.on_daily_signal
        )

    def on_daily_signal(self):
        """Evaluate Bollinger Band mean-reversion signal at daily close."""
        if not self._bb.is_ready:
            return

        price = self.securities[self.spy.symbol].price
        upper = self._bb.upper_band.current.value
        middle = self._bb.middle_band.current.value
        lower = self._bb.lower_band.current.value

        if not self._in_position:
            # Entry: price closes below lower band
            if price < lower:
                self.set_holdings(self.spy.symbol, 1.0)
                self._in_position = True
                self.log(f"ENTRY: SPY close {price:.2f} < lower band {lower:.2f}")
        else:
            # Exit: price closes back above middle band
            if price > middle:
                self.liquidate(self.spy.symbol)
                self._in_position = False
                self.log(f"EXIT: SPY close {price:.2f} > middle band {middle:.2f}")

    def on_order_event(self, order_event):
        """Track fill status to keep position state consistent."""
        if order_event.symbol != self.spy.symbol:
            return
        if order_event.status == OrderStatus.FILLED:
            if order_event.quantity > 0:
                self._in_position = True
            elif order_event.quantity < 0:
                self._in_position = False
