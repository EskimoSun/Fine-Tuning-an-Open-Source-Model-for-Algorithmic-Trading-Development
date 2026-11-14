# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self._option = self.add_option("SPY")
        # Using Staddle() method, it will only return the best-matched ATM call and put contracts expiring after 30 days.
        # It provides better accuracy in filtering, and subscribe only to the needed contracts to save computation resources.
        self._option.set_filter(lambda u: u.staddle(30, 0))

    def on_data(self, data: Slice) -> None:
        if self.portfolio.invested:
            return
        # Only wants the option chain of the selected symbol.
        chain = list(data.option_chains.get(self._option))
        if chain:
            # There should only be 1 expiry and 1 strike from the 2 contracts returned, getting from either contract is fine.
            expiry, strike = chain[0].expiry, chain[0].strike

            # Forms an Iron Condor option strategy using abstraction method ensure accuracy.
            long_put = OptionStrategy.LongPut(self._option, strike - 2, expiry)
            short_put = OptionStrategy.ShortPut(self._option, strike - 1, expiry)
            short_call = OptionStrategy.ShortCall(self._option, strike + 1, expiry)
            long_call = OptionStrategy.LongCall(self._option, strike + 2, expiry)
            iron_condor = OptionStrategies.iron_condor(long_put, short_put, short_call, long_call)

            # Places orders to buy the ATM call and put contracts to form an Iron Condor option strategy.
            self.buy(iron_condor, 1)
