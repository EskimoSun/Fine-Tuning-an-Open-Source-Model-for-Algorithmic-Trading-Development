# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True
        # Filter the option chain to only select 0DTE options.
        self._option = self.add_option("SPY")
        self._option.set_filter(lambda u: u.expiration(0, 7).strikes(-10, 10))
        # Filter the option chain using a Delta range.
        # self._option = self.add_option("SPY")
        # self._option.set_filter(lambda u: u.expiration(0, 7).delta(0.25, 0.75))
        self.schedule.on(self.date_rules.every(DayOfWeek.MONDAY), self.time_rules.after_market_open(self._option, 1), self._rebalance)

    def _rebalance(self) -> None:
        if not self._option.chain:
            return
        # Get the best-matched contracts to form an Iron Condor strategy.
        expiry = min([x.expiration for x in self._option.chain])
        atm_call = sorted([x for x in self._option.chain if x.expiration == expiry and x.right == OptionRight.CALL],
            key=lambda x: abs(self._option.symbol.price - x.strike))[0]
        atm_put = sorted([x for x in self._option.chain if x.expiration == expiry and x.right == OptionRight.PUT],
            key=lambda x: abs(self._option.symbol.price - x.strike))[0]
        # Use the strike of the selected ATM contracts to define the trading range.
        trading_range = (atm_put.strike, atm_call.strike)
        # Use the strike of the selected ATM contracts to define the trading range.
        # trading_range = (atm_put.strike + 3, atm_call.strike - 3)
        # Filter the option chain to only select contracts that are within the trading range.
        expiry_spread = sorted([x for x in self._option.chain if x.expiration == expiry and
            trading_range[0] <= x.strike <= trading_range[1]],
            key=lambda x: x.strike)
        if len(expiry_spread) < 4:
            return
        # Form an Iron Condor strategy using the selected contracts.
        long_call = expiry_spread[1]
        short_call = expiry_spread[0]
        long_put = expiry_spread[-2]
        short_put = expiry_spread[-1]
        # If a position is not open, open an Iron Condor position using the selected contracts.
        if not self.portfolio.options.is_assigned(spread_option=long_call):
            self.combo_market_order([
                self.order(long_call, 1),
                self.order(short_call, -1),
                self.order(long_put, 1),
                self.order(short_put, -1)
            ])
        # If the short strikes are in the money, close the position.
        if self._option.symbol.price < short_put.strike or self._option.symbol.price > short_call.strike:
            self.liquidate(self._option.symbol)
