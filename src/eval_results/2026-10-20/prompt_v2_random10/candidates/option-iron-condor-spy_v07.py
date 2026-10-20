from AlgorithmImports import *


class SpyWeeklyIronCondorIncome(QCAlgorithm):
    """
    Weekly SPY iron condor income reference for Sep-Dec 2024.

    Mechanics:
      - Open on Monday after market open.
      - Close before Friday's close.
      - Defined-risk wings: short call + short put near the money,
        long call + long put further out (fixed dollar offset as a
        proxy for a ~10 delta target, since LEAN does not provide delta).
      - Standard paper account (default brokerage).

    NOTE: LEAN option data does not include delta. Strike selection here
    uses a fixed offset from the underlying price as a reproducible proxy.
    Replace the offset logic with an external delta source if available.
    """

    def initialize(self):
        # Standard paper account: default brokerage, no live broker.
        self.set_start_date(2024, 9, 2)   # First Monday of September 2024
        self.set_end_date(2024, 12, 31)   # End of December 2024
        self.set_cash(100_000)
        self.set_warm_up(timedelta(days=10))

        # Underlying equity for reference price.
        self.spy = self.add_equity("SPY", Resolution.DAILY)

        # Option chain on SPY.
        self.option = self.add_option("SPY", Resolution.DAILY)
        # Filter: weekly expiries, strikes within a reasonable band.
        self.option.set_filter(
            strike_distance=0.10,
            expiry_distance=timedelta(days=7),
            option_type=OptionType.ALL
        )

        # Strike offsets (dollar distance from underlying) as a proxy
        # for a ~10 delta target. Tune these to match your internal model.
        self.short_offset = 15.0   # Short strikes ~15 dollars from spot
        self.wing_offset = 30.0    # Long wings ~30 dollars from spot

        # Track whether we are currently in a position.
        self.in_position = False

        # Schedule: open on Monday after market open, close before Friday close.
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 1),
            self.open_condor
        )
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 15),
            self.close_condor
        )

    def on_data(self, data: Slice):
        # No per-bar logic needed; all actions are scheduled.
        pass

    def _nearest_strike(self, chain: OptionChain, underlying_price: float,
                        offset: float, option_type: OptionType,
                        expiry: datetime) -> str:
        """
        Find the option symbol closest to (underlying_price +/- offset)
        for the given type and expiry.
        """
        target = underlying_price + offset if option_type == OptionType.CALL \
                 else underlying_price - offset
        best_symbol = None
        best_distance = float("inf")
        for symbol in chain:
            if symbol.option_type != option_type:
                continue
            if symbol.expiry.date() != expiry.date():
                continue
            distance = abs(symbol.strike - target)
            if distance < best_distance:
                best_distance = distance
                best_symbol = symbol
        return best_symbol

    def open_condor(self):
        if self.in_position:
            return
        if not self.option.is_ready:
            return

        # Use the nearest weekly expiry.
        chain = self.option_chain
        if not chain:
            return

        # Pick the nearest expiry that is at least a few days out.
        expiries = sorted(set(s.expiry for s in chain))
        if not expiries:
            return
        expiry = expiries[0]

        underlying_price = self.spy.price
        if underlying_price <= 0:
            return

        short_call = self._nearest_strike(chain, underlying_price,
                                          self.short_offset,
                                          OptionType.CALL, expiry)
        short_put = self._nearest_strike(chain, underlying_price,
                                         self.short_offset,
                                         OptionType.PUT, expiry)
        long_call = self._nearest_strike(chain, underlying_price,
                                         self.wing_offset,
                                         OptionType.CALL, expiry)
        long_put = self._nearest_strike(chain, underlying_price,
                                        self.wing_offset,
                                        OptionType.PUT, expiry)

        if not (short_call and short_put and long_call and long_put):
            self.log("Could not find all four condor legs; skipping open.")
            return

        # Defined-risk iron condor:
        #   Short 1 call, short 1 put, long 1 call (wing), long 1 put (wing).
        self.market_order(short_call, -1)
        self.market_order(short_put, -1)
        self.market_order(long_call, 1)
        self.market_order(long_put, 1)

        self.in_position = True
        self.log(f"Opened iron condor on {expiry.date()}: "
                 f"SC {short_call} SP {short_put} LC {long_call} LP {long_put}")

    def close_condor(self):
        if not self.in_position:
            return
        # Liquidate all option positions.
        self.liquidate()
        self.in_position = False
        self.log("Closed iron condor before Friday close.")
