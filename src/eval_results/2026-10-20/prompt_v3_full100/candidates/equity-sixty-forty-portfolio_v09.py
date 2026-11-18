from AlgorithmImports import *
from typing import Dict, Optional


class SixtyFortyReference(QCAlgorithm):
    """60/40 reference portfolio: SPY 60%, TLT 40%, quarterly rebalance."""

    # Compliance / audit constants
    DRIFT_THRESHOLD: float = 0.05  # 5 percentage points
    TARGET_WEIGHTS: Dict[str, float] = {"SPY": 0.60, "TLT": 0.40}

    def initialize(self) -> None:
        """Set up the algorithm: capital, data, schedule, and state."""
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000.0)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Add minute-resolution equity data
        self.spy: Security = self.add_equity("SPY", resolution=Resolution.MINUTE)
        self.tlt: Security = self.add_equity("TLT", resolution=Resolution.MINUTE)

        # Track whether initial allocation has been made
        self._initially_allocated: bool = False

        # Schedule quarterly rebalance: first trading day of each quarter, 1 min after open
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 1),
            self._on_quarterly_rebalance
        )

    def on_data(self, slice: Slice) -> None:
        """Handle incoming data; perform initial allocation on the first bar."""
        if self._initially_allocated:
            return

        # Ensure both symbols have data in this slice
        if "SPY" not in slice or "TLT" not in slice:
            return

        # Perform initial allocation using portfolio targets
        self._allocate_to_targets()
        self._initially_allocated = True
        self.log("Initial 60/40 allocation executed.")

    def _on_quarterly_rebalance(self) -> None:
        """Scheduled callback: check drift and rebalance if needed."""
        if not self._initially_allocated:
            return

        # Compute current weights
        total_value: float = self.portfolio.total_value
        if total_value <= 0:
            self.log("Portfolio total value is non-positive; skipping rebalance.")
            return

        current_weights: Dict[str, float] = {}
        for ticker, target in self.TARGET_WEIGHTS.items():
            symbol = self.Securities[ticker].symbol
            invested: float = self.portfolio[symbol].invested
            current_weights[ticker] = invested / total_value

        # Check if any weight is outside the drift threshold
        needs_rebalance: bool = False
        for ticker, target in self.TARGET_WEIGHTS.items():
            drift: float = abs(current_weights[ticker] - target)
            if drift > self.DRIFT_THRESHOLD:
                self.log(
                    f"Drift detected for {ticker}: current={current_weights[ticker]:.4f}, "
                    f"target={target:.4f}, drift={drift:.4f} > threshold={self.DRIFT_THRESHOLD:.4f}"
                )
                needs_rebalance = True
                break

        if not needs_rebalance:
            self.log("All weights within 5% drift threshold; skipping rebalance.")
            return

        # Rebalance to target weights
        self._allocate_to_targets()
        self.log("Quarterly rebalance executed to target weights.")

    def _allocate_to_targets(self) -> None:
        """Reset portfolio to target weights using set_holdings."""
        for ticker, weight in self.TARGET_WEIGHTS.items():
            symbol = self.Securities[ticker].symbol
            self.set_holdings(symbol, weight)
