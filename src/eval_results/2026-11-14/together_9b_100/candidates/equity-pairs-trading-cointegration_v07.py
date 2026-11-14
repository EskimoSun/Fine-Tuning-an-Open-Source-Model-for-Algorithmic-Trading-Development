# region imports
from AlgorithmImports import *
# endregion


class ConsumerBraggPairsTradingAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(200_000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._ko = self.add_equity("KO", Resolution.DAILY)
        self._pep = self.add_equity("PEP", Resolution.DAILY)
        self._optimizer = LinearRegressionOptimizer(180)
        self._zscore = SimpleMovingAverage(10)
        self._correlation = SimpleMovingAverage(10)
        self._quantity = 0
        self._target_zscore = 2.0
        self._seed_initial_prices = True
        if self._seed_initial_prices:
            history = self.history([self._ko, self._pep], timedelta(180), Resolution.DAILY)
            for data_point in history:
                self._update_indicators(data_point.end_time, data_point.value)

    def _update_indicators(self, time: datetime, value: float) -> bool:
        self._optimizer.update(time, value)
        if not self._optimizer.is_ready:
            return False
        # Ratio of log-prices, fed through a Z-score to normalize and rank the spread.
        ko_log = np.log(value)
        pep_log = np.log(self._pep.price)
        self._zscore.update(time, (ko_log - pep_log) / self._correlation.current.value)
        # Power of 2 spread: when the ratio of prices is 2x or 0.5x, we trade.
        return self._zscore.is_ready

    def on_data(self, slice: Slice) -> None:
        if not self._update_indicators(slice.time, slice.bars[self._ko].close):
            return
        # Long KO when Z-score < -2 (KO relatively cheaper), short when > 2.
        z = self._zscore.current.value
        if self._quantity == 0 and z < -self._target_zscore:
            self._rebalance(z)
        elif self._quantity < 0 and z > self._target_zscore:
            self._rebalance(z)

    def _rebalance(self, z: float) -> None:
        # Equal weight the two assets after scaling by Z-score.
        weight = 0.5 * (1 + z / self._zscore.max.value)
        self.set_holdings(self._ko, weight, True)
