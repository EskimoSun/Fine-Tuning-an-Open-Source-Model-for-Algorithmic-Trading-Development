# region imports
from AlgorithmImports import *
# endregion

class EquityRSIMeanReversionAlgorithm(QCAlgorithm):
    _rsi_threshold_buy = 30
    _rsi_threshold_sell = 70
    _in_uptrend = False

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self._qqq = self.add_equity("QQQ")
        self._qqq.rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
        # Alternatively, use a manual indicator.
        # self._qqq.rsi = RelativeStrengthIndex(14)
        # self.warm_up_indicator(self._qqq, self._qqq.rsi, Resolution.DAILY)
        # self.register_indicator(self._qqq, self._qqq.rsi, Resolution.DAILY)
        self.plot_indicator("RSI", self._qqq.rsi)
        self.schedule.on(
            self.date_rules.every_day(self._qqq),
            self.time_rules.after_market_open(self._qqq, 1),
            self._rebalance
        )

    def _rebalance(self) -> None:
        if not self._qqq.rsi.is_ready:
            return
        rsi = self._qqq.rsi.current.value
        in_uptrend = rsi > self._rsi_threshold_sell
        if in_uptrend and not self._in_uptrend:
            self.set_holdings(self._qqq, -1)
            self._in_uptrend = in_uptrend
        elif not in_uptrend and self._in_uptrend:
            self.liquidate()
            self._in_uptrend = in_uptrend
