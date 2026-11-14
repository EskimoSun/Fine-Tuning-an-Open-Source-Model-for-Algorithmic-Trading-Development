# region imports
from AlgorithmImports import *
# endregion

class EquityBreakoutAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY")
        self._spy.roc = self.roc(self._spy, 30, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._spy.roc = RateOfChange(30)
        # self.warm_up_indicator(self._spy, self._spy.roc, Resolution.DAILY)
        # self.register_indicator(self._spy, self._spy.roc, Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.after_market_open(self._spy, 30), self._rebalance)

    def _rebalance(self) -> None:
        if not self._spy.roc.is_ready:
            return
        in_uptrend = self._spy.price > self._spy.previous_price(30)
        if in_uptrend and not self._spy.holdings.is_long:
            self.set_holdings(self._spy, 1)
        elif not in_uptrend and not self._spy.holdings.is_short:
            self.set_holdings(self._spy, -1)
        self.liquidate(self._spy, True)
