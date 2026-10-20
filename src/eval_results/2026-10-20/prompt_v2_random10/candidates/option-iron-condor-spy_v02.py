from AlgorithmImports import *

class IronCondorStrategy(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_warm_up(1, "d")

        # Add SPY equity for reference
        self.spy = self.add_equity("SPY", Resolution.DAILY)

        # Add SPY options
        self.option = self.add_option("SPY", Resolution.MINUTE)
        self.option.set_filter(
            self.date_rules.range(self.start_date, self.end_date),
            self.strike_rules.every()
        )

        # Schedule: every Monday 1 minute after market open
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 1),
            self.open_iron_condor
        )

        # Schedule: every Friday 5 minutes before market close
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 5),
            self.close_iron_condor
        )

    def open_iron_condor(self):
        if not self.spy.is_ready:
            return

        # Get the option chain for SPY
        chain = self.option.option_chains.get("SPY")
        if chain is None or len(chain) == 0:
            self.log("No option chain found for SPY")
            return

        # Find the expiration closest to this Friday (within 5 days)
        today = self.time.date
        target_expiry = today + timedelta(days=(4 - today.weekday()) % 7)
        if target_expiry < today:
            target_expiry += timedelta(days=7)

        # Filter expirations within 7 days from today
        valid_expirations = [
            exp for exp in chain
            if abs((exp - today).days) <= 7
        ]
        if not valid_expirations:
            self.log("No valid expirations found")
            return

        # Pick the expiration closest to target
        best_expiry = min(valid_expirations, key=lambda e: abs((e - target_expiry).days))

        # Get all options for this expiration
        expiry_options = chain[best_expiry]
        if not expiry_options:
            self.log("No options for selected expiration")
            return

        # Separate calls and puts
        calls = [o for o in expiry_options if o.contract_type == OptionContractType.CALL]
        puts = [o for o in expiry_options if o.contract_type == OptionContractType.PUT]

        if not calls or not puts:
            self.log("Missing calls or puts in chain")
            return

        # Find the call closest to 0.10 delta
        sell_call = self._find_closest_delta(calls, 0.10)
        # Find the put closest to -0.10 delta
        sell_put = self._find_closest_delta(puts, -0.10)

        if sell_call is None or sell_put is None:
            self.log("Could not find sell legs with valid deltas")
            return

        # Find the call 3 strikes further out (higher strike)
        buy_call = self._find_strike_offset(calls, sell_call, +3)
        # Find the put 3 strikes further out (lower strike)
        buy_put = self._find_strike_offset(puts, sell_put, -3)

        if buy_call is None or buy_put is None:
            self.log("Could not find buy legs 3 strikes out")
            return

        # Check that all legs have valid bid/ask
        legs = [sell_call, sell_put, buy_call, buy_put]
        for leg in legs:
            if not self._has_valid_quote(leg):
                self.log(f"Leg {leg.symbol} has no valid bid/ask, skipping week")
                return

        # Place orders: sell 1 each of the inner legs, buy 1 each of the outer legs
        self.market_order(sell_call, -1)
        self.market_order(sell_put, -1)
        self.market_order(buy_call, 1)
        self.market_order(buy_put, 1)

        self.log(f"Iron condor opened: sell {sell_call.symbol} @ {sell_call.strike}, "
                 f"sell {sell_put.symbol} @ {sell_put.strike}, "
                 f"buy {buy_call.symbol} @ {buy_call.strike}, "
                 f"buy {buy_put.symbol} @ {buy_put.strike}")

    def close_iron_condor(self):
        # Liquidate all option positions
        self.liquidate()
        self.log("All positions closed")

    def _find_closest_delta(self, options, target_delta):
        """Find the option with delta closest to target_delta."""
        best = None
        best_diff = float('inf')
        for opt in options:
            if not opt.is_ready:
                continue
            delta = opt.delta
            if delta is None:
                continue
            diff = abs(delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best = opt
        return best

    def _find_strike_offset(self, options, reference, offset):
        """Find the option with strike = reference.strike + offset."""
        target_strike = reference.strike + offset
        for opt in options:
            if abs(opt.strike - target_strike) < 1e-9:
                return opt
        return None

    def _has_valid_quote(self, option):
        """Check if the option has a valid bid and ask."""
        if not option.is_ready:
            return False
        bid = option.bid
        ask = option.ask
        if bid is None or ask is None:
            return False
        if bid <= 0 or ask <= 0:
            return False
        return True
