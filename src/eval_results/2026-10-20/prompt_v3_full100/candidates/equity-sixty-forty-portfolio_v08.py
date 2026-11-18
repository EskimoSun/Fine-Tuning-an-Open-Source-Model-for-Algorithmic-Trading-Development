from AlgorithmImports import *


class SixtyFortyReference(QCAlgorithm):
    """60/40 reference portfolio: SPY 60%, TLT 40%, quarterly rebalance."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)
        self.tlt = self.add_equity("TLT", resolution=Resolution.MINUTE)

        self.targets = {self.spy.symbol: 0.60, self.tlt.symbol: 0.40}
        self._initialized = False

        # Rebalance on the first trading day of each quarter, one minute after open
        self.schedule.on(
            self.date_rules.month_start(self.spy.symbol),
            self.time_rules.after_market_open(self.spy.symbol, 1),
            self._rebalance
        )

    def on_data(self, data: Slice):
        if self._initialized:
            return
        if not data.contains(self.spy.symbol) or not data.contains(self.tlt.symbol):
            return
        if self.spy.symbol not in data or self.tlt.symbol not in data:
            return
        # First bar with both symbols: set initial allocation
        self._set_holdings_to_targets()
        self._initialized = True

    def _rebalance(self):
        # Skip if every weight is within 5 percentage points of target
        for symbol, target in self.targets.items():
            if symbol not in self.portfolio:
                continue
            current_weight = self.portfolio[symbol].invested / self.portfolio.total_portfolio_value
            if abs(current_weight - target) > 0.05:
                self._set_holdings_to_targets()
                return
        # All weights within tolerance; do nothing

    def _set_holdings_to_targets(self):
        for symbol, target in self.targets.items():
            self.set_holdings(symbol, target)
