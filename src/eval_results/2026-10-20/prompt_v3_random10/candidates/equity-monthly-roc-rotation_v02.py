from AlgorithmImports import *


class MomentumRotationAlgorithm(QCAlgorithm):
    """
    Monthly momentum rotation across SPY, EFA, EEM, AGG, GLD.
    On the first trading day of each month, rank the 5 tickers by 60-day
    rate of change (daily bars). Allocate 1/3 of portfolio value to each of
    the top 3. If all 5 are negative, liquidate everything and hold cash.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._roc = {}

        for ticker in self.tickers:
            self.add_equity(ticker, resolution=Resolution.DAILY)
            self._roc[ticker] = self.roc(ticker, 60, resolution=Resolution.DAILY)

        # Schedule the rotation on the first trading day of each month
        self.schedule.on(
            self.date_rules.month_start(self.tickers[0]),
            self.time_rules.at(9, 30),
            self._rotate
        )

    def _rotate(self):
        """Rank tickers by 60-day ROC and rebalance to top 3 (or all cash)."""
        # Check that all indicators are ready
        for ticker in self.tickers:
            if not self._roc[ticker].is_ready:
                self.log(f"ROC for {ticker} not ready yet, skipping rotation.")
                return

        # Collect ROC values
        roc_values = {}
        for ticker in self.tickers:
            roc_values[ticker] = self._roc[ticker].current.value

        self.log(f"60-day ROC values: {roc_values}")

        # If all are negative, liquidate everything
        if all(v < 0 for v in roc_values.values()):
            self.log("All 5 tickers have negative 60-day ROC. Liquidating to cash.")
            for ticker in self.tickers:
                self.liquidate(ticker)
            return

        # Rank by ROC descending, take top 3
        ranked = sorted(roc_values.items(), key=lambda x: x[1], reverse=True)
        top3 = [t for t, _ in ranked[:3]]
        others = [t for t in self.tickers if t not in top3]

        self.log(f"Top 3: {top3}, Selling: {others}")

        # Liquidate the non-top-3 positions
        for ticker in others:
            self.liquidate(ticker)

        # Allocate 1/3 of portfolio value to each top-3 ticker
        for ticker in top3:
            self.set_holdings(ticker, 1.0 / 3.0)
