from AlgorithmImports import *


class SixtyFortyRebalancer(QCAlgorithm):
    """Classic 60/40 SPY/TLT portfolio with quarterly drift-triggered rebalancing."""

    def initialize(self):
        self.set_start_date(2022, 1, 3)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Data
        self.spy = self.add_equity("SPY", Resolution.DAILY)
        self.tlt = self.add_equity("TLT", Resolution.DAILY)

        # Targets and drift threshold
        self._target_equity = 0.60
        self._target_bond = 0.40
        self._drift_threshold = 0.05  # 5 percentage points

        # Schedule: first Monday of each quarter, after market open
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 5),
            self._maybe_rebalance
        )

    def _maybe_rebalance(self):
        if not self.portfolio.invested:
            # Initial allocation
            self._rebalance()
            return

        equity_value = self.portfolio[self.spy.symbol].market_value
        bond_value = self.portfolio[self.tlt.symbol].market_value
        total = equity_value + bond_value
        if total <= 0:
            return

        equity_weight = equity_value / total
        bond_weight = bond_value / total

        equity_drift = abs(equity_weight - self._target_equity)
        bond_drift = abs(bond_weight - self._target_bond)

        if equity_drift >= self._drift_threshold or bond_drift >= self._drift_threshold:
            self.log(f"Drift detected: equity={equity_weight:.2%}, bond={bond_weight:.2%}. Rebalancing.")
            self._rebalance()
        else:
            self.log(f"No significant drift: equity={equity_weight:.2%}, bond={bond_weight:.2%}. Skipping.")

    def _rebalance(self):
        self.set_holdings(self.spy.symbol, self._target_equity)
        self.set_holdings(self.tlt.symbol, self._target_bond)
