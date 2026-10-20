"""
ATR Chandelier Stop reference strategy on SPY.

Desk reference implementation:
- Minute resolution, 2022-01-01 to 2024-12-31, $100,000 capital.
- ATR(14) with automatic warm-up; no signals before ATR is ready.
- When flat: allocate 100% long, set trailing high to entry close.
- Update trailing high with each higher close.
- Stop level = trailing high - 3 * ATR.
- If a close falls below the stop: liquidate, then re-enter 100% on the next bar and reset trailing high.
- Compliance: plot stop level and trailing high for audit; snake_case API; type annotations; no leverage; no short positions.
"""

from typing import Optional
from QuantConnect import *
from QuantConnect.Algorithm import *
from QuantConnect.Data import *
from QuantConnect.Indicators import *


class AtrChandelierStopAlgorithm(QCAlgorithm):
    """ATR chandelier stop reference strategy on SPY."""

    # --- Configuration ---
    SYMBOL: str = "SPY"
    ATR_PERIOD: int = 14
    ATR_MULTIPLIER: float = 3.0
    START_DATE: datetime = datetime(2022, 1, 1)
    END_DATE: datetime = datetime(2024, 12, 31)
    CAPITAL: float = 100_000.0

    # --- State ---
    _atr: ATR
    _trailing_high: float
    _stop_level: float
    _is_long: bool
    _pending_reentry: bool
    _entry_close: float

    def initialize(self) -> None:
        """Initialize the algorithm: set up data, indicators, and state."""
        # Set resolution and date range
        self.set_start_date(self.START_DATE)
        self.set_end_date(self.END_DATE)
        self.set_cash(self.CAPITAL)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS, AccountType.MARGIN)

        # Add equity data at minute resolution
        self.spy = self.add_equity(
            self.SYMBOL,
            resolution=Resolution.MINUTE,
            data_provider=DataProvider.DEFAULT,
            fill_forward=True,
            extended_market_hours=False
        ).symbol

        # ATR indicator with automatic warm-up
        self._atr = self.ATR(self.SYMBOL, self.ATR_PERIOD, MovingAverageType.WILDERS)

        # Initialize state
        self._trailing_high: float = 0.0
        self._stop_level: float = 0.0
        self._is_long: bool = False
        self._pending_reentry: bool = False
        self._entry_close: float = 0.0

        # Plot series for audit
        self.plot("Chandelier Stop", "Stop Level", self._stop_level)
        self.plot("Chandelier Stop", "Trailing High", self._trailing_high)

    def on_data(self, slice: Slice) -> None:
        """Process each minute bar."""
        # Check if ATR is ready
        if not self._atr.is_ready:
            return

        # Get the current bar for SPY
        if self.SYMBOL not in slice.bars:
            return

        bar: Bar = slice.bars[self.SYMBOL]
        close: float = bar.close
        atr_value: float = self._atr.current.value

        # If we are pending reentry, execute it on this bar
        if self._pending_reentry:
            self._pending_reentry = False
            self._enter_long(close)
            return

        # If we are long, update trailing high and check stop
        if self._is_long:
            # Update trailing high with each higher close
            if close > self._trailing_high:
                self._trailing_high = close

            # Compute stop level
            self._stop_level = self._trailing_high - self.ATR_MULTIPLIER * atr_value

            # Check if close falls below stop
            if close < self._stop_level:
                self._liquidate()
                self._pending_reentry = True
                return

        # If flat and not pending reentry, enter long
        if not self._is_long and not self._pending_reentry:
            self._enter_long(close)

    def _enter_long(self, close: float) -> None:
        """Enter a 100% long position and initialize trailing high."""
        # Calculate quantity: 100% of portfolio value at current price
        portfolio_value: float = self.portfolio.total_value
        quantity: int = int(portfolio_value / close)

        if quantity <= 0:
            return

        # Place market order
        self.set_holdings(self.SYMBOL, 1.0)

        # Update state
        self._is_long = True
        self._trailing_high = close
        self._entry_close = close
        self._stop_level = self._trailing_high - self.ATR_MULTIPLIER * self._atr.current.value

    def _liquidate(self) -> None:
        """Liquidate the long position."""
        self.set_holdings(self.SYMBOL, 0.0)
        self._is_long = False
        self._trailing_high = 0.0
        self._stop_level = 0.0
        self._entry_close = 0.0


# Entry point
if __name__ == "__main__":
    algorithm = AtrChandelierStopAlgorithm()
    algorithm.run()
