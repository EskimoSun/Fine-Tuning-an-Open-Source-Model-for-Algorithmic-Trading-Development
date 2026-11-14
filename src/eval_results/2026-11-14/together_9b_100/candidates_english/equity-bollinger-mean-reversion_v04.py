# region imports
from AlgorithmImports import *
# endregion

class EquityBBMeanReversionAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY")
        self._bb = self.bb(self._equity, 20, 2, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._bb = BollingerBands(20, 2)
        # self.warm_up_indicator(self._equity, self._bb, Resolution.DAILY)
        # self.register_indicator(self._equity, self._bb, Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day(self._equity), self.time_rules.before_market_close(self._equity, 1), self._rebalance)

    def _rebalance(self) -> None:
        if not self._bb.is_ready:
            return
        price = self._equity.price
        bb_upper = self._bb.upper_band.current.value
        bb_lower = self._bb.lower_band.current.value
        bb_middle = self._bb.middle_band.current.value
        quantity = self._equity.holdings.quantity
        # Buy when price is near the lower band and we are not already long.
        if price < bb_upper * 0.95 and quantity <= 0:
            self.set_holdings(self._equity, 1)
        # Sell when price is near the upper band and we are not already short.
        elif price > bb_lower * 1.05 and quantity >= 0:
            self.liquidate(self._equity)
