# region imports
from AlgorithmImports import *
# endregion

class FutureRollingAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # automatic_mapping only supports automatic_indicator_updates, not automatic_strategy_management.
        self.settings.automatic_mapping = True
        self.settings.automatic_indicator_updates = True
        # Request SP500E-mini futures for continuous trading.
        self._future = self.add_future(Indices.SP_500_E_MINI, self._trade)
        # Get the current mapping to trade the closest expiry contract.
        self.set_holdings(self._future.mapped)

    def on_data(self, slice: Slice) -> None:
        if not self._future.mapped.is_ready:
            return
        # Trade the mapped contract directly.
        self._trade(self._future.mapped)

    def on_symbol_changed(self, changes: SymbolChangedEventList) -> None:
        # Handles the mapping changes automatically.
        for symbol in changes.added_symbols:
            if not symbol.is_future:
                continue
            contract = self.securities[symbol]
            # Create subscription for the new mapping to start trading immediately.
            self._future = self.add_future(symbol, self._trade, contract)

    def _trade(self, mapped: Future) -> None:
        if not self.portfolio.invested:
            self.market_order(mapped, 1)
            return
        # Exit the current position and lock the profit by rolling over to the next contract.
        self.liquidate(mapped, tag=True)
