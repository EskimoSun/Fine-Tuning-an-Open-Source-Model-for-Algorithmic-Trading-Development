from AlgorithmImports import *


class MonthlyTop3RocRotation(QCAlgorithm):
    """Monthly top-3 ROC rotation across SPY/EFA/EEM/AGG/GLD. Cash if all negative."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.tickers = ["SPY", "EFA", "EEM", "AGG", "GLD"]
        self.securities_map = {}
        for ticker in self.tickers:
            self.securities_map[ticker] = self.add_equity(ticker, resolution=Resolution.DAILY)

        # Monthly rotation on the first trading day of each month
        self.schedule.on(
            self.date_rules.month_start(self.tickers[0]),
            self.time_rules.at(16, 0),
            self.rotate
        )

    def rotate(self):
        if self.portfolio.invested > 0:
            self.liquidate()

        # Compute 1-month ROC for each ticker
        rocs = {}
        for ticker in self.tickers:
            sec = self.securities_map[ticker]
            if sec is None or not sec.has_data:
                continue
            history = self.history(sec.symbol, 21, Resolution.DAILY)
            if len(history) < 21:
                continue
            prices = [bar.close for bar in history]
            if prices[0] <= 0:
                continue
            rocs[ticker] = (prices[-1] - prices[0]) / prices[0]

        if not rocs:
            return

        # Pick top 3 by ROC, only if positive
        ranked = sorted(rocs.items(), key=lambda kv: kv[1], reverse=True)
        top3 = [t for t, r in ranked[:3] if r > 0]

        if not top3:
            self.log("All ROCs negative; staying in cash.")
            return

        weight = 1.0 / len(top3)
        for ticker in top3:
            self.set_holdings(self.securities_map[ticker].symbol, weight)
        self.log(f"Rotated into {top3} with weight {weight:.3f} each.")
