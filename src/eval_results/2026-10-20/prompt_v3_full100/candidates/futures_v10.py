from AlgorithmImports import *

class Sp500EminiRolloverAlgorithm(QCAlgorithm):
    """
    Buys one ES front-month contract and rolls it on contract change.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)

        self.universe_settings.asynchronous = True

        self._future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0
        )
        self._future.set_filter(0, 92)

    def on_data(self, data: Slice):
        # Only enter if we are not currently invested
        if self.portfolio.invested:
            return

        # Buy one contract of the mapped front-month
        self.market_order(self._future.mapped, 1)

    def on_symbol_changed_events(self, symbol_changed_events: dict):
        for symbol, changed_event in symbol_changed_events.items():
            old_symbol = self.symbol(changed_event.old_symbol)
            new_symbol = self.symbol(changed_event.new_symbol)

            quantity = self.portfolio[old_symbol].quantity
            tag = f"Rollover - {old_symbol.value} -> {new_symbol.value}"

            # Close the old contract
            self.liquidate(old_symbol, tag=tag)

            # Open the new contract with the same quantity
            if quantity:
                self.market_order(new_symbol, quantity, tag=tag)
