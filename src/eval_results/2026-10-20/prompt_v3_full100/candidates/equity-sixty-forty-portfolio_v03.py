from AlgorithmImports import *


class SixtyForty(QCAlgorithm):
    REBALANCE_THRESHOLD = 0.05

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)
        self.tlt = self.add_equity("TLT", resolution=Resolution.MINUTE)

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.at(0, 0),
            self._on_quarter_start
        )

    def _on_quarter_start(self):
        today = self.now.date()
        if today.month in (1, 4, 7, 10) and today.day == 1:
            self.schedule.once(
                self.date_rules.on(today),
                self.time_rules.at(9, 31),
                self._rebalance
            )

    def _rebalance(self):
        spy_weight = self.portfolio[self.spy.symbol].invested / self.portfolio.total_portfolio_value
        tlt_weight = self.portfolio[self.tlt.symbol].invested / self.portfolio.total_portfolio_value

        if abs(spy_weight - 0.60) > self.REBALANCE_THRESHOLD or abs(tlt_weight - 0.40) > self.REBALANCE_THRESHOLD:
            self.set_holdings(self.spy.symbol, 0.60)
            self.set_holdings(self.tlt.symbol, 0.40)
            self.Log(f"Rebalanced: SPY={spy_weight:.4f}, TLT={tlt_weight:.4f}")
        else:
            self.Log(f"Rebalance skipped: SPY={spy_weight:.4f}, TLT={tlt_weight:.4f}")

    def on_data(self, data: Slice):
        if not self.portfolio.invested and self.spy.symbol in data and self.tlt.symbol in data:
            self.set_holdings(self.spy.symbol, 0.60)
            self.set_holdings(self.tlt.symbol, 0.40)
            self.Log("Initial buy executed.")
