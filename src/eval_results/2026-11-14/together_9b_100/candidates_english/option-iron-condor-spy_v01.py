# region imports
from AlgorithmImports import *
# endregion

class EquityOptionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(500000)
        # Subscribe to the underlying Equity.
        self._spy = self.add_equity("SPY")
        # Create the Option chain for the subscribed Equity.
        self._chain = self.option_chain(self._spy)
        # Filter the Option contracts to only select 0DTE contracts.
        # Then, sort the filtered contracts by their strike prices.
        self._calls = sorted([x for x in self._chain if x.right == OptionRight.CALL and x.expiry == self._spy.expiry + timedelta(0)], key=lambda x: x.strike)
        self._puts = sorted([x for x in self._chain if x.right == OptionRight.PUT and x.expiry == self._spy.expiry + timedelta(0)], key=lambda x: x.strike)
        # Filter the Option contracts that have strike prices within a certain range of the underlying price.
        # Then, select the contracts with the highest open interest to form a trading strategy.
        self._long_call = self._calls[0]
        self._short_call = self._calls[-1]
        self._long_put = self._puts[0]
        self._short_put = self._puts[-1]
        # Use the generate_strategy method to generate the trading strategy.
        self._strategy = self.generate_strategy(IronCondorStrategy, self._long_call, self._short_call, self._long_put, self._short_put)
        # Use the generate_reminder method to generate a reminder to rebalance the strategy.
        self.schedule.on(self.date_rules.every(DayOfWeek.MONDAY), self.time_rules.before_market_close(self._spy, 1), self._strategy.rebalance)

    def on_data(self, slice: Slice) -> None:
        if not self._strategy.is_ready:
            return
        # Filter the Option contracts that have tradeable volumes.
        expiry = self._spy.expiry + timedelta(0)
        calls = [x for x in slice.option_contracts if x.right == OptionRight.CALL and x.expiry == expiry and x.volume]
        puts = [x for x in slice.option_contracts if x.right == OptionRight.PUT and x.expiry == expiry and x.volume]
        # If there are no new Option contracts with tradeable volumes, the algorithm will hold its current positions.
        if not calls or not puts:
            return
        # Update the Option chain with the new Option contract data.
        self._chain.update(calls, puts)
        # Use the generate_strategy method to generate a new trading strategy with the updated Option contract data.
        self._strategy = self.generate_strategy(IronCondorStrategy, self._chain, self._strategy.long_call, self._strategy.short_call, self._strategy.long_put, self._strategy.short_put)
