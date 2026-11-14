# region imports
from AlgorithmImports import *
# endregion

class OneBarOptionStrategy(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True
        self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol
        self._orb = OneBarOption(self._spy)
        # Warm up so the indicator is ready to use.
        self.warm_up(self._orb, self._spy, Resolution.DAILY)

    def on_data(self, data: Slice) -> None:
        bar = data.bars.get(self._spy)
        if not bar:
            return
        # Update the indicator with the current bar.
        self._orb.update(bar)
        # Create the option chain with the indicator as the pivot.
        chain = self.option_chain(self._spy, self._orb)
        if not chain:
            return
        # Buy a call if the price is above the pivot high.
        if chain.call and chain.call.strike < bar.close:
            self.set_holdings(self._spy, 1)
        # Buy a put if the price is below the pivot low.
        elif chain.put and chain.put.strike > bar.close:
            self.set_holdings(self._spy, -1)

    def on_warmup_finished(self) -> None:
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.at(15, 55), self._liquidate)

    def _liquidate(self) -> None:
        if self.portfolio.invested:
            self.liquidate(self._spy)
