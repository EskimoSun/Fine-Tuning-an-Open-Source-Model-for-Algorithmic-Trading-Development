from AlgorithmImports import *


class EsContinuousRolloverAlgorithm(QCAlgorithm):
    """
    Trades the ES (SP_500_E_MINI) continuous future using LAST_TRADING_DAY mapping,
    BACKWARDS_RATIO normalization, and contract depth offset 0.

    Strategy:
      - On the first data point, enter a market order for 1 contract of the mapped symbol.
      - On symbol change (rollover), liquidate the old contract and re-enter the same
        quantity on the new contract.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add the ES continuous future with the specified settings
        self._future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            resolution=Resolution.MINUTE,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0
        )
        self._future.set_filter(0, 92)

        self._entered = False

    def on_data(self, data: Slice):
        if self._entered:
            return

        # Check if we have data for the mapped symbol
        mapped_symbol = self._future.mapped
        if mapped_symbol not in data:
            return

        # Enter 1 contract on the first available data point
        self.market_order(mapped_symbol, 1)
        self._entered = True
        self.log(f"Entered 1 contract of {mapped_symbol}")

    def on_symbol_changed_events(self, symbol_changed_events: dict):
        for symbol, changed_event in symbol_changed_events.items():
            old_symbol = changed_event.old_symbol
            new_symbol = changed_event.new_symbol

            # Only handle rollovers for our future
            if old_symbol != self._future.mapped:
                continue

            # Get the quantity we were holding in the old contract
            old_quantity = self.portfolio[old_symbol].quantity

            if old_quantity == 0:
                continue

            # Liquidate the old contract
            self.liquidate(old_symbol)
            self.log(f"Liquidated {old_quantity} contracts of {old_symbol}")

            # Re-enter the same quantity on the new contract
            self.market_order(new_symbol, old_quantity)
            self.log(f"Entered {old_quantity} contracts of {new_symbol}")
