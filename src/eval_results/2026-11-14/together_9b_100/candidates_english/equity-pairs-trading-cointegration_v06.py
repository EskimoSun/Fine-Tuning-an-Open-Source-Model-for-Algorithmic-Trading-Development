# region imports
import math
from AlgorithmImports import *
# endregion


class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.settings.seed_initial_prices = True
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        self._pep = self.add_equity("PEP", Resolution.MINUTE)
        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._beta = 1.0
        self._alpha = 0.0
        self._standard_deviation = 0.0
        self._mean = 0.0
        self._count = 0
        self._sum = 0.0
        self._sum_squared = 0.0
        self._sum_x = 0.0
        self._sum_xy = 0.0
        self._covariance = 0.0
        self._variance = 0.0
        self._n = 0
        self._positive_threshold = 2.0
        self._negative_threshold = -2.0
        self._inverted = False
        self._target_percent = 0.5
        self._weight = 0.0
        self._correlation = 0.0
        self._spearman_rank_correlation = 0.0
        self._rsquare = 0.0
        self._residuals = []
        self._z_score = 0.0
        self._total_return = 0.0
        self._drawdown = 0.0
        self._max_drawdown = 0.0
        self._rank = 0
        self._rank_value = 0
        self._rank_signal = 0
        self._rank_target = 0
        self._rank_inverted = False
        self._rank_weight = 0.0
        self._rank_exposure = 0.0
        self._rank_drawdown = 0.0
        self._rank_max_drawdown = 0.0
        self._rank_total_return = 0.0
        self._rank_pep = self._pep.symbol
        self._rank_ko = self._ko.symbol
        self._rank_equity = None
        self._rank_applicable = False
        self._rank_increasing = False
        self._rank_hold = False
        self._rank_liquidate = False
        self._rank_liquidate_target = 0.0
        self._rank_order_quantity = 0
        self._rank_order = None
        self._rank_market_order = MarketOrder(self._rank_equity, self._rank_order_quantity)
        self.schedule.on(
            self.date_rules.week_start(self._pep.symbol),
            self.time_rules.after_market_open(self._pep.symbol, 1),
            self._rebalance
        )

    def on_data(self, data: Slice) -> None:
        if not self.training_mode and not self._pep.invested:
            self._update_factors(data)

    def _update_factors(self, data: Slice) -> None:
        bar = data.bars.get(self._pep.symbol)
        if not bar:
            return
        price = bar.close
        self._sum += price
        self._sum_squared += price * price
        self._count += 1
        if self._count < 2:
            return
        self._mean = self._sum / self._count
        self._standard_deviation = math.sqrt(
            self._sum_squared / self._count - self._mean * self._mean
        )
        if self._standard_deviation == 0:
            return
        z_score = (price - self._mean) / self._standard_deviation
        if abs(z_score) > max(self._positive_threshold, -self._negative_threshold):
            self._rebalance()

    def _rebalance(self) -> None:
        if self.training_mode:
            return
        beta = self._calculate_beta()
        alpha = self._calculate_alpha(beta)
        self._beta = beta
        self._alpha = alpha
        self._update_z_score()

    def _calculate_beta(self) -> float:
        covariance = self._calculate_covariance(self._pep, self._ko)
        variance = self._calculate_variance(self._ko)
        if variance == 0:
            return 0.0
        return covariance / variance

    def _calculate_alpha(self, beta: float) -> float:
        return self._sum / self._count - self._beta * self._sum / self._count

    def _calculate_covariance(self, asset_a: Equity, asset_b: Equity) -> float:
        if self._count < 2:
            return 0.0
        mean_a = self._sum / self._count
        mean_b = 0.0
        covariance = 0.0
        for i in range(self._count):
            bar_a = self.history[Equity](asset_a, i + 1, Resolution.DAILY).bars[0]
            bar_b = self.history[Equity](asset_b, i + 1, Resolution.DAILY).bars[0]
            if not bar_a or not bar_b:
                continue
            price_a = bar_a.close
            price_b = bar_b.close
            covariance += (price_a - mean_a) * (price_b - mean_b)
        return covariance / self._count

    def _calculate_variance(self, asset: Equity) -> float:
        if self._count < 2:
            return 0.0
        mean = self._sum / self._count
        variance = 0.0
        for i in range(self._count):
            bar = self.history[Equity](asset, i + 1, Resolution.DAILY).bars[0]
            if not bar:
                continue
            price = bar.close
            variance += (price - mean) ** 2
        return variance / self._count

    def _update_z_score(self) -> None:
        if not self._pep.invested:
            return
        current_price = self.securities[self._pep.symbol].price
        z_score = (current_price - self._alpha) / (self._beta * self._standard_deviation)
        if not self._pep.invested:
            self._z_score = z_score
            return
        previous_z_score = self._z_score
        self._z_score = z_score
        if previous_z_score < self._negative_threshold and self._z_score > self._negative_threshold:
            self._buy(self._pep, self._target_percent)
            self._sell(self._ko, -self._target_percent * self._beta)
        elif previous_z_score > self._positive_threshold and self._z_score < self._positive_threshold:
            self._sell(self._pep, self._target_percent)
            self._buy(self._ko, -self._target_percent * self._beta)

    def on_warmup_finished(self) -> None:
        self._update_factors(self.slice)
