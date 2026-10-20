from AlgorithmImports import *

class RsiMeanReversionAlgorithm(QCAlgorithm):
    """
    An RSI-based mean reversion strategy on QQQ.
    Buys when RSI < 30, sells when RSI > 50 (if long),
    shorts when RSI > 70, and covers when RSI < 50 (if short).
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.automatic_indicator_warm_up = True

        self._equity = self.add_equity('QQQ', resolution=Resolution.HOUR)
        self._rsi = self.rsi(self._equity, 14, MovingAverageType.WILDERS, resolution=Resolution.HOUR)
        self.plot_indicator('RSI', self._rsi)

    def on_data(self, data: Slice):
        if not self._rsi.is_ready:
            return

        equity = self._equity
        rsi_value = self._rsi.current.value
        quantity = equity.holdings.quantity

        if quantity <= 0 and rsi_value < 30:
            self.set_holdings(equity, 1)
        elif quantity > 0 and rsi_value > 50:
            self.liquidate(equity)
        elif quantity >= 0 and rsi_value > 70:
            self.set_holdings(equity, -1)
        elif quantity < 0 and rsi_value < 50:
            self.liquidate(equity)
