# region imports
from AlgorithmImports import *
# endregion

class AtrTrailingStopAlgorithm(QCAlgorithm):
    _risk: float = 0.03

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._spy = self.add_equity("SPY", Resolution.MINUTE)
        self._spy.atr = self.atr(self._spy, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._spy.atr = AverageTrueRange(14, MovingAverageType.SIMPLE)
        # self.warm_up_indicator(self._spy, self._spy.atr, Resolution.DAILY)
        # self.register_indicator(self._spy, self._spy.atr, Resolution.DAILY)
        self._spy.high = self.maximum(self._spy, 2000, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._spy.high = Maximum(2000)
        # self.warm_up_indicator(self._spy, self._spy.high, Resolution.DAILY)
        # self.register_indicator(self._spy, self._spy.high, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every_day(self._spy),
            self.time_rules.at(9, 0),
            self._rebalance
        )

    def _rebalance(self) -> None:
        if not self._spy.atr.is_ready or not self._spy.high.is_ready:
            return

        price = self.securities[self._spy].price
        if not self.portfolio.invested:
            self.set_holdings(self._spy, 1.0)
            return

        # Stop when price falls 3x ATR below the 2000-day high.
        atr_stop_price = self._spy.high.current.value - 3.0 * self._spy.atr.current.value
        if price < atr_stop_price:
            self.liquidate(self._spy)
            return

        # Trail the 2000-day high by 3x ATR.
        trailing_stop = max(self._spy.high.current.value * (1.0 - self._risk),
            self._spy.high.current.value - 3.0 * self._spy.atr.current.value)
        self.update_stop_loss(self._spy, trailing_stop)
