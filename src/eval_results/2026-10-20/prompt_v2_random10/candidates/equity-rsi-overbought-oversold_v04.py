from AlgorithmImports import *

class QQQRSIMeanReversion(QCAlgorithm):
    """
    QQQ RSI Mean-Reversion Strategy
    - Long when RSI(14) < 30 (oversold)
    - Short when RSI(14) > 70 (overbought)
    - Exit long when RSI crosses above 50 (midline)
    - Exit short when RSI crosses below 50 (midline)
    - Hourly resolution
    - Q4 2024
    """

    def initialize(self):
        # Set start and end dates for Q4 2024
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Add QQQ equity with hourly resolution
        self.symbol = self.add_equity("QQQ", Resolution.HOUR, DataNormalizationMode.BACKWARDS_RATIO).symbol

        # RSI indicator with period 14
        self.rsi = self.rsi(self.symbol, 14, Resolution.HOUR, SMAType.SIMPLE)

        # Track position state
        self.is_long = False
        self.is_short = False

        # Schedule to run logic after market open each day
        self.schedule.on(
            self.date_rules.every_day(self.symbol),
            self.time_rules.after_market_open(self.symbol, 1),
            self.on_hourly_bar
        )

    def on_hourly_bar(self):
        """
        Called after market open each day.
        Checks RSI and manages positions.
        """
        if not self.rsi.is_ready:
            return

        rsi_value = self.rsi.current.value

        # Exit logic first
        if self.is_long and rsi_value >= 50:
            self.liquidate(self.symbol)
            self.is_long = False
            self.log(f"Exiting long at RSI={rsi_value:.2f} (crossed midline)")

        if self.is_short and rsi_value <= 50:
            self.liquidate(self.symbol)
            self.is_short = False
            self.log(f"Exiting short at RSI={rsi_value:.2f} (crossed midline)")

        # Entry logic
        if not self.is_long and not self.is_short:
            if rsi_value < 30:
                self.set_holdings(self.symbol, 1.0)
                self.is_long = True
                self.log(f"Entering long at RSI={rsi_value:.2f} (oversold)")
            elif rsi_value > 70:
                self.set_holdings(self.symbol, -1.0)
                self.is_short = True
                self.log(f"Entering short at RSI={rsi_value:.2f} (overbought)")

    def on_data(self, data: Slice):
        """
        Process hourly bars.
        """
        if self.symbol not in data:
            return

        bar = data[self.symbol]
        if bar.is_trade:
            # Update RSI with current price
            self.rsi.update(bar.end_time, bar.close)
