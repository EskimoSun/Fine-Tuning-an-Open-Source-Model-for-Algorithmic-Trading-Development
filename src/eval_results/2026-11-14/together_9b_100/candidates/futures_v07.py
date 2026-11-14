# region imports
from AlgorithmImports import *
# endregion

class FutureAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        # Request SPX futures for portfolio filtering and trading.
        self._spx = self.add_future("SPX", "SP")
        # Filter for the continuous Futures contract.
        self._spx.filter(self._spx.CONTRACTS[self._spx.ESPX].symbol, 0, 0, int(self._spx.ESPX.time_span))
        # Filter for the next 3 expiry contracts to trade.
        expiry_symbols = [x.symbol for x in self._spx.get_expiries(3)]
        self._spx.set_filter(expiry_symbols)
        # Create a Scheduled Event to rebalance the portfolio.
        self.schedule.on(self.date_rules.every_day(self._spx.symbol), self.time_rules.after_market_open(self._spx.symbol, 1), self._rebalance)

    def _rebalance(self) -> None:
        if not self.portfolio.invested:
            self.set_holdings(self._spx.symbol, 1)
