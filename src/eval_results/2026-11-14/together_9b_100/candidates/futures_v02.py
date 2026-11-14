# region imports
from AlgorithmImports import *
# endregion

class FutureAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # Request SP Futures data to trade.
        self._sp = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            self._rebalance
        )
        # Set the initial leverage.
        self.set_leverage(2)

    def on_data(self, slice: Slice) -> None:
        if not self._sp.is_ready:
            return
        # Get the mapping of the current time to the mapped contract.
        # Then, we can use the mapped contract to index the open interests for the mapping result.
        # Finally, we can use the open interest of the mapped contract to get the most liquid contract.
        mapping = slice.future_mapping(self._sp)
        # Get the open interest of each contract in the mapping result.
        open_interest = [x.open_interest for x in mapping]
        # Select the contract with the highest open interest and trade it.
        index = open_interest.index(max(open_interest))
        contract = mapping[index]
        # We will simply go long the mapped contract.
        if not self.portfolio[contract].is_long:
            self.set_holdings(contract, 1)
        # We will simply go short the mapped contract.
        elif not self.portfolio[contract].is_short:
            self.set_holdings(contract, -1)
