# region imports
from AlgorithmImports import *
# endregion

class SP500HighMomentumOnlyUniverseAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Refilter the ETF constituents monthly to match the rebalance cadence.
        self.universe_settings.schedule.on(self.date_rules.month_start('SPY'))
        # Add a Custom Universe that ranks SPY constituents by dollar volume and price momentum.
        self._universe = self.add_universe(self.universe.etf('SPY', universe_filter_func=self._select_assets))
        # Create a Scheduled Event to rebalance monthly.
        self.schedule.on(self.date_rules.month_start('SPY'), self.time_rules.at(9, 0), self._rebalance)

    def _select_assets(self, constituents: list[ETFConstituentUniverse]) -> list[Symbol]:
        history = self.history([constituent.symbol for constituent in constituents], timedelta(365), Resolution.DAILY)
        if history.empty:
            return []
        # Select the 91st percentile of constituents by dollar volume with positive 1-year price momentum.
        return list(history.dollar_volume.quantile(0.91).index & history.return_.quantile(0.91).index)

    def _rebalance(self) -> None:
        selected_symbols = [symbol for symbol in self._universe.selected]
        if not selected_symbols:
            return
        # Equal-weight the selected momentum stocks.
        weight = 1 / len(selected_symbols)
        targets = [PortfolioTarget(symbol, weight) for symbol in selected_symbols]
        self.set_holdings(targets, liquidate_existing_holdings=True)
