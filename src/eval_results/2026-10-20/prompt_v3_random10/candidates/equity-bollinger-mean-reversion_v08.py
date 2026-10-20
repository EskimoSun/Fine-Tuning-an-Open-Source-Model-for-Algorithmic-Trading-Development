from AlgorithmImports import *


class BollingerMeanReversionAlgorithm(QCAlgorithm):
    """Bollinger mean-reversion reference on SPY for the desk."""

    def initialize(self):
        # Capital and window
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Data
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Indicator: 20-period, 2 std dev, daily
        self._bb = self.bb(self.spy.symbol, 20, 2, resolution=Resolution.DAILY)

        # State
        self._invested = False

        # Schedule: once per trading day at 08:00
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(8, 0),
            self.on_evaluation
        )

    def on_evaluation(self):
        """Evaluate the mean-reversion rules once per trading day."""
        if not self._bb.is_ready:
            return

        price = self.securities[self.spy.symbol].price
        lower = self._bb.lower_band.current.value
        middle = self._bb.middle_band.current.value

        if not self._invested and price < lower:
            # Not invested and price below lower band: go 100% long
            self.set_holdings(self.spy.symbol, 1.0)
            self._invested = True
            self.log(f"BUY: price {price:.2f} < lower band {lower:.2f}")
        elif self._invested and price >= middle:
            # Invested and price at or above middle band: liquidate
            self.liquidate(self.spy.symbol)
            self._invested = False
            self.log(f"SELL: price {price:.2f} >= middle band {middle:.2f}")

    def on_order_event(self, order_event):
        """Track fill status to keep _invested in sync."""
        if order_event.symbol != self.spy.symbol:
            return
        if order_event.status == OrderStatus.FILLED:
            if order_event.fill_quantity > 0:
                self._invested = True
            else:
                self._invested = False
