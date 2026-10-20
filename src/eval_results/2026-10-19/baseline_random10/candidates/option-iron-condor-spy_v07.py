# QuantConnect LEAN Algorithm - Weekly SPY Iron Condor (Sep-Dec 2024)
# Paper account, opened Monday, closed before Friday close

from AlgorithmImports import *

class SPYWeeklyIronCondor(QCAlgorithm):
    def Initialize(self):
        # Paper account
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.SetStartDate(2024, 9, 2)   # First Monday of Sep 2024
        self.SetEndDate(2024, 12, 31)
        self.SetCash(100000)

        # SPY equity
        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol

        # Weekly schedule: run on Mondays
        self.Schedule.On(
            date_rule=DateRules.Weekly(Week.Monday),
            time_rule=TimeRules.AfterMarketOpen("SPY", 5, TimeUnit.Minutes),
            action=self.OpenIronCondor
        )

        # Close before Friday close
        self.Schedule.On(
            date_rule=DateRules.Weekly(Week.Friday),
            time_rule=TimeRules.BeforeMarketClose("SPY", 15, TimeUnit.Minutes),
            action=self.CloseIronCondor
        )

        # Track positions
        self.positions = []

    def OnData(self, data: Slice):
        pass

    def OpenIronCondor(self, context: object):
        """Open a weekly iron condor on SPY."""
        # Get current SPY price
        spy_price = self.Securities[self.spy].Price
        if spy_price <= 0:
            return

        # Approximate 10-delta strikes using a simple heuristic:
        # For SPY, 10-delta is roughly 1.5-2% away from spot for weekly options.
        # We'll use a fixed percentage offset as a reference implementation.
        delta_offset_pct = 0.015  # 1.5% for ~10 delta weekly
        wing_width_pct = 0.01     # 1% wing width

        # Calculate strikes
        short_put_strike = round(spy_price * (1 - delta_offset_pct) / 5) * 5
        short_call_strike = round(spy_price * (1 + delta_offset_pct) / 5) * 5
        long_put_strike = round((short_put_strike - spy_price * wing_width_pct) / 5) * 5
        long_call_strike = round((short_call_strike + spy_price * wing_width_pct) / 5) * 5

        # Ensure strikes are positive and reasonable
        if short_put_strike <= 0 or long_put_strike <= 0:
            return

        # Find the nearest weekly expiration (next Friday)
        expiration = self.NextWeeklyExpiration()

        # Build option chains
        put_chain = self.OptionChain(self.spy, expiration, OptionStyle.American, OptionRight.Put)
        call_chain = self.OptionChain(self.spy, expiration, OptionStyle.American, OptionRight.Call)

        # Find closest strikes in the chains
        short_put_symbol = self.FindClosestStrike(put_chain, short_put_strike)
        long_put_symbol = self.FindClosestStrike(put_chain, long_put_strike)
        short_call_symbol = self.FindClosestStrike(call_chain, short_call_strike)
        long_call_symbol = self.FindClosestStrike(call_chain, long_call_strike)

        if not all([short_put_symbol, long_put_symbol, short_call_symbol, long_call_symbol]):
            self.Log("Could not find all required option strikes.")
            return

        # Check if we already have positions
        if self.positions:
            self.Log("Already have open positions, skipping.")
            return

        # Order quantities: 1 contract per leg
        qty = 1

        # Sell short put, buy long put, sell short call, buy long call
        self.positions.append(self.OrderOption(short_put_symbol, -qty))
        self.positions.append(self.OrderOption(long_put_symbol, qty))
        self.positions.append(self.OrderOption(short_call_symbol, -qty))
        self.positions.append(self.OrderOption(long_call_symbol, qty))

        self.Log(f"Opened Iron Condor: SP={spy_price:.2f}, "
                 f"ShortPut={short_put_strike}, LongPut={long_put_strike}, "
                 f"ShortCall={short_call_strike}, LongCall={long_call_strike}, "
                 f"Exp={expiration}")

    def CloseIronCondor(self, context: object):
        """Close all open iron condor positions."""
        if not self.positions:
            return

        for order in self.positions:
            if order is not None and not order.IsClosed:
                # Reverse the position
                self.Liquidate(order.Symbol)

        self.positions = []
        self.Log("Closed all iron condor positions.")

    def NextWeeklyExpiration(self) -> datetime:
        """Return the next Friday's date for weekly option expiration."""
        today = self.Time.Date
        # Find next Friday
        days_ahead = (4 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    def FindClosestStrike(self, chain: OptionChain, target_strike: float):
        """Find the option symbol with the strike closest to target."""
        if not chain:
            return None
        closest = None
        min_diff = float('inf')
        for option in chain:
            diff = abs(option.Strike - target_strike)
            if diff < min_diff:
                min_diff = diff
                closest = option.Symbol
        return closest
