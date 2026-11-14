# region imports
from AlgorithmImports import *
# endregion


class PermanentPortfolioRotationAlgorithm(QCAlgorithm):
    _targets: list[PortfolioTarget] = []
    _weight: float = 0.2
    _drift_threshold = 0.03

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        for ticker in ["SPY", "EFA", "EEM", "AGG", "GLD"]:
            equity = self.add_equity(ticker)
            equity.roc = self.roc(equity, 63, Resolution.DAILY)
            # Alternatively, use a manual indicator.
            # equity.roc = RateOfChange(63)
            # self.warm_up_indicator(equity, equity.roc, Resolution.DAILY)
            # self.register_indicator(equity, equity.roc, Resolution.DAILY)
            self._targets.append(PortfolioTarget(equity, self._weight))
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.before_market_close("SPY", 1),
            self._rebalance,
        )

    def _rebalance(self) -> None:
        for security in self.securities.values():
            current_weight = security.holdings.quantity / self.portfolio.total_holdings_value
            target_weight = self._targets[security.roc.rank].weight
            if abs(current_weight - target_weight) > self._drift_threshold:
                self.set_holdings(self._targets)
