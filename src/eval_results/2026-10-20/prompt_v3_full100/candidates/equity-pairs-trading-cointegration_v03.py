from AlgorithmImports import *
import numpy as np


class KoPepPairs(QCAlgorithm):
    """Pairs trade between KO and PEP using a weekly regression and daily z-score."""

    def initialize(self):
        # Capital and date range
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Minute data for both legs
        self.ko = self.add_equity("KO", resolution=Resolution.MINUTE)
        self.pep = self.add_equity("PEP", resolution=Resolution.MINUTE)

        # State: "flat", "long" (long KO / short PEP), or "short" (short KO / long PEP)
        self.state = "flat"

        # Regression parameters
        self.slope = 0.0
        self.intercept = 0.0
        self.spread_mean = 0.0
        self.spread_std = 1.0

        # Weekly regression at 9:31 (Monday)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.at(9, 31),
            self.run_regression
        )

        # Daily z-score check at 10:00
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.at(10, 0),
            self.check_zscore
        )

    def run_regression(self):
        """Fit a linear regression of KO price on PEP price over the last 60 daily closes."""
        # Collect the last 60 daily closes for both symbols
        ko_prices = []
        pep_prices = []

        # Walk back through daily bars
        for i in range(60):
            ko_bar = self.ko.history[1]  # placeholder, we'll use a different approach
            break

        # Use the history API to get daily bars
        ko_history = self.history(self.ko.symbol, 60, Resolution.DAILY)
        pep_history = self.history(self.pep.symbol, 60, Resolution.DAILY)

        if len(ko_history) < 60 or len(pep_history) < 60:
            self.log("Not enough history for regression, skipping.")
            return

        # Extract close prices
        ko_closes = np.array([bar.close for bar in ko_history])
        pep_closes = np.array([bar.close for bar in pep_history])

        # Fit linear regression: KO = slope * PEP + intercept
        # Using numpy polyfit for linear regression
        coeffs = np.polyfit(pep_closes, ko_closes, 1)
        self.slope = coeffs[0]
        self.intercept = coeffs[1]

        # Compute the spread: KO - (slope * PEP + intercept)
        spread = ko_closes - (self.slope * pep_closes + self.intercept)

        # Save mean and standard deviation of the spread
        self.spread_mean = np.mean(spread)
        self.spread_std = np.std(spread)

        if self.spread_std == 0:
            self.spread_std = 1.0  # Avoid division by zero

        self.log(f"Regression updated: slope={self.slope:.4f}, intercept={self.intercept:.4f}, "
                 f"spread_mean={self.spread_mean:.4f}, spread_std={self.spread_std:.4f}")

    def check_zscore(self):
        """Compute the z-score of today's spread and act on it."""
        # Get current prices
        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        # Compute today's spread using the regression model
        spread = ko_price - (self.slope * pep_price + self.intercept)

        # Compute z-score
        z_score = (spread - self.spread_mean) / self.spread_std

        self.log(f"Z-score: {z_score:.4f}, state: {self.state}")

        # Rule 1: If z is below -2, buy KO and short PEP (long the pair)
        if z_score < -2 and self.state != "long":
            self.enter_long()
            return

        # Rule 2: If z is above 2, short KO and long PEP (short the pair)
        if z_score > 2 and self.state != "short":
            self.enter_short()
            return

        # Rule 3: If z is between -0.5 and 0.5, close everything
        if -0.5 <= z_score <= 0.5 and self.state != "flat":
            self.close_all()
            return

    def enter_long(self):
        """Buy KO and short PEP with half the portfolio value each."""
        # Close any existing positions first
        self.close_all()

        # Calculate position size: half the portfolio value for each leg
        portfolio_value = self.portfolio.total_value
        half_value = portfolio_value / 2

        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        ko_quantity = int(half_value / ko_price)
        pep_quantity = int(half_value / pep_price)

        if ko_quantity <= 0 or pep_quantity <= 0:
            return

        # Buy KO
        self.market_order(self.ko.symbol, ko_quantity)
        # Short PEP
        self.market_order(self.pep.symbol, -pep_quantity)

        self.state = "long"
        self.log(f"Entered long: bought {ko_quantity} KO, shorted {pep_quantity} PEP")

    def enter_short(self):
        """Short KO and long PEP with half the portfolio value each."""
        # Close any existing positions first
        self.close_all()

        # Calculate position size: half the portfolio value for each leg
        portfolio_value = self.portfolio.total_value
        half_value = portfolio_value / 2

        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        ko_quantity = int(half_value / ko_price)
        pep_quantity = int(half_value / pep_price)

        if ko_quantity <= 0 or pep_quantity <= 0:
            return

        # Short KO
        self.market_order(self.ko.symbol, -ko_quantity)
        # Buy PEP
        self.market_order(self.pep.symbol, pep_quantity)

        self.state = "short"
        self.log(f"Entered short: shorted {ko_quantity} KO, bought {pep_quantity} PEP")

    def close_all(self):
        """Close all positions in KO and PEP."""
        # Liquidate KO
        if self.portfolio[self.ko.symbol].quantity != 0:
            self.liquidate(self.ko.symbol)

        # Liquidate PEP
        if self.portfolio[self.pep.symbol].quantity != 0:
            self.liquidate(self.pep.symbol)

        self.state = "flat"
        self.log("Closed all positions, state is now flat.")
