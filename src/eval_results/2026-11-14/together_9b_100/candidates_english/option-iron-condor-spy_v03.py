# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):
    
    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self._option = self.add_option("SPY")
        # Using Staddle() method, it will only return the best-matched ATM call and put contracts expiring on the same day.
        # It provides better accuracy in filtering, and subscribe only to the needed contracts to save computation resources.
        self._option.set_filter(lambda u: u.staddle(0, 0))

        self.schedule.on(
            self.date_rules.week_start(self._option.symbol),
            self.time_rules.after_market_open(self._option.symbol, 1),
            self._trade
        )
        self.schedule.on(
            self.date_rules.week_end(self._option.symbol),
            self.time_rules.before_market_close(self._option.symbol, 3),
            self._close
        )

    def _trade(self) -> None:
        if not self._option.investable:
            return

        strike = self._option.current.price
        expiry = self._option.current.expiry
        call = self._option.chain.call(strike, expiry)
        put = self._option.chain.put(strike, expiry)

        if not call or not put:
            return

        expiry = min(call.expiry, put.expiry)
        next_week_expiry = expiry + timedelta(7)
        upper_strike = sorted([s for s in self._option.chain.strikes() if s > strike and self._option.chain.call(s, next_week_expiry).investable], reverse=True)[0]
        lower_strike = sorted([s for s in self._option.chain.strikes() if s < strike and self._option.chain.put(s, next_week_expiry).investable])[0]

        if not self.portfolio.invested and lower_strike and upper_strike:
            self.strategy.iron_condor(self._option, strike, lower_strike, upper_strike, expiry)

    def _close(self) -> None:
        if self.portfolio.invested:
            self.liquidate()
