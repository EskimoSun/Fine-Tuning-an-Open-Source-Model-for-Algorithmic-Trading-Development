# region imports
from AlgorithmImports import *
# endregion

class ETFUniverseAlgorithm(QCAlgorithm):
    _momentum: dict[Symbol, float] = {}
    _count = 100
    _target_percent = 0.1

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(250000)
        self.settings.seed_initial_prices = True
        self.settings.minimum_order_margin_portfolio_percentage = 0
        self.universe_settings.resolution = Resolution.MINUTE
        # Add a universe of US ETFs.
        self._universe = self.add_universe(self.universe.etf("SPY", self._count), self._select_assets)
        # Schedule daily rebalancing at 9:30 AM before market open.
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.at(9, 31),
            self._rebalance
        )

    def _select_assets(self, data: List[ETF]) -> List[Symbol]:
        # Select the top 100 ETFs by dollar volume.
        return [d.symbol for d in data[:self._count]]

    def _rebalance(self) -> None:
        if not self._universe.selected:
            return
        # Update momentum indicators for all selected ETFs.
        for symbol in self._universe.selected:
            if not self._momentum:
                # Create a new Momentum indicator for the symbol.
                self._momentum[symbol] = self.indicator.momentum(symbol, 252, Resolution.DAILY)
            self._momentum[symbol].update(self.utc_time, self.securities[symbol].price)
        # Rank the ETFs by their momentum values and form equal-weighted portfolios.
        ranked = sorted(
            [(s, self._momentum[s].current.value) for s in self._universe.selected],
            key=lambda x: x[1], reverse=True
        )
        # Buy the top 10% and short the bottom 10% of the ranked ETFs.
        targets = [PortfolioTarget(s, self._target_percent) for s, _ in ranked[:int(self._count * self._target_percent)]]
        targets += [PortfolioTarget(s, -self._target_percent) for s, _ in ranked[-int(self._count * self._target_percent):]]
        self.set_holdings(targets, True)
