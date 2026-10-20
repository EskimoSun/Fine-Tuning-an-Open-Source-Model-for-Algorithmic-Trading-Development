from AlgorithmImports import *


class SpyTltRebalanceAlgorithm(QCAlgorithm):
    """
    SPY 0.6 / TLT 0.4 portfolio, minute resolution.
    - Allocate bar 1 (first minute bar after warm-up).
    - Quarter start + 1 minute: rebalance only if any |weight - target| > 0.05.
    - Backtest 2022-01-01 to 2024-12-31, 100k starting cash.
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        # Minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)
        self.tlt = self.add_equity("TLT", resolution=Resolution.MINUTE)

        # Target weights
        self._targets = {self.spy.symbol: 0.6, self.tlt.symbol: 0.4}

        # Track whether initial allocation has been done
        self._allocated = False

        # Schedule quarter-start rebalance check at +1 minute after market open
        self.schedule.on(
            self.date_rules.month_start(self.spy.symbol, 1, 4, 7, 10),
            self.time_rules.after_market_open(self.spy.symbol, 1),
            self._on_quarter_start
        )

    def on_data(self, data: Slice):
        # Allocate on the first minute bar
        if not self._allocated:
            self._allocate()
            self._allocated = True
            return

    def _allocate(self):
        """Allocate initial holdings to target weights."""
        for symbol, weight in self._targets.items():
            self.set_holdings(symbol, weight)
        self.log(f"Initial allocation: SPY 0.6, TLT 0.4")

    def _on_quarter_start(self):
        """Rebalance only if any |weight - target| > 0.05."""
        portfolio_value = self.portfolio.portfolio_value
        if portfolio_value <= 0:
            return

        needs_rebalance = False
        for symbol, target in self._targets.items():
            invested = self.portfolio[symbol].invested
            current_weight = invested / portfolio_value
            if abs(current_weight - target) > 0.05:
                needs_rebalance = True
                self.log(f"{symbol}: current={current_weight:.4f}, target={target:.4f}, diff={abs(current_weight - target):.4f}")
                break

        if needs_rebalance:
            for symbol, weight in self._targets.items():
                self.set_holdings(symbol, weight)
            self.log("Rebalanced to target weights.")
        else:
            self.log("No rebalance needed; all weights within 0.05 of target.")
