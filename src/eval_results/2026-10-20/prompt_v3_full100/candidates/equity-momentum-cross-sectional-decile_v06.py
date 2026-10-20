from AlgorithmImports import *


class MomentumTop100Algorithm(QCAlgorithm):
    """
    Monthly momentum rotation over the top 100 SPY constituents by dollar volume.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
        self.set_order_margin_checking(False)

        # Universe: top 100 SPY constituents by dollar volume, minute resolution
        self._universe = self.add_universe(
            "SPY",
            UniverseSelectionPeriod.DAILY,
            self._select_universe,
            self._on_universe_changed,
            UniverseStyle.CONSOLIDATED,
            Resolution.MINUTE
        )

        # Warm up 253 daily bars for the 252-day momentum lookback
        self.set_warm_up(253, Resolution.DAILY)

        # Seed initial prices for the universe
        self._seed_initial_prices()

        # Schedule monthly rebalance at 09:31
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.at(9, 31),
            self._rebalance
        )

    def _select_universe(self, slice):
        """Select top 100 SPY constituents by dollar volume."""
        if not slice.has_fundamentals:
            return []

        candidates = []
        for symbol, fundamental in slice.fundamentals.items():
            if not isinstance(fundamental, EquityFundamental):
                continue
            if fundamental.dollar_volume is None or fundamental.dollar_volume <= 0:
                continue
            candidates.append((symbol, fundamental.dollar_volume))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [symbol for symbol, _ in candidates[:100]]

    def _on_universe_changed(self, added, removed):
        """Handle universe changes."""
        for symbol in added:
            self.debug(f"Universe added: {symbol}")
        for symbol in removed:
            self.debug(f"Universe removed: {symbol}")

    def _seed_initial_prices(self):
        """Seed initial prices for universe members."""
        for symbol in self._universe:
            if symbol in self.securities:
                self.securities[symbol].set_price(1.0)

    def _rebalance(self):
        """Monthly rebalance: top decile by 252-day momentum, equal weight."""
        if self.is_warming_up:
            return

        # Compute momentum for each universe member
        momentum_scores = {}
        for symbol in self._universe:
            if symbol not in self.securities:
                continue
            security = self.securities[symbol]
            if not security.has_data:
                continue

            # Get fundamental adjusted price history for 252 days
            history = self.history(symbol, 252, Resolution.DAILY, DataNormalizationMode.ADJUSTED)
            if len(history) < 252:
                continue

            # Use adjusted close prices
            prices = [bar.close for bar in history.values()]
            if len(prices) < 252:
                continue

            current_price = prices[-1]
            past_price = prices[0]
            if past_price <= 0:
                continue

            momentum = (current_price - past_price) / past_price
            momentum_scores[symbol] = momentum

        if not momentum_scores:
            self.debug("No momentum scores computed; skipping rebalance.")
            return

        # Sort by momentum descending
        sorted_symbols = sorted(momentum_scores.keys(), key=lambda s: momentum_scores[s], reverse=True)

        # Top decile (min 1)
        top_decile_count = max(1, len(sorted_symbols) // 10)
        selected = sorted_symbols[:top_decile_count]

        self.debug(f"Rebalancing to top {top_decile_count} by momentum: {selected}")

        # Liquidate existing holdings
        self.liquidate_existing_holdings()

        # Equal weight portfolio targets
        if selected:
            weight = 1.0 / len(selected)
            for symbol in selected:
                self.set_holdings(symbol, weight)

    def liquidate_existing_holdings(self):
        """Liquidate all current holdings."""
        for symbol in list(self.portfolio.keys()):
            if self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)
