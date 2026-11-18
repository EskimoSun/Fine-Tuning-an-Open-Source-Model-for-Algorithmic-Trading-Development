from AlgorithmImports import *


class CrossSectionalMomentumAlgorithm(QCAlgorithm):
    """Cross-sectional momentum reference strategy.

    Universe: SPY constituents capped at the 100 highest by dollar volume.
    Signal: 252-period momentum percent from daily adjusted prices.
    Rebalance: first trading day of each month at 09:31.
    Portfolio: top 10% of the capped universe, equal-weight.
    """

    def initialize(self):
        # Window and capital
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250_000)

        # Benchmark
        self.set_benchmark("SPY")

        # Add SPY for universe membership and benchmark
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Add universe of SPY constituents, daily resolution
        self.universe = self.add_universe_selection(
            lambda date: self.spy.constituents,
            lambda date: self.select_universe(date),
            Resolution.DAILY,
            timedelta(days=1),
        )

        # Warm up 253 daily bars before selecting
        self.set_warm_up(253, Resolution.DAILY)

        # Schedule monthly rebalance on first trading day at 09:31
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.at(9, 31),
            self.rebalance,
        )

        # Track selected universe
        self._selected_symbols = []

    def select_universe(self, date):
        """Select top 100 SPY constituents by dollar volume."""
        constituents = self.spy.constituents
        if not constituents:
            return []

        # Compute dollar volume for each constituent
        scored = []
        for symbol in constituents:
            if symbol in self.securities:
                security = self.securities[symbol]
                if security.has_data and security.data is not None:
                    price = security.data.close
                    volume = security.data.volume
                    dollar_volume = price * volume
                    scored.append((symbol, dollar_volume))

        # Sort by dollar volume descending and take top 100
        scored.sort(key=lambda x: x[1], reverse=True)
        top_100 = [symbol for symbol, _ in scored[:100]]
        return top_100

    def on_universe_changed(self, added, removed):
        """Handle universe changes."""
        # No immediate action; rebalance handles position adjustments
        pass

    def rebalance(self):
        """Rebalance portfolio: hold top 10% of capped universe equal-weight."""
        if not self.is_warm_up_complete:
            return

        # Get current selected universe
        current_universe = self.universe.current
        if not current_universe:
            return

        # Compute 252-period momentum percent for each symbol
        momentum_scores = {}
        for symbol in current_universe:
            if symbol not in self.securities:
                continue
            security = self.securities[symbol]
            if not security.has_data:
                continue

            # Get daily price history for momentum calculation
            history = self.history(symbol, 253, Resolution.DAILY)
            if len(history) < 253:
                continue

            # Use adjusted close prices
            prices = [bar.close for bar in history]
            if len(prices) < 253:
                continue

            # 252-period momentum percent: (current_price / price_252_ago - 1) * 100
            current_price = prices[-1]
            price_252_ago = prices[-253]
            if price_252_ago == 0:
                continue

            momentum_percent = (current_price / price_252_ago - 1) * 100
            momentum_scores[symbol] = momentum_percent

        if not momentum_scores:
            return

        # Sort by momentum descending
        sorted_symbols = sorted(momentum_scores.keys(), key=lambda s: momentum_scores[s], reverse=True)

        # Top 10% of the capped universe
        top_count = max(1, int(len(sorted_symbols) * 0.10))
        top_symbols = sorted_symbols[:top_count]

        # Liquidate all current positions
        for symbol in list(self.portfolio.keys()):
            if symbol in self.securities and self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)

        # Equal-weight the top symbols
        if top_symbols:
            weight = 1.0 / len(top_symbols)
            for symbol in top_symbols:
                self.set_holdings(symbol, weight)

        self.log(f"Rebalanced: holding {len(top_symbols)} symbols, top momentum: {momentum_scores[top_symbols[0]]:.2f}%")

    def on_data(self, data):
        """No per-bar action needed; rebalance is scheduled."""
        pass
