from AlgorithmImports import *


class CrossAssetMomentumRotation(QCAlgorithm):
    """
    Monthly cross-asset momentum rotation across US equity, developed ex-US,
    emerging markets, aggregate bonds and gold (SPY, EFA, EEM, AGG, GLD).
    Uses a cash fallback in broad drawdowns.
    """

    def initialize(self):
        # Set start/end dates
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)

        # Standard paper account
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
        self.set_cash(100_000, USD)

        # Assets
        self.assets = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self._securities = {}
        for ticker in self.assets:
            sec = self.add_equity(ticker, resolution=Resolution.DAILY)
            self._securities[ticker] = sec

        # Momentum lookback (6 months ~ 126 trading days)
        self._lookback = 126

        # Drawdown threshold for cash fallback (e.g., 10% drawdown from peak)
        self._drawdown_threshold = 0.10

        # Track peak portfolio value for drawdown detection
        self._peak_portfolio_value = self.portfolio.total_value

        # Schedule monthly rebalance on the first trading day of each month
        self.schedule.on(
            self.date_rules.month_start(self.assets[0]),
            self.time_rules.at(16, 0),  # 4:00 PM ET
            self._rebalance
        )

        # Warm up for momentum calculation
        self.set_warm_up(timedelta(days=self._lookback + 10))

    def on_data(self, data: Slice):
        # Update peak portfolio value
        current_value = self.portfolio.total_value
        if current_value > self._peak_portfolio_value:
            self._peak_portfolio_value = current_value

        # Check for broad drawdown
        drawdown = (self._peak_portfolio_value - current_value) / self._peak_portfolio_value
        if drawdown > self._drawdown_threshold:
            # Liquidate all positions and hold cash
            for ticker in self.assets:
                if self.portfolio[ticker].quantity != 0:
                    self.liquidate(ticker)
            self.log(f"Broad drawdown detected: {drawdown:.2%}. Holding cash.")

    def _rebalance(self):
        """Monthly rebalance: pick top 2 momentum assets, equal weight."""
        # Check if we're in drawdown mode
        current_value = self.portfolio.total_value
        drawdown = (self._peak_portfolio_value - current_value) / self._peak_portfolio_value
        if drawdown > self._drawdown_threshold:
            self.log(f"Skipping rebalance due to drawdown: {drawdown:.2%}")
            return

        # Calculate momentum for each asset
        momentum_scores = {}
        for ticker in self.assets:
            sec = self._securities[ticker]
            if not sec.has_data:
                continue
            # Get price history
            history = self.history([sec], timedelta(days=self._lookback + 5), Resolution.DAILY)
            if len(history) < self._lookback:
                continue
            # Calculate momentum: return over lookback period
            prices = history.close
            if len(prices) >= self._lookback:
                initial_price = prices.iloc[-self._lookback]
                current_price = prices.iloc[-1]
                if initial_price > 0:
                    momentum = (current_price - initial_price) / initial_price
                    momentum_scores[ticker] = momentum

        if not momentum_scores:
            self.log("No momentum scores available. Skipping rebalance.")
            return

        # Sort by momentum descending, pick top 2
        sorted_assets = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_assets = [ticker for ticker, _ in sorted_assets[:2]]

        self.log(f"Momentum scores: {momentum_scores}")
        self.log(f"Selected assets: {top_assets}")

        # Liquidate all current positions
        for ticker in self.assets:
            if self.portfolio[ticker].quantity != 0:
                self.liquidate(ticker)

        # Equal weight allocation to top 2 assets
        if top_assets:
            weight = 1.0 / len(top_assets)
            for ticker in top_assets:
                self.set_holdings(ticker, weight)
