# region imports
from AlgorithmImports import *
# endregion

class EquityRSIMeanReversionAlgorithm(QCAlgorithm):
    _long_threshold = 30
    _short_threshold = 70

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._qqq = self.add_equity("QQQ")
        self._rsi = self.rsi(self._qqq, 14, Resolution.DAILY)
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

        # Exit on cross of 30 or 70
        if quantity <= 0 and rsi_value > self._short_threshold:
            self.liquidate(self._qqq)
        elif quantity >= 0 and rsi_value < self._long_threshold:
            self.liquidate(self._qqq)
        return

        # Entry only when flat (one position at a time)
        # Buy when RSI crosses below 30; sell when it crosses above 70
        # See https://www.investopedia.com/ask/answers/04/rsimember.asp
        if quantity == 0:
            if rsi_value < self._long_threshold and self._rsi.previous.value > self._long_threshold:
                self.set_holdings(self._qqq, -1)
            elif rsi_value > self._short_threshold and self._rsi.previous.value < self._short_threshold:
                self.set_holdings(self._qqq, 1)
