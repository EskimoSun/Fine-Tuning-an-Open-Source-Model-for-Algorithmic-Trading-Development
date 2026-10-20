from AlgorithmImports import *
from typing import Optional


class AtrChandelierStopAlgorithm(QCAlgorithm):
    """
    ATR Chandelier Stop reference strategy on SPY.

    Rules:
    - When flat, allocate 100% long and set the trailing high to the entry close.
    - Update the trailing high with each higher close.
    - Stop level is trailing high minus 3 times ATR.
    - If a close falls below the stop, liquidate, then re-enter 100% on the next bar and reset the trailing high.
    """

    def initialize(self) -> None:
        """Initialize the algorithm with SPY equity, ATR indicator, and scheduling."""
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY equity at minute resolution
        self.spy = self.add_equity("SPY", Resolution.MINUTE, DataNormalizationMode.BACKWARDS_RATIO)

        # ATR indicator with 14 periods
        self.atr: ATR = self.atr(self.spy, 14, MovingAverageType.WILDERS, Resolution.MINUTE)

        # State variables
        self.trailing_high: Optional[float] = None
        self.stop_level: Optional[float] = None
        self.pending_reentry: bool = False

        # Plotting
        self.plot("Chandelier Stop", "Trailing High", "Stop Level")

        # Schedule logic on each minute bar
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.every_bar(),
            self.on_bar
        )

    def on_bar(self, bar: Bar) -> None:
        """
        Process each minute bar for the chandelier stop logic.
        """
        # No signals before ATR is ready
        if not self.atr.is_ready:
            return

        current_close: float = bar.close
        current_atr: float = self.atr.current.value

        # If we are pending reentry, execute it now
        if self.pending_reentry:
            self.pending_reentry = False
            self.set_holdings(self.spy, 1.0)
            self.trailing_high = current_close
            self.stop_level = self.trailing_high - 3.0 * current_atr
            self.log(f"Re-entered long SPY at {current_close:.2f}, trailing high: {self.trailing_high:.2f}, stop: {self.stop_level:.2f}")
            return

        # If flat and not pending reentry, enter long
        if not self.portfolio[self.spy].invested:
            self.set_holdings(self.spy, 1.0)
            self.trailing_high = current_close
            self.stop_level = self.trailing_high - 3.0 * current_atr
            self.log(f"Entered long SPY at {current_close:.2f}, trailing high: {self.trailing_high:.2f}, stop: {self.stop_level:.2f}")
            return

        # If invested, update trailing high and check stop
        if current_close > self.trailing_high:
            self.trailing_high = current_close

        self.stop_level = self.trailing_high - 3.0 * current_atr

        # Check if close falls below stop
        if current_close < self.stop_level:
            self.liquidate(self.spy)
            self.pending_reentry = True
            self.log(f"Stop hit: close {current_close:.2f} < stop {self.stop_level:.2f}. Liquidated, pending reentry.")

        # Plot for audit
        self.plot("Chandelier Stop", "Trailing High", self.trailing_high)
        self.plot("Chandelier Stop", "Stop Level", self.stop_level)
