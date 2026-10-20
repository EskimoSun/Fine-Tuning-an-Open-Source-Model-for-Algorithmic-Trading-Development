"""Manual API repair of Qwen output v01; original strategy choices retained."""

from AlgorithmImports import *


class QQQRSIBot(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 7, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self._symbol = self.add_equity("QQQ", Resolution.HOUR).symbol
        self._rsi_period = 14
        self._oversold_level = 30
        self._overbought_level = 70
        self._rsi = self.rsi(
            self._symbol, self._rsi_period, MovingAverageType.WILDERS, Resolution.HOUR
        )
        self._is_long = False
        self._is_short = False
        self.set_warm_up(20 * 24, Resolution.HOUR)

    def on_data(self, data: Slice):
        if self.is_warming_up or not self._rsi.is_ready:
            return
        if not data.bars.contains_key(self._symbol):
            return
        value = self._rsi.current.value
        # Preserve v01's chosen exits at the opposite extreme, including
        # same-bar reversal. The vague prompt does not specify an exit level.
        if self._is_long and value >= self._overbought_level:
            self.liquidate(self._symbol)
            self._is_long = False
        if self._is_short and value <= self._oversold_level:
            self.liquidate(self._symbol)
            self._is_short = False
        if not self._is_long and not self._is_short:
            if value <= self._oversold_level:
                self.set_holdings(self._symbol, 1.0)
                self._is_long = True
            elif value >= self._overbought_level:
                self.set_holdings(self._symbol, -1.0)
                self._is_short = True
