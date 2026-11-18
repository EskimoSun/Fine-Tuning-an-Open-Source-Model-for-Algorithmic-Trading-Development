from AlgorithmImports import *

class MomentumRotationAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.automatic_indicator_warm_up = True

        self._tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._securities = {}
        self._rocs = {}

        for ticker in self._tickers:
            equity = self.add_equity(ticker, resolution=Resolution.MINUTE)
            self._securities[ticker] = equity
            self._rocs[ticker] = self.roc(equity, 60, resolution=Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance
        )

    def _rebalance(self):
        securities = [self._securities[t] for t in self._tickers]
        rocs = [self._rocs[t] for t in self._tickers]

        if not all(roc.is_ready for roc in rocs):
            return

        if all(roc.current.value < 0 for roc in rocs):
            self.liquidate()
            return

        ranked = sorted(securities, key=lambda s: self._rocs[s.symbol].current.value, reverse=True)[:3]
        targets = [PortfolioTarget(s.symbol, 1.0 / 3.0) for s in ranked]
        self.set_holdings(targets, liquidate_existing_holdings=True)
