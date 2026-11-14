# region imports
from AlgorithmImports import *
import math
from datetime import timedelta
# endregion

class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
    _z_score_threshold = 2
    _z_score_exit_threshold = 0.5
    _drift_threshold = 0.01
    _drift_target_percent = 0.005
    _correlation_window = 60
    _num_std_devs = 3

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(200000)
        self.settings.seed_initial_prices = True
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._pep = self.add_equity("PEP", Resolution.MINUTE)
        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pair = self.get_pair(self._pep, self._ko)
        self._pair.correlation = self.correlation(self._pair, self._correlation_window)
        self._pair.mean = self.rolling_mean(self._pair, self._correlation_window)
        self._pair.standard_deviation = self.rolling_standard_deviation(self._pair, self._correlation_window)
        self.schedule.on(self.date_rules.week_start(self._pep), self.time_rules.after_market_open(self._pep, 1), self._rebalance)

    def on_data(self, data: Slice) -> None:
        bar = data.bars.get(self._pair)
        if not bar:
            return
        price = bar.close
        inverted = 1 / price
        self._pair.update(inverted)
        z_score = self._pair.current.z_score(self._num_std_devs)
        if not self._pair.invested:
            if z_score > self._z_score_threshold:
                self._pair.invested = True
                self._pair.target_percent = -self._drift_target_percent
                self._pair.offset_percent = self._drift_target_percent
            elif z_score < -self._z_score_threshold:
                self._pair.invested = True
                self._pair.target_percent = self._drift_target_percent
                self._pair.offset_percent = -self._drift_target_percent
        elif self._pair.invested:
            drift = price / self._pair.mean.current.value - 1
            if abs(drift) > self._drift_threshold and abs(z_score) < self._z_score_exit_threshold:
                self._pair.invested = False
                self._pair.target_percent = 0
                self._pair.offset_percent = 0

    def _rebalance(self) -> None:
        if not self._pair.invested:
            return
        targets = [PortfolioTarget(self._pair.symbol, self._pair.target_percent)]
        if self._pair.offset_percent:
            targets.append(PortfolioTarget(self._pair.offsetting_symbol, self._pair.offset_percent))
        self.set_holdings(targets, True)
