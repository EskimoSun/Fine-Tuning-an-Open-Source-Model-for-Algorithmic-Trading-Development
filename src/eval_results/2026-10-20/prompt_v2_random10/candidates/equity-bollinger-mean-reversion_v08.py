from AlgorithmImports import *


class BollingerMeanReversion(QCAlgorithm):
    """
    Bollinger mean-reversion reference on SPY.

    Rules:
      - Not invested and price below the lower band -> allocate 100% long.
      - Invested and price at or above the middle band -> liquidate.

    Evaluation: once per trading day at 08:00 (exchange local time).
    """

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Daily-resolution equity
        self.spy = self.add_equity(
            "SPY",
            resolution=Resolution.DAILY,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
        )

        # Bollinger Bands: 20-period, 2 standard deviations, daily
        self.bb = self.bb(self.spy, 20, 2, resolution=Resolution.DAILY)

        # Evaluate once per trading day at 08:00 exchange local time
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(8, 0, self.spy),
            self.evaluate,
        )

        self.plot("Bollinger Bands", self.bb)

    def evaluate(self):
        """
        Called once per trading day at 08:00.
        Applies the mean-reversion entry/exit rules.
        """
        if not self.bb.is_ready:
            return

        price = self.spy.price
        lower = self.bb.lower_band.current.value
        middle = self.bb.middle_band.current.value

        if not self.portfolio[self.spy].invested:
            # Not invested: enter long if price is below the lower band
            if price < lower:
                self.set_holdings(self.spy, 1.0)
                self.log(f"Entry: price {price:.2f} < lower band {lower:.2f}")
        else:
            # Invested: exit if price is at or above the middle band
            if price >= middle:
                self.liquidate(self.spy)
                self.log(f"Exit: price {price:.2f} >= middle band {middle:.2f}")
