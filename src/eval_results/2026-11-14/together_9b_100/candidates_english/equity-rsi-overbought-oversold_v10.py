# region imports
from AlgorithmImports import *
# endregion

class EquityRSIMeanReversionAlgorithm(QCAlgorithm):
    _target_percent = 0.75

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._qqq = self.add_equity("QQQ", Resolution.HOUR)
        self._rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
        # Alternatively, use a manual indicator.
        # self._rsi = RelativeStrengthIndex(14)
        # self.warm_up_indicator(self._qqq, self._rsi, Resolution.HOUR)
        # self.register_indicator(self._qqq, self._rsi, Resolution.HOUR)
        self.plot_indicator("RSI", self._rsi)

    def on_data(self, data: Slice) -> None:
        if not self._rsi.is_ready:
            return
        rsi = self._rsi.current.value
        holdings = self._qqq.holdings.quantity
        if holdings <= 0 and rsi < 30:
            self.set_holdings(self._qqq, self._target_percent)
        if holdings >= 0 and rsi > 50:
            self.liquidate(self._qqq)
        if holdings < 0 and rsi > 70:
            self.set_holdings(self._qqq, -self._target_percent)
        if holdings > 0 and rsi < 50:
            self.liquidate(self._qqq)
