from AlgorithmImports import *


class SpyIronCondorIncomeReference(QCAlgorithm):
    """Weekly SPY iron condor income reference for Sep-Dec 2024.

    Opens a defined-risk iron condor on Monday and closes it before Friday's close.
    Strikes are selected near 10 delta using the option chain greeks.
    """

    def initialize(self):
        self.set_start_date(2024, 9, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Underlying
        self.spy = self.add_equity("SPY", resolution=Resolution.MINUTE)

        # Option chain
        self.option = self.add_option("SPY", resolution=Resolution.MINUTE)
        # Keep only weekly expirations within 0-7 days, strikes within +/-10 of ATM
        self.option.set_filter(
            lambda u: u.include_weeklys().strikes(-10, 10).expiration(0, 7)
        )

        # Schedule: open Monday after market open, close Friday before market close
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 5),
            self.open_iron_condor
        )
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 15),
            self.close_iron_condor
        )

        # Track current position
        self._positions = []  # list of (symbol, quantity)

    def on_data(self, data: Slice):
        pass

    def open_iron_condor(self):
        """Open a weekly iron condor near 10 delta."""
        if self._positions:
            return  # already in a position

        # Get the nearest weekly expiration
        chain = self.option_chain()
        if not chain:
            return

        # Find the nearest expiration
        expirations = sorted(set(c.expiry for c in chain))
        if not expirations:
            return
        nearest_expiry = expirations[0]

        # Get ATM strike
        spy_price = self.spy.price
        atm_strikes = [c for c in chain if c.expiry == nearest_expiry]
        if not atm_strikes:
            return

        # Find strikes closest to ATM
        calls = [c for c in atm_strikes if c.right == OptionRight.CALL]
        puts = [c for c in atm_strikes if c.right == OptionRight.PUT]

        if not calls or not puts:
            return

        # Select strikes near 10 delta
        # For calls: we want the call with delta closest to 0.10 (short call)
        # For puts: we want the put with delta closest to -0.10 (short put)
        short_call = self._select_strike_by_delta(calls, 0.10)
        short_put = self._select_strike_by_delta(puts, -0.10)

        if short_call is None or short_put is None:
            return

        # Wing strikes: one strike width away from the short strikes
        # Determine strike width
        call_strikes = sorted(set(c.strike for c in calls))
        put_strikes = sorted(set(p.strike for p in puts))

        # Find the strike width (typically 1 or 2 for SPY)
        strike_width = 1
        if len(call_strikes) > 1:
            diffs = [call_strikes[i+1] - call_strikes[i] for i in range(len(call_strikes)-1)]
            strike_width = min(d for d in diffs if d > 0) if any(d > 0 for d in diffs) else 1

        # Long call wing: one strike above short call
        long_call_strike = short_call.strike + strike_width
        # Long put wing: one strike below short put
        long_put_strike = short_put.strike - strike_width

        # Find the long wing contracts
        long_call = self._find_contract(calls, long_call_strike, nearest_expiry)
        long_put = self._find_contract(puts, long_put_strike, nearest_expiry)

        if long_call is None or long_put is None:
            return

        # Calculate premium
        short_call_premium = (short_call.bid_price + short_call.ask_price) / 2
        short_put_premium = (short_put.bid_price + short_put.ask_price) / 2
        long_call_premium = (long_call.bid_price + long_call.ask_price) / 2
        long_put_premium = (long_put.bid_price + long_put.ask_price) / 2

        net_credit = (short_call_premium + short_put_premium - long_call_premium - long_put_premium) * 100

        if net_credit <= 0:
            self.Log(f"No positive credit for iron condor. Skipping.")
            return

        # Determine number of contracts based on account size
        # Risk per contract = (strike_width - net_credit/100) * 100
        risk_per_contract = (strike_width - net_credit / 100) * 100
        max_risk = self.portfolio.cash * 0.02  # 2% of account
        num_contracts = max(1, int(max_risk / risk_per_contract)) if risk_per_contract > 0 else 1

        self.Log(f"Opening iron condor: short {short_call.strike}C / {short_put.strike}P, "
                 f"long {long_call.strike}C / {long_put.strike}P, "
                 f"expiry {nearest_expiry.date()}, {num_contracts} contracts, "
                 f"net credit ${net_credit:.2f}")

        # Place orders
        # Short the calls and puts
        self.market_order(short_call.symbol, -num_contracts)
        self.market_order(short_put.symbol, -num_contracts)
        # Long the wings
        self.market_order(long_call.symbol, num_contracts)
        self.market_order(long_put.symbol, num_contracts)

        # Track positions
        self._positions = [
            (short_call.symbol, -num_contracts),
            (short_put.symbol, -num_contracts),
            (long_call.symbol, num_contracts),
            (long_put.symbol, num_contracts),
        ]

    def close_iron_condor(self):
        """Close the iron condor before Friday's close."""
        if not self._positions:
            return

        self.Log("Closing iron condor position.")
        for symbol, quantity in self._positions:
            self.liquidate(symbol)

        self._positions = []

    def option_chain(self):
        """Get the current option chain for SPY."""
        # Access the option chain from the option data
        # In LEAN, we can access the chain via the option symbol
        chain = []
        # We need to get the chain from the data slice
        # Since we're in a scheduled event, we need to access the latest data
        # Use the option's underlying to get the chain
        # Actually, in LEAN Python, we can access the chain via self.option
        # Let's use a different approach: store the chain in on_data
        return self._last_chain

    def _select_strike_by_delta(self, contracts, target_delta):
        """Select the contract with delta closest to target_delta."""
        if not contracts:
            return None
        best = None
        best_diff = float('inf')
        for c in contracts:
            delta = c.greeks.delta
            diff = abs(delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best = c
        return best

    def _find_contract(self, contracts, strike, expiry):
        """Find a contract with the given strike and expiry."""
        for c in contracts:
            if c.strike == strike and c.expiry == expiry:
                return c
        return None

    def on_data(self, data: Slice):
        """Store the latest option chain for use in scheduled events."""
        if self.option.symbol in data.option_chains:
            chain = data.option_chains[self.option.symbol]
            self._last_chain = list(chain)
        else:
            # Try to get the chain from the option data
            if "SPY" in data.option_chains:
                chain = data.option_chains["SPY"]
                self._last_chain = list(chain)

    def __init__(self):
        super().__init__()
        self._last_chain = []
