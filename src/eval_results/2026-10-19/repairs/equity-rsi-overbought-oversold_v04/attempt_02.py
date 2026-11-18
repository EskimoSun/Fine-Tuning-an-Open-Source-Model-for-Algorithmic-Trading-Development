# QuantConnect LEAN Algorithm
# QQQ RSI Mean Reversion Strategy
# Hourly timeframe, Long when RSI < 30, Short when RSI > 70
# Exit at RSI midline (50)
# Backtest period: Q4 2024 (Oct 1, 2024 - Dec 31, 2024)

from AlgorithmImports import *
from datetime import datetime, timedelta

class QQQRSIMeanReversion(QCAlgorithm):
    def initialize(self):
        # Set backtest period: Q4 2024
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2024, 12, 31)
        
        # Set initial capital
        self.set_cash(100000)
        
        # Add QQQ equity with hourly resolution
        self._equity = self.add_equity("QQQ", Resolution.HOUR)
        self.symbol = self._equity.symbol
        
        # RSI parameters
        self.rsi_period = 14
        self.oversold_level = 30
        self.overbought_level = 70
        self.midline = 50
        
        # Position tracking
        self.in_position = False
        self.position_side = None  # 'long' or 'short'
        
        # Create RSI indicator
        self._rsi = self.rsi(self.symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.HOUR)
        
        # Log initialization
        self.log("QQQ RSI Mean Reversion Strategy Initialized")
        self.log(f"RSI Period: {self.rsi_period}, Oversold: {self.oversold_level}, Overbought: {self.overbought_level}, Midline: {self.midline}")

    def on_data(self, data: Slice):
        # Only process if we have the symbol in data
        if self.symbol not in data:
            return
        
        # Check if RSI indicator is ready
        if not self._rsi.is_ready:
            return
        
        # Get current RSI value
        rsi = self._rsi.current.value
        
        # Get current price safely
        if self.symbol not in data or data[self.symbol] is None:
            return
        current_price = data[self.symbol].close
        
        # Check if we have an open position
        if self.in_position:
            # Check for exit condition: RSI crosses midline
            if self.position_side == 'long' and rsi >= self.midline:
                self.liquidate(self.symbol)
                self.log(f"EXIT LONG: RSI={rsi:.2f} >= Midline={self.midline}, Price={current_price:.2f}")
                self.in_position = False
                self.position_side = None
            elif self.position_side == 'short' and rsi <= self.midline:
                self.liquidate(self.symbol)
                self.log(f"EXIT SHORT: RSI={rsi:.2f} <= Midline={self.midline}, Price={current_price:.2f}")
                self.in_position = False
                self.position_side = None
        else:
            # No position, check for entry conditions
            if rsi < self.oversold_level:
                # Go long
                self.set_holdings(self.symbol, 1.0)
                self.in_position = True
                self.position_side = 'long'
                self.log(f"ENTRY LONG: RSI={rsi:.2f} < Oversold={self.oversold_level}, Price={current_price:.2f}")
            elif rsi > self.overbought_level:
                # Go short
                self.set_holdings(self.symbol, -1.0)
                self.in_position = True
                self.position_side = 'short'
                self.log(f"ENTRY SHORT: RSI={rsi:.2f} > Overbought={self.overbought_level}, Price={current_price:.2f}")

    def on_end(self):
        # Liquidate any remaining positions
        if self.in_position:
            self.liquidate(self.symbol)
            self.log(f"END: Liquidated remaining position. Side: {self.position_side}")
        
        self.log("Algorithm Ended")
