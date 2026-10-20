from AlgorithmImports import *
from typing import Optional, Dict


class OpeningRangeBreakoutAlgorithm(QCAlgorithm):
    """Opening-range breakout reference strategy on SPY.

    Captures the 09:30-10:00 opening range, enters long/short on the first
    minute close that breaks the range after 10:00, and liquidates at 15:55
    each trading day. No overnight positions, no leverage beyond 100% notional.
    """

    def initialize(self) -> None:
        """Initialize the algorithm: data, capital, scheduling, and state."""
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Seed initial prices so the first bar is available immediately.
        self.set_fill_forward(True)

        # Add SPY at minute resolution.
        self.spy: Security = self.add_equity(
            "SPY",
            resolution=Resolution.MINUTE,
            fill_forward=True,
        )

        # State for the opening range.
        self._range_high: Optional[float] = None
        self._range_low: Optional[float] = None
        self._range_captured: bool = False
        self._entered_today: bool = False
        self._trade_direction: int = 0  # 1 = long, -1 = short, 0 = flat

        # Plotting series for audit.
        self._plot_range_high: Dict[str, float] = {}
        self._plot_range_low: Dict[str, float] = {}
        self._plot_direction: Dict[str, int] = {}

        # Schedule: capture range at 10:00, check breakout every minute after,
        # liquidate at 15:55.
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(10, 0),
            self._capture_range,
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(10, 1),
            self._check_breakout,
        )
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(15, 55),
            self._liquidate_and_reset,
        )

    def on_data(self, slice: Slice) -> None:
        """Process minute bars: accumulate range, check breakout, plot."""
        if self.spy not in slice.bars:
            return

        bar: Bar = slice.bars[self.spy]
        if not bar.is_traded:
            return

        current_time: datetime = bar.end_time
        current_date: date = current_time.date()

        # Accumulate range bars from 09:30 to 10:00 (inclusive of 09:30, exclusive of 10:00).
        if (
            not self._range_captured
            and current_time.hour == 9
            and current_time.minute >= 30
        ):
            if self._range_high is None or bar.high > self._range_high:
                self._range_high = bar.high
            if self._range_low is None or bar.low < self._range_low:
                self._range_low = bar.low

        # Check for breakout after 10:00 if range is captured and no entry yet.
        if (
            self._range_captured
            and not self._entered_today
            and current_time.hour >= 10
        ):
            self._check_breakout()

        # Plot range bounds and trade direction for audit.
        if self._range_high is not None:
            self._plot_range_high[current_date] = self._range_high
        if self._range_low is not None:
            self._plot_range_low[current_date] = self._range_low
        self._plot_direction[current_date] = self._trade_direction

    def _capture_range(self) -> None:
        """Finalize the opening range at 10:00."""
        if self._range_high is not None and self._range_low is not None:
            self._range_captured = True
            self.log(
                f"Opening range captured: high={self._range_high:.4f}, "
                f"low={self._range_low:.4f}"
            )

    def _check_breakout(self) -> None:
        """Check if the current close breaks the opening range."""
        if not self._range_captured or self._entered_today:
            return

        if self.spy not in self.securities:
            return

        current_price: float = self.securities[self.spy].price
        if current_price <= 0:
            return

        if current_price > self._range_high:
            # Breakout above: go 100% long.
            self.set_holdings(self.spy, 1.0)
            self._entered_today = True
            self._trade_direction = 1
            self.log(
                f"Breakout above range high {self._range_high:.4f} at "
                f"{current_price:.4f}. Entering 100% long."
            )
        elif current_price < self._range_low:
            # Breakout below: go 100% short.
            self.set_holdings(self.spy, -1.0)
            self._entered_today = True
            self._trade_direction = -1
            self.log(
                f"Breakout below range low {self._range_low:.4f} at "
                f"{current_price:.4f}. Entering 100% short."
            )

    def _liquidate_and_reset(self) -> None:
        """Liquidate all positions at 15:55 and reset daily state."""
        if self.spy in self.portfolio and self.portfolio[self.spy].quantity != 0:
            self.liquidate(self.spy)
            self.log(
                f"Liquidated SPY position at 15:55. "
                f"Direction was {self._trade_direction}."
            )

        # Reset range and entry state for the next trading day.
        self._range_high = None
        self._range_low = None
        self._range_captured = False
        self._entered_today = False
        self._trade_direction = 0

    def on_end_of_algorithm(self) -> None:
        """Plot accumulated audit data at the end of the algorithm."""
        if self._plot_range_high:
            dates = sorted(self._plot_range_high.keys())
            highs = [self._plot_range_high[d] for d in dates]
            self.plot("Range High", dates, highs)

        if self._plot_range_low:
            dates = sorted(self._plot_range_low.keys())
            lows = [self._plot_range_low[d] for d in dates]
            self.plot("Range Low", dates, lows)

        if self._plot_direction:
            dates = sorted(self._plot_direction.keys())
            directions = [self._plot_direction[d] for d in dates]
            self.plot("Trade Direction", dates, directions)
