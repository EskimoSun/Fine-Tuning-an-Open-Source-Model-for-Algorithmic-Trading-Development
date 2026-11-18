from AlgorithmImports import *

class SpxEminiHoldAlgorithm(QCAlgorithm):
    """
    Holds one S&P 500 E-mini futures contract and automatically rolls to the next
    contract when the current one expires.
    """

    def initialize(self):
        # Set start and end dates for the last few months of 2024
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add the S&P 500 E-mini futures with minute resolution
        # Use LAST_TRADING_DAY mapping so we always trade the front-month contract
        self._future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            resolution=Resolution.MINUTE,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0
        )

        # Only consider the front-month contract (depth 0)
        self._future.set_filter(0, 0)

        # Track the currently held symbol
        self._current_symbol = None

    def on_data(self, data: Slice):
        # Get the mapped (front-month) symbol
        mapped_symbol = self._future.mapped

        # If we don't have a position yet, buy one contract
        if self._current_symbol is None:
            if mapped_symbol in self.securities and self.securities[mapped_symbol].is_tradable:
                self._current_symbol = mapped_symbol
                self.market_order(mapped_symbol, 1)
                self.log(f"Opened 1 contract of {mapped_symbol}")
        else:
            # If the mapped symbol has changed, we need to roll
            if mapped_symbol != self._current_symbol:
                # Check if we still hold the old contract
                old_symbol = self._current_symbol
                if old_symbol in self.securities and self.portfolio[old_symbol].quantity != 0:
                    # Close the old position
                    self.liquidate(old_symbol)
                    self.log(f"Closed old contract {old_symbol}")

                # Open the new contract
                if mapped_symbol in self.securities and self.securities[mapped_symbol].is_tradable:
                    self._current_symbol = mapped_symbol
                    self.market_order(mapped_symbol, 1)
                    self.log(f"Rolled to new contract {mapped_symbol}")
                else:
                    self._current_symbol = None
                    self.log(f"New contract {mapped_symbol} not yet tradable, will retry")

    def on_symbol_changed_events(self, symbol_changed_events):
        """
        Handle symbol changes (rollover) for the futures series.
        """
        for symbol, changed_event in symbol_changed_events.items():
            old_symbol = changed_event.old_symbol
            new_symbol = changed_event.new_symbol
            self.log(f"Symbol changed: {old_symbol} -> {new_symbol}")

            # If we hold the old symbol, close it
            if old_symbol in self.securities and self.portfolio[old_symbol].quantity != 0:
                self.liquidate(old_symbol)
                self.log(f"Closed old contract {old_symbol} due to rollover")

            # Open the new symbol
            if new_symbol in self.securities and self.securities[new_symbol].is_tradable:
                self._current_symbol = new_symbol
                self.market_order(new_symbol, 1)
                self.log(f"Opened 1 contract of new contract {new_symbol}")
            else:
                self._current_symbol = None
                self.log(f"New contract {new_symbol} not yet tradable, will retry in on_data")
