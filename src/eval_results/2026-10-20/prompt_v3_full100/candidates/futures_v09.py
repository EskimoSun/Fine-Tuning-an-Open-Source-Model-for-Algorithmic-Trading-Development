from AlgorithmImports import *
from typing import Dict, List, Optional


class ContinuousFuturesReference(QCAlgorithm):
    """Continuous E-mini S&P 500 futures reference strategy.

    Maintains a single long contract on the mapped continuous series,
    rolling over automatically when the underlying contract changes.
    """

    def initialize(self) -> None:
        """Initialize the algorithm: set window, add data, configure universe."""
        # Set the algorithm window
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add the continuous futures series
        self._future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            resolution=Resolution.MINUTE,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0,
        )
        self._future.set_filter(0, 92)

        # Asynchronous universe settings
        self._future.universe_settings = UniverseSettings(
            is_async=True,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
        )

        # Track the currently held contract symbol
        self._current_contract: Optional[Symbol] = None

    def on_data(self, slice: Slice) -> None:
        """Handle incoming data; enter a position when flat."""
        # Only act during market hours
        if not self.is_market_hours_open:
            return

        # Get the mapped continuous symbol
        mapped_symbol = self._future.mapped

        # If we are flat, buy one contract
        if self._current_contract is None:
            self._current_contract = mapped_symbol
            self.market_order(mapped_symbol, 1, tag="initial_entry")

    def on_symbol_changed_events(self, symbol_changed_events: Dict[Symbol, SymbolChangedEvent]) -> None:
        """Handle futures contract rollover events.

        For each symbol change event, liquidate the old contract and
        open the same quantity on the new contract. All rollover orders
        are tagged with both symbols and the event time for audit purposes.

        Args:
            symbol_changed_events: Dictionary mapping old symbols to their
                corresponding SymbolChangedEvent objects.
        """
        for old_symbol, changed_event in symbol_changed_events.items():
            new_symbol = changed_event.new_symbol

            # Read the quantity held in the old contract
            old_position = self.portfolio.get(old_symbol)
            if old_position is None:
                continue
            quantity = old_position.quantity
            if quantity == 0:
                continue

            # Build an audit tag naming both symbols and the rollover time
            rollover_time = self.time.strftime("%Y-%m-%d %H:%M:%S")
            tag = f"rollover:{old_symbol.value}->{new_symbol.value}@{rollover_time}"

            # Liquidate the old contract
            self.liquidate(old_symbol, tag=tag)

            # Open the same quantity on the new contract
            self.market_order(new_symbol, quantity, tag=tag)

            # Update the tracked contract
            self._current_contract = new_symbol
