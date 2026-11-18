from AlgorithmImports import *

class QQQRSIHourly(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.settings.automatic_indicator_warm_up = True
        self._symbol = self.add_equity("QQQ", resolution=Resolution.HOUR).symbol
        self._rsi = rsi(self._symbol, 14, moving_average_type=MovingAverageType.WILDERS, resolution=Resolution.HOUR)
        self.set_plot("RSI", self._rsi, "RSI")

    def on_data(self, data: Slice):
        if not self._rsi.is_ready:
            return
        if self._symbol not in data:
            return
        rsi_value = self._rsi.current.value
        if rsi_value < 30:
            self.set_holdings(self._symbol, 1.0)
        elif rsi_value > 50:
            self.liquidate(self._symbol)
        if rsi_value > 70:
            self.set_holdings(self._symbol, -1.0)
        elif rsi_value < 50:
            self.liquidate(self._symbol)
