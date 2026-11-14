# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # Filter the option universe to only select 0DTE options.
        self._option = self.add_option("SPY")
        self._option.set_filter(lambda u: u.expiry(0, 7).strikes(-10, 10))

    def on_data(self, data: Slice) -> None:
        if self.portfolio.invested:
            return
        # Create an Iron Condor using the Option Strategies helper method.
        expiry, strike_call, strike_put = list(data.option.chains['SPY'].expiry)[0], list(data.option.chains['SPY'].strikes)[-10:-5]
        if not expiry or not strike_call or not strike_put:
            return
        iron_condor = self._option.strategies.iron_condor(expiry, strike_call[0], strike_put[0])
        # Request margin to trade the Iron Condor.
        self.buy(iron_condor, 1)
        # Liquidate the Iron Condor on Friday at 3:45 PM to avoid weekend gap risk.
        self.schedule.on(self.date_rules.every(DayOfWeek.FRIDAY), self.time_rules.at(15, 45), self.liquidate)
