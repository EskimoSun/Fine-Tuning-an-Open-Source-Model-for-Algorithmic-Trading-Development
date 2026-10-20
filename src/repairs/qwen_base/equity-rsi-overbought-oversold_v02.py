"""Manual API repair of Qwen output v02; entry/exit thresholds retained."""

from AlgorithmImports import *


class QQQRSIBot(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self._symbol = self.add_equity("QQQ", Resolution.HOUR).symbol
        self._rsi = self.rsi(
            self._symbol, 14, MovingAverageType.WILDERS, Resolution.HOUR
        )
        self._position = 0
        self.set_warm_up(20, Resolution.HOUR)

    def on_data(self, data: Slice):
        if self.is_warming_up or not self._rsi.is_ready:
            return
        if not data.bars.contains_key(self._symbol):
            return
        value = self._rsi.current.value
        if self._position == 0 and value < 30:
            self.liquidate()
            self.set_holdings(self._symbol, 1.0)
            self._position = 1
        elif self._position == 0 and value > 70:
            self.liquidate()
            self.set_holdings(self._symbol, -1.0)
            self._position = -1
        elif self._position == 1 and value > 50:
            self.liquidate()
            self._position = 0
        elif self._position == -1 and value < 50:
            self.liquidate()
            self._position = 0
