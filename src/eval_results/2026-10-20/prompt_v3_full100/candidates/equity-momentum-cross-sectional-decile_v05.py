from AlgorithmImports import *


class MomentumTop100Algorithm(QCAlgorithm):
    """
    Monthly momentum strategy on the top 100 SPY constituents by dollar volume.
    Ranks by 252-day momentum (adjusted close / close 252 days ago - 1),
    buys the top decile (10 names) equal-weighted, liquidates the rest.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Warm up 253 daily bars so the 252-day momentum is available on day one.
        self.set_warm_up(253, Resolution.DAILY)

        # Universe: SPY constituents, capped to top 100 by dollar volume.
        self._universe = self.add_universe_selection(
            lambda date: self.spy_constituents(date),
            lambda date: self.top_by_dollar_volume(date, 100),
            Resolution.DAILY,
            timedelta(days=1),
        )

        # Schedule monthly rebalance at 09:31 market time.
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.at(9, 31),
            self.rebalance,
        )

        self._momentum = {}  # symbol -> float momentum value

    def spy_constituents(self, date):
        """Return the current SPY ETF constituents."""
        return self.fundamental.equity.spy_constituents(date)

    def top_by_dollar_volume(self, date, count):
        """Filter constituents to the top `count` by dollar volume."""
        constituents = self.fundamental.equity.spy_constituents(date)
        if not constituents:
            return []
        # Sort by dollar volume descending, take top `count`.
        sorted_constituents = sorted(
            constituents,
            key=lambda c: c.dollar_volume,
            reverse=True,
        )
        return sorted_constituents[:count]

    def on_universe_changed(self, added, removed):
        """Handle universe membership changes."""
        for symbol in removed:
            if symbol in self.portfolio and self.portfolio[symbol].invested != 0:
                self.liquidate(symbol)

    def on_data(self, data):
        """Compute 252-day momentum for each held/universe security."""
        if self.is_warming_up:
            return

        for symbol in self._universe.current_constituents:
            if symbol not in data:
                continue
            security = self.securities[symbol]
            if not security.has_data:
                continue

            # Need at least 253 daily bars (252 days of history + current).
            if len(security) < 253:
                continue

            current_price = security.close
            past_price = security[-252].close

            if past_price <= 0:
                continue

            momentum = current_price / past_price - 1.0
            self._momentum[symbol] = momentum

    def rebalance(self):
        """Monthly rebalance: buy top decile equal-weight, liquidate rest."""
        if not self._momentum:
            return

        # Sort by momentum descending.
        ranked = sorted(self._momentum.items(), key=lambda x: x[1], reverse=True)

        # Top decile of 100 = top 10.
        top_decile_count = max(1, len(ranked) // 10)
        top_symbols = [s for s, _ in ranked[:top_decile_count]]

        # Liquidate everything not in the top decile.
        for symbol in list(self.portfolio.keys()):
            if symbol not in top_symbols:
                if self.portfolio[symbol].invested != 0:
                    self.liquidate(symbol)

        # Equal-weight the top decile.
        if top_symbols:
            weight = 1.0 / len(top_symbols)
            for symbol in top_symbols:
                self.set_holdings(symbol, weight)

        self.log(f"Rebalanced: {len(top_symbols)} holdings, weight={weight:.4f}")
