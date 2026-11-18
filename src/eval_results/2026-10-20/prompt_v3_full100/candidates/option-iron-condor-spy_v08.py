from AlgorithmImports import *


class SpyIronCondorAlgorithm(QCAlgorithm):
    """Weekly SPY iron condor reference strategy."""

    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        # Add SPY option chain at minute resolution
        self._option = self.add_option("SPY", resolution=Resolution.MINUTE)
        self._option.set_filter(
            lambda u: u.include_weeklys().strikes(-10, 10).expiration(0, 7)
        )

        # Schedule: open Monday 1 min after open, close Friday 5 min before close
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 1),
            self._open_condor
        )
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 5),
            self._close_condor
        )

    def _open_condor(self):
        """Open one iron condor using contracts expiring this Friday."""
        # Find the target expiry: the Friday of this week
        target_expiry = self._get_this_friday()

        # Get the option chain for SPY
        chain = self._option.option_chains
        if not chain:
            self.Log("No option chain available.")
            return

        # Find the chain entry for SPY
        spy_chain = None
        for key, value in chain.items():
            if key == "SPY":
                spy_chain = value
                break

        if spy_chain is None:
            self.Log("SPY not found in option chains.")
            return

        # Filter contracts by target expiry
        contracts = [c for c in spy_chain if c.expiry.date() == target_expiry]
        if not contracts:
            self.Log(f"No contracts found for expiry {target_expiry}.")
            return

        # Separate calls and puts
        calls = [c for c in contracts if c.right == OptionRight.CALL]
        puts = [c for c in contracts if c.right == OptionRight.PUT]

        if not calls or not puts:
            self.Log("Missing calls or puts in chain.")
            return

        # Find ATM strike: closest to current SPY price
        spy_price = self.securities["SPY"].price
        atm_strike = min(
            set([c.strike for c in calls] + [p.strike for p in puts]),
            key=lambda s: abs(s - spy_price)
        )

        # Short call: nearest +0.10 delta (i.e., delta closest to 0.10 from above)
        short_call = self._find_nearest_delta(calls, 0.10, side="call")
        # Short put: nearest -0.10 delta (i.e., delta closest to -0.10, or 0.10 in magnitude)
        short_put = self._find_nearest_delta(puts, 0.10, side="put")

        if short_call is None or short_put is None:
            self.Log("Could not find short legs with appropriate delta.")
            return

        # Long call: 3 strikes further out (higher strike than short call)
        long_call = self._find_strike_outside(calls, short_call.strike, direction="up", steps=3)
        # Long put: 3 strikes further out (lower strike than short put)
        long_put = self._find_strike_outside(puts, short_put.strike, direction="down", steps=3)

        if long_call is None or long_put is None:
            self.Log("Could not find long legs 3 strikes further out.")
            return

        # Check that all legs have bid and ask
        for leg in [short_call, short_put, long_call, long_put]:
            if leg.bid_price <= 0 or leg.ask_price <= 0:
                self.Log(f"Leg {leg.symbol} lacks bid or ask. Skipping.")
                return

        # Place orders: short 1 each of short call and short put, long 1 each of long call and long put
        self._place_order(short_call, -1)
        self._place_order(short_put, -1)
        self._place_order(long_call, 1)
        self._place_order(long_put, 1)

        self.Log(
            f"Opened iron condor: short call {short_call.symbol} @ {short_call.strike}, "
            f"short put {short_put.symbol} @ {short_put.strike}, "
            f"long call {long_call.symbol} @ {long_call.strike}, "
            f"long put {long_put.symbol} @ {long_put.strike}"
        )

    def _close_condor(self):
        """Liquidate all positions."""
        for symbol in list(self.portfolio.keys()):
            if self.portfolio[symbol].quantity != 0:
                self.liquidate(symbol)
        self.Log("Liquidated all positions.")

    def _get_this_friday(self):
        """Return the date of the most recent or current Friday."""
        today = self.now.date()
        # DayOfWeek: MONDAY=0, TUESDAY=1, WEDNESDAY=2, THURSDAY=3, FRIDAY=4, SATURDAY=5, SUNDAY=6
        days_since_friday = (today.weekday() - 4) % 7
        friday = today - timedelta(days=days_since_friday)
        return friday

    def _find_nearest_delta(self, contracts, target_delta, side):
        """Find the contract with delta closest to the target delta magnitude."""
        if not contracts:
            return None

        if side == "call":
            # For calls, delta is positive; we want nearest to +0.10
            best = min(contracts, key=lambda c: abs(c.greeks.delta - target_delta))
        else:
            # For puts, delta is negative; we want nearest to -0.10 (magnitude 0.10)
            best = min(contracts, key=lambda c: abs(abs(c.greeks.delta) - target_delta))

        return best

    def _find_strike_outside(self, contracts, reference_strike, direction, steps):
        """Find the contract `steps` strikes further out from the reference strike."""
        if not contracts:
            return None

        # Get unique strikes sorted
        strikes = sorted(set(c.strike for c in contracts))

        # Find index of reference strike
        try:
            ref_idx = strikes.index(reference_strike)
        except ValueError:
            return None

        if direction == "up":
            target_idx = ref_idx + steps
        else:
            target_idx = ref_idx - steps

        if target_idx < 0 or target_idx >= len(strikes):
            return None

        target_strike = strikes[target_idx]

        # Find the contract with that strike
        for c in contracts:
            if c.strike == target_strike:
                return c

        return None

    def _place_order(self, contract, quantity):
        """Place a market order for the given contract and quantity."""
        order = self.market_order(contract.symbol, quantity)
        if order is not None:
            self.Log(f"Placed order: {contract.symbol} qty={quantity}")
