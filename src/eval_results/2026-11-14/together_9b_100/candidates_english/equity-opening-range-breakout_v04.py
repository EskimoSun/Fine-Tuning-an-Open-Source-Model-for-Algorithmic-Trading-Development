# region imports
from AlgorithmImports import *
# endregion

class OneRuleBreakoutAlgorithm(QCAlgorithm):
    _stop_loss = 0.01
    _take_profit = 0.02

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True

        self._spy = self.add_equity("SPY", Resolution.MINUTE)

        self.universe_settings.resolution = Resolution.MINUTE
        # Option universe to filter the expiry and strike of the underlying.
        self.universe_settings.universe_type = UniverseType.OPTIONS
        # Create a OptionFilter to filter the options.
        self._option_filter = OptionFilter()
        # Set the expiry to be the closest ATM call expiry.
        self._option_filter.expiry = OptionExpiry.CLOSEST_OPEN
        # Set the strike to be the ATM strike.
        self._option_filter.strike = OptionStrike.ATM
        # Attach the option filter to the algorithm.
        self.add_universe(self._spy, self._option_filter)

        self.schedule.on(
            self.date_rules.every_day(self._spy.symbol),
            self.time_rules.before_market_close(self._spy.symbol, 15, 55),
            self._rebalance
        )

    def on_securities_changed(self, changes: SecurityChanges) -> None:
        for security in changes.added_securities:
            if security.type == SecurityType.OPTION:
                # Generate trading signals for the option.
                indicator = IndicatorExtensions.create_indicator(BollingerBands(2, 20, MovingAverageType.SIMPLE), security)
                security.indicator = indicator
                # Warm up the indicator and its windows.
                self.indicator_history(indicator, security, self.warm_up_period)

    def _rebalance(self) -> None:
        if not self._spy.indicator.is_ready:
            return

        bb = self._spy.indicator
        price = self._spy.price
        in_uptrend = price > bb.upper_band.current.value
        in_downtrend = price < bb.lower_band.current.value

        if not self.portfolio.invested and (in_uptrend or in_downtrend):
            stop_loss_percent = self._stop_loss if in_uptrend else -self._stop_loss
            take_profit_percent = self._take_profit if in_uptrend else -self._take_profit

            self.set_holdings(self._spy, 1, stop_loss_percent, take_profit_percent)
        elif self.portfolio.invested:
            self.liquidate(self._spy, tag=f"Exit {self._spy.symbol}")
