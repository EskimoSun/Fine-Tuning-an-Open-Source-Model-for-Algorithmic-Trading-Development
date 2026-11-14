# region imports
from AlgorithmImports import *
# endregion

class EquityOptionChandelierExitAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._option = self.add_option("SPY")
        self._option.set_filter(0, 1)
        self._option.chandelier_exit = self.chandelier_exit(self._option, 22, 3*self._option.atr(14).current.value)
        # Alternatively, use a manual indicator.
        # self._option.chandelier_exit = ChandelierExit(22, 3*self._option.atr(14).current.value)
        # self.warm_up_indicator(self._option, self._option.chandelier_exit, Resolution.DAILY)
        # self.register_indicator(self._option, self._option.chandelier_exit, Resolution.DAILY)
        self.plot_indicator("Chandelier Exit", self._option.chandelier_exit)

    def on_data(self, data: Slice) -> None:
        if not self._option.chandelier_exit.is_ready:
            return
        # Stop loss based on Chandelier Exit: close if price falls below the dynamic stop level.
        # We will buy if the price is above the stop level
        # and sell if the price is below the stop level
        if not self._option.holdings.invested and data.end_time >= self.time + timedelta(1) and self._option.price > self._option.chandelier_exit.current.value:
            self.buy(self._option, 1)
        elif self._option.holdings.invested and data.end_time >= self.time + timedelta(1) and self._option.price < self._option.chandelier_exit.current.value:
            self.liquidate(self._option)
