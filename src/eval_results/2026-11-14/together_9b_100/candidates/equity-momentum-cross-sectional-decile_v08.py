# region imports
from AlgorithmImports import *
# endregion

class ETFUniverseAlgorithm(QCAlgorithm):
    _momentum: dict[Symbol, float] = {}
    _weight: float = 0.1
    _target: list[PortfolioTarget] = []
    _count: int = 100
    _rank: int = 10

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.universe_settings.resolution = Resolution.MINUTE
        # Select the 100 most liquid stocks from the SPY ETF constituents and rank them by dollar volume.
        self._universe = self.add_universe(self.universe.etf("SPY", self._etf_constituents_filter))
        # Add a Momentum indicator to rank the selected securities.
        self._momentum = PortfolioMomentum(252)
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.at(9, 31),
            self._rebalance
        )

    def on_warmup_finished(self) -> None:
        self._momentum.warm_up(self._universe.selected)

    def _etf_constituents_filter(self, constituents: List[ETFConstituentUniverse]) -> List[Symbol]:
        # Filter for the 100 most liquid stocks by dollar volume.
        return [c.symbol for c in sorted(
            constituents if constituents else [],
            key=lambda c: c.dollar_volume, reverse=True
        )[:self._count]]

    def on_data(self, data: Slice) -> None:
        # Update the momentum ranking with the updated dollar volume of the selected securities.
        self._momentum.update(data, self._universe.selected)

    def _rebalance(self) -> None:
        if not self._momentum.is_ready:
            return
        # Rank the selected securities by their dollar volume and keep the top 10.
        ranked = sorted(
            self._momentum,
            key=lambda x: x.value, reverse=True
        )[:self._rank]
        # Form an equal weighted portfolio with the top 10 ranked securities.
        self._target = [PortfolioTarget(x.symbol, self._weight) for x in ranked]
        # Place orders to rebalance the portfolio.
        self.set_holdings(self._target, True)
