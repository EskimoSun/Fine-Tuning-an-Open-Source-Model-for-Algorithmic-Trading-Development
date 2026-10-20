# QuantConnect LEAN Algorithm
# ES (SP_500_E_MINI) continuous future with LAST_TRADING_DAY mapping
# Strategy: Flat -> market order 1 of mapped contract
# On symbol changed: liquidate old, re-enter same qty on new
# Period: 2024-09-01 to 2024-12-31

from AlgorithmImports import *

class EsContinuousLastTradingDayAlgorithm(QCAlgorithm):
    def Initialize(self):
        # Set start and end dates
        self.SetStartDate(2024, 9, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(100000)

        # Add continuous future with LAST_TRADING_DAY mapping
        # BACKWARDS_RATIO, depth 0, extended hours, filter 0-92 days
        self._es = self.AddFuture(
            "SP_500_E_MINI",
            Resolution.DAILY,
            MarketDataMappingMethod.LAST_TRADING_DAY,
            dataNormalizationMode=DataNormalizationMode.BACKWARDS_RATIO,
            depth=0,
            extendedMarketHours=True,
            filter=FutureFilter(0, 92)
        ).Symbol

        # Track current position quantity
        self._position_qty = 0

        # Subscribe to symbol changed events
        self._es.SymbolChanged += self.OnSymbolChanged

    def OnSymbolChanged(self, sender, args):
        """
        Handle symbol changed event:
        - Liquidate old contract
        - Re-enter same quantity on new contract
        """
        old_symbol = args.OldSymbol
        new_symbol = args.NewSymbol

        # Liquidate old position
        if self._position_qty != 0:
            self.Liquidate(old_symbol)
            self.Log(f"Liquidated {self._position_qty} contracts of {old_symbol}")

        # Re-enter same quantity on new contract
        if self._position_qty != 0:
            self.MarketOrder(new_symbol, self._position_qty)
            self.Log(f"Entered {self._position_qty} contracts of {new_symbol}")

    def OnData(self, data: Slice):
        """
        Main data handler:
        - If flat, place market order for 1 contract of the mapped symbol
        """
        # Check if we have data for our ES symbol
        if not data.ContainsKey(self._es):
            return

        # Get the current mapped symbol (the actual contract)
        current_symbol = self._es

        # Check if we are flat
        if self._position_qty == 0:
            # Place market order for 1 contract
            self.MarketOrder(current_symbol, 1)
            self._position_qty = 1
            self.Log(f"Entered 1 contract of {current_symbol}")

    def OnOrderEvent(self, orderEvent: OrderEvent):
        """
        Track position changes from order events
        """
        if orderEvent.Symbol == self._es:
            if orderEvent.Status == OrderStatus.FILLED:
                self._position_qty += orderEvent.FillQuantity
                self.Log(f"Order filled: {orderEvent.FillQuantity} contracts, total position: {self._position_qty}")
