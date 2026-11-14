# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # Seed the price of each asset with its last known price to avoid trading errors.
        self.settings.seed_initial_prices = True
        # Set the data normalization mode as raw for option strike-price comparability.
        self._spy = self.add_equity("SPY", data_normalization_mode=DataNormalizationMode.RAW)
        self.schedule.on(self.date_rules.every(DayOfWeek.MONDAY), self.time_rules.after_market_open(self._spy, 1), self._rebalance)

    def _rebalance(self) -> None:
        if not self._spy.options.active_strikes:
            return
        next_friday = (self.time + timedelta(4)).date()
        expiry = min([x.expiry.date() for x in self._spy.options.active_strikes])
        if expiry.date() != next_friday:
            return
        # Filter for contracts expiring on Friday with strikes near the current price.
        atm_calls = [x for x in self._spy.options.active_strikes if x.strike and x.expiry.date() == next_friday and x.right == OptionRight.CALL and abs(self._spy.price - x.strike) <= 1]
        atm_puts = [x for x in self._spy.options.active_strikes if x.strike and x.expiry.date() == next_friday and x.right == OptionRight.PUT and abs(self._spy.price - x.strike) <= 1]
        if not atm_calls or not atm_puts:
            return
        # Select the contracts with the highest open interest for liquidity.
        atm_call = sorted(atm_calls, key=lambda x: x.open_interest)[-1]
        atm_put = sorted(atm_puts, key=lambda x: x.open_interest)[-1]
        # Create an Iron Condor by buying OTM wings and selling ATM wings.
        strike_call = atm_call.strike + 3
        strike_put = atm_put.strike - 3
        # Filter for contracts expiring on Friday with strikes matching the wing strike prices.
        expiry_contracts = [x for x in self._spy.options.active_strikes if x.strike and x.expiry.date() == next_friday]
        if not expiry_contracts:
            return
        # Select the contracts with the highest open interest for liquidity.
        wing_call = sorted([x for x in expiry_contracts if x.strike == strike_call], key=lambda x: x.open_interest)[-1]
        wing_put = sorted([x for x in expiry_contracts if x.strike == strike_put], key=lambda x: x.open_interest)[-1]
        # Check if the algorithm has enough cash to buy the wing contracts.
        cost = wing_call.contract.price + wing_put.contract.price
        if self.portfolio.cash < cost:
            return
        # Remove the ATM contracts to form an Iron Condor.
        self.remove_option(atm_call)
        self.remove_option(atm_put)
        # Buy the OTM wing contracts to form an Iron Condor.
        self.buy(wing_call, 1)
        self.buy(wing_put, 1)
        # Exit the strategy if the market closes without rebalancing.
        self.schedule.on(self.date_rules.every(DayOfWeek.FRIDAY), self.time_rules.before_market_close(self._spy, 5), self._close)

    def _close(self) -> None:
        if self.portfolio.invested:
            self.liquidate()
