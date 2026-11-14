# region imports
from AlgorithmImports import *
# endregion


class EmaCrossRotationAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._weight = 1.0 / len(tickers)

        for ticker in tickers:
            equity = self.add_equity(ticker)
            equity.roc = self.roc(equity, 60, Resolution.DAILY)
            # Alternatively, use a manual indicator.
            # equity.roc = RateOfChange(60)
            # self.warm_up_indicator(equity, equity.roc, Resolution.DAILY)
            # self.register_indicator(equity, equity.roc, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start("SPY", 2),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance
        )

    def _rebalance(self) -> None:
        for security in self.securities.values():
            if not security.roc.is_ready:
                continue

            value = security.roc.current.value
            if value < 0:
                self.liquidate(security)
                continue

            self.set_holdings(security, self._weight)
