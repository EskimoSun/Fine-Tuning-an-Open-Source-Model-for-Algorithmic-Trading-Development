from AlgorithmImports import *
from typing import Dict, List, Optional


class MonthlyRocRotation(QCAlgorithm):
    """Monthly rate-of-change rotation across SPY, EFA, EEM, AGG, GLD."""

    def initialize(self) -> None:
        """Set up the algorithm: data, indicators, schedule, and portfolio rules."""
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Enable automatic indicator warm-up so ROC is ready before the first signal
        self.settings.automatic_indicator_warm_up = True

        # Asset universe
        self._symbols: List[Symbol] = []
        for ticker in ("SPY", "EFA", "EEM", "AGG", "GLD"):
            equity = self.add_equity(ticker, resolution=Resolution.MINUTE)
            self._symbols.append(equity.symbol)

        # 60-period ROC on daily bars per asset
        self._roc: Dict[Symbol, RateOfChange] = {}
        for symbol in self._symbols:
            indicator = self.roc(symbol, 60, resolution=Resolution.DAILY)
            self._roc[symbol] = indicator

        # Schedule: first trading day of each month, one minute after market open
        self.schedule.on(
            self.date_rules.month_start(self._symbols[0]),
            self.time_rules.after_market_open(self._symbols[0], 1),
            self._on_monthly_rotation
        )

    def _on_monthly_rotation(self) -> None:
        """Execute the monthly rotation: rank by ROC, hold top 3 or go to cash."""
        # Collect ROC values for all assets
        roc_values: Dict[Symbol, float] = {}
        for symbol in self._symbols:
            indicator = self._roc[symbol]
            if not indicator.is_ready:
                self.log(f"ROC not ready for {symbol}; skipping rotation.")
                return
            roc_values[symbol] = indicator.current.value

        # Check if all ROC values are negative
        if all(value < 0 for value in roc_values.values()):
            self.log("All ROC values are negative. Liquidating all positions and holding cash.")
            self.liquidate()
            return

        # Rank symbols by ROC descending
        ranked: List[Symbol] = sorted(roc_values.keys(), key=lambda s: roc_values[s], reverse=True)
        top_3: List[Symbol] = ranked[:3]

        self.log(f"ROC values: { {str(s): round(v, 4) for s, v in roc_values.items()} }")
        self.log(f"Top 3 holdings: { [str(s) for s in top_3] }")

        # Liquidate existing holdings, then set equal-weight targets for top 3
        self.liquidate_existing_holdings()
        for symbol in top_3:
            self.set_holdings(symbol, 1.0 / 3.0)

    def on_data(self, slice: Slice) -> None:
        """No per-bar logic needed; rotation is driven by the scheduled event."""
        pass
