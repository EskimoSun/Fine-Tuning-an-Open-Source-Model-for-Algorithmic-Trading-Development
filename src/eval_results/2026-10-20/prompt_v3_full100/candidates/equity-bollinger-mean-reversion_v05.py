from AlgorithmImports import *


class BollingerMeanReversion(QCAlgorithm):
    """
    Daily Bollinger Band mean-reversion strategy on SPY.

    Rules (checked pre-open each trading day):
      - If flat and price < lower band -> go 100% long.
      - If invested and price >= middle band -> liquidate.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY at daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands (20 period, 2 std devs) on daily bars
        self._bb = self.bb(self.spy.symbol, 20, 2, resolution=Resolution.DAILY)

        # Schedule a pre-open check every trading day
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(9, 30),  # 9:30 AM ET, just before market open
            self.on_pre_open_check
        )

    def on_pre_open_check(self):
        """Evaluate Bollinger Band conditions and act accordingly."""
        if not self._bb.is_ready:
            return

        price = self.securities[self.spy.symbol].price
        lower_band = self._bb.lower_band.current.value
        middle_band = self._bb.middle_band.current.value

        position = self.portfolio[self.spy.symbol]

        if position.quantity == 0 and price < lower_band:
            self.log(f"Pre-open: price {price:.2f} < lower band {lower_band:.2f} -> going 100% long")
            self.set_holdings(self.spy.symbol, 1.0)
        elif position.quantity != 0 and price >= middle_band:
            self.log(f"Pre-open: price {price:.2f} >= middle band {middle_band:.2f} -> liquidating")
            self.liquidate(self.spy.symbol)
