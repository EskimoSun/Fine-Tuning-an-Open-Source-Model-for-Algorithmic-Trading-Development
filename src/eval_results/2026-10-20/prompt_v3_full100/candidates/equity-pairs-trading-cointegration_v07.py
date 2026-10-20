from AlgorithmImports import *

import math
from datetime import datetime, timedelta


class KoPepPairsTrading(QCAlgorithm):
    """
    Market-neutral pairs trading reference on KO and PEP (2022-2024).

    Strategy:
      - Rolling OLS hedge ratio (beta) over a lookback window.
      - Z-score of the spread (KO - beta * PEP) for entries/exits.
      - Dollar-neutral legs: position sizes are set so that the dollar
        exposure of the long leg equals the dollar exposure of the short leg.
      - Standard paper account (default brokerage).
    """

    def initialize(self):
        self.set_start_date(2022, 1, 3)
        self.set_end_date(2024, 12, 31)
        self.set_cash(1_000_000)

        # Data
        self.ko = self.add_equity("KO", resolution=Resolution.DAILY)
        self.pep = self.add_equity("PEP", resolution=Resolution.DAILY)

        # Parameters
        self.lookback = 60          # rolling OLS window (trading days)
        self.entry_z = 2.0           # enter when |z| >= entry_z
        self.exit_z = 0.5            # exit when |z| <= exit_z
        self.max_position_value = 100_000  # max dollar value per leg

        # State
        self._prices = []            # list of (ko_price, pep_price)
        self._in_position = False
        self._direction = 0          # +1: long KO / short PEP, -1: long PEP / short KO
        self._last_trade_date = None

        # Schedule daily check after market close
        self.schedule.on(
            self.date_rules.every_day(self.ko.symbol),
            self.time_rules.at(16, 30),
            self._on_daily_check
        )

    def _on_daily_check(self):
        """Evaluate spread z-score and manage positions."""
        if len(self._prices) < self.lookback:
            return

        # Compute rolling OLS: ko = alpha + beta * pep
        # Use the last `lookback` observations
        window = self._prices[-self.lookback:]
        ko_vals = [p[0] for p in window]
        pep_vals = [p[1] for p in window]

        n = len(window)
        mean_ko = sum(ko_vals) / n
        mean_pep = sum(pep_vals) / n

        # Covariance and variance
        cov = sum((ko_vals[i] - mean_ko) * (pep_vals[i] - mean_pep) for i in range(n)) / n
        var_pep = sum((pep_vals[i] - mean_pep) ** 2 for i in range(n) / n)

        if var_pep == 0:
            return

        beta = cov / var_pep
        alpha = mean_ko - beta * mean_pep

        # Current spread
        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price
        spread = ko_price - beta * pep_price

        # Compute z-score using the spread history
        # We need the spread values over the lookback window
        spread_vals = [ko_vals[i] - beta * pep_vals[i] for i in range(n)]
        mean_spread = sum(spread_vals) / n
        std_spread = math.sqrt(sum((s - mean_spread) ** 2 for s in spread_vals) / n)

        if std_spread == 0:
            return

        z_score = (spread - mean_spread) / std_spread

        # Log for reference
        self.Log(f"Date: {self.now.date()}, KO: {ko_price:.2f}, PEP: {pep_price:.2f}, "
                 f"Beta: {beta:.4f}, Spread: {spread:.2f}, Z: {z_score:.3f}, "
                 f"InPosition: {self._in_position}, Dir: {self._direction}")

        if not self._in_position:
            # Entry logic
            if z_score >= self.entry_z:
                # Spread is high: short KO, long PEP
                self._direction = -1
                self._enter_position()
            elif z_score <= -self.entry_z:
                # Spread is low: long KO, short PEP
                self._direction = 1
                self._enter_position()
        else:
            # Exit logic
            if abs(z_score) <= self.exit_z:
                self._exit_position()

    def _enter_position(self):
        """Enter a dollar-neutral pair position."""
        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        # Dollar-neutral: allocate max_position_value to each leg
        # Long leg gets +shares, short leg gets -shares
        if self._direction == 1:
            # Long KO, Short PEP
            ko_shares = int(self.max_position_value / ko_price)
            pep_shares = int(self.max_position_value / pep_price)
            self.market_order(self.ko.symbol, ko_shares)
            self.market_order(self.pep.symbol, -pep_shares)
        else:
            # Short KO, Long PEP
            ko_shares = int(self.max_position_value / ko_price)
            pep_shares = int(self.max_position_value / pep_price)
            self.market_order(self.ko.symbol, -ko_shares)
            self.market_order(self.pep.symbol, pep_shares)

        self._in_position = True
        self._last_trade_date = self.now.date()
        self.Log(f"Entered position: direction={self._direction}, "
                 f"KO shares={self.portfolio[self.ko.symbol].quantity}, "
                 f"PEP shares={self.portfolio[self.pep.symbol].quantity}")

    def _exit_position(self):
        """Exit the current pair position."""
        self.liquidate(self.ko.symbol)
        self.liquidate(self.pep.symbol)
        self._in_position = False
        self._direction = 0
        self.Log(f"Exited position on {self.now.date()}")

    def on_data(self, data: Slice):
        """Collect daily closing prices for the rolling window."""
        if self.ko.symbol in data and self.pep.symbol in data:
            ko_price = data[self.ko.symbol].close
            pep_price = data[self.pep.symbol].close
            self._prices.append((ko_price, pep_price))
            # Keep only the last lookback + buffer prices
            if len(self._prices) > self.lookback + 10:
                self._prices = self._prices[-(self.lookback + 10):]
