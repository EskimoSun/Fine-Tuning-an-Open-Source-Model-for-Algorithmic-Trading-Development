# region imports
from AlgorithmImports import *
# endregion

class FutureRollingAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # Request SP500 Futures subscription.
        self._future = self.add_future("SP500", self._rebalance)
        # Set the data normalization mode as raw for accurate price comparisons.
        self._future.data_normalization_mode = DataNormalizationMode.RAW
        # Set the account currency to match the future contract currency.
        self.set_account_currency("USD", 100000)

    def _rebalance(self, futures: List[Future]) -> None:
        # Get the expiry of the front month contract.
        expiry = min([x.expiry for x in futures])
        # Check if we are close to the expiry of the front month contract.
        if self.time > expiry - timedelta(3):
            # Remove the expired contract.
            self.remove_future(self._future, expiry)
            # Add the next trading contract to track and trade.
            next_contract = sorted(futures, key=lambda f: f.expiry)[0]
            self.add_future(self._future, next_contract.symbol)
            # Place a market order to trade the selected contract.
            self.market_order(next_contract, 1)
