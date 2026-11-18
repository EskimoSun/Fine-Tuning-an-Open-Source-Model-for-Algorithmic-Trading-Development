from AlgorithmImports import *


class RsiMeanReversionAlgorithm(QCAlgorithm):
    """Two-sided RSI mean-reversion reference on QQQ at hourly resolution."""

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self._symbol = self.add_equity("QQQ", resolution=Resolution.HOUR).symbol

        self._rsi = rsi(self._symbol, 14, moving_average_type=MovingAverageType.WILDERS, resolution=Resolution.HOUR)

        self._rsi_ready = False

    def on_data(self, slice: Slice):
        if not self._rsi.is_ready:
            return

        if not self._rsi_ready:
            self._rsi_ready = True

        rsi_value = self._rsi.current.value
        position = self.portfolio[self._symbol].quantity

        if position <= 0 and rsi_value < 30:
            self.set_holdings(self._symbol, 1.0)
        elif position > 0 and rsi_value > 50:
            self.liquidate(self._symbol)
        elif position >= 0 and rsi_value > 70:
            self.set_holdings(self._symbol, -1.0)
        elif position < 0 and rsi_value < 50:
            self.liquidate(self._symbol)
