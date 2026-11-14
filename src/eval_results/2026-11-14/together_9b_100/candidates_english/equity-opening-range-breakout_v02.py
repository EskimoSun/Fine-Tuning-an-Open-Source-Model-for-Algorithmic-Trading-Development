# region imports
from AlgorithmImports import *
# endregion

class OneMinuteRangeBreakAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol
        self._range = IndicatorExtensions.create_range(self, self._spy, 30, Resolution.MINUTE)
        self._previous_close = None
        self._long = False
        # Warm up the indicator and its windows with historical data.
        self.indicator_history(self._range, self._spy, 30, Resolution.MINUTE)

    def on_data(self, data: Slice) -> None:
        if not self._range.is_ready:
            return
        # Get the current bar's high and low.
        bar = data.bars.get(self._spy)
        if not bar:
            return
        high = bar.high
        low = bar.low
        # Update the range indicator with the current bar's high and low.
        self._range.update(high, low)
        # We will buy if the close is above the range high and sell if it's below the range low.
        # We'll wait for the close to avoid trading on stale data.
        previous_close = self._previous_close or bar.close
        if not self._long and bar.close > self._range.window[0].current.value:
            self.set_holdings(self._spy, 1)
            self._previous_close = previous_close
            self._long = True
        elif self._long and bar.close < self._range.window[-1].current.value:
            self.set_holdings(self._spy, -1)
            self._previous_close = previous_close
            self._long = False

    def on_order_event(self, order_event: OrderEvent) -> None:
        if order_event.status == OrderStatus.FILLED:
            self._previous_close = None
