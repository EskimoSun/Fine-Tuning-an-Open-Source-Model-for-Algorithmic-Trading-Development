# region imports
from AlgorithmImports import *
# endregion

class EquityCustomAttrTrailingStopAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY")
        self._equity.set_holdings_target(1.0)
        self._stop_loss = self.atr(self._equity, 14, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._stop_loss = AverageTrueRange(14)
        # self.warm_up_indicator(self._equity, self._stop_loss, Resolution.DAILY)
        # self.register_indicator(self._equity, self._stop_loss, Resolution.DAILY)
        self.plot_indicator("Stop Loss", self._stop_loss)

    def on_data(self, data: Slice) -> None:
        if not self._equity.invested:
            return
        bar = data.bars.get(self._equity)
        if not bar:
            return
        # Using the max() function instead of a conditional statement for better readability
        self._equity.set_holdings_target(
            1.0 if bar.close > self._stop_loss.current.value * (1 + 0.01) else -1.0
        )
