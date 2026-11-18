from AlgorithmImports import *

class BollingerRebalanceAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True
        self.settings.automatic_indicator_warm_up = True

        equity = self.add_equity('SPY')
        self._equity = equity

        self._bb = self.bb(equity, 20, 2, resolution=Resolution.DAILY)
        self.plot_indicator('SPY', self._bb.upper_band, self._bb.middle_band, self._bb.lower_band)

        self.schedule.on(self.date_rules.every_day(equity), self.time_rules.at(8, 0), self._rebalance)

    def _rebalance(self):
        if not self.portfolio.invested:
            if self._equity.price < self._bb.lower_band.current.value:
                self.set_holdings(self._equity, 1)
        else:
            if self._equity.price >= self._bb.middle_band.current.value:
                self.liquidate()
