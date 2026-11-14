# region imports
from AlgorithmImports import *
# endregion

class EquityRSIMeanReversionAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._qqq = self.add_equity("QQQ")
        self._rsi = self.rsi(self._qqq, 14, Resolution.HOUR)
        # Alternatively, use a manual indicator.
        # self._rsi = RelativeStrengthIndex(14)
        # self.warm_up_indicator(self._qqq, self._rsi, Resolution.DAILY)
        # self.register_indicator(self._qqq, self._rsi, Resolution.DAILY)
        self.plot_indicator("RSI", self._rsi)

    def on_data(self, data: Slice) -> None:
        if not self._rsi.is_ready:
            return

        rsi_value = self._rsi.current.value
        quantity = self._qqq.holdings.quantity

        if quantity == 0 and rsi_value < 30:
            self.set_holdings(self._qqq, 1)
        elif quantity > 0 and rsi_value > 70:
            self.liquidate()
