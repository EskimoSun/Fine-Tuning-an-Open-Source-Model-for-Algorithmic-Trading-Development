from AlgorithmImports import *

class BollingerDipBuyer(QCAlgorithm):
    """
    SPY Bollinger Band dip-buying strategy.
    Buys when price is below the lower band (if flat), sells when price is at/above the middle band (if long).
    """

    def initialize(self):
        # Set start, end, and cash
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity with daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands: 20 period, 2 standard deviations, simple moving average
        self._bb = self.bb(self.spy.symbol, 20, 2, moving_average_type=MovingAverageType.SIMPLE, resolution=Resolution.DAILY)

        # Seed the starting prices so day one works (warm up the indicator)
        self.set_warm_up(20)

        # Schedule the check once a day before the market open
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(9, 30),  # 9:30 AM ET, just before/at open
            self.on_pre_market_check
        )

        # Plot the bands
        self.plot(self._bb.upper_band, "Upper Band")
        self.plot(self._bb.middle_band, "Middle Band")
        self.plot(self._bb.lower_band, "Lower Band")

    def on_pre_market_check(self):
        """
        Called once a day before the open.
        Checks Bollinger Band conditions and executes trades accordingly.
        """
        if not self._bb.is_ready:
            return

        price = self.spy.price
        upper = self._bb.upper_band.current.value
        middle = self._bb.middle_band.current.value
        lower = self._bb.lower_band.current.value

        # If not in a position and price is below the lower band, buy with everything
        if self.portfolio[self.spy.symbol].quantity == 0 and price < lower:
            self.set_holdings(self.spy.symbol, 1.0)
            self.log(f"BUY: Price {price:.2f} below lower band {lower:.2f}")

        # If in a position and price is at or above the middle band, sell everything
        elif self.portfolio[self.spy.symbol].quantity > 0 and price >= middle:
            self.liquidate(self.spy.symbol)
            self.log(f"SELL: Price {price:.2f} at/above middle band {middle:.2f}")
