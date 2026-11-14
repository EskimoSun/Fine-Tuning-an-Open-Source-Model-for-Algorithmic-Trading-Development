# region imports
from AlgorithmImports import *
# endregion

class EquityBollingerBandsMeanReversionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY")
        self._bb = self.bb(self._spy, 20, 2, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._bb = BollingerBands(20, 2)
        # self.warm_up_indicator(self._spy, self._bb, Resolution.DAILY)
        # self.register_indicator(self._spy, self._bb, Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.before_market_open(self._spy, 1), self._rebalance)

    def _rebalance(self) -> None:
        if not self._bb.is_ready:
            return
        price = self._spy.price
        lower = self._bb.lower_band.current.value
        middle = self._bb.middle_band.current.value
        upper = self._bb.upper_band.current.value
        if not self._spy.invested and price < lower:
            self.set_holdings(self._spy, 1)
        elif self._spy.invested and price > middle:
            self.liquidate(self._spy)
