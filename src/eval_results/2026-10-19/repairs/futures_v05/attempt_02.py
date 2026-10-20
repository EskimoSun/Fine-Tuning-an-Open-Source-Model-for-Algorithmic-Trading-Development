# QuantConnect LEAN Algorithm
# ES (SP_500_E_MINI) continuous future with LAST_TRADING_DAY mapping
# Strategy: Flat -> market order 1 of mapped contract
# On symbol changed: liquidate old, re-enter same quantity on new
# Period: 2024-09-01 to 2024-12-31

from AlgorithmImports import *
from datetime import datetime, timedelta

class EsContinuousLastTradingDayAlgorithm(QCAlgorithm):
    def initialize(self):
        # Set start and end dates
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Add continuous future with LAST_TRADING_DAY mapping
        # BACKWARDS_RATIO, depth 0, extended hours, filter 0-92 days
        self._es = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0
        )
        
        # Set filter for 0-92 days
        self._es.set_filter(0, 92)
        
        # Track current position quantity
        self._position_qty = 0
        
        # Subscribe to symbol changed events
        self._es.on_symbol_changed_event += self.on_symbol_changed

    def on_symbol_changed(self, sender, args):
        """
        Handle symbol changed event:
        - Liquidate old contract
        - Re-enter same quantity on new contract
        """
        old_symbol = args.old_symbol
        new_symbol = args.new_symbol

        # Liquidate old position
        if self._position_qty != 0:
            self.liquidate(old_symbol)
            self.log(f"Liquidated {self._position_qty} contracts of {old_symbol}")

        # Re-enter same quantity on new contract
        if self._position_qty != 0:
            self.market_order(new_symbol, self._position_qty)
            self.log(f"Entered {self._position_qty} contracts of {new_symbol}")

    def on_data(self, data: Slice):
        """
        Main data handler:
        - If flat, place market order for 1 contract of the mapped symbol
        """
        # Check if we have data for our ES symbol
        if not data.contains_key(self._es):
            return

        # Get the current mapped symbol (the actual contract)
        current_symbol = self._es.mapped
        
        # Check if we are flat
        if self._position_qty == 0:
            # Place market order for 1 contract
            self.market_order(current_symbol, 1)
            self._position_qty = 1
            self.log(f"Entered 1 contract of {current_symbol}")

    def on_order_event(self, order_event: OrderEvent):
        """
        Track position changes from order events
        """
        if order_event.symbol == self._es.mapped:
            if order_event.status == OrderStatus.FILLED:
                self._position_qty += order_event.fill_quantity
                self.log(f"Order filled: {order_event.fill_quantity} contracts, total position: {self._position_qty}")
