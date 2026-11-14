# region imports
from AlgorithmImports import *
# endregion

class AtrendTrailingTemplateAlgorithm(QCAlgorithm):
    _atr_multiplier = 3.0

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
        self._spy.previous_close = 0.0
        self._spy.trailing_high = 0.0

        self.plot_indicator("ATR", self._spy.atr)

    def on_data(self, data: Slice) -> None:
        if not self._spy.atr.is_ready:
            return
        bar = data.bars.get(self._spy)
        if not bar:
            return

        close = bar.close
        self._spy.previous_close = self._spy.previous_close or close
        if close > self._spy.trailing_high:
            self._spy.trailing_high = close

        stop_price = self._spy.trailing_high - self._atr_multiplier * self._spy.atr.current.value
        if stop_price < self._spy.previous_close:
            self.liquidate(self._spy.symbol)
            self._spy.trailing_high = 0.0
            self._spy.previous_close = 0.0
        elif not self.portfolio.invested:
            self.set_holdings(self._spy.symbol, 1.0)
            self._spy.trailing_high = self._spy.trailing_high or close
