# region imports
from AlgorithmImports import *
# endregion

class SP500HighsLowstsisUniverseAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Refilter the ETF constituents monthly to match the rebalance cadence.
        self.universe_settings.schedule.on(self.date_rules.month_start('SPY'))
        # Add a universe of the SPY constituents ranked by dollar volume.
        self._universe = self.add_universe(self.universe.etf('SPY', universe_filter_func=self._select_assets))
        # Add a Scheduled Event to rebalance the portfolio monthly.
        self.schedule.on(self.date_rules.month_start('SPY'), self.time_rules.at(9, 31, 0), self._rebalance)

    def _select_assets(self, constituents: list[ETFConstituentUniverse]) -> list[Symbol]:
        history = self.history([constituent.symbol for constituent in constituents], timedelta(252), Resolution.DAILY)
        if history.empty:
            return []
        # Select the 100 ETF constituents with the highest dollar volume.
        return list(history.reset_index().sort_values(-("open" * 2)).iloc[:100].index)

    def _rebalance(self) -> None:
        selected_symbols = [symbol for symbol in self._universe.selected]
        if not selected_symbols:
            return
        # Rank the selected securities by fundamental data and form equal weight portfolios.
        targets = self._get_targets(selected_symbols)
        if not targets:
            return
        self.set_holdings(targets, liquidate_existing_holdings=True)
