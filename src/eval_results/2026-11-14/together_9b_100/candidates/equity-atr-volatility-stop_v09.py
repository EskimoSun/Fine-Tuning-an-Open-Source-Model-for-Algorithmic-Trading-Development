# region imports
from AlgorithmImports import *
# endregion

class EquityChandelierExitAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY", Resolution.MINUTE)
        self._equity.atr = self.atr(self._equity, 14, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._equity.atr = AverageTrueRange(14)
        # self.warm_up_indicator(self._equity, self._equity.atr, Resolution.DAILY)
        # self.register_indicator(self._equity, self._equity.atr, Resolution.DAILY)
        self._equity.chandelier = self.chandelier_exit(self._equity, 22, self._equity.atr, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._equity.chandelier = ChandelierExit(22, AverageTrueRange(14))
        # self.warm_up_indicator(self._equity, self._equity.chandelier, Resolution.DAILY)
        # self.register_indicator(self._equity, self._equity.chandelier, Resolution.DAILY)
        self._equity.previous_close = self._equity.close
        self._equity.in_uptrend = False
        self.plot_indicator("Chandelier Exit", self._equity.chandelier)

    def on_data(self, data: Slice) -> None:
        if not self._equity.atr.is_ready:
            return
        # Update the Chandelier Exit indicator with the updated ATR value.
        self._equity.chandelier.update(data.time, self._equity.atr.current.value)

    def on_warmup_finished(self) -> None:
        self._check_exit()

    def _check_exit(self) -> None:
        if not self._equity.chandelier.is_ready:
            return
        # Stop loss based on the Chandelier Exit strategy.
        # If the price closes below the stop loss, we will exit the position.
        stop_loss = self._equity.chandelier.current.value
        self._equity.previous_close = self._equity.close
        if not self._equity.in_uptrend and self._equity.close < stop_loss:
            self.liquidate(self._equity)
        elif self._equity.in_uptrend and self._equity.previous_close < stop_loss:
            self._equity.in_uptrend = False
