from AlgorithmImports import *


class BollingerMeanReversionAlgorithm(QCAlgorithm):
    """Daily Bollinger Band mean-reversion strategy on SPY."""

    # Named constants (no magic numbers)
    BB_PERIOD = 20
    BB_STD_DEV = 2
    PRE_OPEN_HOUR = 8
    PRE_OPEN_MINUTE = 0
    START_DATE = datetime(2024, 9, 1)
    END_DATE = datetime(2024, 12, 31)
    STARTING_CASH = 100_000

    def initialize(self):
        self.set_start_date(self.START_DATE)
        self.set_end_date(self.END_DATE)
        self.set_cash(self.STARTING_CASH)

        # Use automatic indicator warm-up so BB is ready before first signal
        self.settings.automatic_indicator_warm_up = True

        # Add SPY at daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands (20, 2) on daily close
        self._bb = self.bb(self.spy.symbol, self.BB_PERIOD, self.BB_STD_DEV,
                           resolution=Resolution.DAILY)

        # Plot all three bands
        self.plot(self._bb.upper_band, "Upper Band")
        self.plot(self._bb.middle_band, "Middle Band")
        self.plot(self._bb.lower_band, "Lower Band")

        # Schedule daily check at 08:00 (pre-open)
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(self.PRE_OPEN_HOUR, self.PRE_OPEN_MINUTE),
            self.on_pre_open_check
        )

    def on_pre_open_check(self):
        """Evaluate Bollinger Band signal before market open."""
        if not self._bb.is_ready:
            self.log("Bollinger Bands not ready yet.")
            return

        price = self.spy.price
        lower_band = self._bb.lower_band.current.value
        middle_band = self._bb.middle_band.current.value
        invested = self.portfolio[self.spy.symbol].invested

        self.log(f"Pre-open check: price={price:.2f}, lower={lower_band:.2f}, middle={middle_band:.2f}, invested={invested:.2f}")

        if invested == 0 and price < lower_band:
            self.log("Signal: flat and price below lower band -> go 100% long.")
            self.set_holdings(self.spy.symbol, 1.0)
        elif invested > 0 and price >= middle_band:
            self.log("Signal: invested and price at/above middle band -> liquidate.")
            self.liquidate(self.spy.symbol)
