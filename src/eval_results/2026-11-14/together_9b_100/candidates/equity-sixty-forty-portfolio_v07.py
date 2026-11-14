# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):
    _weight_by_symbol: dict[Symbol, float] = {}

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        for equity in [self.add_equity("SPY"), self.add_equity("TLT")]:
            equity.weight = 1 / len(self._weight_by_symbol)
            equity.target_percent = 1 / len(self._weight_by_symbol)
            self._weight_by_symbol[equity.symbol] = equity.weight
            equity.set_filter(0, 0)
        self.schedule.on(self.date_rules.year_start("SPY", 2), self.time_rules.after_market_open("SPY", 5), self._rebalance)

    def _rebalance(self) -> None:
        for symbol, weight in self._weight_by_symbol.items():
            self.set_holdings(symbol, weight, True)
