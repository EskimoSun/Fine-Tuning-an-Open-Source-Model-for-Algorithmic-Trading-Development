# region imports
from AlgorithmImports import *
# endregion

class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
    _pep_ratio = SimpleMovingAverage(20)
    _target = 0.0
    _tolerance = 0.01
    _trailing_stop_factor = 1.5

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pep = self.add_equity("PEP", Resolution.MINUTE)

        self._pep_ratio.sma = 20
        # Alternatively, use a manual indicator.
        # self._pep_ratio = SimpleMovingAverage(20)
        # self.warm_up_indicator(self._pep_ratio, self._ko.symbol, Resolution.DAILY)
        # self.register_indicator(self._ko.symbol, self._pep_ratio, Resolution.DAILY)
        self.plot_indicator("PEP Ratio", self._pep_ratio)

        self.schedule.on(
            self.date_rules.every_day(self._ko.symbol),
            self.time_rules.after_market_open(self._ko.symbol, 30),
            self._rebalance
        )

    def _rebalance(self) -> None:
        if not self._pep_ratio.is_ready:
            return

        ratio = self._pep_ratio.current.value
        self.plot("Strategy", "Ratio", ratio)
        self.plot("Strategy", "Target", self._target)

        if not self.portfolio.invested and abs(ratio - self._target) < self._tolerance:
            self._target = ratio
            self.set_holdings(self._ko.symbol, 0.5, True)

        if self.portfolio.invested:
            ko_weight = self._ko.holdings.weight
            pep_weight = self._pep.holdings.weight

            if ratio > self._target + self._tolerance and ko_weight < -self._trailing_stop_factor / 2:
                self.liquidate()
            elif ratio < self._target - self._tolerance and pep_weight < -self._trailing_stop_factor / 2:
                self.liquidate()
