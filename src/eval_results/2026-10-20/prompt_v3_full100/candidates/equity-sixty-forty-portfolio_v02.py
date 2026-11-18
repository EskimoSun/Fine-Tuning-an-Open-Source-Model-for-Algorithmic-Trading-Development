from AlgorithmImports import *


class Rebalance6040(QCAlgorithm):
    """60% SPY / 40% TLT portfolio with quarterly rebalancing."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)
        self.tlt = self.add_equity("TLT", resolution=Resolution.MINUTE)

        self._first_bar_done = False

        # Rebalance at the start of every quarter (Jan, Apr, Jul, Oct)
        self.schedule.on(
            self.date_rules.month_start(self.spy, 1, 4, 7, 10),
            self.time_rules.at(9, 31),
            self._rebalance
        )

    def on_data(self, data: Slice):
        if self._first_bar_done:
            return
        if "SPY" not in data or "TLT" not in data:
            return
        self._first_bar_done = True
        self.set_holdings("SPY", 0.60)
        self.set_holdings("TLT", 0.40)

    def _rebalance(self):
        spy_symbol = "SPY"
        tlt_symbol = "TLT"
        if spy_symbol not in self.securities or tlt_symbol not in self.securities:
            return
        if not self.securities[spy_symbol].has_data or not self.securities[tlt_symbol].has_data:
            return

        portfolio_value = self.portfolio.total_portfolio_value
        if portfolio_value <= 0:
            return

        spy_value = self.portfolio[spy_symbol].market_value
        tlt_value = self.portfolio[tlt_symbol].market_value

        spy_weight = spy_value / portfolio_value
        tlt_weight = tlt_value / portfolio_value

        # Check if either weight is more than 5 percentage points off target
        if abs(spy_weight - 0.60) > 0.05 or abs(tlt_weight - 0.40) > 0.05:
            self.set_holdings(spy_symbol, 0.60)
            self.set_holdings(tlt_symbol, 0.40)
            self.log(f"Rebalanced: SPY {spy_weight:.4f} -> 0.60, TLT {tlt_weight:.4f} -> 0.40")
        else:
            self.log(f"No rebalance needed: SPY {spy_weight:.4f}, TLT {tlt_weight:.4f}")
