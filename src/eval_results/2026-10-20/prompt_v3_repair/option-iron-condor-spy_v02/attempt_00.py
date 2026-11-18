from AlgorithmImports import *

class IronCondorAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", Resolution.MINUTE)
        self.option = self.add_option("SPY", Resolution.MINUTE)
        self.option.set_filter(
            lambda u: u.include_weeklys().strikes(-10, 10).expiration(0, 7)
        )

        self._legs = []

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.at(9, 31),
            self.open_iron_condor
        )
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 5),
            self.close_iron_condor
        )

    def on_data(self, data: Slice):
        if not self._legs:
            return
        for leg in self._legs:
            if leg in data.option_chains:
                chain = data.option_chains[leg]
                if chain is not None and len(chain) > 0:
                    contract = chain[0]
                    if contract.bid_price <= 0 or contract.ask_price <= 0:
                        self.Log(f"Leg {leg} has no valid bid/ask, closing position.")
                        self.close_iron_condor()
                        return

    def open_iron_condor(self):
        if self._legs:
            return

        chain = self.option_chains.get(self.option.symbol)
        if chain is None or len(chain) == 0:
            self.Log("No option chain available.")
            return

        # Find contracts expiring this Friday
        today = self.Time.Date
        friday = today + timedelta(days=(4 - today.weekday()) % 7)
        if friday < today:
            friday += timedelta(days=7)

        candidates = [
            c for c in chain
            if c.expiry.Date == friday
        ]
        if not candidates:
            self.Log(f"No options expiring on {friday}.")
            return

        # Find sell call closest to 0.10 delta
        sell_call = None
        min_call_delta_diff = float('inf')
        for c in candidates:
            if c.right == OptionRight.CALL and c.greeks.delta is not None:
                diff = abs(c.greeks.delta - 0.10)
                if diff < min_call_delta_diff:
                    min_call_delta_diff = diff
                    sell_call = c

        # Find sell put closest to -0.10 delta
        sell_put = None
        min_put_delta_diff = float('inf')
        for c in candidates:
            if c.right == OptionRight.PUT and c.greeks.delta is not None:
                diff = abs(c.greeks.delta - (-0.10))
                if diff < min_put_delta_diff:
                    min_put_delta_diff = diff
                    sell_put = c

        if sell_call is None or sell_put is None:
            self.Log("Could not find suitable sell legs.")
            return

        # Find buy call 3 strikes further out (higher strike)
        buy_call = None
        for c in candidates:
            if c.right == OptionRight.CALL and c.strike > sell_call.strike:
                if buy_call is None or abs(c.strike - (sell_call.strike + 3)) < abs(buy_call.strike - (sell_call.strike + 3)):
                    buy_call = c

        # Find buy put 3 strikes further out (lower strike)
        buy_put = None
        for c in candidates:
            if c.right == OptionRight.PUT and c.strike < sell_put.strike:
                if buy_put is None or abs(c.strike - (sell_put.strike - 3)) < abs(buy_put.strike - (sell_put.strike - 3)):
                    buy_put = c

        if buy_call is None or buy_put is None:
            self.Log("Could not find suitable buy legs.")
            return

        # Check bid/ask for all legs
        for leg in [sell_call, sell_put, buy_call, buy_put]:
            if leg.bid_price <= 0 or leg.ask_price <= 0:
                self.Log(f"Leg {leg.symbol} has no valid bid/ask. Skipping week.")
                return

        # Execute orders: sell 1 each of sell_call and sell_put, buy 1 each of buy_call and buy_put
        self._legs = [sell_call.symbol, sell_put.symbol, buy_call.symbol, buy_put.symbol]

        self.market_order(sell_call.symbol, -1)
        self.market_order(sell_put.symbol, -1)
        self.market_order(buy_call.symbol, 1)
        self.market_order(buy_put.symbol, 1)

        self.Log(f"Opened iron condor: sell {sell_call.symbol} @ {sell_call.strike}, "
                 f"sell {sell_put.symbol} @ {sell_put.strike}, "
                 f"buy {buy_call.symbol} @ {buy_call.strike}, "
                 f"buy {buy_put.symbol} @ {buy_put.strike}")

    def close_iron_condor(self):
        if not self._legs:
            return

        for leg in self._legs:
            if leg in self.portfolio:
                position = self.portfolio[leg]
                if position.quantity != 0:
                    self.liquidate(leg)
                    self.Log(f"Closed {leg} with quantity {position.quantity}")

        self._legs = []
