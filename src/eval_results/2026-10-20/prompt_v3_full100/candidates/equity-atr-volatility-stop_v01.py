from AlgorithmImports import *

class AtrReentryAlgorithm(QCAlgorithm):
    """
    Always hold SPY, but sell if price drops more than 2*ATR(14) below the 20-day high.
    Buy back immediately when price recovers to within 0.5*ATR of the 20-day high.
    """

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY at daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Indicators
        self._atr = self.atr("SPY", 14, resolution=Resolution.DAILY)
        self._sma_high = self.sma("SPY", 20, resolution=Resolution.DAILY)

        # State
        self._in_position = False
        self._sell_threshold = 2.0   # sell if price < high - 2*ATR
        self._buy_threshold = 0.5    # buy back if price > high - 0.5*ATR

        # Schedule daily check after market close
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.at(16, 30),
            self.on_daily_check
        )

    def on_daily_check(self):
        if not self._atr.is_ready or not self._sma_high.is_ready:
            return

        price = self.securities[self.spy].price
        atr_value = self._atr.current.value
        high_20 = self._sma_high.current.value  # Using SMA as proxy for recent high level

        # For a true "recent high" we'd need a rolling max, but SMA(20) is a reasonable
        # smoothed reference. Alternatively, we can track the 20-day high manually.
        # Let's use a proper rolling high instead.
        # We'll compute the 20-day high from the security's history.
        history = self.history(self.spy, 20, Resolution.DAILY)
        if len(history) < 20:
            return

        recent_high = max(bar.close for bar in history)

        if not self._in_position:
            # Check if we should buy back
            if price >= recent_high - self._buy_threshold * atr_value:
                self.set_holdings(self.spy, 1.0)
                self._in_position = True
                self.log(f"BUY BACK SPY at {price:.2f}, recent_high={recent_high:.2f}, ATR={atr_value:.2f}")
        else:
            # Check if we should sell
            if price <= recent_high - self._sell_threshold * atr_value:
                self.liquidate(self.spy)
                self._in_position = False
                self.log(f"SELL SPY at {price:.2f}, recent_high={recent_high:.2f}, ATR={atr_value:.2f}")

    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.FILLED:
            if order_event.symbol == self.spy:
                if order_event.direction == OrderDirection.BUY:
                    self._in_position = True
                elif order_event.direction == OrderDirection.SELL:
                    self._in_position = False
