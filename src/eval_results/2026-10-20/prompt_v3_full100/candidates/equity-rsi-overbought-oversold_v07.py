from AlgorithmImports import *


class RsiMeanReversionQqq(QCAlgorithm):
    """Two-sided RSI mean-reversion strategy on QQQ at hourly resolution."""

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.symbol = self.add_equity("QQQ", resolution=Resolution.HOUR).symbol

        # Conventional RSI parameters
        self._rsi = rsi(self.symbol, 14, resolution=Resolution.HOUR)

        # Thresholds
        self._rsi_oversold = 30
        self._rsi_overbought = 70

        # Position sizing: use 100% of portfolio when entering
        self._position_fraction = 1.0

        # Track current position state
        self._in_long = False
        self._in_short = False

    def on_data(self, data: Slice):
        if not self._rsi.is_ready:
            return

        if self.symbol not in data:
            return

        rsi_value = self._rsi.current.value
        price = self.securities[self.symbol].price

        # Exit logic first
        if self._in_long and rsi_value >= 50:
            self.liquidate(self.symbol)
            self._in_long = False
            self.log(f"Exited long at RSI={rsi_value:.2f}, price={price:.2f}")

        if self._in_short and rsi_value <= 50:
            self.liquidate(self.symbol)
            self._in_short = False
            self.log(f"Exited short at RSI={rsi_value:.2f}, price={price:.2f}")

        # Entry logic
        if not self._in_long and not self._in_short:
            if rsi_value <= self._rsi_oversold:
                self.set_holdings(self.symbol, self._position_fraction)
                self._in_long = True
                self.log(f"Entered long at RSI={rsi_value:.2f}, price={price:.2f}")
            elif rsi_value >= self._rsi_overbought:
                self.set_holdings(self.symbol, -self._position_fraction)
                self._in_short = True
                self.log(f"Entered short at RSI={rsi_value:.2f}, price={price:.2f}")
