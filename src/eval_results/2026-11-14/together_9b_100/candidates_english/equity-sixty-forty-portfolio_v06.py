# region imports
from AlgorithmImports import *
# endregion

class DynamicPortfolioRebalancingAlgorithm(QCAlgorithm):
    _drift_threshold = 0.05

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._spy = self.add_equity("SPY", Resolution.MINUTE).symbol
        self._tlt = self.add_equity("TLT", Resolution.MINUTE).symbol

        self.schedule.on(
            self.date_rules.quarter_start(self._spy),
            self.time_rules.after_market_open(self._spy, 1),
            self._rebalance
        )

    def on_warm_up_finished(self) -> None:
        self._rebalance()

    def _rebalance(self) -> None:
        for security in [self._spy, self._tlt]:
            holdings_value = self.portfolio.holdings_value(security)
            weight = holdings_value / self.portfolio.total_portfolio_value
            target_weight = self._get_target_weight(security)

            if abs(weight - target_weight) > self._drift_threshold:
                self.set_holdings([self._spy, self._tlt])

    def _get_target_weight(self, security: Security) -> float:
        risk_free_rate = self.risk_free_interest_rate_model.get(risk_free_interest_rate_type.TREASURY_BILL_3MONTH)
        duration = security.duration

        if not risk_free_rate or duration == 0:
            return 0.5

        beta = duration * (1 + risk_free_rate)
        covariance = self.portfolio.covariance(security, self._spy) / beta

        if covariance == 0:
            return 0.5

        correlation = self.portfolio.correlation(security, self._spy)
        if correlation == 0:
            return 0.5

        security_contribution = covariance / correlation
        total_contribution = sum([
            self.portfolio.covariance(other_security, self._spy)
            / self.portfolio.correlation(other_security, self._spy)
            for other_security in [self._spy, self._tlt]
        ])

        if total_contribution == 0:
            return 0.5

        return max(0, min(1, 0.5 - (security_contribution / total_contribution)))
