from AlgorithmImports import *


class PairsTradeKOPEP(QCAlgorithm):
    """Pairs trade between KO and PEP using a rolling 60-day regression spread."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        self.ko = self.add_equity("KO", resolution=Resolution.MINUTE)
        self.pep = self.add_equity("PEP", resolution=Resolution.MINUTE)

        self._ko_prices = []
        self._pep_prices = []
        self._slope = None
        self._intercept = None
        self._spread_mean = None
        self._spread_std = None

        # Weekly regression fit (Monday 09:30 ET)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.at(9, 30),
            self._fit_regression
        )

        # Daily z-score check at 10:00 ET
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.at(10, 0),
            self._check_zscore
        )

    def on_data(self, data: Slice):
        if not self.is_warming_up:
            if self.ko in data and self.pep in data:
                self._ko_prices.append(data[self.ko].close)
                self._pep_prices.append(data[self.pep].close)
                # Keep only the last 60 daily closes
                if len(self._ko_prices) > 60:
                    self._ko_prices = self._ko_prices[-60:]
                    self._pep_prices = self._pep_prices[-60:]

    def _fit_regression(self):
        """Fit linear regression of KO on PEP over the last 60 daily closes."""
        if len(self._ko_prices) < 60:
            self.Log("Not enough data for regression yet.")
            return

        x = self._pep_prices
        y = self._ko_prices
        n = len(x)

        # Compute slope and intercept via least squares
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            self.Log("Regression denominator is zero; skipping.")
            return

        self._slope = (n * sum_xy - sum_x * sum_y) / denominator
        self._intercept = (sum_y - self._slope * sum_x) / n

        # Compute spread = KO - (slope * PEP + intercept)
        spreads = [yi - (self._slope * xi + self._intercept) for xi, yi in zip(x, y)]
        self._spread_mean = sum(spreads) / n
        variance = sum((s - self._spread_mean) ** 2 for s in spreads) / (n - 1)
        self._spread_std = variance ** 0.5

        self.Log(f"Regression updated: slope={self._slope:.6f}, intercept={self._intercept:.4f}, "
                 f"spread_mean={self._spread_mean:.4f}, spread_std={self._spread_std:.4f}")

    def _check_zscore(self):
        """Compute z-score of today's spread and act on it."""
        if self._slope is None or self._intercept is None or self._spread_std is None or self._spread_std == 0:
            self.Log("Regression not yet available; skipping z-score check.")
            return

        ko_price = self.securities[self.ko].price
        pep_price = self.securities[self.pep].price

        spread = ko_price - (self._slope * pep_price + self._intercept)
        z_score = (spread - self._spread_mean) / self._spread_std

        self.Log(f"Z-score: {z_score:.4f} (spread={spread:.4f})")

        if z_score < -2:
            # Buy KO, short PEP with half the money each
            self._open_position(self.ko, 0.5)
            self._open_position(self.pep, -0.5)
        elif z_score > 2:
            # Short KO, buy PEP with half the money each
            self._open_position(self.ko, -0.5)
            self._open_position(self.pep, 0.5)
        elif -0.5 <= z_score <= 0.5:
            # Close everything
            self.liquidate(self.ko)
            self.liquidate(self.pep)
            self.Log("Positions closed due to z-score in neutral zone.")

    def _open_position(self, symbol: Symbol, fraction: float):
        """Open or adjust a position to the given portfolio fraction."""
        current_invested = self.portfolio[symbol].invested
        target_invested = fraction * self.portfolio.total_value
        delta = target_invested - current_invested

        if abs(delta) < 100:  # Ignore tiny adjustments
            return

        price = self.securities[symbol].price
        if price <= 0:
            return

        quantity = int(delta / price)
        if quantity != 0:
            self.market_order(symbol, quantity)
            self.Log(f"Order: {symbol} qty={quantity} (target fraction={fraction})")
