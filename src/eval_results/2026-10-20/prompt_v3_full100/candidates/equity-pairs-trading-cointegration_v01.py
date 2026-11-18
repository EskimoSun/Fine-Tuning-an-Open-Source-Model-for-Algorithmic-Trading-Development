from AlgorithmImports import *

import math
from datetime import datetime, timedelta


class PairsTradingCokePepsi(QCAlgorithm):
    """
    Pairs trading strategy for KO (Coca-Cola) and PEP (PepsiCo).
    Uses a z-score of the price ratio to detect mean-reversion opportunities.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Add equities
        self.ko = self.add_equity("KO", Resolution.DAILY)
        self.pep = self.add_equity("PEP", Resolution.DAILY)

        # Parameters
        self.lookback = 60          # days for rolling mean/std
        self.entry_z = 2.0          # enter when |z| >= 2
        self.exit_z = 0.5           # exit when |z| <= 0.5
        self.position_size = 0.4    # fraction of portfolio per leg

        # State
        self._in_position = False
        self._long_symbol = None
        self._short_symbol = None

        # Schedule daily check after market open
        self.schedule.on(
            self.date_rules.every_day(self.ko),
            self.time_rules.at(9, 35),
            self.on_daily_check
        )

    def on_daily_check(self):
        """Check z-score and manage positions."""
        if not self.ko.is_tradable or not self.pep.is_tradable:
            return

        ko_price = self.securities[self.ko].price
        pep_price = self.securities[self.pep].price

        if ko_price <= 0 or pep_price <= 0:
            return

        # Compute ratio and z-score using historical data
        ratio_history = []
        for i in range(self.lookback):
            ko_hist = self.ko.history(1, timedelta(days=i + 1))
            pep_hist = self.pep.history(1, timedelta(days=i + 1))
            if len(ko_hist) > 0 and len(pep_hist) > 0:
                ko_p = ko_hist[0].close
                pep_p = pep_hist[0].close
                if pep_p > 0:
                    ratio_history.append(ko_p / pep_p)

        if len(ratio_history) < self.lookback:
            return

        current_ratio = ko_price / pep_price
        mean_ratio = sum(ratio_history) / len(ratio_history)
        variance = sum((r - mean_ratio) ** 2 for r in ratio_history) / len(ratio_history)
        std_ratio = math.sqrt(variance)

        if std_ratio == 0:
            return

        z_score = (current_ratio - mean_ratio) / std_ratio

        if not self._in_position:
            # No position: check for entry
            if z_score >= self.entry_z:
                # KO is expensive relative to PEP -> short KO, long PEP
                self._enter_pair(self.pep, self.ko)
            elif z_score <= -self.entry_z:
                # KO is cheap relative to PEP -> long KO, short PEP
                self._enter_pair(self.ko, self.pep)
        else:
            # In position: check for exit
            if abs(z_score) <= self.exit_z:
                self._exit_pair()

    def _enter_pair(self, long_symbol, short_symbol):
        """Enter a pair trade: long one leg, short the other."""
        self.liquidate()  # ensure clean slate
        self._in_position = True
        self._long_symbol = long_symbol
        self._short_symbol = short_symbol

        # Use set_holdings for long leg
        self.set_holdings(long_symbol, self.position_size)
        # Short the other leg with equal notional
        short_qty = int(self.portfolio.cash * self.position_size / self.securities[short_symbol].price)
        if short_qty > 0:
            self.market_order(short_symbol, -short_qty)

        self.log(f"ENTER: Long {long_symbol}, Short {short_symbol}, Z-score triggered")

    def _exit_pair(self):
        """Close out the pair trade."""
        self.liquidate()
        self._in_position = False
        self._long_symbol = None
        self._short_symbol = None
        self.log("EXIT: Pair closed, z-score back to normal")
