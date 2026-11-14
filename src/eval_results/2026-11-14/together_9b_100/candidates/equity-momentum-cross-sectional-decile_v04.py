# region imports
from AlgorithmImports import *
# endregion


class SP500HighVolumeMomentumUniverseAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250_000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Refilter the ETF constituents monthly to match the rebalance cadence.
        self.universe_settings.schedule.on(self.date_rules.month_start('SPY'))
        # Add a universe of the SPY constituents ranked by dollar volume and 12-month momentum.
        self._universe = self.add_universe(self.universe.etf('SPY', universe_filter_func=self._select_assets))
        # Create a Scheduled Event to rebalance the portfolio monthly.
        self.schedule.on(self.date_rules.month_start('SPY'), self.time_rules.at(9, 0), self._rebalance)

    def _select_assets(self, constituents: list[ETFConstituentUniverse]) -> list[Symbol]:
        history = self.history([constituent.symbol for constituent in constituents], timedelta(12), Resolution.DAILY)
        if history.empty:
            return []
        # Select the 100 SPY constituents with the highest dollar volume and 12-month momentum.
        return list(history.sort(
            Series.sort_keys([
                lambda x: x.dollar_volume,
                lambda x: x.end_time - x.start_time
            ])
        ).index[:100])

    def _rebalance(self) -> None:
        selected_symbols = [symbol for symbol in self._universe.selected]
        if not selected_symbols:
            return
        # Equal-weight the selected constituents and place orders to rebalance the portfolio.
        weight = 1 / len(selected_symbols)
        targets = [PortfolioTarget(symbol, weight) for symbol in selected_symbols]
        self.set_holdings(targets, liquidate_existing_holdings=True)
