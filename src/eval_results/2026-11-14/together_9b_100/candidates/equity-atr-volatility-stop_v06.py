# region imports
from AlgorithmImports import *
# endregion

class EquityTrailingStopTemplateAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY", Resolution.MINUTE)
        self._equity.trailing_stop = self.trailing_stop(self._equity, 3, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._equity.trailing_stop = TrailStop(3, 0, 0)
        # self.warm_up_indicator(self._equity, self._equity.trailing_stop, Resolution.DAILY)
        # self.register_indicator(self._equity, self._equity.trailing_stop, Resolution.DAILY)
        self.plot_indicator("TrailingStop", self._equity.trailing_stop)

    def on_data(self, data: Slice) -> None:
        if not self._equity.trailing_stop.is_ready:
            return
        # Stop price = previous highest price - 3*dailyATR
        # If price falls below stop price, exit.
        if self._equity.holdings.quantity > 0 and data.end_time >= self._equity.trailing_stop.update_time:
            stop_price = self._equity.trailing_stop.stop_price
            if not self.portfolio.invested and data.symbol.price < stop_price:
                self.liquidate(self._equity)
