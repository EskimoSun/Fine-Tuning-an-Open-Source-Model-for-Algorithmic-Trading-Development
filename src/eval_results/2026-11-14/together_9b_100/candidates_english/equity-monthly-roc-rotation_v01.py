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
            symbol = self.add_equity(ticker, Resolution.MINUTE).symbol
            self._targets.append(PortfolioTarget(symbol, self._weight))
        self.schedule.on(
            self.date_rules.month_end("SPY", 2),
            self.time_rules.after_market_open("SPY", 5),
            self._rebalance,
        )

    def _rebalance(self) -> None:
        if not self.portfolio.invested:
            return
        securities = list(self.securities.values())
        if not securities:
            return
        returns = []
        for security in securities:
            symbol = security.symbol
            period_return = self.return(symbol, self.time_rules.month)
            returns.append((symbol, period_return))
        returns.sort(key=lambda x: x[1], reverse=True)
        top_2 = returns[:2]
        bottom_3 = returns[2:]
        new_weights = [self._weight for _, _ in top_2] + [self._weight * -1 for _, _ in bottom_3]
        sum_weight = sum([self._weight for _, _ in top_2]) + sum([self._weight * -1 for _, _ in bottom_3])
        if abs(sum_weight) > self._drift_threshold:
            self.set_holdings(self._targets, True)
