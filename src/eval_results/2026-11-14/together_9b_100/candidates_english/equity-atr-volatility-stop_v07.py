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
        self._equity = self.add_equity("SPY")
        self._atr = self.atr(self._equity, 22, resolution=Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._atr = AverageTrueRange(22)
        # self.warm_up_indicator(self._equity, self._atr, Resolution.DAILY)
        # self.register_indicator(self._equity, self._atr, Resolution.DAILY)
        self._stop_price = 0
        self._previous_close = 0
        self._in_uptrend = False
        self._entry_price = 0
        self.plot_indicator("ATR", self._atr)

    def on_data(self, data: Slice) -> None:
        if not self._atr.is_ready:
            return
        bar = data.bars.get(self._equity)
        if not bar:
            return
        # Stop price = current price - 3 * ATR
        stop_price = bar.close - 3 * self._atr.current.value
        if stop_price > self._stop_price:
            self._stop_price = stop_price
        # Trend-following entry: buy if price closes above stop
        if bar.close > self._stop_price and not self._equity.invested:
            self.set_holdings(self._equity, 1)
            self._in_uptrend = True
        # Exit on break of trailing stop
        elif bar.close < self._stop_price and self._equity.invested:
            self.liquidate(self._equity)
            self._in_uptrend = False

    def on_warmup_finished(self) -> None:
        bar = self.history[Bars](self._equity, 1, Resolution.DAILY).bars[-1]
        self._previous_close = bar.close
        self._stop_price = bar.close - 3 * self._atr.current.value
