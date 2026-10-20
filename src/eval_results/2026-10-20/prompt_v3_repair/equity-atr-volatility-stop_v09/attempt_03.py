from AlgorithmImports import *
from typing import Optional


class AtrChandelierStopAlgorithm(QCAlgorithm):
    """ATR chandelier stop reference strategy on SPY (long-only, 100% allocation)."""

    def initialize(self) -> None:
        """Initialize the algorithm: data, capital, warm-up, indicators, and scheduling."""
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Automatic indicator warm-up so ATR is ready before the first signal
        self.settings.automatic_indicator_warm_up = True

        # Add SPY at minute resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # ATR indicator, 14 periods
        self._atr: ATR = self.atr("SPY", 14, resolution=Resolution.MINUTE)

        # Strategy state
        self._trailing_high: Optional[float] = None
        self._stop_level: Optional[float] = None
        self._is_long: bool = False
        self._pending_reentry: bool = False

        # Plotting series for audit
        self.add_series("Chandelier Stop", "Trailing High", SeriesType.LINE)
        self.add_series("Chandelier Stop", "Stop Level", SeriesType.LINE)

    def on_data(self, slice: Slice) -> None:
        """Process each minute bar: update trailing high, stop, and execute exits/entries."""
        if "SPY" not in slice:
            return

        bar = slice["SPY"]
        if not isinstance(bar, TradeBar):
            return

        # No signals before ATR is ready
        if not self._atr.is_ready:
            return

        atr_value: float = self._atr.current.value
        close: float = bar.close

        # Update trailing high if we are long
        if self._is_long:
            if self._trailing_high is None or close > self._trailing_high:
                self._trailing_high = close

            # Compute stop level
            self._stop_level = self._trailing_high - 3.0 * atr_value

            # Check if close falls below stop -> liquidate
            if close < self._stop_level:
                self.liquidate("SPY")
                self._is_long = False
                self._trailing_high = None
                self._stop_level = None
                # Re-entry will happen on the next bar
                self._pending_reentry = True
                return

        # If flat and not pending reentry, enter 100% long
        if not self._is_long and not self._pending_reentry:
            self._enter_long(close)
            return

        # If pending reentry, enter on this bar
        if self._pending_reentry:
            self._pending_reentry = False
            self._enter_long(close)
            return

        # Plot for audit
        self._update_plots(bar, close)

    def _enter_long(self, close: float) -> None:
        """Enter 100% long position and initialize trailing high."""
        self.set_holdings("SPY", 1.0)
        self._is_long = True
        self._trailing_high = close
        self._stop_level = self._trailing_high - 3.0 * self._atr.current.value

    def _update_plots(self, bar: TradeBar, close: float) -> None:
        """Update plot series for trailing high and stop level."""
        if self._trailing_high is not None:
            self.plot("Chandelier Stop", "Trailing High", bar.end_time, self._trailing_high)
        if self._stop_level is not None:
            self.plot("Chandelier Stop", "Stop Level", bar.end_time, self._stop_level)
