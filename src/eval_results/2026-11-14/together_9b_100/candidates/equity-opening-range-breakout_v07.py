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
        self._range = self._spy.opening_range(30, Resolution.MINUTE)
        # Alternatively, use a manual indicator.
        # self._range = OpeningRangeBar()
        # self.warm_up_indicator(self._spy, self._range)
        # self.register_indicator(self._spy, self._range)
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.after_market_open(self._spy, 30), self._rebalance)

    def _rebalance(self) -> None:
        if not self._range.is_ready:
            return
        low = self._range.low
        high = self._range.high
        price = self._spy.price
        if not self._spy.invested and price > high:
            self.set_holdings(self._spy, 1)
        elif not self._spy.invested and price < low:
            self.set_holdings(self._spy, -1)
        elif self._spy.invested and price < low:
            self.liquidate(self._spy)
        elif self._spy.invested and price > high:
            self.liquidate(self._spy)
