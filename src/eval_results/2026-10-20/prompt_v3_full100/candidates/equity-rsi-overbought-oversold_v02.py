from AlgorithmImports import *

class QQQRSIBot(QCAlgorithm):
    """
    QQQ RSI mean-reversion bot on 1-hour candles.
    - Long when RSI(14) < 30, exit long when RSI > 50.
    - Short when RSI(14) > 70, exit short when RSI < 50.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add QQQ at 1-hour resolution
        self._qqq = self.add_equity("QQQ", resolution=Resolution.HOUR)

        # RSI indicator with 14 periods
        self._rsi = self.rsi("QQQ", 14, resolution=Resolution.HOUR)

        # Track position state
        self._is_long = False
        self._is_short = False

    def on_data(self, data: Slice):
        if not self._rsi.is_ready:
            return

        if "QQQ" not in data:
            return

        rsi_value = self._rsi.current.value

        # Exit long if RSI > 50
        if self._is_long and rsi_value > 50:
            self.liquidate("QQQ")
            self._is_long = False
            self.Log(f"Exited long at RSI={rsi_value:.2f}")

        # Exit short if RSI < 50
        if self._is_short and rsi_value < 50:
            self.liquidate("QQQ")
            self._is_short = False
            self.Log(f"Exited short at RSI={rsi_value:.2f}")

        # Enter long if RSI < 30 and not already in a position
        if not self._is_long and not self._is_short and rsi_value < 30:
            self.set_holdings("QQQ", 1.0)
            self._is_long = True
            self.Log(f"Entered long at RSI={rsi_value:.2f}")

        # Enter short if RSI > 70 and not already in a position
        if not self._is_long and not self._is_short and rsi_value > 70:
            self.set_holdings("QQQ", -1.0)
            self._is_short = True
            self.Log(f"Entered short at RSI={rsi_value:.2f}")
