# region imports
from AlgorithmImports import *
# endregion

class EquityStopLossTrailingTemplateAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY")
        self._equity.atr = self.atr(self._equity, 14, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._equity.atr = AverageTrueRange(14)
        # self.warm_up_indicator(self._equity, self._equity.atr, Resolution.DAILY)
        # self.register_indicator(self._equity, self._equity.atr, Resolution.DAILY)
        self._equity.stop_loss_trailing_template = StopLossTrailingTemplate(-3.0)
        self.plot_indicator("ATR", self._equity.atr)

    def on_data(self, data: Slice) -> None:
        if not self._equity.atr.is_ready:
            return
        # Trail the stop-loss using a template.
        # It plots the trailing stop on the price chart and emits OrderEvent
        # when the price closes below the stop, so we can trade several
        # assets with the same logic.
        self._equity.stop_loss_trailing_template.update(
            self._equity,
            self._equity.atr.current.value,
            self._equity.price
        )

        if not self._equity.invested and self._equity.stop_loss_trailing_template.triggered:
            self.set_holdings(self._equity, 1)
        elif self._equity.invested and not self._equity.stop_loss_trailing_template.triggered:
            self.liquidate()
