# region imports
from AlgorithmImports import *
# endregion

class FutureAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # Subscribe to the CFE:SPX continuous contract.
        self._index = self.add_index("SPX")
        self._future = self.add_future(self._index, Symbol.create("CFE", "SPX", Market.CFE))
        # Set the rolling schedule to roll the future when the front month expires.
        self.schedule.on(self.date_rules.every_day(self._index), self.time_rules.after_market_open(self._index, 1), self._roll)

    def on_data(self, slice: Slice) -> None:
        # Update the future with the updated margin interest rate.
        self._future.update(slice)

    def _roll(self) -> None:
        # Get the open interest of the two closest contracts.
        open_interest = self.open_interest(self._future)
        next_contract = self.add_future(self._index, open_interest.next(self._index, Market.CFE))
        # Remove the expired contract and update the index mapping.
        self.remove_future(self._future)
        self._future = next_contract
