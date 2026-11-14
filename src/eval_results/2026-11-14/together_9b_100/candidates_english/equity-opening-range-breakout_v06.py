# region imports
from AlgorithmImports import *
# endregion

class WarmUpRangeExpansionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True
        self._spy = self.add_equity("SPY", Resolution.MINUTE)
        self._spy.range = None
        self._spy.low = None
        self._spy.high = None
        self.schedule.on(self.date_rules.every_day("SPY"), self.time_rules.after_market_open("SPY", 39), self._rebalance)

    def on_data(self, data: Slice) -> None:
        bar = data.bars.get(self._spy)
        if not bar:
            return
        close = bar.close
        if not self._spy.range:
            self._spy.range = (close, close)
            self._spy.low = bar.low
            self._spy.high = bar.high
        else:
            self._spy.range = (min(self._spy.range[0], close), max(self._spy.range[1], close))
            self._spy.low = min(self._spy.low, bar.low)
            self._spy.high = max(self._spy.high, bar.high)

    def _rebalance(self) -> None:
        if not self._spy.range:
            return
        range_high = self._spy.range[1]
        range_low = self._spy.range[0]
        current = self._spy.price
        if not self.portfolio.invested and (current > range_high or current < range_low):
            self.set_holdings(self._spy, 1 if current > range_high else -1)
        if self.time.minute == 55:
            self.liquidate()
