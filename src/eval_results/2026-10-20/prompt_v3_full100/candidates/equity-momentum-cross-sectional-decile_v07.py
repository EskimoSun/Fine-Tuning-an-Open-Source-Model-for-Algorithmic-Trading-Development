from AlgorithmImports import *


class MomentumFactorReference(QCAlgorithm):
    """Long-only cross-sectional momentum reference on liquid S&P 500 names.

    - Universe: S&P 500 constituents (daily data).
    - Signal: trailing 12-month momentum (price return over the last 252 trading days).
    - Selection: top decile (10%) by momentum, long-only, equal-weighted.
    - Rebalance: monthly, after market open.
    - Period: 2022-01-01 through 2024-12-31.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(1_000_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Daily resolution is sufficient for monthly rebalancing and 12-month lookback.
        self._universe = self.add_universe(
            self.universe_settings(
                self.date_rules.every_day(),
                self.time_rules.at(16, 0),
                self.universe_selection,
                self.on_universe_changed,
            )
        )

        # Monthly rebalance: first trading day of each month, 15 minutes after open.
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.at(9, 30),
            self._rebalance,
        )

        self._momentum_window = 252  # ~12 months of daily bars
        self._top_fraction = 0.10    # top decile
        self._selected = []          # list of symbols currently held

    def universe_selection(self, date, candidates):
        """Filter to liquid S&P 500 names with sufficient history."""
        selected = []
        for symbol in candidates:
            security = self.securities.get(symbol)
            if security is None:
                continue
            # Must be a common stock, US market, and have enough history.
            if not isinstance(security, Equity):
                continue
            if security.market != Market.USA:
                continue
            # Require at least 252 daily bars of history for momentum calc.
            if len(security.history) < self._momentum_window:
                continue
            # Liquidity filter: average daily volume > 100k shares.
            recent = security.history[0:20]
            if len(recent) < 20:
                continue
            avg_volume = sum(bar.volume for bar in recent) / len(recent)
            if avg_volume < 100_000:
                continue
            selected.append(symbol)
        return selected

    def on_universe_changed(self, date, added, removed):
        """Log universe changes for reference."""
        if added:
            self.log(f"Universe added {len(added)} symbols on {date.date()}")
        if removed:
            self.log(f"Universe removed {len(removed)} symbols on {date.date()}")

    def _compute_momentum(self, symbol):
        """Compute trailing 12-month momentum (simple return) for a symbol."""
        security = self.securities.get(symbol)
        if security is None:
            return None
        history = security.history[0:self._momentum_window]
        if len(history) < self._momentum_window:
            return None
        # Use close prices; first bar is oldest, last is most recent.
        oldest_close = history[0].close
        latest_close = history[-1].close
        if oldest_close <= 0:
            return None
        return (latest_close - oldest_close) / oldest_close

    def _rebalance(self):
        """Monthly rebalance: select top decile by momentum, equal-weight long-only."""
        # Gather all current universe symbols.
        universe_symbols = list(self._universe.current_symbols)
        if not universe_symbols:
            self.log("No symbols in universe; skipping rebalance.")
            return

        # Compute momentum for each symbol.
        momentum_scores = {}
        for symbol in universe_symbols:
            mom = self._compute_momentum(symbol)
            if mom is not None:
                momentum_scores[symbol] = mom

        if not momentum_scores:
            self.log("No valid momentum scores; skipping rebalance.")
            return

        # Sort by momentum descending, take top decile.
        sorted_symbols = sorted(momentum_scores.keys(), key=lambda s: momentum_scores[s], reverse=True)
        n_select = max(1, int(len(sorted_symbols) * self._top_fraction))
        self._selected = sorted_symbols[:n_select]

        self.log(f"Rebalance: selected {len(self._selected)} of {len(sorted_symbols)} symbols. "
                 f"Top: {self._selected[0]} (mom={momentum_scores[self._selected[0]]:.4f}), "
                 f"Bottom: {self._selected[-1]} (mom={momentum_scores[self._selected[-1]]:.4f})")

        # Liquidate any holdings not in the new selection.
        for symbol in list(self.portfolio.keys()):
            if symbol in self._selected:
                continue
            if self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)
                self.log(f"Liquidated {symbol}")

        # Equal-weight the selected symbols.
        n = len(self._selected)
        if n == 0:
            return
        weight = 1.0 / n
        for symbol in self._selected:
            self.set_holdings(symbol, weight)
            self.log(f"Set holdings {symbol} to {weight:.4f}")
