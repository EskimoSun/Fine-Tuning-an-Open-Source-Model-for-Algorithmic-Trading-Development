from AlgorithmImports import *

class SPYBollingerMeanReversion(QCAlgorithm):
    """
    Mean-reversion strategy for SPY:
    - Buys when price drops below the lower Bollinger Band.
    - Sells when price returns to the middle (SMA) band.
    - Checks once per day (at market open).
    - Uses daily resolution data.
    """

    def initialize(self):
        # Set start and end dates for late 2024
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        # Add SPY equity with daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands: 20-period SMA, 2 standard deviations
        self._bb = self.bb(self.spy.symbol, 20, 2, resolution=Resolution.DAILY)

        # Schedule a daily check at market open
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(9, 30),  # 9:30 AM market open
            self.on_daily_check
        )

    def on_daily_check(self):
        """
        Called once per day at market open.
        Checks Bollinger Band conditions and executes trades accordingly.
        """
        if not self._bb.is_ready:
            return

        price = self.securities[self.spy.symbol].price
        lower_band = self._bb.lower_band.current.value
        middle_band = self._bb.middle_band.current.value

        # Check if we're currently holding SPY
        holding = self.portfolio[self.spy.symbol].quantity > 0

        if not holding and price < lower_band:
            # Buy when price drops below the lower Bollinger Band
            self.log(f"BUY signal: Price {price:.2f} < Lower Band {lower_band:.2f}")
            self.set_holdings(self.spy.symbol, 1.0)  # Invest 100% of portfolio

        elif holding and price >= middle_band:
            # Sell when price returns to the middle band
            self.log(f"SELL signal: Price {price:.2f} >= Middle Band {middle_band:.2f}")
            self.liquidate(self.spy.symbol)
