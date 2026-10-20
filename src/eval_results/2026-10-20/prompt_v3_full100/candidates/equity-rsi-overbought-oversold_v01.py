from AlgorithmImports import *

class RsiMeanReversionAlgorithm(QCAlgorithm):
    """
    A simple RSI-based mean reversion strategy for QQQ.
    Buys when RSI is oversold (< 30) and shorts when RSI is overbought (> 70).
    Uses hourly data.
    """

    def initialize(self):
        # Set start and end dates for backtesting (last few months of 2024)
        self.set_start_date(2024, 7, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add QQQ equity with hourly resolution
        self._qqq = self.add_equity("QQQ", resolution=Resolution.HOUR)

        # Create RSI indicator with period 14 on hourly data
        self._rsi = self.rsi("QQQ", 14, resolution=Resolution.HOUR)

        # Enable automatic warm-up for indicators
        self.settings.automatic_indicator_warm_up = True

        # Thresholds
        self._oversold = 30
        self._overbought = 70

        # Schedule to run logic on each hourly bar
        self.schedule.on(
            self.date_rules.every_day(self._qqq.symbol),
            self.time_rules.every_minute(),
            self.on_hourly_bar
        )

    def on_hourly_bar(self):
        """
        Called every minute, but we only act when a new hourly bar is available.
        """
        if not self._rsi.is_ready:
            return

        current_rsi = self._rsi.current.value
        current_price = self.securities[self._qqq.symbol].price

        # Check if we have a position
        position = self.portfolio[self._qqq.symbol]
        quantity = position.quantity

        # If RSI is oversold and we are not already long, buy
        if current_rsi < self._oversold and quantity <= 0:
            if quantity < 0:
                # Close short position first
                self.liquidate(self._qqq.symbol)
            # Go long
            self.set_holdings(self._qqq.symbol, 1.0)
            self.log(f"BUY signal: RSI={current_rsi:.2f}, Price={current_price:.2f}")

        # If RSI is overbought and we are not already short, short
        elif current_rsi > self._overbought and quantity >= 0:
            if quantity > 0:
                # Close long position first
                self.liquidate(self._qqq.symbol)
            # Go short
            self.set_holdings(self._qqq.symbol, -1.0)
            self.log(f"SHORT signal: RSI={current_rsi:.2f}, Price={current_price:.2f}")

        # Optional: Exit when RSI returns to neutral zone (50)
        elif 45 <= current_rsi <= 55:
            if quantity != 0:
                self.liquidate(self._qqq.symbol)
                self.log(f"EXIT signal: RSI={current_rsi:.2f}, Price={current_price:.2f}")
