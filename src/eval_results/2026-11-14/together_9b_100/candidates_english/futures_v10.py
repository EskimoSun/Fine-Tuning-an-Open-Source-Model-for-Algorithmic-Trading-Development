# region imports
from AlgorithmImports import *
# endregion

class FutureRollingAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        # Trade SP500E-mini Futures daily.
        self._future = self.add_future(Indices.SP_500_E_MINI, self._select_assets)
        # Roll the SP500E-mini Futures daily to trade the front month continuously.
        self.schedule.on(self.date_rules.every_day("SP500E-mini"), self.time_rules.at(9, 0, 0), self._rebalance)

    def _select_assets(self, data: List[Future]) -> List[Symbol]:
        # Select the front month contract of SP500E-mini Futures.
        front_month = min(data, key=lambda x: x.end_time).symbol
        # Create a MappingSymbol for the selected future contract.
        return [MappingSymbol.create_future_mapping_symbol(Indices.SP_500_E_MINI, front_month)]

    def _rebalance(self) -> None:
        if not self._future.mapped.symbol in self.securities:
            return
        # Ensure we are trading the front month contract.
        front_month = self.securities[self._future.mapped.symbol].underlying
        if not front_month.is_trading_day:
            return
        # Check if we need to roll the future.
        if self.portfolio[front_month].liquidate_time < self.time:
            # Liquidate the old future and trade the new front month.
            self.liquidate(front_month, tag=f"Roll {front_month.symbol}")
