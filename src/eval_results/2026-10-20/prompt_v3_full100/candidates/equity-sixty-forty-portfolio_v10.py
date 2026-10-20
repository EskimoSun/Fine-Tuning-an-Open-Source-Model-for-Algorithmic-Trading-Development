from AlgorithmImports import *


class DriftRebalanceAlgorithm(QCAlgorithm):
    _drift_threshold = 0.05

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.spy = self.add_equity('SPY', resolution=Resolution.MINUTE).symbol
        self.tlt = self.add_equity('TLT', resolution=Resolution.MINUTE).symbol

        self.targets = {self.spy: 0.6, self.tlt: 0.4}
        self._initially_invested = False

        self.schedule.on(
            self.date_rules.quarter_start('SPY'),
            self.time_rules.after_market_open('SPY', 1),
            self._rebalance
        )

    def on_data(self, data: Slice):
        if self._initially_invested:
            return
        if self.portfolio.invested == 0:
            for symbol, target in self.targets.items():
                self.set_holdings(symbol, target)
            self._initially_invested = True

    def _rebalance(self):
        total_value = self.portfolio.total_portfolio_value
        if total_value <= 0:
            return

        weights = {}
        for symbol in self.targets:
            holdings_value = self.portfolio[symbol].holdings_value
            weights[symbol] = holdings_value / total_value

        for symbol, target in self.targets.items():
            if abs(weights[symbol] - target) > self._drift_threshold:
                self.set_holdings([
                    PortfolioTarget(self.spy, 0.6),
                    PortfolioTarget(self.tlt, 0.4)
                ])
                return
