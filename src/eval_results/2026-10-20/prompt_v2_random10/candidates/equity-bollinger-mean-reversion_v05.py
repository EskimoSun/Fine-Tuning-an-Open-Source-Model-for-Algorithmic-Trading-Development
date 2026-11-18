from AlgorithmImports import *

class BollingerMeanReversionAlgorithm(QCAlgorithm):
    def initialize(self):
        """Initialize the algorithm with SPY equity and Bollinger Bands indicator."""
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity with daily resolution
        self.spy = self.add_equity("SPY", Resolution.DAILY)

        # Add Bollinger Bands indicator (20 period, 2 standard deviations)
        self.bb = self.bb(self.spy, 20, 2, Resolution.DAILY)

        # Schedule daily check pre-open
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.before_market_open(self.spy, 15),
            self.check_signal
        )

    def check_signal(self, context):
        """Check Bollinger Bands signal and execute trade if conditions are met."""
        if not self.bb.is_ready:
            return

        # Get current price from the security
        price = self.spy.price

        # Get Bollinger Bands values
        lower_band = self.bb.lower_band.current.value
        middle_band = self.bb.middle_band.current.value

        # Check if we are flat and price is below lower band -> go long
        if self.portfolio[self.spy].invested is False and price < lower_band:
            self.set_holdings(self.spy, 1.0)
            self.log(f"BUY: Price {price:.2f} < Lower Band {lower_band:.2f}")

        # Check if we are invested and price is at or above middle band -> liquidate
        elif self.portfolio[self.spy].invested is True and price >= middle_band:
            self.liquidate(self.spy)
            self.log(f"SELL: Price {price:.2f} >= Middle Band {middle_band:.2f}")
