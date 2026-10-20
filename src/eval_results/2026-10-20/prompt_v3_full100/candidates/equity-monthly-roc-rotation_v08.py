from AlgorithmImports import *


class MonthlyRocRotation(QCAlgorithm):
    """Monthly rate-of-change rotation across SPY, EFA, EEM, AGG, GLD."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self._symbols = [
            self.add_equity("SPY", resolution=Resolution.DAILY),
            self.add_equity("EFA", resolution=Resolution.DAILY),
            self.add_equity("EEM", resolution=Resolution.DAILY),
            self.add_equity("AGG", resolution=Resolution.DAILY),
            self.add_equity("GLD", resolution=Resolution.DAILY),
        ]

        self._rocs = {}
        for symbol in self._symbols:
            self._rocs[symbol] = self.roc(symbol, 60, resolution=Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start(self._symbols[0]),
            self.time_rules.at(9, 31),
            self._rotate,
        )

    def _rotate(self):
        if not all(roc.is_ready for roc in self._rocs.values()):
            self.log("Skipping rotation: ROC indicators not ready.")
            return

        roc_values = {symbol: roc.current.value for symbol, roc in self._rocs.items()}
        self.log(f"ROC values: {roc_values}")

        if all(value < 0 for value in roc_values.values()):
            self.log("All ROC values negative; liquidating to cash.")
            for symbol in self._symbols:
                self.liquidate(symbol)
            return

        ranked = sorted(roc_values.items(), key=lambda item: item[1], reverse=True)
        top_three = [symbol for symbol, _ in ranked[:3]]
        rest = [symbol for symbol in self._symbols if symbol not in top_three]

        for symbol in rest:
            self.liquidate(symbol)

        for symbol in top_three:
            self.set_holdings(symbol, 1.0 / 3.0)
