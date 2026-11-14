# region imports
from AlgorithmImports import *
import numpy as np
from scipy import stats
# endregion

class KoPepPairsTradingAlgorithm(QCAlgorithm):
    _averages: dict[Symbol, 'MovingAveragePair'] = {}
    _count = 0

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        pep = self.add_equity("PEP")
        ko = self.add_equity("KO")

        self._averages[pep] = self._create_average(pep, ko)
        self._averages[ko] = self._create_average(ko, pep)

        self.schedule.on(
            self.date_rules.week_start(),
            self.time_rules.after_market_open(pep, 1),
            self._rebalance
        )

    def _create_average(self, up: Symbol, down: Symbol) -> 'MovingAveragePair':
        average = MovingAveragePair(20, 20)
        self.warm_up_indicator(average, up)
        self.register_indicator(up, average)
        return average

    def _rebalance(self) -> None:
        if not self._averages:
            return

        pep = self.securities["PEP"]
        ko = self.securities["KO"]
        average = self._averages[pep]
        correlation = average.correlation.ko

        if not correlation.is_ready:
            return

        z_score = stats.zscore(average.current.value, average.mean, average.standard_deviation)

        if not self._count:
            if z_score < -2:
                self.set_holdings(pep, 0.5)
                self.set_holdings(ko, -0.5)
                self._count = 1
            elif z_score > 2:
                self.set_holdings(pep, -0.5)
                self.set_holdings(ko, 0.5)
                self._count = 1
        elif self._count == 1:
            if -0.5 < z_score and z_score < 0.5:
                self.liquidate()
                self._count = 0
