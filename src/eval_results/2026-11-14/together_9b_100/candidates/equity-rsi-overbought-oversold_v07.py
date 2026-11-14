# region imports
from AlgorithmImports import *
# endregion

class EquityRSIMeanReversionAlgorithm(QCAlgorithm):
    _rsi_thresholds = (30, 70)

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self._qqq = self.add_equity("QQQ")
        self._qqq.rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
        # Alternatively, use a manual indicator.
        # self._qqq.rsi = RelativeStrengthIndex(14)
        # self.warm_up_indicator(self._qqq, self._qqq.rsi, Resolution.HOUR)
        # self.register_indicator(self._qqq, self._qqq.rsi, Resolution.HOUR)
        self.schedule.on(
            self.date_rules.every_day(self._qqq),
            self.time_rules.after_market_open(self._qqq, 1),
            self._rebalance
        )

    def _rebalance(self) -> None:
        if not self._qqq.rsi.is_ready:
            return
        rsi = self._qqq.rsi.current.value
        quantity = self._qqq.holdings.quantity
        if quantity == 0 and rsi < self._rsi_thresholds[0]:
            self.set_holdings(self._qqq, 1)
        elif quantity > 0 and rsi > self._rsi_thresholds[1]:
            self.liquidate()
