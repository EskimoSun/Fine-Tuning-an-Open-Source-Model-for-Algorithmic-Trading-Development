from AlgorithmImports import *

class OrbBreakoutAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.seed_initial_prices = True

        self.spy = self.add_equity('SPY', resolution=Resolution.MINUTE).symbol

        self._orb_high = None
        self._orb_low = None

        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at(15, 55),
            self._liquidate_eod
        )

    def _liquidate_eod(self):
        self.liquidate(self.spy)
        self._orb_high = None
        self._orb_low = None

    def on_data(self, data: Slice):
        if not self.spy in data.bars:
            return

        bar = data.bars[self.spy]
        t = self.time.time()

        if time(9, 30) <= t < time(10, 0):
            if self._orb_high is None or bar.high > self._orb_high:
                self._orb_high = bar.high
            if self._orb_low is None or bar.low < self._orb_low:
                self._orb_low = bar.low
        elif t >= time(10, 0):
            if self._orb_high is not None and bar.close > self._orb_high:
                self.set_holdings(self.spy, 1.0)
                self._orb_high = None
                self._orb_low = None
            elif self._orb_low is not None and bar.close < self._orb_low:
                self.set_holdings(self.spy, -1.0)
                self._orb_high = None
                self._orb_low = None
