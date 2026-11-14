# region imports
from AlgorithmImports import *
import math
from datetime import timedelta
from time import sleep
import pandas as pd
# endregion

class ConsumerBraggingRightsAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pep = self.add_equity("PEP", Resolution.MINUTE)

        self._beta = 0.0
        self._alpha = 0.0
        self._standard_error = 0.0
        self._count = 0
        self._sum_y = 0.0
        self._sum_x = 0.0
        self._sum_xy = 0.0
        self._sum_x_sq = 0.0
        self._sum_y_sq = 0.0

        self.schedule.on(
            self.date_rules.week_start(self._ko.symbol),
            self.time_rules.after_market_open(self._ko.symbol, 1),
            self._rebalance
        )

    def on_data(self, data: Slice) -> None:
        if not self.training_mode and self.time % timedelta(minutes=10) == 0:
            self._update(data)

    def _update(self, data: Slice) -> None:
        bar = data.bars.get(self._pep.symbol)
        if not bar:
            return

        x = bar.close
        ko_bar = data.bars.get(self._ko.symbol)
        y = ko_bar.close if ko_bar else 0.0

        self._sum_y += y
        self._sum_x += x
        self._sum_xy += x * y
        self._sum_x_sq += x * x
        self._sum_y_sq += y * y
        self._count += 1

        if self._count >= 60:
            self._count = 0
            self._standard_error, self._alpha, self._beta = self._calculate_linear_regression(
                self._sum_x, self._sum_y, self._sum_xy, self._sum_x_sq, self._sum_y_sq
            )

    def _calculate_linear_regression(self, sum_x: float, sum_y: float, sum_xy: float, sum_x_sq: float, sum_y_sq: float) -> tuple[float, float, float]:
        n = self._count
        denominator = n * sum_x_sq - sum_x * sum_x
        beta = (n * sum_xy - sum_x * sum_y) / denominator
        alpha = (sum_y - beta * sum_x) / n
        standard_error = math.sqrt((sum_y_sq - 2 * beta * sum_xy + beta * beta * sum_x_sq) / (n - 1) / sum_x_sq)
        return standard_error, alpha, beta

    def _rebalance(self) -> None:
        if self._count < 60:
            return

        standard_error, alpha, beta = self._standard_error, self._alpha, self._beta
        pep_bar = self.securities[self._pep.symbol].bar
        if not pep_bar:
            return

        ko_theory_price = alpha + beta * pep_bar.close
        ko_actual_price = self.securities[self._ko.symbol].bar.close
        z_score = (ko_actual_price - ko_theory_price) / standard_error

        if abs(z_score) < 0.5:
            self.liquidate(self._ko.symbol, self._pep.symbol)
            return

        weight = -z_score / 2.0
        if weight < -1.0:
            weight = -1.0
        if weight > 1.0:
            weight = 1.0

        target_pep_weight = 0.5 + weight * 0.5
        target_ko_weight = 0.5 - weight * 0.5

        pep_order_quantity = self.calculate_order_quantity(self._pep.symbol, target_pep_weight)
        ko_order_quantity = self.calculate_order_quantity(self._ko.symbol, target_ko_weight)

        if not self.portfolio.invested:
            self.market_order(self._pep.symbol, pep_order_quantity)
            self.market_order(self._ko.symbol, ko_order_quantity)
            return

        pep_order_quantity = self.order_quantity(self._pep.symbol, target_pep_weight)
        ko_order_quantity = self.order_quantity(self._ko.symbol, target_ko_weight)

        if not self.portfolio.invested:
            self.market_order(self._pep.symbol, pep_order_quantity)
            self.market_order(self._ko.symbol, ko_order_quantity)
