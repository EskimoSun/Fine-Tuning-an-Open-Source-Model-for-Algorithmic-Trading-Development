# region imports
from AlgorithmImports import *
# endregion

class RsiMeanReversionAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._qqq = self.add_equity("QQQ", Resolution.HOUR)

        self._rsi = self.rsi(self._qqq.symbol, 14, Resolution.HOUR)
        # Alternatively, use a manual indicator.
        # self._rsi = RelativeStrengthIndex(14)
        # self.warm_up_indicator(self._qqq, self._rsi)
        # self.register_indicator(self._qqq, self._rsi)
        self.plot_indicator("RSI", self._rsi)

        self.schedule.on(
            self.date_rules.every_day(self._qqq.symbol),
            self.time_rules.after_market_open(self._qqq.symbol, 30),
            self._check_rsi
        )

    def _check_rsi(self) -> None:
        if not self._rsi.is_ready:
            return

        rsi_value = self._rsi.current.value
        quantity = self._qqq.holdings.quantity

        # Buy when RSI < 30 and we don't have a large buy敞口
        if rsi_value < 30 and quantity > -2:
            self.set_holdings(self._qqq.symbol, 1)

        # Exit long when RSI > 70
        elif quantity > 0 and rsi_value > 70:
            self.liquidate(self._qqq.symbol)

        # Cover short when RSI < 30
        elif quantity < 0 and rsi_value < 30:
            self.liquidate(self._qqq.symbol)
