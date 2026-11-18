from AlgorithmImports import *


class DriftRebalanceAlgorithm(QCAlgorithm):
    _drift_threshold = 0.05
    _spy_target = 0.6
    _tlt_target = 0.4
    _start_date = datetime(2022, 1, 1)
    _end_date = datetime(2024, 12, 31)
    _initial_capital = 100_000
    _rebalance_minutes_after_open = 1

    def initialize(self):
        self.set_start_date(self._start_date)
        self.set_end_date(self._end_date)
        self.set_cash(self._initial_capital)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)
        self.tlt = self.add_equity("TLT", resolution=Resolution.MINUTE)

        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, self._rebalance_minutes_after_open),
            self._rebalance
        )

    def on_data(self, data: Slice):
        if self.portfolio.portfolio_value <= 0:
            return
        if not self.spy.symbol.has_data(data) or not self.tlt.symbol.has_data(data):
            return
        if self.portfolio.invested == 0:
            self.set_holdings(self.spy.symbol, self._spy_target)
            self.set_holdings(self.tlt.symbol, self._tlt_target)

    def _rebalance(self):
        total = self.portfolio.portfolio_value
        if total <= 0:
            return
        spy_value = self.portfolio[self.spy.symbol].invested
        tlt_value = self.portfolio[self.tlt.symbol].invested
        spy_weight = spy_value / total
        tlt_weight = tlt_value / total
        if abs(spy_weight - self._spy_target) > self._drift_threshold or abs(tlt_weight - self._tlt_target) > self._drift_threshold:
            self.set_holdings(self.spy.symbol, self._spy_target)
            self.set_holdings(self.tlt.symbol, self._tlt_target)
