# region imports
from AlgorithmImports import *
import math
from datetime import timedelta
# endregion

class ConsumerBraggPairsTradingAlgorithm(QCAlgorithm):
    _beta: float = 0.0
    _alpha: float = 0.0
    _standard_deviation: float = 0.0
    _count = 0
    _tag = "ConsumerBragg"

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pep = self.add_equity("PEP", Resolution.MINUTE)

        self._optimizer = LinearRegressionOptimizer(1)
        self._optimizer.time_period = 60
        # Alternatively, use a manual indicator.
        # self._optimizer = LinearRegression(1)
        # self.warm_up_indicator(self._optimizer, self._pep, Resolution.DAILY)
        # self.register_indicator(self._pep, self._optimizer, Resolution.DAILY)
        self.plot_indicator("Optimizer", self._optimizer)

        self.schedule.on(
            self.date_rules.week_start(self._ko.symbol),
            self.time_rules.after_market_open(self._ko.symbol, 1),
            self._rebalance
        )

    def on_warmup_finished(self) -> None:
        self._rebalance()

    def _rebalance(self) -> None:
        if not self._optimizer.is_ready:
            return

        pep_price = self.securities[self._pep.symbol].price
        # Update the alpha and beta using the updated price and the indicator.
        self._alpha, self._beta = self._optimizer.update(pep_price)

        # We will simply go long KO when PEP lags behind and short when it surges.
        # Using the residual standard error for normalization.
        predicted_ko = self._alpha + self._beta * pep_price
        residual = self._ko.securities[self._ko.symbol].price - predicted_ko
        self._standard_deviation = self._optimizer.residual_standard_error

        if self._standard_deviation == 0:
            return

        z_score = residual / self._standard_deviation
        self._count += 1
        self.plot("Z-Score", "ConsumerBragg", z_score)

        # Stop trading after 10 trades to avoid excessive trading.
        if self._count > 10:
            return

        # Equal weight allocation for the pair trading.
        target_ko = 0.5
        target_pep = -0.5

        # Sufficient sample size for trading.
        if abs(z_score) > 2 and not self.portfolio.invested:
            self.set_holdings(self._ko.symbol, target_ko)
            self.set_holdings(self._pep.symbol, target_pep)
        # Exit when the z-score reverts to near zero, indicating mean reversion.
        elif self.portfolio.invested and abs(z_score) < 0.5:
            self.liquidate()
