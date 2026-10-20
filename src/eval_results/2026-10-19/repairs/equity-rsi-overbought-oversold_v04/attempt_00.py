# QuantConnect LEAN Algorithm
# QQQ RSI Mean Reversion Strategy
# Hourly timeframe, Long when RSI < 30, Short when RSI > 70
# Exit at RSI midline (50)
# Backtest period: Q4 2024 (Oct 1, 2024 - Dec 31, 2024)

from AlgorithmImports import *

class QQQRSIMeanReversion(QCAlgorithm):
    def Initialize(self):
        # Set backtest period: Q4 2024
        self.SetStartDate(2024, 10, 1)
        self.SetEndDate(2024, 12, 31)
        
        # Set initial capital
        self.SetCash(100000)
        
        # Add QQQ equity
        self.symbol = self.AddEquity("QQQ", Resolution.Hourly).Symbol
        
        # RSI parameters
        self.rsi_period = 14
        self.oversold_level = 30
        self.overbought_level = 70
        self.midline = 50
        
        # Position tracking
        self.in_position = False
        self.position_side = None  # 'long' or 'short'
        
        # Schedule hourly data
        self.Schedule.On(self.DateRules.Every(self.symbol), self.TimeRules.AfterMarketOpen(self.symbol, 0), self.OnHourlyBar)
        
        # Log initialization
        self.Log("QQQ RSI Mean Reversion Strategy Initialized")
        self.Log(f"RSI Period: {self.rsi_period}, Oversold: {self.oversold_level}, Overbought: {self.overbought_level}, Midline: {self.midline}")

    def OnHourlyBar(self, context):
        # Get historical data for RSI calculation
        # We need at least rsi_period + 1 bars
        lookback = self.rsi_period + 1
        history = self.History(self.symbol, lookback, Resolution.Hourly)
        
        if history is None or len(history) < lookback:
            return
        
        # Calculate RSI
        rsi = self.CalculateRSI(history, self.rsi_period)
        
        if rsi is None:
            return
        
        current_price = self.Securities[self.symbol].Price
        
        # Check if we have an open position
        if self.in_position:
            # Check for exit condition: RSI crosses midline
            if self.position_side == 'long' and rsi >= self.midline:
                self.Liquidate(self.symbol)
                self.Log(f"EXIT LONG: RSI={rsi:.2f} >= Midline={self.midline}, Price={current_price:.2f}")
                self.in_position = False
                self.position_side = None
            elif self.position_side == 'short' and rsi <= self.midline:
                self.Liquidate(self.symbol)
                self.Log(f"EXIT SHORT: RSI={rsi:.2f} <= Midline={self.midline}, Price={current_price:.2f}")
                self.in_position = False
                self.position_side = None
        else:
            # No position, check for entry conditions
            if rsi < self.oversold_level:
                # Go long
                self.SetHoldings(self.symbol, 1.0)
                self.in_position = True
                self.position_side = 'long'
                self.Log(f"ENTRY LONG: RSI={rsi:.2f} < Oversold={self.oversold_level}, Price={current_price:.2f}")
            elif rsi > self.overbought_level:
                # Go short
                self.SetHoldings(self.symbol, -1.0)
                self.in_position = True
                self.position_side = 'short'
                self.Log(f"ENTRY SHORT: RSI={rsi:.2f} > Overbought={self.overbought_level}, Price={current_price:.2f}")

    def CalculateRSI(self, history, period):
        """
        Calculate RSI from historical price data.
        history: list of Slice objects with Close prices
        period: RSI lookback period
        """
        if history is None or len(history) < period + 1:
            return None
        
        # Extract close prices in chronological order
        closes = []
        for bar in history:
            if self.symbol in bar:
                closes.append(bar[self.symbol].Close)
        
        if len(closes) < period + 1:
            return None
        
        # Calculate price changes
        changes = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        
        if len(changes) < period:
            return None
        
        # Separate gains and losses
        gains = [max(change, 0) for change in changes]
        losses = [max(-change, 0) for change in changes]
        
        # Calculate average gain and loss (simple average for initial period)
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        # If avg_loss is 0, RSI is 100
        if avg_loss == 0:
            return 100.0
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    def OnEnd(self):
        # Liquidate any remaining positions
        if self.in_position:
            self.Liquidate(self.symbol)
            self.Log(f"END: Liquidated remaining position. Side: {self.position_side}")
        
        self.Log("Algorithm Ended")
