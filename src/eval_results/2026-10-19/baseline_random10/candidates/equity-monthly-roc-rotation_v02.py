# QuantConnect LEAN Algorithm
# Monthly rotation based on 60-day rate of change for SPY, EFA, EEM, AGG, GLD

from AlgorithmImports import *

class MonthlyRateOfChangeRotation(QCAlgorithm):
    def Initialize(self):
        # Set start and end dates
        self.SetStartDate(2022, 1, 1)
        self.SetEndDate(2024, 12, 31)
        
        # Set initial capital
        self.SetCash(100_000)
        
        # Define the universe of tickers
        self.tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        
        # Add equity data for each ticker with daily resolution
        self.equities = {}
        for ticker in self.tickers:
            equity = self.AddEquity(ticker, Resolution.DAILY)
            equity.SetDataConsolidation(Consolidation.DAILY)
            self.equities[ticker] = equity
        
        # Track the last rebalance month to avoid multiple rebalances in the same month
        self.last_rebalance_month = None
        
        # Schedule the rebalance on the first trading day of each month
        self.Schedule.On(
            date_rule=self.DateRules.MonthStart(),
            time_rule=self.TimeRules.At(9, 30),
            action=self.Rebalance
        )
    
    def Rebalance(self):
        # Get the current month
        current_month = self.Time.Month
        current_year = self.Time.Year
        
        # Only rebalance once per month
        if self.last_rebalance_month == (current_year, current_month):
            return
        
        self.last_rebalance_month = (current_year, current_month)
        
        # Calculate 60-day rate of change for each ticker
        roc_values = {}
        for ticker in self.tickers:
            # Get the last 61 daily bars (need 60 days of change)
            history = self.History(self.equities[ticker], 61, Resolution.DAILY)
            
            if len(history) < 61:
                # Not enough data, skip this ticker
                continue
            
            # Rate of change = (current_price - price_60_days_ago) / price_60_days_ago
            current_price = history[-1].Close
            price_60_days_ago = history[0].Close
            
            if price_60_days_ago == 0:
                continue
            
            roc = (current_price - price_60_days_ago) / price_60_days_ago
            roc_values[ticker] = roc
        
        # If we don't have enough data for all tickers, skip rebalance
        if len(roc_values) < 5:
            return
        
        # Check if all five are negative
        if all(roc < 0 for roc in roc_values.values()):
            # Sell everything and hold cash
            for ticker in self.tickers:
                if self.Portfolio[ticker].Quantity != 0:
                    self.Liquidate(ticker)
            self.Debug(f"All tickers negative. Holding cash. ROC: {roc_values}")
            return
        
        # Sort tickers by rate of change in descending order
        sorted_tickers = sorted(roc_values.keys(), key=lambda t: roc_values[t], reverse=True)
        
        # Top 3 tickers
        top_3 = sorted_tickers[:3]
        
        # Sell any positions not in the top 3
        for ticker in self.tickers:
            if ticker not in top_3:
                if self.Portfolio[ticker].Quantity != 0:
                    self.Liquidate(ticker)
        
        # Calculate target allocation: 1/3 of portfolio value in each top 3
        portfolio_value = self.Portfolio.TotalPortfolioValue
        target_per_ticker = portfolio_value / 3.0
        
        # Buy/adjust positions for top 3
        for ticker in top_3:
            current_value = self.Portfolio[ticker].MarketValue
            difference = target_per_ticker - current_value
            
            if abs(difference) > 100:  # Only trade if difference is significant
                if difference > 0:
                    # Buy more
                    self.MarketOrder(ticker, difference / self.Securities[ticker].Price)
                else:
                    # Sell some
                    self.MarketOrder(ticker, difference / self.Securities[ticker].Price)
        
        self.Debug(f"Rebalanced. Top 3: {top_3}. ROC: {roc_values}")
