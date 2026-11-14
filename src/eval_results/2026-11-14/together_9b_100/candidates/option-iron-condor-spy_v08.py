# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):
    _chain: list[OptionContract] = []
    _long_strike = -1
    _short_strike = 1

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self._option = self.add_option("SPY")
        self._option.set_filter(lambda u: self._filter(u))
        self.schedule.on(self.date_rules.every(DayOfWeek.MONDAY), self.time_rules.after_market_open("SPY", 1), self._place_orders)
        self.schedule.on(self.date_rules.every(DayOfWeek.FRIDAY), self.time_rules.before_market_close("SPY", 5), self._close_irons)

    def _filter(self, chain: list[OptionContract]) -> list[OptionContract]:
        expiry = min([x.expiry for x in chain])
        atm = sorted([x for x in chain if x.expiry == expiry and x.right == OptionRight.CALL], key=lambda x: abs(self._option.symbol.value - x.strike))[0]
        self._short_strike = atm.strike + 10
        self._long_strike = atm.strike - 10
        return chain

    def _get_contracts(self) -> tuple[OptionContract, OptionContract, OptionContract, OptionContract]:
        call = sorted([x for x in self._chain if x.strike == self._short_strike and x.expiry >= self.time + timedelta(7)], key=lambda x: x.expiry)[0]
        put = sorted([x for x in self._chain if x.strike == self._long_strike and x.expiry >= self.time + timedelta(7)], key=lambda x: x.expiry)[0]
        atm_call = sorted([x for x in self._chain if x.strike == atm.strike and x.expiry >= self.time + timedelta(7)], key=lambda x: x.expiry)[0]
        atm_put = sorted([x for x in self._chain if x.strike == atm.strike and x.expiry >= self.time + timedelta(7)], key=lambda x: x.expiry)[0]
        return call, put, atm_call, atm_put

    def _place_orders(self) -> None:
        if not self.portfolio.invested:
            call, put, atm_call, atm_put = self._get_contracts()
            self._chain = list(set(self._chain + [call, put, atm_call, atm_put]))
            self.buy(atm_call, -1)
            self.sell(call, 1)
            self.buy(atm_put, -1)
            self.sell(put, 1)

    def _close_irons(self) -> None:
        for security in self.securities.values():
            if security.invested:
                self.liquidate(security)
