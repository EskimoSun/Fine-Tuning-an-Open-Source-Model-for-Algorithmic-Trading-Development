"""Manual API/event repair of v04. Uses hourly data instead of a daily schedule.

The generated simple-average RSI calculation, Q4 dates, sizing and thresholds
are retained. This is a repaired experiment, not an unmodified model output.
"""

from AlgorithmImports import *


class QQQRSIMeanReversion(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self._symbol = self.add_equity("QQQ", Resolution.HOUR).symbol
        self._rsi_period = 14
        self._oversold_level = 30
        self._overbought_level = 70
        self._midline = 50
        self._in_position = False
        self._position_side = None

    def on_data(self, data: Slice):
        if self.is_warming_up or not data.bars.contains_key(self._symbol):
            return
        # Typed history returns TradeBars; untyped history returns a DataFrame.
        bars = list(self.history[TradeBar](
            self._symbol, self._rsi_period + 1, Resolution.HOUR
        ))
        value = self._calculate_rsi(bars, self._rsi_period)
        if value is None:
            return
        if self._in_position:
            if self._position_side == "long" and value >= self._midline:
                self.liquidate(self._symbol)
                self._in_position = False
                self._position_side = None
            elif self._position_side == "short" and value <= self._midline:
                self.liquidate(self._symbol)
                self._in_position = False
                self._position_side = None
        elif value < self._oversold_level:
            self.set_holdings(self._symbol, 1.0)
            self._in_position = True
            self._position_side = "long"
        elif value > self._overbought_level:
            self.set_holdings(self._symbol, -1.0)
            self._in_position = True
            self._position_side = "short"

    def _calculate_rsi(self, bars, period):
        if len(bars) < period + 1:
            return None
        closes = [bar.close for bar in bars]
        changes = [b - a for a, b in zip(closes, closes[1:])]
        avg_gain = sum(max(change, 0) for change in changes[:period]) / period
        avg_loss = sum(max(-change, 0) for change in changes[:period]) / period
        if avg_loss == 0:
            return 100.0
        return 100 - 100 / (1 + avg_gain / avg_loss)

    def on_end_of_algorithm(self):
        if self._in_position:
            self.liquidate(self._symbol)
