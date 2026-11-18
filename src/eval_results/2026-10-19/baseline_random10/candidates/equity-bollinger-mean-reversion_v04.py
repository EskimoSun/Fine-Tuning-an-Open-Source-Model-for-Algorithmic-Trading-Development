# QuantConnect LEAN Algorithm
# SPY BB(20,2) Dip Buy, Exit at Midline, Daily Check, Q4 2024

from AlgorithmImports import *

class BB202DipBuyMidlineExitQ42024(QCAlgorithm):

    def initialize(self):
        # Set start and end dates for Q4 2024
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2025, 1, 1)
        
        # Set cash
        self.set_cash(100000)
        
        # Add SPY equity
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        
        # Set up Bollinger Bands indicator (20 period, 2 std dev)
        self.bb = self.bollinger_bands(20, 2, MovingAverageType.SIMPLE)
        self.set_benchmark("SPY")
        
        # Track position state
        self.in_position = False
        self.entry_price = 0.0
        
        # Schedule daily check at market open
        self.schedule.on(self.spy, MarketHours.Open, self.daily_check)

    def on_data(self, data: Slice):
        # No action needed here; logic is in scheduled event
        pass

    def daily_check(self):
        # Check if we have enough data for BB
        if len(self.bb) < 20:
            return
            
        # Get current price
        if self.spy not in data:
            return
            
        current_price = data[self.spy].price
        
        # Get BB values
        upper = self.bb.upper
        middle = self.bb.middle
        lower = self.bb.lower
        
        # If not in position, check for dip buy (price <= lower band)
        if not self.in_position:
            if current_price <= lower:
                # Buy SPY
                self.set_holdings(self.spy, 1.0)
                self.in_position = True
                self.entry_price = current_price
                self.log(f"BUY SPY at {current_price:.2f} (Lower BB: {lower:.2f})")
                
        # If in position, check for exit at midline
        else:
            if current_price >= middle:
                # Sell SPY
                self.set_holdings(self.spy, 0.0)
                self.in_position = False
                self.log(f"SELL SPY at {current_price:.2f} (Midline BB: {middle:.2f})")
