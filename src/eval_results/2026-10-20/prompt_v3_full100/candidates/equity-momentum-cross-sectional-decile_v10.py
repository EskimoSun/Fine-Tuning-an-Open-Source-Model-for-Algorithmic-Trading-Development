from AlgorithmImports import *


class MomentumDecileAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250_000)
        self.settings.seed_initial_prices = True
        self.settings.minimum_order_margin_portfolio_percentage = 0

        self._lookback = 252
        self._universe_cap = 100
        self._top_decile_pct = 0.1

        # MomentumPercent per symbol
        self._momentum = {}

        universe_settings = UniverseSettings(
            resolution=Resolution.MINUTE,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
        )

        self._universe = self.add_universe(
            self.universe.etf('SPY'),
            self._select_assets,
            universe_settings=universe_settings,
        )

        self.set_warm_up(253, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start('SPY'),
            self.time_rules.at(9, 31),
            self._rebalance,
        )

    def _select_assets(self, slice):
        # Update momentum for each symbol in the slice
        for symbol, equity in slice.equities.items():
            if equity.has_data:
                self._momentum[symbol] = MomentumPercent(
                    equity.end_time,
                    equity.adjusted_price,
                )

        # While warming up, keep the universe unchanged
        if self.is_warming_up:
            return Universe.UNCHANGED

        # Filter to ready symbols (enough history)
        ready = [
            (symbol, mp)
            for symbol, mp in self._momentum.items()
            if mp.is_ready
        ]

        if not ready:
            return Universe.UNCHANGED

        # Sort by dollar volume descending, cap at _universe_cap
        def dollar_volume(symbol):
            sec = self.securities.get(symbol)
            if sec is None:
                return 0.0
            return sec.price * sec.volume

        ready.sort(key=lambda x: dollar_volume(x[0]), reverse=True)
        ready = ready[: self._universe_cap]

        # Rank by momentum descending
        ready.sort(key=lambda x: x[1].value, reverse=True)

        # Return top decile
        n = len(ready)
        top_count = max(1, int(n * self._top_decile_pct))
        return [symbol for symbol, _ in ready[:top_count]]

    def _rebalance(self):
        selected = list(self._universe.selected)
        if not selected:
            return

        targets = [
            PortfolioTarget(symbol, 1.0 / len(selected))
            for symbol in selected
        ]
        self.set_holdings(targets, liquidate_existing_holdings=True)
