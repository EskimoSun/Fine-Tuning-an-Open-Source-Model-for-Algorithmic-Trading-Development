# region imports
from AlgorithmImports import *
# endregion

class EquityOpeningRangeBreakoutAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY")
        self._spy.range = self.indicator(self._spy, RangeBar(30, Resolution.MINUTE))
        # Alternatively, use a manual indicator.
        # self._spy.range = RangeBar(30, Resolution.MINUTE)
        # self.warm_up_indicator(self._spy, self._spy.range, Resolution.DAILY)
        # self.register_indicator(self._spy, self._spy.range, Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.after_market_open(self._spy, 30), self._rebalance)

    def _rebalance(self) -> None:
        if not self._spy.range.is_ready:
            return
        bar = self._spy.range.current
        price = self.securities[self._spy].price
        if not self._spy.holdings.is_long and price > bar.high:
            self.set_holdings(self._spy, 1)
        elif self._spy.holdings.is_long and price < bar.low:
            self.set_holdings(self._spy, -1)
