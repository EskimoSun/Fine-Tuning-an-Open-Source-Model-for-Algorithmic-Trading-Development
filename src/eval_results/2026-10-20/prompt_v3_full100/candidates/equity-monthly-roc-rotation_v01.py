from AlgorithmImports import *


class MomentumRotationAlgorithm(QCAlgorithm):
    """
    Monthly momentum rotation among SPY, EFA, EEM, AGG, and GLD.
    Ranks assets by trailing 3-month momentum and holds the top 2.
    If all assets have negative momentum, stays in cash.
    Backtest period: 2022-01-01 to 2024-12-31.
    """

    def initialize(self):
        # Set backtest period
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        # Tickers to rotate among
        self.tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self.securities_dict = {}

        # Add equity data for each ticker
        for ticker in self.tickers:
            equity = self.add_equity(ticker, resolution=Resolution.DAILY)
            self.securities_dict[ticker] = equity

        # Number of assets to hold
        self.hold_count = 2

        # Momentum lookback period in days
        self.momentum_lookback = 63  # ~3 months of trading days

        # Schedule monthly rebalancing on the first trading day of each month
        self.schedule.on(
            self.date_rules.month_start(self.tickers[0]),
            self.time_rules.at(16, 0),  # 4 PM ET, after market close
            self.rebalance
        )

        # Track current holdings
        self.current_holdings = []

    def on_data(self, data: Slice):
        pass

    def rebalance(self):
        """
        Monthly rebalancing: rank assets by trailing momentum,
        hold the top N if positive, otherwise stay in cash.
        """
        # Calculate momentum for each ticker
        momentum_scores = {}
        for ticker in self.tickers:
            security = self.securities_dict[ticker]
            if not security.has_data:
                continue

            # Get price history for momentum calculation
            history = self.history(security, self.momentum_lookback, Resolution.DAILY)
            if len(history) < self.momentum_lookback:
                continue

            # Momentum = current price / price N days ago - 1
            current_price = history[-1].close
            past_price = history[0].close
            if past_price <= 0:
                continue

            momentum = (current_price / past_price) - 1
            momentum_scores[ticker] = momentum

        if not momentum_scores:
            self.log("No momentum data available. Staying in cash.")
            self.liquidate_all()
            return

        # Sort by momentum descending
        sorted_tickers = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)

        # Select top N tickers with positive momentum
        selected = []
        for ticker, score in sorted_tickers:
            if score > 0:
                selected.append(ticker)
            if len(selected) >= self.hold_count:
                break

        self.log(f"Momentum scores: {momentum_scores}")
        self.log(f"Selected holdings: {selected}")

        # Liquidate current holdings
        self.liquidate_all()

        # Buy selected tickers with equal weight
        if selected:
            weight = 1.0 / len(selected)
            for ticker in selected:
                self.set_holdings(ticker, weight)
            self.current_holdings = selected
        else:
            self.log("All assets have negative momentum. Staying in cash.")
            self.current_holdings = []

    def liquidate_all(self):
        """Liquidate all current holdings."""
        for ticker in self.tickers:
            security = self.securities_dict[ticker]
            if security in self.portfolio and self.portfolio[security].quantity != 0:
                self.liquidate(security)
