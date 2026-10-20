from AlgorithmImports import *


class RsiBot(QCAlgorithm):
    """
    QQQ RSI mean-reversion bot on 1-hour candles.

    Rules:
    - Long entry:  RSI(14, Wilder) crosses below 30 -> buy with 100% of portfolio.
    - Long exit:   RSI crosses above 50 while long -> liquidate.
    - Short entry: RSI crosses above 70 -> short with 100% of portfolio.
    - Short exit:  RSI crosses below 50 while short -> buy back (liquidate).
    """

    def initialize(self):
        # Set start/end dates and starting cash
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Use 1-hour resolution for QQQ
        self._qqq = self.add_equity("QQQ", resolution=Resolution.HOUR)

        # Enable automatic indicator warm-up so we don't trade before RSI is ready
        self.settings.automatic_indicator_warm_up = True

        # Create the 14-period Wilder RSI indicator
        self._rsi = self.rsi("QQQ", 14, moving_average_type=MovingAverageType.WILDERS, resolution=Resolution.HOUR)

        # Track previous RSI value to detect crossovers
        self._prev_rsi = None

        # Plot RSI on a chart for visual inspection
        self._rsi_plot = self.add_plot("RSI")
        self._rsi_plot.add_plot_series("RSI(14)", "rsi", "#FF0000")

    def on_data(self, data: Slice):
        # Only process when QQQ has data in this slice
        if not data.contains(self._qqq.symbol):
            return

        # Don't trade until the RSI indicator has enough data to be reliable
        if not self._rsi.is_ready:
            return

        current_rsi = self._rsi.current.value

        # Plot the current RSI value
        self._rsi_plot.plot(self._qqq.symbol, current_rsi)

        # Detect crossovers using the previous RSI value
        if self._prev_rsi is not None:
            # Rule 1: Long entry - RSI crosses below 30 (oversold)
            if self._prev_rsi >= 30 and current_rsi < 30:
                # Check if we are not already long
                if self.portfolio[self._qqq.symbol].quantity <= 0:
                    self.set_holdings(self._qqq.symbol, 1.0)
                    self.log(f"LONG ENTRY: RSI crossed below 30 (prev={self._prev_rsi:.2f}, curr={current_rsi:.2f})")

            # Rule 2: Long exit - RSI crosses above 50 while long
            elif self._prev_rsi <= 50 and current_rsi > 50:
                if self.portfolio[self._qqq.symbol].quantity > 0:
                    self.liquidate(self._qqq.symbol)
                    self.log(f"LONG EXIT: RSI crossed above 50 (prev={self._prev_rsi:.2f}, curr={current_rsi:.2f})")

            # Rule 3: Short entry - RSI crosses above 70 (overbought)
            if self._prev_rsi <= 70 and current_rsi > 70:
                # Check if we are not already short
                if self.portfolio[self._qqq.symbol].quantity >= 0:
                    self.set_holdings(self._qqq.symbol, -1.0)
                    self.log(f"SHORT ENTRY: RSI crossed above 70 (prev={self._prev_rsi:.2f}, curr={current_rsi:.2f})")

            # Rule 4: Short exit - RSI crosses below 50 while short
            elif self._prev_rsi >= 50 and current_rsi < 50:
                if self.portfolio[self._qqq.symbol].quantity < 0:
                    self.liquidate(self._qqq.symbol)
                    self.log(f"SHORT EXIT: RSI crossed below 50 (prev={self._prev_rsi:.2f}, curr={current_rsi:.2f})")

        # Update previous RSI for next bar
        self._prev_rsi = current_rsi
