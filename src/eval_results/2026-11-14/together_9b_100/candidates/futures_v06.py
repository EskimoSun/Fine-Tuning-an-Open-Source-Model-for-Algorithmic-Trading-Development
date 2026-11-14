# region imports
from AlgorithmImports import *
# endregion

class FutureRollExampleAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # Map the US Index to its continuous Futures contract.
        self._index = self.add_index("SPX")
        self._future = self.add_future(self._index, self._roll)
        # Schedule daily rebalancing at 5 PM to lock today's open interest.
        self.schedule.on(self.date_rules.every_day(self._index), self.time_rules.at(18, 0), self._rebalance)

    def _roll(self, mapping: List[FuturesMapping]) -> Optional[Future]:
        # Select the best-matched contract with open interest in the last 3 days.
        return next((c for c in mapping if c.symbol.value.endswith(str(self.time.date - timedelta(1, 0, 0)))) or mapping[0])

    def _rebalance(self) -> None:
        if not self.portfolio.invested:
            return
        # Create a new continuous Futures contract based on the updated open interest.
        index = self._index
        # Get the updated mapping with the latest open interest.
        mapping = self.future_market.index_mapping[index]
        # Select the best-matched contract with open interest in the last 3 days.
        contract = next((c for c in mapping if c.symbol.value.endswith(str(self.time.date - timedelta(1, 0, 0)))) or mapping[0])
        # Create a new continuous Futures contract based on the updated open interest.
        new_future = self.add_future(index, contract)
        # Cancel the old subscription to avoid duplicate subscriptions.
        self.remove_future(self._future)
        # Update the reference to the future for the next rebalance.
        self._future = new_future
