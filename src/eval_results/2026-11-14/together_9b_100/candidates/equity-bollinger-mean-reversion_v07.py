# region imports
from AlgorithmImports import *
# endregion

class EquityBollingerBandMeanReversionAlgorithm(QCAlgorithm):

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

    def on_data(self, data: Slice) -> None:
        if not self._bb.is_ready:
            return
        # BB mid-band = SMA 20; buy when price near lower band, sell when near upper band.
        price = self._equity.price
        lower = self._bb.lower_band.current.value
        upper = self._bb.upper_band.current.value
        if not self._equity.holdings.invested and price < lower * 0.995:
            self.set_holdings(self._equity, 1)
        elif self._equity.holdings.invested and price > upper * 1.005:
            self.liquidate()
