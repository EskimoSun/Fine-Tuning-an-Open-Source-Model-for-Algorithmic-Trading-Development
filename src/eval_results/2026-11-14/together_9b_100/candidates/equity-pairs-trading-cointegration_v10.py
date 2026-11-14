# region imports
from AlgorithmImports import *
import math
from datetime import timedelta
import numpy as np
# endregion

class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
    _alpha: float = 0.0
    _beta: float = 0.0
    _spread_mean: float = 0.0
    _spread_std: float = 0.0
    _num_warm_up_days = 60

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pep = self.add_equity("PEP", Resolution.MINUTE)
        self._ko.session.size = timedelta(minutes=60)
        self._pep.session.size = timedelta(minutes=60)

        self._alpha = self._estimate_factor(self._ko, self._pep)
        self._beta = self._estimate_factor(self._pep, self._ko)

        self._update_spread_statistics()
        self.set_warm_up(self._num_warm_up_days, Resolution.DAILY)

    def _estimate_factor(self, independent: Equity, dependent: Equity) -> float:
        regression = LinearRegression()
        self.train(regression, independent, dependent, self._num_warm_up_days, Resolution.DAILY)
        return regression.slope

    def _update_spread_statistics(self) -> None:
        price = self.securities[self._ko].price
        pair_price = price / self.securities[self._pep].price
        self._spread_mean += (pair_price - self._spread_mean) / self._num_warm_up_days
        self._spread_std = np.sqrt(
            sum((pair_price - self._spread_mean) ** 2 for _ in range(self._num_warm_up_days)) / self._num_warm_up_days
        )

    def on_data(self, data: Slice) -> None:
        if not self.is_warming_up:
            bar = data.bars.get(self._ko)
            if not bar:
                return
            pair_price = bar.close / data.bars[self._pep].close
            z_score = (pair_price - self._spread_mean) / self._spread_std
            if not self.portfolio.invested and abs(z_score) > 2:
                self._rebalance(z_score)
            elif self.portfolio.invested and abs(z_score) < 0.5:
                self.liquidate()

    def _rebalance(self, z_score: float) -> None:
        target_percent = -z_score * 0.5
        weight = min(max(target_percent, -1), 1)
        self.set_holdings([
            PortfolioTarget(self._ko, weight),
            PortfolioTarget(self._pep, -weight)
        ])
