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
        self._plot_trailing_high: Optional[PlotSeries] = None
        self._plot_stop_level: Optional[PlotSeries] = None

        # Schedule a daily check at market open to handle re-entry logic
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.at(9, 31),
            self._on_daily_check
        )

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

    def _on_daily_check(self) -> None:
        """Daily check: if flat and ATR ready, ensure we are positioned."""
        if self._is_long:
            return
        if not self._atr.is_ready:
            return
        # If we are flat (not pending reentry), enter
        if not self._pending_reentry:
            price = self.securities["SPY"].price
            if price > 0:
                self._enter_long(price)

    def _update_plots(self, bar: TradeBar, close: float) -> None:
        """Update plot series for trailing high and stop level."""
        if self._plot_trailing_high is None:
            self._plot_trailing_high = self.add_series("Trailing High")
            self._plot_stop_level = self.add_series("Stop Level")

        if self._trailing_high is not None:
            self._plot_trailing_high.plot(bar.end_time, self._trailing_high)
        if self._stop_level is not None:
            self._plot_stop_level.plot(bar.end_time, self._stop_level)
