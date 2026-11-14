# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):
    _chain: list[OptionContract] = []
    _min_strike = -1
    _max_strike = 1

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.universe_settings.minimum_time_in_universe = timedelta(0)

        self._option = self.add_option("SPY")
        self._option.set_filter(lambda u: u.strikes(-10, 10).expiries(0, 7))

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 1),
            self._rebalance
        )

    def _rebalance(self) -> None:
        if not self._option.chain:
            return

        expiry = min([x for x in self._option.chain if x.expiry > self.time][0].expiry)
        calls = [x for x in self._option.chain if x.expiry == expiry and x.right == OptionRight.CALL]
        puts = [x for x in self._option.chain if x.expiry == expiry and x.right == OptionRight.PUT]

        if len(calls) < 4 or len(puts) < 4:
            return

        underlying = self.securities[self._option.underlying]
        price = underlying.price
        delta = underlying.delta

        if not self._min_strike:
            self._min_strike = min([x.strike for x in puts])
            self._max_strike = max([x.strike for x in calls])

        selected_calls = sorted([x for x in calls if self._min_strike < x.strike < self._max_strike],
                                key=lambda x: abs(delta - self._option.delta(x)))[:4]
        selected_puts = sorted([x for x in puts if self._min_strike < x.strike < self._max_strike],
                               key=lambda x: abs(-delta - self._option.delta(x)))[:4]

        if not selected_calls or not selected_puts:
            return

        expiry = selected_calls[0].expiry

        def get_spread(wide: OptionContract, narrow: OptionContract) -> SpreadOptionStrategy:
            return SpreadOptionStrategy(wide, narrow, expiry, -1)

        strategy = PortfolioConstructionStrategy("Custom Iron Condor",
            get_spread(selected_calls[0], selected_calls[3]),
            get_spread(selected_puts[0], selected_puts[3])
        )

        self.portfolio_construction.set_strategy(strategy, True)
