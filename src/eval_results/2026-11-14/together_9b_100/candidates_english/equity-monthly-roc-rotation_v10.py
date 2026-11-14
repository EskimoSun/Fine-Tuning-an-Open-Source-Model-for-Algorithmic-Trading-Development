# region imports
from AlgorithmImports import *
# endregion


class PermanentPortfolioAlgorithm(QCAlgorithm):
    _targets: list[PortfolioTarget] = []
    _weight: float = 1.0 / 3.0
    _drift_threshold = 0.01

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.automatic_indicator_warm_up = True
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        for ticker in ["SPY", "EFA", "EEM", "AGG", "GLD"]:
            equity = self.add_equity(ticker, Resolution.MINUTE)
            equity.roc = self.roc(equity, 60, Resolution.DAILY)
            # Alternatively, use a manual indicator.
            # equity.roc = RateOfChange(60)
            # self.warm_up_indicator(equity, equity.roc, Resolution.DAILY)
            # self.register_indicator(equity, equity.roc, Resolution.DAILY)
            self._targets.append(PortfolioTarget(equity.symbol, self._weight))
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance,
        )

    def _rebalance(self) -> None:
        for target in self._targets:
            current_weight = self.portfolio[target.symbol].holdings_value / self.portfolio.total_holdings_value
            if abs(current_weight - self._weight) > self._drift_threshold:
                self.set_holdings(self._targets, liquidate_existing_holdings=True)
                return
