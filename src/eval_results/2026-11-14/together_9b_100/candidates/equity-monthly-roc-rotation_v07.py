# region imports
from AlgorithmImports import *
# endregion


class EFAEMAQLongOnlyAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(200_000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        # Trade multiple asset classes.
        tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        for ticker in tickers:
            # Add the ETF with its universe filter and its selection function.
            equity = self.add_equity(ticker)
            equity.universe_filter = self.universe.etf(ticker)
            # Create an EMA indicator for the equity.
            equity.indicator = self.ema(ticker, 63, Resolution.DAILY)
            # Alternatively, use a manual indicator.
            # equity.indicator = ExponentialMovingAverage(63)
            # self.warm_up_indicator(equity, equity.indicator, Resolution.DAILY)
            # self.register_indicator(equity, equity.indicator, Resolution.DAILY)

    def on_data(self, data: Slice) -> None:
        # Wait for indicators to be ready and have at least 2 days of data.
        if not all([equity.indicator.is_ready for equity in self._equities.values()]):
            return
        # Select the equity with the highest EMA value.
        top_equity = max(self._equities.keys(), key=lambda ticker: self._equities[ticker].indicator.current.value)
        # If the top equity is different from the previous top, trade.
        if not self.portfolio[top_equity].is_long and self.portfolio[self._previous_top_equity].is_long:
            self.set_holdings([PortfolioTarget(top_equity, 1.0)])
        self._previous_top_equity = top_equity
