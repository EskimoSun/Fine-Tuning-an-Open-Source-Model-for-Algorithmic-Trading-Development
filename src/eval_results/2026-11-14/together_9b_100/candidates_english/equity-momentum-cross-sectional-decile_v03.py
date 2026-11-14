# region imports
from AlgorithmImports import *
# endregion

class SP500MomentumUniverseAlgorithm(QCAlgorithm):
    _momentum_threshold = 0.10

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Refilter the ETF constituents monthly to match the rebalance cadence.
        self.universe_settings.schedule.on(self.date_rules.month_start('SPY'))
        # Add a Momentum universe filtered on dollar volume to obtain the 100 most liquid SPY constituents.
        self._universe = self.add_universe(self.universe.etf('SPY', self._etf_constituents_filter))
        # Create a Scheduled Event to rebalance the portfolio monthly.
        self.schedule.on(self.date_rules.month_start('SPY'), self.time_rules.at(9, 31), self._rebalance)

    def _etf_constituents_filter(self, constituents: List[ETFConstituentUniverse]) -> List[Symbol]:
        # Select the 100 ETF constituents with the highest dollar volume.
        return [c.symbol for c in constituents
                if c.weight and c.symbol in self.securities
                for _ in range(100)]

    def _rebalance(self) -> None:
        if not self._universe.selected:
            return
        # Calculate the 1-year momentum for each security in the universe.
        momentum = [s for s in self._universe.selected
                    if self.portfolio.momentum(s, 1 * 252, Resolution.DAILY).current.value > self._momentum_threshold]
        # Form an equal-weighted portfolio of the top 10% 1-year momentum stocks.
        if not momentum:
            return
        weight = 1 / len(momentum)
        targets = [PortfolioTarget(symbol, weight) for symbol in momentum]
        self.set_holdings(targets, True)
