# region imports
from AlgorithmImports import *
# endregion

class FutureAlgorithmQcbs(EmaCrossAlgorithm):
    _size = 1

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        # automatic_indicator_warm_up only supports automatic indicators, not manual indicators.
        self.settings.automatic_indicator_warm_up = True
        # Roll the E-mini SP 500 Futures continuously.
        self._future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            contract_depth_offset=0
        )
        # Roll the mapped futures contract automatically.
        self._future.set_property(FutureProperty.ROLLOVER_TARGET, self._get_rollover_target)
        # Update the indicators when the mapped futures contract updates.
        self.register_indicator(self._future, self._ema_fast)
        self.register_indicator(self._future, self._ema_slow)
        # Warm up the indicators and subscriptions.
        self.set_warm_up(200, Resolution.DAILY)
        # Schedule daily trading at 8 AM to trade today's mapped futures contract.
        self.schedule.on(
            self.date_rules.every_day(self._future.symbol),
            self.time_rules.at(8, 0),
            self._rebalance
        )

    def _get_rollover_target(self, current: Future) -> Future:
        next = self.futures_chain.get_next_contract(current, 30)
        if not next:
            return current
        # Prefer front-month contracts with valid price data.
        return next if next.has_data else current

    def _rebalance(self) -> None:
        if not self._ema_fast.is_ready or not self._ema_slow.is_ready:
            return
        fast = self._ema_fast.current.value
        slow = self._ema_slow.current.value
        # EMA cross trend-following strategy.
        if fast > slow and not self._future.invested:
            self.set_holdings(self._future, self._size)
        elif fast < slow and self._future.invested:
            self.liquidate()
