# region imports
from AlgorithmImports import *
# endregion


class MonthlyRocRotationAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

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

        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance,
        )

    def _rebalance(self) -> None:
        securities = list(self.securities.values())
        if not all(security.roc.is_ready for security in securities):
            return

        ranked = sorted(
            securities,
            key=lambda security: security.roc.current.value,
            reverse=True,
        )

        top_3 = ranked[:3]
        targets = [PortfolioTarget(security.symbol, self._weight) for security in top_3]
        self.set_holdings(targets, liquidate_existing_holdings=True)
