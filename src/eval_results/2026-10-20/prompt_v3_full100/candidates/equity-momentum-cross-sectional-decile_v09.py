from AlgorithmImports import *
from typing import Dict, List, Optional


class CrossSectionalMomentumAlgorithm(QCAlgorithm):
    """Cross-sectional momentum reference strategy.

    Universe: SPY constituents capped at the 100 highest by dollar volume.
    Signal: 252-period momentum percent from daily adjusted prices.
    Rebalance: first trading day of each month at 09:31, hold top 10% equal-weight.
    """

    def initialize(self) -> None:
        """Initialize the algorithm."""
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)
        self.set_minimum_order_margin_portfolio_percentage(0.0)

        # Add SPY as the universe source
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # Add universe: SPY constituents, capped at 100 by dollar volume
        self.universe = self.add_universe_selection(
            lambda date, holdings: self._select_universe(date, holdings),
            resolution=Resolution.MINUTE,
            selected_fill_forward=True,
            selected_leverage=0,
            selected_extended_market_hours=False,
            deselected_fill_forward=False,
            deselected_leverage=0,
            deselected_extended_market_hours=False,
        )

        # Warm up 253 daily bars
        self.set_warm_up(253, Resolution.DAILY)

        # Schedule monthly rebalance on first trading day at 09:31
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.at(9, 31),
            self._rebalance,
        )

        # Track momentum values per symbol
        self._momentum: Dict[Symbol, float] = {}
        self._is_warming_up: bool = True

    def _select_universe(self, date: datetime, holdings: List[Symbol]) -> List[Symbol]:
        """Select the top 100 SPY constituents by dollar volume."""
        # Get SPY holdings
        spy_holdings = self.securities["SPY"].holdings
        if not spy_holdings:
            return []

        # Get constituent symbols
        constituents = list(spy_holdings.keys())

        # Filter to equity symbols only
        equity_symbols = [
            s for s in constituents
            if s.market == Market.USA and s.security_type == SecurityType.EQUITY
        ]

        # Rank by dollar volume (price * volume)
        def dollar_volume(symbol: Symbol) -> float:
            if symbol in self.securities:
                sec = self.securities[symbol]
                if sec.has_data and sec.price > 0:
                    # Use the most recent daily bar for volume
                    daily_data = self.history(symbol, 1, Resolution.DAILY)
                    if daily_data:
                        last_bar = daily_data.iloc[-1]
                        return float(last_bar.close) * float(last_bar.volume)
                return 0.0
            return 0.0

        # Sort by dollar volume descending
        ranked = sorted(equity_symbols, key=dollar_volume, reverse=True)

        # Cap at 100
        return ranked[:100]

    def on_data(self, data: Slice) -> None:
        """Handle incoming data."""
        if self.is_warming_up:
            return

        # Compute momentum for each symbol in the universe
        for symbol in self.universe:
            if symbol not in self.securities:
                continue
            sec = self.securities[symbol]
            if not sec.has_data:
                continue

            # Get 253 daily bars (252 for momentum + 1 current)
            history = self.history(symbol, 253, Resolution.DAILY)
            if history is None or len(history) < 253:
                continue

            # Use adjusted close prices
            adjusted_closes = history["adj_close"].values
            if len(adjusted_closes) < 253:
                continue

            # 252-period momentum percent: (P_t / P_{t-252}) - 1
            current_price = float(adjusted_closes[-1])
            past_price = float(adjusted_closes[-253])
            if past_price <= 0:
                continue

            momentum_pct = (current_price / past_price) - 1.0
            self._momentum[symbol] = momentum_pct

    def _rebalance(self) -> None:
        """Rebalance the portfolio to the top 10% of the universe by momentum."""
        if self.is_warming_up:
            return

        if not self._momentum:
            return

        # Sort symbols by momentum descending
        sorted_symbols = sorted(self._momentum.keys(), key=lambda s: self._momentum[s], reverse=True)

        # Top 10% of the capped universe (100 symbols -> top 10)
        top_count = max(1, len(sorted_symbols) // 10)
        top_symbols = sorted_symbols[:top_count]

        # Equal weight among top symbols
        weight = 1.0 / len(top_symbols) if top_symbols else 0.0

        # Liquidate all current holdings first
        for symbol in list(self.portfolio.keys()):
            if symbol in self.securities and self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)

        # Set holdings for top symbols
        for symbol in top_symbols:
            if symbol in self.securities:
                self.set_holdings(symbol, weight)

    def on_universe_changed(self, added: List[Symbol], removed: List[Symbol]) -> None:
        """Handle universe changes."""
        # Remove momentum tracking for removed symbols
        for symbol in removed:
            self._momentum.pop(symbol, None)

    def on_order_event(self, order_event: OrderEvent) -> None:
        """Handle order events."""
        pass
