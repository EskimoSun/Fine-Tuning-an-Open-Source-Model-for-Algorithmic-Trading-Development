from AlgorithmImports import *

class MomentumTop10Percent(QCAlgorithm):
    def initialize(self):
        # Set start, end, and cash
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(250_000)

        # Fixed universe of large-cap US stocks (proxy for SPY constituents)
        self.universe = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
            "AVGO", "JPM", "V", "UNH", "XOM", "LLY", "MA", "COST", "WMT",
            "PG", "HD", "MRK", "ABBV", "CVX", "KO", "PEP", "TMO", "BAC",
            "CSCO", "MCD", "ABT", "CRM", "AMD", "NFLX", "LIN", "TXN", "ORCL",
            "ADBE", "INTC", "QCOM", "IBM", "CAT", "GE", "UPS", "HON", "LOW",
            "SBUX", "DIS", "NKE", "PFE", "T", "VZ", "CMCSA", "TJX", "ISRG",
            "AMGN", "BKNG", "PLTR", "PANW", "SNOW", "SHOP", "COIN", "RBLX",
            "UBER", "ABNB", "DASH", "RIVN", "LCID", "NIO", "XPEV", "LI",
            "BABA", "JD", "PDD", "BIDU", "NTES", "TME", "BILI", "FUTU",
            "SE", "GRAB", "GOOG", "AMAT", "KLAC", "LRCX", "MU", "ON",
            "SWKS", "MRVL", "INTU", "ADP", "CTAS", "FTNT", "CRWD", "ZS",
            "DDOG", "NET", "OKTA", "TWLO", "TEAM", "WDAY", "HUBS", "PATH",
            "ZM", "SNPS", "CDNS", "SNOW", "PLTR", "PANW", "CRWD", "ZS",
            "DDOG", "NET", "OKTA", "TWLO", "TEAM", "WDAY", "HUBS", "PATH"
        ]
        # Remove duplicates while preserving order
        seen = set()
        self.universe = [s for s in self.universe if not (s in seen or seen.add(s))]

        # Add equity data for each stock at daily resolution
        self.securities_dict = {}
        for ticker in self.universe:
            equity = self.add_equity(ticker, resolution=Resolution.DAILY)
            self.securities_dict[ticker] = equity

        # Store price history for each stock (list of (date, adjusted_close))
        self.price_history = {ticker: [] for ticker in self.universe}

        # Track current holdings
        self.current_holdings = set()

        # Schedule monthly rebalancing at market open
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.at(9, 30),
            self.rebalance
        )

    def on_data(self, data: Slice):
        # Update price history for each stock
        for ticker in self.universe:
            if ticker in data:
                bar = data[ticker]
                if bar.is_traded:
                    # Use adjusted close price
                    adjusted_close = bar.close
                    self.price_history[ticker].append((bar.end_time, adjusted_close))
                    # Keep only last 300 entries to save memory
                    if len(self.price_history[ticker]) > 300:
                        self.price_history[ticker] = self.price_history[ticker][-300:]

    def get_percent_change_252(self, ticker):
        """Calculate percent price change over last 252 trading days."""
        history = self.price_history[ticker]
        if len(history) < 253:
            return None
        # Last 252 trading days: from index -253 to -1
        start_price = history[-253][1]
        end_price = history[-1][1]
        if start_price == 0:
            return None
        return (end_price - start_price) / start_price * 100

    def rebalance(self):
        """Rebalance portfolio at start of each month."""
        # Calculate percent change for each stock
        percent_changes = {}
        for ticker in self.universe:
            pct_change = self.get_percent_change_252(ticker)
            if pct_change is not None:
                percent_changes[ticker] = pct_change

        if not percent_changes:
            return

        # Sort by percent change descending
        sorted_tickers = sorted(percent_changes.items(), key=lambda x: x[1], reverse=True)

        # Top 10% of 100 stocks = 10 stocks
        top_10 = [ticker for ticker, _ in sorted_tickers[:10]]

        # Sell stocks no longer in top 10
        for ticker in list(self.current_holdings):
            if ticker not in top_10:
                self.liquidate(ticker)
                self.current_holdings.discard(ticker)

        # Buy new stocks in top 10
        for ticker in top_10:
            if ticker not in self.current_holdings:
                # Equal weight: 1/10 of portfolio value
                target_value = self.portfolio.portfolio_value / 10
                current_value = self.portfolio[ticker].invested if ticker in self.portfolio else 0
                delta_value = target_value - current_value
                if delta_value > 0:
                    price = self.securities[ticker].price
                    if price > 0:
                        quantity = int(delta_value / price)
                        if quantity > 0:
                            self.market_order(ticker, quantity)
                            self.current_holdings.add(ticker)

        # Update current holdings to top 10
        self.current_holdings = set(top_10)
