from AlgorithmImports import *


class ApiProbe(QCAlgorithm):
    """Checks that every API example in SYSTEM_V3 is accepted by LEAN."""

    def initialize(self):
        self.set_start_date(2024, 11, 4)
        self.set_end_date(2024, 11, 8)
        self.set_cash(100000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.settings.automatic_indicator_warm_up = True
        self._spy = self.add_equity("SPY", resolution=Resolution.MINUTE,
                                    data_normalization_mode=DataNormalizationMode.ADJUSTED).symbol
        self._bb = self.bb(self._spy, 20, 2, resolution=Resolution.DAILY)
        self._rsi = self.rsi(self._spy, 14, moving_average_type=MovingAverageType.WILDERS, resolution=Resolution.HOUR)
        self._atr = self.atr(self._spy, 14, resolution=Resolution.DAILY)
        self._sma = self.sma(self._spy, 50, resolution=Resolution.DAILY)
        self._roc = self.roc(self._spy, 60, resolution=Resolution.DAILY)
        self._ema = self.ema(self._spy, 20, resolution=Resolution.DAILY)
        self._macd = self.macd(self._spy, 12, 26, 9, type=MovingAverageType.EXPONENTIAL,
                               resolution=Resolution.DAILY)
        self.set_warm_up(timedelta(days=30))
        self._future = self.add_future(Futures.Indices.SP_500_E_MINI, resolution=Resolution.MINUTE,
                                       extended_market_hours=True,
                                       data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
                                       data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
                                       contract_depth_offset=0)
        self._future.set_filter(0, 92)
        self._option = self.add_option("SPY", resolution=Resolution.MINUTE)
        self._option.set_filter(lambda u: u.include_weeklys().strikes(-10, 10).expiration(0, 7))
        self._indicators = {}
        for ticker in ["EFA", "AGG"]:
            symbol = self.add_equity(ticker, resolution=Resolution.DAILY).symbol
            self._indicators[symbol] = self.roc(symbol, 60, resolution=Resolution.DAILY)
        self._checked = False
        self.schedule.on(self.date_rules.every_day(self._spy), self.time_rules.after_market_open(self._spy, 1), self._daily)
        self.schedule.on(self.date_rules.week_start(self._spy), self.time_rules.before_market_close(self._spy, 5), self._noop)
        self.schedule.on(self.date_rules.every(DayOfWeek.MONDAY), self.time_rules.at(10, 0), self._noop)
        self.schedule.on(self.date_rules.month_start(self._spy), self.time_rules.after_market_open(self._spy, 1), self._noop)

    def _noop(self):
        pass

    def _daily(self):
        if self.is_warming_up or not self._bb.is_ready:
            return
        lower = self._bb.lower_band.current.value
        middle = self._bb.middle_band.current.value
        price = self.securities[self._spy].price
        if not self.portfolio[self._spy].invested:
            self.set_holdings(self._spy, 0.5)
        elif price >= middle and lower > 0:
            self.liquidate(self._spy)

    def on_data(self, slice: Slice):
        if self.is_warming_up or self._checked:
            return
        chain = slice.option_chains.get(self._option.symbol)
        if chain:
            calls = [c for c in chain if c.right == OptionRight.CALL]
            if calls:
                c = min(calls, key=lambda x: abs(x.greeks.delta - 0.10))
                self.debug(f"probe call {c.symbol} strike={c.strike} expiry={c.expiry} bid={c.bid_price} ask={c.ask_price}")
                self._checked = True
        if self._future.mapped and not self.portfolio[self._future.mapped].invested:
            self.market_order(self._future.mapped, 1)

    def on_symbol_changed_events(self, symbol_changed_events: SymbolChangedEvents):
        for symbol, changed_event in symbol_changed_events.items():
            quantity = self.portfolio[changed_event.old_symbol].quantity
            self.liquidate(changed_event.old_symbol)
            if quantity:
                self.market_order(changed_event.new_symbol, quantity)

    def on_order_event(self, order_event: OrderEvent):
        if order_event.status == OrderStatus.FILLED:
            self.debug(f"filled {order_event.symbol} {order_event.fill_quantity}")
