# region imports
from AlgorithmImports import *
# endregion


class EFAEMMGOLDRotationAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        # Trade multiple ETFs.
        tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._weight = 1.0 / len(tickers)
        for ticker in tickers:
            # Minute-resolution data, but rank on a daily ROC indicator.
            equity = self.add_equity(ticker)
            equity.roc = self.roc(equity, 60, Resolution.DAILY)
            # Alternatively, use a manual indicator.
            # equity.roc = RateOfChange(60)
            # self.warm_up_indicator(equity, equity.roc, Resolution.DAILY)
            # self.register_indicator(equity, equity.roc, Resolution.DAILY)
        # Rebalance monthly to trade the top 3 performers.
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance
        )


    def _rebalance(self) -> None:
        for security in self.securities.values():
            if not security.roc.is_ready:
                continue
            roi = security.roc.current.value
            if roi < 0:
                security.target_weight = 0
                continue
            # 3 best performers by dollar ROC.
            security.weight = sorted([s for s in self.securities.values()], key=lambda s: s.roc.current.value, reverse=True)[
                :3
            ][-1].symbol
            self.plot(RowColumnLabel(security.symbol.value, "ROC"), roi)

        if not any([security.target_weight for security in self.securities.values()]):
            self.liquidate()
            return
        # Equal weight among the top 3.
        sum_of_weights = sum([security.target_weight for security in self.securities.values()])
        self.set_holdings(self.securities, self._weight / sum_of_weights)
