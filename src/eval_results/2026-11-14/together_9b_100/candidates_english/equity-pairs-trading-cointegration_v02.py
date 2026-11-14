# region imports
from AlgorithmImports import *
# endregion

class CocaCokePepsiPairTradingAlgorithm(QCAlgorithm):
    _pep_ratio = LinearRegression(60)
    _pep_residues = RollingWindow(60)
    _pep_z_score = SimpleMovingAverage(60)

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._ko = self.add_equity("KO", Resolution.MINUTE)
        self._pep = self.add_equity("PEP", Resolution.MINUTE)

        self._pep_ratio = self.linear_regression(self._ko, self._pep, 60, Resolution.DAILY)
        # Alternatively, use a manual indicator.
        # self._pep_ratio = LinearRegression(60)
        # self.warm_up_indicator(self._pep_ratio, self._ko, Resolution.DAILY)
        # self.register_indicator(self._ko, self._pep_ratio, Resolution.DAILY)
        self._pep_residues = RollingWindow(60)
        self._pep_z_score = SimpleMovingAverage(60)

        self.schedule.on(
            self.date_rules.every_day(self._pep.symbol),
            self.time_rules.at(10, 0),
            self._rebalance
        )

    def _rebalance(self) -> None:
        if not self._pep_ratio.is_ready:
            return

        # Update the standard deviation of the residuals
        current_residual = self._ko.price - self._pep_ratio.current.value * self._pep.price
        self._pep_residues.add(current_residual)
        if not self._pep_residues.is_ready:
            return

        # Z-score = (current value - mean) / standard_deviation
        mean = self._pep_residues.mean
        std = self._pep_residues.standard_deviation
        if std == 0:
            return
        z_score = (current_residual - mean) / std

        # We will buy KO when the Z-score is below -2 and sell when it is above 2
        # We will short PEP when the Z-score is below -2 and buy when it is above 2
        # We will close the positions when the Z-score is between -0.5 and 0.5
        if z_score < -2.0:
            self.set_holdings(self._ko, 0.5)
            self.set_holdings(self._pep, -0.5)
        elif z_score > 2.0:
            self.set_holdings(self._ko, -0.5)
            self.set_holdings(self._pep, 0.5)
        elif -0.5 < z_score < 0.5:
            self.liquidate()
