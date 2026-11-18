from AlgorithmImports import *
import numpy as np
import pandas as pd


class KoPepStatArb(QCAlgorithm):
    """
    Statistical arbitrage strategy on KO and PEP.
    - Weekly OLS hedge ratio recomputation over a 60-day rolling window.
    - Daily z-score of the spread (KO - beta * PEP).
    - Enter long KO / short PEP when z <= -2, enter short KO / long PEP when z >= +2.
    - Exit when z crosses back through 0.5 (in the direction of the position).
    - Dollar-neutral: position sizes are equal in dollar value.
    - Backtest period: 2022-01-01 to 2024-12-31.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(1_000_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Add equities
        self.ko = self.add_equity("KO", resolution=Resolution.DAILY)
        self.pep = self.add_equity("PEP", resolution=Resolution.DAILY)

        # State
        self._beta = 1.0
        self._alpha = 0.0
        self._z_score = 0.0
        self._position = 0  # +1 long spread, -1 short spread, 0 flat
        self._price_history = {
            "KO": [],
            "PEP": []
        }
        self._max_history = 60

        # Schedule weekly hedge recomputation (Monday 9:30 AM)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.at(9, 30),
            self._recompute_hedge
        )

        # Schedule daily z-score check and trading (every day 9:30 AM)
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.at(9, 30),
            self._check_and_trade
        )

    def on_data(self, data: Slice):
        # Collect daily closing prices for history
        for symbol in ["KO", "PEP"]:
            if symbol in data:
                price = data[symbol].close
                self._price_history[symbol].append(price)
                if len(self._price_history[symbol]) > self._max_history:
                    self._price_history[symbol] = self._price_history[symbol][-self._max_history:]

    def _recompute_hedge(self):
        """Recompute OLS hedge ratio using the last 60 days of prices."""
        ko_prices = self._price_history["KO"]
        pep_prices = self._price_history["PEP"]

        if len(ko_prices) < 10 or len(pep_prices) < 10:
            return

        # Use the last 60 observations
        n = min(len(ko_prices), len(pep_prices), self._max_history)
        ko_arr = np.array(ko_prices[-n:])
        pep_arr = np.array(pep_prices[-n:])

        # OLS: KO = alpha + beta * PEP + error
        # beta = Cov(KO, PEP) / Var(PEP)
        cov = np.cov(ko_arr, pep_arr)
        var_pep = cov[1, 1]
        if var_pep == 0:
            return
        self._beta = cov[0, 1] / var_pep
        self._alpha = np.mean(ko_arr) - self._beta * np.mean(pep_arr)

        self.log(f"Hedge recomputed: beta={self._beta:.4f}, alpha={self._alpha:.4f}")

    def _check_and_trade(self):
        """Compute daily z-score and execute trades based on thresholds."""
        ko_prices = self._price_history["KO"]
        pep_prices = self._price_history["PEP"]

        if len(ko_prices) < 10 or len(pep_prices) < 10:
            return

        n = min(len(ko_prices), len(pep_prices), self._max_history)
        ko_arr = np.array(ko_prices[-n:])
        pep_arr = np.array(pep_prices[-n:])

        # Compute spread: KO - beta * PEP
        spread = ko_arr - self._beta * pep_arr

        # Z-score of the current spread value
        mean_spread = np.mean(spread)
        std_spread = np.std(spread)
        if std_spread == 0:
            return

        current_spread = spread[-1]
        self._z_score = (current_spread - mean_spread) / std_spread

        self.log(f"Z-score: {self._z_score:.4f}, Position: {self._position}")

        # Entry/exit logic
        if self._position == 0:
            if self._z_score <= -2.0:
                self._enter_position(+1)
            elif self._z_score >= 2.0:
                self._enter_position(-1)
        elif self._position == +1:
            # Long spread: exit when z crosses above 0.5
            if self._z_score >= 0.5:
                self._exit_position()
        elif self._position == -1:
            # Short spread: exit when z crosses below -0.5
            if self._z_score <= -0.5:
                self._exit_position()

    def _enter_position(self, direction: int):
        """
        Enter a dollar-neutral position.
        direction = +1: long KO, short PEP
        direction = -1: short KO, long PEP
        """
        ko_price = self.securities["KO"].price
        pep_price = self.securities["PEP"].price

        if ko_price <= 0 or pep_price <= 0:
            return

        # Use half of available cash for each leg to maintain dollar neutrality
        available_cash = self.portfolio.cash
        if available_cash <= 0:
            return

        # Allocate 50% of cash to each leg
        allocation = available_cash * 0.5

        ko_shares = int(allocation / ko_price)
        pep_shares = int(allocation / pep_price)

        if ko_shares <= 0 or pep_shares <= 0:
            return

        if direction == +1:
            # Long KO, Short PEP
            self.market_order("KO", ko_shares)
            self.market_order("PEP", -pep_shares)
        else:
            # Short KO, Long PEP
            self.market_order("KO", -ko_shares)
            self.market_order("PEP", pep_shares)

        self._position = direction
        self.log(f"Entered position {direction}: KO={ko_shares}, PEP={pep_shares}")

    def _exit_position(self):
        """Liquidate both legs."""
        self.liquidate("KO")
        self.liquidate("PEP")
        self._position = 0
        self.log("Exited position, liquidated both legs.")
