# region imports
from AlgorithmImports import *
# endregion

class EquityOpeningRangeBreakoutAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY")
        self._orb = self._orb(self._spy, 30)
        # Alternatively, use a manual indicator.
        # self._orb = ((Minimum(30), Maximum(30)))
        # self.warm_up_indicator(self._spy, self._orb, Resolution.DAILY)
        # self.register_indicator(self._spy, self._orb, Resolution.DAILY)
        self.plot_indicator("ORB", self._orb)

    def _orb(self, equity: Equity, lookback: int) -> IndicatorExtensions.ConsolidatedIndicator:
        bar consolidator = self.consolidate(equity, timedelta(minutes=lookback), self._consolidated_callback)
        min = IndicatorExtensions.of(equity, IndicatorExtensions.MIN, bar consolidator)
        max = IndicatorExtensions.of(equity, IndicatorExtensions.MAX, bar consolidator)
        return IndicatorExtensions.consolidated(min, max, bar consolidator)

    def _consolidated_callback(self, consolidated_bar: ConsolidatedBar) -> None:
        if not self._orb.is_ready:
            return
        open = consolidated_bar.open
        close = consolidated_bar.close
        high = consolidated_bar.high
        low = consolidated_bar.low
        previous_close = self._spy.previous_close
        if not self.portfolio.invested and previous_close > low and previous_close < high:
            if close > high:
                self.set_holdings(self._spy, 1)
            elif close < low:
                self.set_holdings(self._spy, -1)
        self.plot("Trades", "Close", close)
        self.plot("Trades", "Open", open)

    def on_data(self, slice: Slice) -> None:
        self.set_holdings(self._spy, 0)
        if self.time.hour == 15 and self.time.minute == 55:
            self.liquidate()
