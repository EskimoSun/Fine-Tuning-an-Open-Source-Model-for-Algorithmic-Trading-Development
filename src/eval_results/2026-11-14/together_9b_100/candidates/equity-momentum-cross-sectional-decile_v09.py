# region imports
from AlgorithmImports import *
# endregion

class SP500LowPctUpcomingEarningsUniverseAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Refilter the ETF constituents monthly to match the rebalance cadence.
        self.universe_settings.schedule.on(self.date_rules.month_start('SPY'))
        # Add a universe of SPY constituents ranked by dollar volume.
        self._universe = self.add_universe(self.universe.etf('SPY', universe_filter_func=self._select_assets))
        # Add a momentum indicator for all securities in the universe.
        self._momentum = self.momentum(self._universe, 252, Resolution.DAILY)
        # Create a Scheduled Event to rebalance the portfolio monthly.
        self.schedule.on(self.date_rules.month_start('SPY'), self.time_rules.at(9, 31, 0), self._rebalance)

    def _select_assets(self, constituents: list[ETFConstituentUniverse]) -> list[Symbol]:
        # Filter for securities with 10%+ weight in the ETF and 30+ days of daily data.
        filtered = [c.symbol for c in constituents
                    if c.weight and c.symbol in self.securities and
                    self.securities[c.symbol].history.length >= 30]
        # Sort the filtered symbols by dollar volume, largest first.
        return [x for x in sorted([self.securities[symbol].dollar_volume
                                  for symbol in filtered], reverse=True)[:100]]

    def _rebalance(self) -> None:
        if not self._momentum.is_ready:
            return
        # Rank all universe members by raw return and keep the top 10%.
        ranked = sorted(self._momentum.keys(), key=lambda s: self._momentum[s])[-len(self._universe.selected)[:10]:]
        # Build target weights for the top performers and liquidate the rest.
        targets = [PortfolioTarget(symbol, 1.0 / len(ranked)) for symbol in ranked]
        self.set_holdings(targets, True)
