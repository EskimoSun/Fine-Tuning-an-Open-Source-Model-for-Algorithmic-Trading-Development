from AlgorithmImports import *


class RocRotationAlgorithm(QCAlgorithm):
    """Monthly rotation among SPY, EFA, EEM, AGG, GLD based on 60-day ROC."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._roc = {}

        for ticker in self.tickers:
            self.add_equity(ticker, resolution=Resolution.DAILY)
            self._roc[ticker] = self.roc(ticker, 60, resolution=Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.at_market_open(),
            self._on_month_start
        )

    def _on_month_start(self):
        if not all(roc.is_ready for roc in self._roc.values()):
            return

        values = {ticker: roc.current.value for ticker, roc in self._roc.items()}
        self.Log(f"Month start ROC: {values}")

        # Liquidate all current holdings first
        for ticker in self.tickers:
            self.liquidate(ticker)

        # If all ROC < 0, stay in cash
        if all(v < 0 for v in values.values()):
            self.Log("All ROC < 0, staying in cash.")
            return

        # Pick top 3 by ROC
        ranked = sorted(values.items(), key=lambda x: x[1], reverse=True)
        top3 = [ticker for ticker, _ in ranked[:3]]

        for ticker in top3:
            self.set_holdings(ticker, 1.0 / 3.0)
            self.Log(f"Allocated 1/3 to {ticker} (ROC={values[ticker]:.4f})")
