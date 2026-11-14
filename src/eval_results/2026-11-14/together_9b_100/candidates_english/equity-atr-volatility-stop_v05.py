# region imports
from AlgorithmImports import *
# endregion

class EquityTrailingStopTemplateAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._equity = self.add_equity("SPY", Resolution.MINUTE)
        self._equity.trailing_stop = self.trailing_stop(self._equity, 3, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._equity.trailing_stop = TrailStop(3, 3)
        # self.warm_up_indicator(self._equity, self._equity.trailing_stop, Resolution.DAILY)
        # self.register_indicator(self._equity, self._equity.trailing_stop, Resolution.DAILY)

    def on_data(self, data: Slice) -> None:
        if not self._equity.trailing_stop.is_ready:
            return
        # Manage the trailing stop using the helper method.
        self.manage_trailing_stop(self._equity)

    def manage_trailing_stop(self, equity: Equity) -> None:
        if not equity.holdings.invested:
            equity.set_holdings(1, self._equity.trailing_stop)
            return
        # If the price falls below the trailing stop, liquidate the equity.
        if equity.price < equity.holdings.average_purchase_price - equity.trailing_stop.stop_offset:
            equity.liquidate()
