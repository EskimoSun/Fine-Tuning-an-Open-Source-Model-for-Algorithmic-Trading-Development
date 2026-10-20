# QuantConnect LEAN Algorithm
# SPY Bollinger Bands (20, 2) Daily Strategy

from AlgorithmImports import *

class SPYBollingerStrategy(QCAlgorithm):

    def Initialize(self):
        # Set start and end dates
        self.SetStartDate(2024, 9, 1)
        self.SetEndDate(2024, 12, 31)
        
        # Set initial capital
        self.SetCash(100_000)
        
        # Add SPY equity
        self.spy = self.AddEquity("SPY", Resolution.DAILY).Symbol
        
        # Set up Bollinger Bands indicator (20 period, 2 standard deviations)
        self.bb = self.Indicator(self.spy, 20, Resolution.DAILY, 2)
        
        # Schedule daily check pre-open (9:00 AM ET, before market open at 9:30 AM)
        self.Schedule.On(
            self.DateRules.Every(self.spy),
            self.TimeRules.BeforeMarketOpen(self.spy, 30),
            self.OnPreOpenCheck
        )
        
        # Log initialization
        self.Log("SPY Bollinger Bands Strategy initialized")

    def OnPreOpenCheck(self):
        """
        Daily pre-open check:
        - If flat and price < lower band -> go 100% long
        - If invested and price >= middle band -> liquidate
        """
        # Get the latest close price (previous day's close since we're pre-open)
        if not self.bb.IsReady:
            self.Log("Bollinger Bands not ready yet")
            return
        
        # Get the most recent close price
        price = self.Securities[self.spy].Price
        
        # Get Bollinger Bands values
        lower_band = self.bb.LowerBand.Current.Value
        middle_band = self.bb.MovingAverage.Current.Value
        upper_band = self.bb.UpperBand.Current.Value
        
        self.Log(f"Pre-open check: Price={price:.2f}, Lower={lower_band:.2f}, Middle={middle_band:.2f}, Upper={upper_band:.2f}")
        
        # Check if we're flat
        if self.Portfolio[self.spy].Quantity == 0:
            # Flat and price < lower band -> go 100% long
            if price < lower_band:
                self.Log(f"Signal: BUY - Price {price:.2f} < Lower Band {lower_band:.2f}")
                self.SetHoldings(self.spy, 1.0)
        else:
            # Invested and price >= middle band -> liquidate
            if price >= middle_band:
                self.Log(f"Signal: SELL - Price {price:.2f} >= Middle Band {middle_band:.2f}")
                self.Liquidate(self.spy)

    def OnOrderEvent(self, orderEvent):
        """Log order events"""
        if orderEvent.Status == OrderStatus.Filled:
            self.Log(f"Order filled: {orderEvent.Symbol} {orderEvent.Direction} {orderEvent.FillQuantity} @ {orderEvent.FillPrice:.2f}")
