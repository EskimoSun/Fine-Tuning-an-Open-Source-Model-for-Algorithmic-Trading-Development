from AlgorithmImports import *
from typing import Optional, Tuple


class KoPepPairsTrading(QCAlgorithm):
    """Pairs trading reference on KO and PEP using a weekly OLS spread model."""

    def initialize(self) -> None:
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.ko = self.add_equity("KO", resolution=Resolution.MINUTE)
        self.pep = self.add_equity("PEP", resolution=Resolution.MINUTE)

        self._beta: float = 0.0
        self._alpha: float = 0.0
        self._spread_mean: float = 0.0
        self._spread_std: float = 1e-6
        self._position: str = "FLAT"  # FLAT, LONG, SHORT
        self._model_ready: bool = False

        self.set_warm_up(60, Resolution.DAILY)

        # Weekly model refit at 09:31
        self.schedule.on(
            self.date_rules.every_day(self.ko.symbol),
            self.time_rules.at(9, 31),
            self._refit_model
        )

        # Daily signal at 10:00
        self.schedule.on(
            self.date_rules.every_day(self.ko.symbol),
            self.time_rules.at(10, 0),
            self._evaluate_signal
        )

    def on_warm_up_end(self) -> None:
        """Fit the model once when warm-up finishes."""
        self._refit_model()

    def _refit_model(self) -> None:
        """Fit OLS of KO on PEP over the last 60 daily closes."""
        ko_history = self.history(self.ko.symbol, 60, Resolution.DAILY)
        pep_history = self.history(self.pep.symbol, 60, Resolution.DAILY)

        if len(ko_history) < 60 or len(pep_history) < 60:
            self.Log("Insufficient history for model refit.")
            return

        # Align by date
        ko_dates = {bar.EndTime.date(): bar.Close for bar in ko_history}
        pep_dates = {bar.EndTime.date(): bar.Close for bar in pep_history}

        common_dates = sorted(set(ko_dates.keys()) & set(pep_dates.keys()))
        if len(common_dates) < 60:
            self.Log("Insufficient aligned history for model refit.")
            return

        x = [pep_dates[d] for d in common_dates]  # PEP prices
        y = [ko_dates[d] for d in common_dates]   # KO prices

        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        ss_xx = sum((xi - mean_x) ** 2 for xi in x)
        ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))

        if ss_xx < 1e-12:
            self.Log("Zero variance in PEP prices; cannot fit model.")
            return

        self._beta = ss_xy / ss_xx
        self._alpha = mean_y - self._beta * mean_x

        # Compute spread = KO - beta * PEP for each common date
        spreads = [yi - self._beta * xi for xi, yi in zip(x, y)]
        self._spread_mean = sum(spreads) / n
        variance = sum((s - self._spread_mean) ** 2 for s in spreads) / (n - 1)
        self._spread_std = max(variance ** 0.5, 1e-6)

        self._model_ready = True
        self.Log(f"Model refit: beta={self._beta:.4f}, alpha={self._alpha:.4f}, "
                 f"spread_mean={self._spread_mean:.4f}, spread_std={self._spread_std:.4f}")

    def _evaluate_signal(self) -> None:
        """Compute z-score of current spread and act on entry/exit rules."""
        if not self._model_ready:
            return

        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        current_spread = ko_price - self._beta * pep_price
        z_score = (current_spread - self._spread_mean) / self._spread_std

        self.Log(f"Signal: z={z_score:.4f}, position={self._position}")

        # Exit rule: |z| < 0.5 while in a position
        if abs(z_score) < 0.5 and self._position != "FLAT":
            self._liquidate()
            return

        # Entry rules
        if z_score < -2.0 and self._position != "LONG":
            self._liquidate()
            self._enter_long()
        elif z_score > 2.0 and self._position != "SHORT":
            self._liquidate()
            self._enter_short()

    def _enter_long(self) -> None:
        """Long KO 50%, short PEP 50% (dollar-neutral)."""
        portfolio_value = self.portfolio.total_value
        ko_value = portfolio_value * 0.5
        pep_value = portfolio_value * 0.5

        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        ko_qty = int(ko_value / ko_price)
        pep_qty = int(pep_value / pep_price)

        if ko_qty > 0:
            self.market_order(self.ko.symbol, ko_qty)
        if pep_qty > 0:
            self.market_order(self.pep.symbol, -pep_qty)

        self._position = "LONG"
        self.Log(f"Entered LONG spread: KO qty={ko_qty}, PEP qty={-pep_qty}")

    def _enter_short(self) -> None:
        """Short KO 50%, long PEP 50% (dollar-neutral)."""
        portfolio_value = self.portfolio.total_value
        ko_value = portfolio_value * 0.5
        pep_value = portfolio_value * 0.5

        ko_price = self.securities[self.ko.symbol].price
        pep_price = self.securities[self.pep.symbol].price

        if ko_price <= 0 or pep_price <= 0:
            return

        ko_qty = int(ko_value / ko_price)
        pep_qty = int(pep_value / pep_price)

        if ko_qty > 0:
            self.market_order(self.ko.symbol, -ko_qty)
        if pep_qty > 0:
            self.market_order(self.pep.symbol, pep_qty)

        self._position = "SHORT"
        self.Log(f"Entered SHORT spread: KO qty={-ko_qty}, PEP qty={pep_qty}")

    def _liquidate(self) -> None:
        """Liquidate both legs."""
        self.liquidate(self.ko.symbol)
        self.liquidate(self.pep.symbol)
        self._position = "FLAT"
        self.Log("Liquidated all positions.")
