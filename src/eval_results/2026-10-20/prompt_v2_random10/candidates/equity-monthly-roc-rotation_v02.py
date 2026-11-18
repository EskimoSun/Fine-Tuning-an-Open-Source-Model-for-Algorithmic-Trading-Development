from AlgorithmImports import *


class MomentumRotationAlgorithm(QCAlgorithm):
    """
    Monthly momentum rotation across SPY, EFA, EEM, AGG, GLD.
    On the first trading day of each month, rank the 5 tickers by 60-day
    rate of change (daily bars). Allocate one-third of portfolio value to
    each of the top 3. If all 5 are negative, liquidate everything.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.symbols = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self.rsi_lookback = 60  # 60-day rate of change

        # Add equities with daily resolution
        self.equities = {}
        self.roc_indicators = {}
        for symbol_str in self.symbols:
            symbol = self.add_equity(symbol_str, Resolution.DAILY)
            self.equities[symbol] = symbol
            # 60-day rate of change
            roc = self.roc(symbol, self.rsi_lookback, Resolution.DAILY)
            self.roc_indicators[symbol] = roc

        # Schedule: first trading day of each month
        for symbol in self.equities.values():
            self.schedule.on(
                self.date_rules.month_start(symbol),
                self.time_rules.at_market_open(symbol),
                self.on_month_start
            )

    def on_month_start(self, context):
        """
        Called on the first trading day of each month.
        Rank tickers by 60-day ROC, allocate to top 3, or liquidate if all negative.
        """
        # Check that all ROC indicators are ready
        for symbol, roc in self.roc_indicators.items():
            if not roc.is_ready:
                self.log(f"ROC not ready for {symbol.get_name()} yet.")
                return

        # Collect ROC values
        roc_values = {}
        for symbol, roc in self.roc_indicators.items():
            roc_values[symbol] = roc.current.value

        self.log(f"Month start. ROC values: { {s.get_name(): round(v, 4) for s, v in roc_values.items()} }")

        # Check if all are negative
        if all(v < 0 for v in roc_values.values()):
            self.log("All 5 tickers have negative 60-day ROC. Liquidating all positions.")
            self.liquidate()
            return

        # Rank by ROC descending
        ranked = sorted(roc_values.items(), key=lambda x: x[1], reverse=True)
        top3 = [s for s, v in ranked[:3]]
        others = [s for s in self.equities if s not in top3]

        self.log(f"Top 3: { [s.get_name() for s in top3] }")
        self.log(f"Selling: { [s.get_name() for s in others] }")

        # Liquidate the non-top-3 positions
        for symbol in others:
            if symbol in self.portfolio and self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)

        # Allocate one-third of portfolio value to each top-3 ticker
        portfolio_value = self.portfolio.total_value
        target_per_ticker = portfolio_value / 3.0

        for symbol in top3:
            self.set_holdings(symbol, target_per_ticker / portfolio_value)

    def on_data(self, data: Slice):
        """
        No per-bar logic needed; all actions are scheduled on month start.
        """
        pass
