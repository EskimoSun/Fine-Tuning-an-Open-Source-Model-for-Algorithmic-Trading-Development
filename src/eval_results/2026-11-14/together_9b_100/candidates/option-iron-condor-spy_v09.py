# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):
    _chain_filter = OptionChainFilter()

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.automatic_indicator_warm_up = True
        self.universe_settings.minimum_time_in_universe = timedelta(0)

        self._option = self.add_option("SPY")
        self._option.set_filter(self._chain_filter)
        # Using Staddle() method, it will only return the best-matched ATM call and put contracts expiring after 30 days.
        # It provides better accuracy in filtering, and subscribe only to the needed contracts to save computation resources.
        self._option.set_filter(OptionFilter.staddle(30))

        self.schedule.on(
            self.date_rules.week_start(self._option),
            self.time_rules.after_market_open(self._option, 1),
            self._buy_irons
        )
        self.schedule.on(
            self.date_rules.week_end(self._option),
            self.time_rules.before_market_close(self._option, 1),
            self._sell_irons
        )

    def _get_contract_delta(self, contract: OptionContract) -> float:
        if not contract.delta:
            return contract.strike
        return contract.delta

    def _buy_irons(self) -> None:
        if not self._option.expirations:
            return
        next_expiration = min(self._option.expirations)
        calls = self.option_chain(self._option, next_expiration).calls
        puts = self.option_chain(self._option, next_expiration).puts

        if not calls or not puts:
            return

        atm_strike = self._option underlying().price
        sorted_calls = sorted(calls, key=lambda x: abs(atm_strike - x.strike))
        sorted_puts = sorted(puts, key=lambda x: abs(atm_strike - x.strike))

        atm_call = sorted_calls[0]
        atm_put = sorted_puts[0]

        delta_call = self._get_contract_delta(atm_call)
        delta_put = self._get_contract_delta(atm_put)

        if not self.portfolio.invested and abs(delta_call) < 0.1 and abs(delta_put) < 0.1:
            width = 3
            cap_strike = atm_strike + width
            floor_strike = atm_strike - width

            long_call = sorted_calls[-1]
            long_put = sorted_puts[-1]

            if (self.calculate_order_quantity(atm_call, 1) * atm_call.price
                    + self.calculate_order_quantity(atm_put, 1) * atm_put.price
                    <= self.portfolio.total_portfolio_value):
                self.combo_market_order([
                    ComboLeg.create(atm_call.symbol, -1),
                    ComboLeg.create(atm_put.symbol, -1),
                    ComboLeg.create(long_call.symbol, 1),
                    ComboLeg.create(long_put.symbol, 1)
                ])

    def _sell_irons(self) -> None:
        if not self._option.expirations:
            return
        next_expiration = min(self._option.expirations)
        calls = self.option_chain(self._option, next_expiration).calls
        puts = self.option_chain(self._option, next_expiration).puts

        if not calls or not puts:
            return

        atm_strike = self._option underlying().price
        sorted_calls = sorted(calls, key=lambda x: abs(atm_strike - x.strike))
        sorted_puts = sorted(puts, key=lambda x: abs(atm_strike - x.strike))

        atm_call = sorted_calls[0]
        atm_put = sorted_puts[0]

        if self.portfolio.invested:
            self.liquidate()
