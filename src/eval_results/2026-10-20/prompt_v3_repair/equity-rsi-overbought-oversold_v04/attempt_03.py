from AlgorithmImports import *

class QQQRSIMeanReversion(QCAlgorithm):
    """
    QQQ RSI Mean-Reversion Strategy
    - Long when RSI < 30 (oversold)
    - Short when RSI > 70 (overbought)
    - Exit at RSI midline (50)
    - Hourly resolution
    - Backtest period: Q4 2024 (Oct 1 - Dec 31, 2024)
    """

    def initialize(self):
        # Set backtest period: Q4 2024
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Add QQQ equity with hourly resolution
        self._qqq = self.add_equity("QQQ", resolution=Resolution.HOUR)

        # RSI indicator with period 14
        self._rsi = self.rsi(self._qqq.symbol, 14, resolution=Resolution.HOUR)

        # Position state
        self._is_long = False
        self._is_short = False

        # Schedule hourly checks
        self.schedule.on(
            self.date_rules.every_day(self._qqq.symbol),
            self.time_rules.at(9, 30),  # Start after market open
            self.on_hourly_bar
        )

        # Also check at each hour boundary
        for hour in range(10, 16):  # 10:00 to 15:00
            self.schedule.on(
                self.date_rules.every_day(self._qqq.symbol),
                self.time_rules.at(hour, 0),
                self.on_hourly_bar
            )

    def on_hourly_bar(self):
        """Check RSI and manage positions on each hourly bar."""
        if not self._rsi.is_ready:
            return

        rsi_value = self._rsi.current.value
        price = self.securities[self._qqq.symbol].price

        # Exit conditions: RSI crosses midline (50)
        if self._is_long and rsi_value >= 50:
            self.liquidate(self._qqq.symbol)
            self._is_long = False
            self.log(f"Long exit at RSI={rsi_value:.2f}, Price={price:.2f}")
            return

        if self._is_short and rsi_value <= 50:
            self.liquidate(self._qqq.symbol)
            self._is_short = False
            self.log(f"Short exit at RSI={rsi_value:.2f}, Price={price:.2f}")
            return

        # Entry conditions
        if not self._is_long and not self._is_short:
            if rsi_value < 30:
                # Go long
                self.set_holdings(self._qqq.symbol, 1.0)
                self._is_long = True
                self.log(f"Long entry at RSI={rsi_value:.2f}, Price={price:.2f}")
            elif rsi_value > 70:
                # Go short
                self.set_holdings(self._qqq.symbol, -1.0)
                self._is_short = True
                self.log(f"Short entry at RSI={rsi_value:.2f}, Price={price:.2f}")

    def on_data(self, data: Slice):
        """Update RSI indicator with each data point."""
        if self._qqq.symbol in data:
            bar = data[self._qqq.symbol]
            if bar is not None:
                self._rsi.update(bar)
