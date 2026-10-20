# QuantConnect LEAN algorithm
# Rebalance top 3 by 60-day ROC at month start +1 minute
# All ROC < 0 -> liquidate all

from AlgorithmImports import *


class RocRotationAlgorithm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        self.symbols = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self.roc_window = 60  # 60 daily bars

        # Enable automatic indicator warm-up
        self.settings.automatic_indicator_warm_up = True

        # Attach ROC to each security object
        for symbol in self.symbols:
            sec = self.add_equity(symbol, Resolution.MINUTE)
            sec.set_warm_up(self.roc_window, Resolution.DAILY)
            # Create ROC indicator on daily resolution
            sec.roc = self.roc(symbol, self.roc_window, Resolution.DAILY)

        # Schedule rebalance at month start + 1 minute after market open
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.after_market_open(1, TimeUnit.MINUTES),
            self.rebalance
        )

    def on_data(self, data: Slice):
        # No need to compute ROC manually; indicators are updated automatically
        # We just ensure indicators are ready before rebalance
        pass

    def rebalance(self):
        # Collect ROC values from the attached indicators
        roc_values = {}
        for symbol in self.symbols:
            sec = self.securities[symbol]
            if sec.roc is not None and sec.roc.is_ready:
                roc_values[symbol] = sec.roc.current.value

        if not roc_values:
            return

        # If all ROC < 0, liquidate everything
        if all(v < 0 for v in roc_values.values()):
            self.liquidate()
            self.log("All ROC < 0, liquidated all positions.")
            return

        # Sort by ROC descending, pick top 3
        sorted_symbols = sorted(roc_values.keys(), key=lambda s: roc_values[s], reverse=True)
        top3 = sorted_symbols[:3]

        # Liquidate any holdings not in top3
        for symbol in self.symbols:
            if symbol not in top3 and self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)

        # Target 1/3 of portfolio in each top-3 security
        for symbol in top3:
            self.set_holdings(symbol, 1.0 / 3.0, PortfolioTargetType.PERCENT_PORTFOLIO)

        self.log(f"Rebalanced to top 3: {top3} with ROCs: {[roc_values[s] for s in top3]}")
