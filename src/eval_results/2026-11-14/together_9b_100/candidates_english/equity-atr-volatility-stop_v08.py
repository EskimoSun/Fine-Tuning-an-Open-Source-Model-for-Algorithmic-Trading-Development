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
        self._equity.chandelier_exit = self.chandelier_exit(self._equity, 20, 3, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._equity.chandelier_exit = ChandelierExit(20, 3, MovingAverageType.SIMPLE)
        # self.warm_up_indicator(self._equity, self._equity.chandelier_exit, Resolution.DAILY)
        # self.register_indicator(self._equity, self._equity.chandelier_exit, Resolution.DAILY)
        self.plot_indicator("Chandelier Exit", self._equity.chandelier_exit)

    def on_data(self, data: Slice) -> None:
        if not self._equity.chandelier_exit.is_ready:
            return
        # Stop price = Entry price - 3*ATR
        # We will buy if the stop price is above the current price
        # We will sell if the stop price is below the current price
        stop_price = self._equity.chandelier_exit.current.value
        if not self._equity.holdings.invested and stop_price > self._equity.price:
            self.set_holdings(self._equity, 1)
        elif self._equity.holdings.invested and stop_price < self._equity.price:
            self.liquidate()
