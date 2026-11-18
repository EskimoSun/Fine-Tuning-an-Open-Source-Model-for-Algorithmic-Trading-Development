from AlgorithmImports import *


class RocRotationAlgorithm(QCAlgorithm):
    """Monthly rotation among SPY, EFA, EEM, AGG, GLD using daily ROC(60)."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.settings.automatic_indicator_warm_up = True

        self._tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._roc = {}

        for ticker in self._tickers:
            equity = self.add_equity(ticker, resolution=Resolution.MINUTE)
            roc = self.roc(ticker, 60, resolution=Resolution.DAILY)
            self._roc[ticker] = roc
            # Attach the indicator to the security object so it is available via equity.roc
            setattr(equity, "roc", roc)

        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance
        )

    def _rebalance(self):
        if not all(roc.is_ready for roc in self._roc.values()):
            return

        values = {ticker: roc.current.value for ticker, roc in self._roc.items()}
        if any(value < 0 for value in values.values()):
            for ticker in self._tickers:
                self.liquidate(ticker)
            self.log(f"Rebalance: all ROC < 0, liquidated all. Values: {values}")
            return

        top3 = sorted(values, key=lambda t: values[t], reverse=True)[:3]
        for ticker in self._tickers:
            if ticker in top3:
                self.set_holdings(ticker, 1.0 / 3)
            else:
                self.liquidate(ticker)
        self.log(f"Rebalance: top 3 = {top3}. Values: {values}")
