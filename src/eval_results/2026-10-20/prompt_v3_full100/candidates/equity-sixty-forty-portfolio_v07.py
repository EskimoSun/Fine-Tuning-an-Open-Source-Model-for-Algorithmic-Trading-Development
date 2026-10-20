from AlgorithmImports import *


class SpyTlt6040Benchmark(QCAlgorithm):
    """
    60/40 SPY/TLT benchmark portfolio with quarterly rebalancing and drift tolerance.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 3)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Data
        self.spy = self.add_equity("SPY", Resolution.DAILY)
        self.tlt = self.add_equity("TLT", Resolution.DAILY)

        # Target weights
        self._target_weights = {
            self.spy.symbol: 0.60,
            self.tlt.symbol: 0.40,
        }

        # Drift tolerance: only rebalance if any asset deviates by more than 2% absolute from target
        self._drift_tolerance = 0.02

        # Schedule quarterly rebalancing on the first trading day of Jan, Apr, Jul, Oct
        for month in [1, 4, 7, 10]:
            self.schedule.on(
                self.date_rules.month_start(self.spy.symbol, month),
                self.time_rules.at(9, 31),
                self._rebalance
            )

        # Initial allocation at start
        self._initially_allocated = False

    def on_data(self, data: Slice):
        if self._initially_allocated:
            return
        if not data.contains(self.spy.symbol) or not data.contains(self.tlt.symbol):
            return
        if self.spy.symbol not in data or self.tlt.symbol not in data:
            return
        # Ensure both securities have valid prices
        if self.securities[self.spy.symbol].price <= 0 or self.securities[self.tlt.symbol].price <= 0:
            return

        # Initial allocation
        self._set_target_weights(self._target_weights)
        self._initially_allocated = True
        self.log("Initial 60/40 allocation executed.")

    def _rebalance(self):
        """Check drift and rebalance if needed."""
        if not self._initially_allocated:
            return

        current_weights = self._get_current_weights()
        max_drift = max(
            abs(current_weights[sym] - self._target_weights[sym])
            for sym in self._target_weights
        )

        if max_drift <= self._drift_tolerance:
            self.log(f"Drift {max_drift:.4f} within tolerance {self._drift_tolerance}. No rebalance.")
            return

        self.log(f"Drift {max_drift:.4f} exceeds tolerance {self._drift_tolerance}. Rebalancing.")
        self._set_target_weights(self._target_weights)

    def _get_current_weights(self):
        """Compute current portfolio weights for SPY and TLT."""
        total_value = self.portfolio.total_value
        if total_value <= 0:
            return {sym: 0.0 for sym in self._target_weights}
        weights = {}
        for sym in self._target_weights:
            invested = self.portfolio[sym].invested
            weights[sym] = invested / total_value
        return weights

    def _set_target_weights(self, target_weights):
        """Set holdings to target weights using set_holdings."""
        for sym, weight in target_weights.items():
            self.set_holdings(sym, weight)
