from AlgorithmImports import *


class IronCondorDeltaProxyAlgorithm(QCAlgorithm):
    """
    Weekly SPY iron condor (delta-free proxy).

    Entry: Monday, 1 minute after market open.
      - Expiry: the Friday of the current week (0-7 day window).
      - Short call: nearest strike to underlying price (ATM proxy for +0.10 delta).
      - Short put:  nearest strike to underlying price (ATM proxy for -0.10 delta).
      - Wings: 3 strikes out on each side.
      - Skip entry if any of the 4 legs is missing a valid bid/ask.
      - Buy 1x iron condor via OptionStrategies.iron_condor.

    Exit: Friday, 5 minutes before market close -> liquidate all positions.

    Window: 2024-09-01 to 2024-12-31, starting capital $100,000.
    """

    def initialize(self):
        self.set_start_date(datetime(2024, 9, 1))
        self.set_end_date(datetime(2024, 12, 31))
        self.set_cash(100_000)

        # Underlying equity for reference price and market hours.
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # Option chain on SPY, minute resolution.
        self.option = self.add_option("SPY", resolution=Resolution.MINUTE)
        # Strikes within +/-10 of ATM, expirations 0-7 days out.
        self.option.set_filter(
            lambda u: u.include_weeklys().strikes(-10, 10).expiration(0, 7)
        )

        # Track whether we currently hold a condor (to avoid double entry).
        self._holding_condor = False

        # Schedule entry: every Monday, 1 minute after market open.
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 1),
            self.on_entry,
        )

        # Schedule exit: every Friday, 5 minutes before market close.
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 5),
            self.on_exit,
        )

    def on_data(self, slice: Slice):
        # No per-bar logic needed; all actions are scheduled.
        pass

    def _find_expiry_friday(self, chain: OptionChain) -> datetime:
        """Return the Friday expiry (0-7 days out) present in the chain."""
        today = self.time.date
        # Find the next Friday within 0-7 days.
        days_ahead = (4 - today.weekday()) % 7  # Friday is weekday 4
        if days_ahead == 0:
            days_ahead = 7  # If today is Friday, use next Friday (0-7 window)
        target = today + timedelta(days=days_ahead)
        # Match by date only.
        for expiry in chain.expirations:
            if expiry.date() == target:
                return expiry
        return None

    def _nearest_strike(self, chain: OptionChain, expiry: datetime, underlying_price: float) -> float:
        """Return the strike in the chain closest to the underlying price."""
        best = None
        best_diff = float("inf")
        for strike in chain.strikes:
            diff = abs(strike - underlying_price)
            if diff < best_diff:
                best_diff = diff
                best = strike
        return best

    def _get_contract(self, chain: OptionChain, expiry: datetime, strike: float, right: OptionRight):
        """Find a contract in the chain matching expiry, strike, and right."""
        for contract in chain:
            if (
                contract.expiry.date() == expiry.date()
                and abs(contract.strike - strike) < 1e-9
                and contract.right == right
            ):
                return contract
        return None

    def _has_valid_quote(self, contract) -> bool:
        """A leg is tradable if it has a positive bid and ask."""
        return contract.bid_price > 0 and contract.ask_price > 0

    def on_entry(self):
        if self._holding_condor:
            return

        chain = self.option_chain
        if chain is None or len(chain) == 0:
            self.Log("No option chain available; skipping entry.")
            return

        expiry = self._find_expiry_friday(chain)
        if expiry is None:
            self.Log("No Friday expiry found in 0-7 day window; skipping entry.")
            return

        underlying_price = self.spy.price
        if underlying_price <= 0:
            self.Log("Underlying price unavailable; skipping entry.")
            return

        # ATM proxy for short legs.
        short_strike = self._nearest_strike(chain, expiry, underlying_price)
        if short_strike is None:
            self.Log("Could not determine nearest strike; skipping entry.")
            return

        # Wings 3 strikes out.
        wing_offset = 3.0
        call_wing_strike = short_strike + wing_offset
        put_wing_strike = short_strike - wing_offset

        # Locate all four legs.
        short_call = self._get_contract(chain, expiry, short_strike, OptionRight.CALL)
        short_put = self._get_contract(chain, expiry, short_strike, OptionRight.PUT)
        long_call = self._get_contract(chain, expiry, call_wing_strike, OptionRight.CALL)
        long_put = self._get_contract(chain, expiry, put_wing_strike, OptionRight.PUT)

        legs = {
            "short_call": short_call,
            "short_put": short_put,
            "long_call": long_call,
            "long_put": long_put,
        }

        # Skip if any leg is missing.
        missing = [name for name, c in legs.items() if c is None]
        if missing:
            self.Log(f"Missing legs {missing}; skipping entry.")
            return

        # Skip if any leg lacks a valid bid/ask.
        bad_quote = [name for name, c in legs.items() if not self._has_valid_quote(c)]
        if bad_quote:
            self.Log(f"Legs without valid bid/ask {bad_quote}; skipping entry.")
            return

        # Build the iron condor: short the inner strikes, long the outer wings.
        # OptionStrategies.iron_condor expects (short_call, short_put, long_call, long_put).
        order = OptionStrategies.iron_condor(
            short_call, short_put, long_call, long_put, 1
        )
        self.submit_order(order)
        self._holding_condor = True
        self.Log(
            f"Entered iron condor: short {short_strike} C/P, "
            f"long {call_wing_strike} C / {put_wing_strike} P, expiry {expiry.date()}."
        )

    def on_exit(self):
        if not self._holding_condor:
            return
        self.liquidate()
        self._holding_condor = False
        self.Log("Liquidated all positions (Friday close exit).")
