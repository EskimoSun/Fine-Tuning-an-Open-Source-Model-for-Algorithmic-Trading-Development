from AlgorithmImports import *
from typing import Dict, Optional


class BollingerMeanReversionAlgorithm(QCAlgorithm):
    """Desk reference strategy: Bollinger mean-reversion on SPY (long-only)."""

    def initialize(self) -> None:
        """Set up the algorithm: data, indicators, scheduling, and compliance settings."""
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Compliance: automatic indicator warm-up and seed initial prices
        self.settings.automatic_indicator_warm_up = True

        # Add SPY at daily resolution
        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        # Bollinger Bands: 20-period, 2 standard deviations
        self._bb: BollingerBands = self.bb(
            self.spy.symbol,
            20,
            2,
            moving_average_type=MovingAverageType.SIMPLE,
            resolution=Resolution.DAILY
        )

        # Schedule evaluation once per trading day at 08:00
        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(8, 0),
            self.on_daily_evaluation
        )

    def on_daily_evaluation(self) -> None:
        """Evaluate Bollinger mean-reversion rules once per trading day."""
        if not self._bb.is_ready:
            return

        price: float = self.securities[self.spy.symbol].price
        upper: float = self._bb.upper_band.current.value
        middle: float = self._bb.middle_band.current.value
        lower: float = self._bb.lower_band.current.value

        # Plot bands for audit
        self.plot("Bollinger Bands", "Upper", upper)
        self.plot("Bollinger Bands", "Middle", middle)
        self.plot("Bollinger Bands", "Lower", lower)

        invested: bool = self.portfolio[self.spy.symbol].invested

        if not invested and price < lower:
            # Not invested and price below lower band: allocate 100% long
            self.set_holdings(self.spy.symbol, 1.0)
            self.log(f"BUY: price {price:.2f} < lower band {lower:.2f}")
        elif invested and price >= middle:
            # Invested and price at or above middle band: liquidate
            self.liquidate(self.spy.symbol)
            self.log(f"SELL: price {price:.2f} >= middle band {middle:.2f}")

    def on_data(self, slice: Slice) -> None:
        """Update Bollinger Bands indicator with daily data."""
        if self.spy.symbol in slice.bars:
            bar: Bar = slice.bars[self.spy.symbol]
            self._bb.update(bar.end_time, bar.close)
