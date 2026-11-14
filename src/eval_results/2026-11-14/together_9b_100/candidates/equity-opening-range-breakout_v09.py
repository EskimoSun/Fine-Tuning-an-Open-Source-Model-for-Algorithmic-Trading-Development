# region imports
from AlgorithmImports import *
# endregion

class EquityOpeningRangeBreakoutAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # Seed the price with the last known price to avoid trading errors.
        self.settings.seed_initial_prices = True
        # Trade daily on SPY.
        self._spy = self.add_equity("SPY")
        # Create an ORB strategy for automatic trading.
        self._orb = self.orb(self._spy, 30, 30, Resolution.MINUTE)
        # Warm up for immediate usage of indicators and strategies.
        self.set_warm_up(self._orb.warm_up_period + 1, Resolution.DAILY)

    def on_data(self, slice: Slice) -> None:
        pass
