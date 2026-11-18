# QuantConnect LEAN Algorithm - Bollinger Mean Reversion on SPY
# Window: 2024-09-01 to 2024-12-31
# Capital: 100,000
# Indicator: Bollinger Bands, 20-period, 2 std devs, daily
# Evaluation: once per trading day at 08:00
# Rules:
#   - Not invested and price < lower band -> 100% long
#   - Invested and price >= middle band -> liquidate

from AlgorithmImports import *

class BollingerMeanReversionAlgorithm(QCAlgorithm):

    def Initialize(self):
        # Set start/end dates
        self.SetStartDate(2024, 9, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(100_000)

        # Add SPY equity
        self.spy = self.AddEquity("SPY", Resolution.DAILY).Symbol

        # Bollinger Bands: 20 period, 2 standard deviations
        self.bb = self.Indicator(self.spy, 20, 20, Resolution.DAILY)

        # Schedule evaluation once per trading day at 08:00
        self.Schedule.On(
            date_rules.EveryDay(),
            time_rules.At(8, 0),
            Action(self.OnDailyEvaluation)
        )

    def OnDailyEvaluation(self):
        # Ensure indicator is ready
        if not self.bb.IsReady:
            return

        # Get current price (use the close of the most recent daily bar)
        price = self.Securities[self.spy].Price

        lower_band = self.bb.LowerBand
        middle_band = self.bb.MidPoint

        # Rule 1: Not invested and price below lower band -> go 100% long
        if not self.Portfolio[self.spy].Invested and price < lower_band:
            self.SetHoldings(self.spy, 1.0)
            self.Debug(f"BUY: Price {price:.2f} < Lower Band {lower_band:.2f}")

        # Rule 2: Invested and price at or above middle band -> liquidate
        elif self.Portfolio[self.spy].Invested and price >= middle_band:
            self.Liquidate(self.spy)
            self.Debug(f"SELL: Price {price:.2f} >= Middle Band {middle_band:.2f}")
