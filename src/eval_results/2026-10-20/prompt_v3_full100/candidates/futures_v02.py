from AlgorithmImports import *


class EminiSpxRollAlgorithm(QCAlgorithm):
    """
    Buys one E-mini S&P 500 contract when flat and rolls the position
    when the continuous future mapping changes.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add the continuous E-mini S&P 500 future
        self.future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            resolution=Resolution.MINUTE,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0
        )
        self.future.set_filter(0, 92)

        # Track the currently held contract symbol
        self._held_symbol = None

    def on_data(self, data: Slice):
        # Only act on the mapped continuous contract
        if self.future.mapped not in data:
            return

        current_mapped = self.future.mapped

        # If we have no position, buy one contract of the currently mapped month
        if self._held_symbol is None:
            self.market_order(current_mapped, 1)
            self._held_symbol = current_mapped
            self.log(f"BUY 1 {current_mapped}")
            return

        # If the mapped contract changed, roll the position
        if current_mapped != self._held_symbol:
            old_symbol = self._held_symbol
            # Sell the old contract
            self.market_order(old_symbol, -1)
            self.log(f"SELL 1 {old_symbol}")

            # Buy the new contract
            self.market_order(current_mapped, 1)
            self.log(f"BUY 1 {current_mapped}")

            self._held_symbol = current_mapped

    def on_symbol_changed_events(self, symbol_changed_events):
        """
        Handle futures contract rollover events.
        """
        for symbol, changed_event in symbol_changed_events.items():
            old_symbol = changed_event.old_symbol
            new_symbol = changed_event.new_symbol

            # Only handle the E-mini S&P 500 continuous contract
            if symbol != self.future.mapped:
                continue

            self.log(f"Rollover detected: {old_symbol} -> {new_symbol}")

            # If we hold the old contract, sell it and buy the new one
            if self._held_symbol == old_symbol:
                self.market_order(old_symbol, -1)
                self.log(f"SELL 1 {old_symbol} (rollover)")

                self.market_order(new_symbol, 1)
                self.log(f"BUY 1 {new_symbol} (rollover)")

                self._held_symbol = new_symbol
