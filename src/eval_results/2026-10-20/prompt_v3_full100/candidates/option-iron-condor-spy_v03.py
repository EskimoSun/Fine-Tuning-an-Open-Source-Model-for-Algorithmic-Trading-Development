from AlgorithmImports import *


class WeeklyCondor(QCAlgorithm):
    """
    Weekly iron condor on SPY.

    - Every Monday, 1 minute after the open: open a 1-contract iron condor
      in the SPY option chain expiring that Friday.
        * Short the call closest to +0.10 delta.
        * Short the put  closest to -0.10 delta.
        * Buy a call  3 strikes further out (above the short call).
        * Buy a put   3 strikes further out (below the short put).
      Skip the week if any leg has no bid or ask.
    - Every Friday, 5 minutes before the close: close all four legs.
    - Active window: Sept 1 to Dec 31, 2024. Starting capital: 100k.
    - Chain filtered to strikes -10..+10 and expirations 0..7 days for speed.
    """

    def initialize(self):
        # Starting capital
        self.set_cash(100_000)

        # Active trading window
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)

        # SPY option chain, minute resolution, filtered for speed.
        # Strikes -10..+10 and expirations 0..7 days from today.
        self.option = self.add_option("SPY", resolution=Resolution.MINUTE)
        self.option.set_filter(
            lambda u: u.strikes(-10, 10).expiration(0, 7)
        )

        # Track the four legs currently open so we can close them on Friday.
        self._legs = []  # list of Symbol

        # Monday entry: 1 minute after the SPY market open.
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 1),
            self.on_monday_open,
        )

        # Friday exit: 5 minutes before the SPY market close.
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 5),
            self.on_friday_close,
        )

    def on_monday_open(self):
        # Only act inside the active window.
        if not (datetime(2024, 9, 1) <= self.time <= datetime(2024, 12, 31, 23, 59, 59)):
            return

        # If we already hold a condor, do not open another.
        if self._legs:
            self.log("Already holding a condor; skipping Monday entry.")
            return

        chain = self.option_chains.get("SPY")
        if not chain:
            self.log("No SPY option chain available; skipping.")
            return

        # Find the Friday expiration (the chain is filtered to 0..7 days,
        # so the Friday of this week is present).
        friday_expiry = None
        for expiry in chain.expirations:
            if expiry.weekday() == DayOfWeek.FRIDAY:
                friday_expiry = expiry
                break
        if friday_expiry is None:
            self.log("No Friday expiration in the filtered chain; skipping.")
            return

        # Collect all contracts expiring this Friday.
        friday_contracts = [c for c in chain.values() if c.expiry == friday_expiry]
        if not friday_contracts:
            self.log("No contracts for Friday expiration; skipping.")
            return

        calls = [c for c in friday_contracts if c.right == OptionRight.CALL]
        puts = [c for c in friday_contracts if c.right == OptionRight.PUT]
        if not calls or not puts:
            self.log("Missing calls or puts for Friday expiration; skipping.")
            return

        # Sort by strike so we can step 3 strikes out.
        calls.sort(key=lambda c: c.strike)
        puts.sort(key=lambda c: c.strike)

        # Short call: closest to +0.10 delta.
        short_call = min(calls, key=lambda c: abs(c.greeks.delta - 0.10))
        # Short put: closest to -0.10 delta.
        short_put = min(puts, key=lambda c: abs(c.greeks.delta - (-0.10)))

        # Buy call: 3 strikes further out (higher strike) than the short call.
        buy_call = self._strike_out(calls, short_call.strike, direction=+1, steps=3)
        # Buy put: 3 strikes further out (lower strike) than the short put.
        buy_put = self._strike_out(puts, short_put.strike, direction=-1, steps=3)

        if buy_call is None or buy_put is None:
            self.log("Could not find wings 3 strikes out; skipping.")
            return

        # Validate that every leg has a two-sided quote (bid and ask).
        for leg in (short_call, short_put, buy_call, buy_put):
            if leg.bid_price <= 0 or leg.ask_price <= 0:
                self.log(
                    f"Leg {leg.symbol} has no bid/ask "
                    f"(bid={leg.bid_price}, ask={leg.ask_price}); skipping week."
                )
                return

        # Place the four one-contract legs.
        # Leg 1: short the call closest to +0.10 delta.
        self.market_order(short_call.symbol, -1)
        # Leg 2: short the put closest to -0.10 delta.
        self.market_order(short_put.symbol, -1)
        # Leg 3: buy the call 3 strikes further out (wing).
        self.market_order(buy_call.symbol, +1)
        # Leg 4: buy the put 3 strikes further out (wing).
        self.market_order(buy_put.symbol, +1)

        self._legs = [short_call.symbol, short_put.symbol, buy_call.symbol, buy_put.symbol]
        self.log(
            f"Opened iron condor expiring {friday_expiry.date()}: "
            f"short call {short_call.symbol} (Δ={short_call.greeks.delta:.3f}), "
            f"short put {short_put.symbol} (Δ={short_put.greeks.delta:.3f}), "
            f"buy call {buy_call.symbol}, buy put {buy_put.symbol}."
        )

    def on_friday_close(self):
        # Only act inside the active window.
        if not (datetime(2024, 9, 1) <= self.time <= datetime(2024, 12, 31, 23, 59, 59)):
            return

        if not self._legs:
            self.log("No condor open; nothing to close on Friday.")
            return

        # Close every leg we opened.
        for symbol in self._legs:
            self.liquidate(symbol)
        self.log(f"Closed all {len(self._legs)} condor legs on Friday.")
        self._legs = []

    @staticmethod
    def _strike_out(sorted_contracts, base_strike, direction, steps):
        """
        Return the contract `steps` strikes away from `base_strike` in the
        given direction (+1 = higher strike, -1 = lower strike), or None if
        it is not present in the filtered chain.
        """
        target = base_strike + direction * steps
        for c in sorted_contracts:
            if c.strike == target:
                return c
        return None
