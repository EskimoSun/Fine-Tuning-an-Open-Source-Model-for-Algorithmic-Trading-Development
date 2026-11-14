# region imports
from AlgorithmImports import *
import statsmodels.api as sm
import math
# endregion

class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
    _beta: float = 0
    _residuals: list[float] = []
    _mean_residual: float = 0
    _std_residual: float = 0
    _count = 0

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pep = self.add_equity("PEP", Resolution.MINUTE)

        self._signal = self.signal_registry.add(self._rebalance)

        self.warm_up(self._get_warm_up_period(), Resolution.DAILY)

    def _get_warm_up_period(self) -> int:
        return 60

    def on_data(self, data: Slice) -> None:
        if not self._signal.is_ready:
            return

        bar = data.bars.get(self._ko)
        if not bar:
            return

        price = bar.close
        scaled_price = price / self.portfolio[self._pep].price
        if scaled_price < 0:
            return

        self._count += 1
        if self._count < self._get_warm_up_period():
            return

        predicted = self._beta * math.log(scaled_price)
        residual = math.log(scaled_price) - predicted
        self._residuals.append(residual)

        if len(self._residuals) > self._get_warm_up_period():
            self._residuals.pop(0)

        self._mean_residual = sum(self._residuals) / len(self._residuals)
        variance = sum((r - self._mean_residual) ** 2 for r in self._residuals) / len(self._residuals)
        self._std_residual = math.sqrt(variance)

        if self._std_residual == 0:
            return

        z_score = (self._mean_residual + residual) / self._std_residual

        if z_score < -2:
            self._signal.target(self._ko, -1)
            self._signal.target(self._pep, 1)
        elif z_score > 2:
            self._signal.target(self._ko, 1)
            self._signal.target(self._pep, -1)

    def _rebalance(self) -> Optional[bool]:
        if self._count < self._get_warm_up_period():
            return False

        scaled_price = self.portfolio[self._ko].price / self.portfolio[self._pep].price
        if scaled_price < 0:
            return False

        predicted = self._beta * math.log(scaled_price)
        residual = math.log(scaled_price) - predicted

        if self._std_residual == 0:
            return False

        z_score = (self._mean_residual + residual) / self._std_residual

        if z_score < -2:
            self.set_holdings(self._ko, -0.5, True)
            self.set_holdings(self._pep, 0.5, True)
        elif z_score > 2:
            self.set_holdings(self._ko, 0.5, True)
            self.set_holdings(self._pep, -0.5, True)

        return True

    def on_warmup_finished(self) -> None:
        history = self.history[TradeBar](self._ko, self._get_warm_up_period(), Resolution.DAILY)
        pep_prices = [bar.close for bar in history]
        ko_prices = [bar.close for bar in self.history[TradeBar](self._ko, self._get_warm_up_period(), Resolution.DAILY)]

        X = sm.add_constant(pep_prices)
        Y = [math.log(x / pep_prices[-1]) for x in ko_prices]

        ols = sm.OLS(Y, X)
        results = ols.fit()
        self._beta = results.params[1]
