from AlgorithmImports import *

class MonthlyRotation(QCAlgorithm):
    """
    Monthly rotation strategy:
    - Uses 60-day rate of change on daily bars for SPY, EFA, EEM, AGG, GLD.
    - On the first trading day of each month, one minute after the open:
        * If all five assets have negative ROC, liquidate everything and hold cash.
        * Otherwise, allocate one-third of portfolio value to each of the top 3 by ROC,
          and liquidate the remaining two.
    """

    # Named variables for easy tweaking
    ROC_PERIOD = 60
    TOP_N = 3

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)  # Dec 31, 2024 inclusive
        self.set_cash(100_000)

        # Tickers
        self.tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]

        # Add daily data for each ticker
        self.securities_dict = {}
        for ticker in self.tickers:
            equity = self.add_equity(ticker, resolution=Resolution.DAILY)
            self.securities_dict[ticker] = equity

        # Create 60-day rate of change indicators for each ticker
        self.roc_indicators = {}
        for ticker in self.tickers:
            roc = self.roc(ticker, self.ROC_PERIOD, resolution=Resolution.DAILY)
            self.roc_indicators[ticker] = roc

        # Schedule: first trading day of each month, 1 minute after market open
        self.schedule.on(
            self.date_rules.month_start(self.tickers[0]),
            self.time_rules.after_market_open(self.tickers[0], 1),
            self.on_monthly_rotation
        )

    def on_data(self, data: Slice):
        pass  # No intraday logic needed; all actions are scheduled

    def on_monthly_rotation(self):
        """
        Execute monthly rotation logic:
        - Check if all ROC values are negative -> liquidate all and hold cash.
        - Otherwise, pick top 3 by ROC, allocate 1/3 of portfolio to each, liquidate the rest.
        """
        # Ensure all indicators are ready
        if not all(ind.is_ready for ind in self.roc_indicators.values()):
            self.log("Indicators not ready yet. Skipping rotation.")
            return

        # Get current ROC values
        roc_values = {}
        for ticker in self.tickers:
            roc_values[ticker] = self.roc_indicators[ticker].current.value

        self.log(f"ROC values: {roc_values}")

        # Cash rule: If all five assets have negative rate of change,
        # sell everything and hold cash to avoid exposure in a broadly declining market.
        if all(val < 0 for val in roc_values.values()):
            self.log("All ROC values are negative. Liquidating all positions and holding cash.")
            for ticker in self.tickers:
                self.liquidate(ticker)
            return

        # Sort tickers by ROC descending
        sorted_tickers = sorted(roc_values.keys(), key=lambda t: roc_values[t], reverse=True)
        top_n = sorted_tickers[:self.TOP_N]
        others = sorted_tickers[self.TOP_N:]

        self.log(f"Top {self.TOP_N}: {top_n}, Others: {others}")

        # Liquidate the non-top assets
        for ticker in others:
            self.liquidate(ticker)

        # Allocate one-third of portfolio value to each top asset
        portfolio_value = self.portfolio.portfolio_value
        allocation_per_asset = portfolio_value / self.TOP_N

        for ticker in top_n:
            # Calculate quantity to buy
            price = self.securities[ticker].price
            if price > 0:
                quantity = int(allocation_per_asset / price)
                if quantity > 0:
                    self.market_order(ticker, quantity)
                    self.log(f"Buying {quantity} shares of {ticker} at ${price:.2f}")
