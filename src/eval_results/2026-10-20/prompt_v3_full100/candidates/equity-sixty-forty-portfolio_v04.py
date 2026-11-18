from AlgorithmImports import *


class SixtyFortyRebalance(QCAlgorithm):
    """60/40 SPY/TLT portfolio with quarterly rebalancing and a 5% drift band."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", Resolution.DAILY)
        self.tlt = self.add_equity("TLT", Resolution.DAILY)

        self.target_weights = {self.spy.symbol: 0.60, self.tlt.symbol: 0.40}
        self.drift_band = 0.05

        # Rebalance on the first trading day of each quarter
        self.schedule.on(
            self.date_rules.month_start(self.spy.symbol),
            self.time_rules.at_market_open(self.spy.symbol),
            self.on_rebalance
        )

    def on_data(self, data: Slice):
        if not self.portfolio.invested:
            return

        # Check drift band on every bar
        for symbol, target in self.target_weights.items():
            if symbol not in data:
                continue
            current_weight = self.portfolio[symbol].invested / self.portfolio.total_portfolio_value
            if abs(current_weight - target) > self.drift_band:
                self.log(f"Drift detected for {symbol}: current={current_weight:.4f}, target={target:.4f}")
                self.rebalance()
                break

    def on_rebalance(self):
        self.log("Quarterly rebalance triggered")
        self.rebalance()

    def rebalance(self):
        total_value = self.portfolio.total_portfolio_value
        if total_value <= 0:
            return

        for symbol, target in self.target_weights.items():
            if symbol not in self.securities:
                continue
            current_invested = self.portfolio[symbol].invested
            target_invested = total_value * target
            delta = target_invested - current_invested

            # Only trade if the difference is meaningful (avoid tiny orders)
            if abs(delta) < 10:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            quantity = int(delta / price)
            if quantity == 0:
                continue

            self.log(f"Rebalancing {symbol}: delta={delta:.2f}, quantity={quantity}")
            self.market_order(symbol, quantity)
