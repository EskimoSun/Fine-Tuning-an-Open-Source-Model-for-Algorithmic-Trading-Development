# region imports
from AlgorithmImports import *
# endregion

class OneMinuteRangeBreakAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol
        self._range = IndicatorExtensions.create_range(self, self._spy, 2*24*60)
        # Alternatively, use a manual indicator.
        # self._range = Range(-2*24*60, 2*24*60)
        # self.warm_up_indicator(self._spy, self._range)
        # self.register_indicator(self._spy, self._range)
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.after_market_open(self._spy, 1), self._rebalance)

    def _rebalance(self) -> None:
        if not self._range.is_ready:
            return
        close = self.securities[self._spy].close
        if close > self._range.high:
            self.set_holdings(self._spy, 1)
        elif close < self._range.low:
            self.set_holdings(self._spy, -1)
        self._range.current.value = close
        self._range.previous.value = close
