# region imports
from AlgorithmImports import *
# endregion

class FutureOnETFMappingAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        # Trade daily on the ETF itself, mapped through to the underlying future contract.
        self._index = self.add_index("SPX")
        # Create a Futures contract for the mapped target.
        self._contract = self.add_future(self._index, self._get_mapping_target)
        # Schedule daily rebalancing at 9:00 AM before market open.
        self.schedule.on(self.date_rules.every_day(self._index), self.time_rules.at(9, 0), self._rebalance)

    def _get_mapping_target(self, index: BaseIndex) -> Future:
        # Use the mapping table to get the mapped future contract.
        mapped = self.mapping_table.get_mapping_target(index)
        if mapped:
            return mapped
        # Fallback to the default mapping target if the mapping table doesn't have it.
        return self.add_future(index)

    def _rebalance(self) -> None:
        if not self._contract.mapped:
            return
        # Scale the position size to 1/10th of the portfolio value.
        weight = 1 / 10
        quantity = self.calculate_order_quantity(self._contract, weight)
        if not self.portfolio.invested:
            quantity = self.calculate_order_quantity(self._contract, 1)
        # Place a market order to rebalance.
        self.market_order(self._contract, quantity)
