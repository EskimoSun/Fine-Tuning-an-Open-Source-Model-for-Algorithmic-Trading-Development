from AlgorithmImports import *
import numpy as np


class PairsTradingAlgorithm(QCAlgorithm):
    """Pairs trading strategy between KO and PEP using a rolling OLS hedge ratio."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.ko = self.add_equity("KO", resolution=Resolution.MINUTE)
        self.pep = self.add_equity("PEP", resolution=Resolution.MINUTE)

        # 60-minute session size for both symbols
        self.ko.session.size = 60
        self.pep.session.size = 60

        # Model parameters
        self._alpha = 0.0
        self._beta = 1.0
        self._spread_mean = 0.0
        self._spread_std = 1.0
        self._state = 0  # 0 = flat, 1 = long KO / short PEP, -1 = short KO / long PEP

        self.set_warm_up(60, Resolution.DAILY)

        # Weekly model update at 9:31 AM
        self.schedule.on(
            self.date_rules.week_start(),
            self.time_rules.at(9, 31),
            self._update_model
        )

        # Daily trade logic at 10:00 AM
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.at(10, 0),
            self._trade_logic
        )

    def on_warmup_finished(self):
        self._update_model()

    def _update_model(self):
        """Compute OLS hedge ratio and spread statistics from the last 60 daily closes."""
        ko_closes = self.ko.history(60, Resolution.DAILY, "close")
        pep_closes = self.pep.history(60, Resolution.DAILY, "close")

        if len(ko_closes) < 60 or len(pep_closes) < 60:
            self.log("Not enough history to update model.")
            return

        ko_values = np.array([bar.close for bar in ko_closes])
        pep_values = np.array([bar.close for bar in pep_closes])

        # OLS: ko = alpha + beta * pep
        X = np.column_stack([np.ones_like(pep_values), pep_values])
        result = np.linalg.lstsq(X, ko_values, rcond=None)
        self._alpha, self._beta = result[0]

        # Spread = ko - (beta * pep + alpha)
        spread = ko_values - (self._beta * pep_values + self._alpha)
        self._spread_mean = float(np.mean(spread))
        self._spread_std = float(np.std(spread))

        self.log(
            f"Model updated: alpha={self._alpha:.4f}, beta={self._beta:.4f}, "
            f"spread_mean={self._spread_mean:.4f}, spread_std={self._spread_std:.4f}"
        )

    def _trade_logic(self):
        """Execute pair trades based on z-score of the current spread."""
        ko_price = self.securities[self.ko.symbol].close
        pep_price = self.securities[self.pep.symbol].close

        if ko_price is None or pep_price is None:
            return

        current_spread = ko_price - (self._beta * pep_price + self._alpha)
        z = (current_spread - self._spread_mean) / self._spread_std

        self.log(f"Z-score: {z:.4f}, state: {self._state}")

        if z < -2 and self._state != 1:
            # Spread is too low: long KO, short PEP
            self.set_holdings([
                PortfolioTarget(self.ko.symbol, 0.5),
                PortfolioTarget(self.pep.symbol, -0.5)
            ])
            self._state = 1
            self.log("Opened long KO / short PEP position.")

        elif z > 2 and self._state != -1:
            # Spread is too high: short KO, long PEP
            self.set_holdings([
                PortfolioTarget(self.ko.symbol, -0.5),
                PortfolioTarget(self.pep.symbol, 0.5)
            ])
            self._state = -1
            self.log("Opened short KO / long PEP position.")

        elif abs(z) < 0.5 and self._state != 0:
            # Spread has mean-reverted: close position
            self.liquidate()
            self._state = 0
            self.log("Closed position, spread mean-reverted.")
