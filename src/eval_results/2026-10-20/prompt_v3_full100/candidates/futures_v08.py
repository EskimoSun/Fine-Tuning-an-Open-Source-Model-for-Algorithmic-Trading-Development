from AlgorithmImports import *


class ContinuousFuturesReference(QCAlgorithm):
    """Continuous E-mini S&P 500 futures reference strategy."""

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Continuous futures series with last-trading-day mapping and backwards-ratio normalization
        self._future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            resolution=Resolution.MINUTE,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0,
        )
        self._future.set_filter(0, 92)

        # Track the currently mapped (traded) contract
        self._mapped_symbol = self._future.mapped

        # Initial entry: buy one contract of the mapped contract
        self.market_order(self._mapped_symbol, 1)

    def on_data(self, slice: Slice):
        # No intraday logic needed; entry and rollover are handled at init and on symbol change.
        pass

    def on_symbol_changed_events(self, symbol_changed_events: Dict[Symbol, SymbolChangedEvent]):
        for symbol, changed_event in symbol_changed_events.items():
            old_symbol = changed_event.old_symbol
            new_symbol = changed_event.new_symbol

            # Only handle rollovers for our futures series
            if symbol != self._future.mapped and symbol != old_symbol:
                continue

            # Liquidate the old contract
            self.liquidate(old_symbol)

            # Re-establish the same quantity in the new contract
            quantity = 1
            self.market_order(new_symbol, quantity)

            # Update tracked mapped symbol
            self._mapped_symbol = new_symbol
