# region imports
from AlgorithmImports import *
# endregion

class SP500HighVolumeTotalReturnUniverseAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Refilter the ETF constituents monthly to match the rebalance cadence.
        self.universe_settings.schedule.on(self.date_rules.month_start('SPY'))
        # Add a TotalReturn universe filtered by dollar volume for the classic smart-beta pipeline.
        self._universe = self.add_universe(self.universe.etf('SPY', universe_filter_func=self._select_assets))
        # Create a Scheduled Event to rebalance the portfolio monthly.
        self.schedule.on(self.date_rules.month_start('SPY'), self.time_rules.at(9, 0), self._rebalance)

    def _select_assets(self, constituents: list[ETFConstituentUniverse]) -> list[Symbol]:
        # Filter for assets with above $100M dollar volume for liquidity.
        filtered = [c.symbol for c in constituents if c.dollar_volume > 100000000]
        if len(filtered) < 10:
            return []
        # Rank the filtered assets by total return over the past year.
        return [s for s in sorted(
            filtered,
            key=lambda s: self.total_return(s, 252),
            reverse=True
        )[:10]]

    def _rebalance(self) -> None:
        selected = self._universe.selected
        if not selected:
            return
        # Calculate equal weights for the selected securities.
        weight = 1 / len(selected)
        targets = [PortfolioTarget(symbol, weight) for symbol in selected]
        self.set_holdings(targets, liquidate_existing_holdings=True)
