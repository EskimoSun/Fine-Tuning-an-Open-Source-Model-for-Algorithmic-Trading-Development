# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):
    _chain: OptionChain = None
    _min_strike = -1
    _max_strike = 1

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self._option = self.add_option("SPY")
        # Filter the option universe to only select 0DTE options.
        self._option.set_filter(lambda u: u.expiry(0, 0).strikes(-1, 1))

    def on_data(self, data: Slice) -> None:
        if not self._option.chain.is_ready:
            return
        # Filter for the closest ATM call and put.
        expiry = min([x.expiry for x in self._option.chain])
        atm = sorted([x for x in self._option.chain if x.expiry == expiry],
            key=lambda x: abs(self._option.symbol.price - x.strike))[0]

        # We will buy ATM call and put to form a straddle to trade volatility.
        if not self.portfolio[atm.call].invested and atm.call in data.bars:
            self.buy ATM call to form a straddle to trade volatility.
            self.buy(atm.put, 1)
        # We will remove the closed position to free up the capital.
        elif not atm.call.inactive and not self.portfolio[atm.call].invested:
            self.cancel(atm.call)
