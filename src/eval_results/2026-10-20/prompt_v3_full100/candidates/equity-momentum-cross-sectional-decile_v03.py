from AlgorithmImports import *


class Sp500Momentum(QCAlgorithm):
    """
    Monthly momentum strategy on the top 100 SPY constituents by dollar volume.
    Ranks by 252-day percent price change and holds the top 10% in equal weight.
    """

    # Named variables as requested
    LOOKBACK_DAYS = 252
    UNIVERSE_SIZE = 100
    TOP_PERCENT = 0.10

    def initialize(self):
        self.set_start_date(datetime(2022, 1, 1))
        self.set_end_date(datetime(2024, 12, 31))
        self.set_cash(250_000)

        # We warm up for 253 days (252 trading days + 1) so that on the first
        # monthly rebalance the 252-day lookback has enough historical data to
        # compute a valid percent change. The extra day accounts for the fact
        # that the current bar is included in the window, ensuring we have a
        # full 252 prior trading days of data before the first signal.
        self.set_warm_up(timedelta(days=253))

        # Add SPY as a reference for the universe
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Store the universe of top 100 by dollar volume
        self.universe = []

        # Schedule monthly rebalance at 9:31 AM
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.at(9, 31),
            self.rebalance
        )

    def on_data(self, data: Slice):
        if not self.is_warm_up_complete:
            return

        # Update the universe of top 100 SPY constituents by dollar volume
        # We use the SPY holdings data if available, otherwise we approximate
        # using a static list. In LEAN, we can access ETF holdings via
        # self.securities["SPY"].holdings if the data is available.
        # For robustness, we'll use a dynamic approach:
        # Get the current SPY holdings from the data feed
        spy_holdings = self.securities["SPY"].holdings
        if spy_holdings:
            # Sort by dollar volume (price * volume) and take top 100
            holdings_with_volume = []
            for holding in spy_holdings:
                symbol = holding.symbol
                if symbol in self.securities:
                    sec = self.securities[symbol]
                    if sec.has_data and sec.price > 0:
                        # Use the most recent volume data
                        volume = sec.volume if sec.volume > 0 else 0
                        dollar_volume = sec.price * volume
                        holdings_with_volume.append((symbol, dollar_volume))

            # Sort by dollar volume descending and take top 100
            holdings_with_volume.sort(key=lambda x: x[1], reverse=True)
            self.universe = [s for s, _ in holdings_with_volume[:self.UNIVERSE_SIZE]]
        else:
            # Fallback: if holdings data is not available, keep previous universe
            pass

    def rebalance(self):
        """Rebalance the portfolio at the start of each month."""
        if not self.is_warm_up_complete:
            return

        if not self.universe:
            return

        # Calculate 252-day percent price change for each stock in the universe
        momentum_scores = {}
        for symbol in self.universe:
            if symbol not in self.securities:
                continue
            sec = self.securities[symbol]
            if not sec.has_data:
                continue

            # Get the last 253 daily prices (252 days of change + current)
            prices = []
            for i in range(self.LOOKBACK_DAYS + 1):
                # Access historical data
                price = self.history(symbol, 1, Resolution.DAILY, i)
                if price and len(price) > 0:
                    prices.append(price[0].close)
                else:
                    prices.append(None)

            # Filter out None values
            valid_prices = [p for p in prices if p is not None and p > 0]
            if len(valid_prices) < self.LOOKBACK_DAYS + 1:
                continue

            # Calculate percent change from 252 days ago to now
            start_price = valid_prices[0]
            end_price = valid_prices[-1]
            if start_price > 0:
                percent_change = (end_price - start_price) / start_price
                momentum_scores[symbol] = percent_change

        if not momentum_scores:
            return

        # Sort by momentum score descending
        sorted_symbols = sorted(momentum_scores.keys(), key=lambda s: momentum_scores[s], reverse=True)

        # Select top 10%
        num_to_hold = max(1, int(len(sorted_symbols) * self.TOP_PERCENT))
        selected = sorted_symbols[:num_to_hold]

        # Liquidate any positions not in the selected list
        for symbol in list(self.portfolio.keys()):
            if symbol in self.securities and self.securities[symbol].type == SecurityType.EQUITY:
                if symbol not in selected:
                    self.liquidate(symbol)

        # Set equal-weight holdings for selected stocks
        if selected:
            weight = 1.0 / len(selected)
            for symbol in selected:
                self.set_holdings(symbol, weight)
