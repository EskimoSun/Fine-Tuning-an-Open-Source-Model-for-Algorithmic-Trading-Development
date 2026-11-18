from AlgorithmImports import *

class SPYBollingerStrategy(QCAlgorithm):
    """
    SPY Bollinger Bands mean-reversion strategy.
    - Buy all-in when price is below the lower band (when flat).
    - Sell all-in when price is at or above the middle band (when long).
    - Signals evaluated once per day before the market open.
    """

    def initialize(self):
        # Set start, end, and cash
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity with daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands: 20 period, 2 standard deviations
        self._bb = self.bb(self.spy.symbol, 20, 2, resolution=Resolution.DAILY)

        # Schedule the signal check once per day before market open
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(8, 30),  # 8:30 AM ET, before 9:30 open
            self.on_pre_market_signal
        )

    def on_pre_market_signal(self):
        """Evaluate Bollinger Bands signal before the market opens."""
        if not self._bb.is_ready:
            return

        # Use the most recent daily close as the reference price
        price = self.spy.price
        lower_band = self._bb.lower_band.current.value
        middle_band = self._bb.middle_band.current.value

        invested = self.portfolio[self.spy.symbol].invested

        if invested == 0:
            # Flat: buy if price is below the lower band
            if price < lower_band:
                self.log(f"BUY signal: price {price:.2f} < lower band {lower_band:.2f}")
                self.set_holdings(self.spy.symbol, 1.0)
        else:
            # Long: sell if price is at or above the middle band
            if price >= middle_band:
                self.log(f"SELL signal: price {price:.2f} >= middle band {middle_band:.2f}")
                self.liquidate(self.spy.symbol)
