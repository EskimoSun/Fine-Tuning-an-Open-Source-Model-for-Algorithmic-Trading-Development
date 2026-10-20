# QuantConnect LEAN Algorithm
# Iron Condor on SPY: Sell 0.10 delta call/put, buy 3 strikes further out
# Every Monday 1 minute after open, close Friday 5 minutes before close
# Sept 1 to Dec 31 2024, $100k

from AlgorithmImports import *

class IronCondorSPYAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2024, 9, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(100_000)

        # SPY equity
        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol

        # Options on SPY
        self.options = self.AddOption("SPY", Resolution.Minute, DataNormalizationMode.Adjusted)
        self.options.SetFilter(-1, 0, timedelta(days=7), timedelta(days=30))
        self.options.SetUniverseSelection(self.OptionUniverseFilter)

        # Track open positions
        self.open_positions = []  # list of (symbol, quantity)

        # Schedule: Monday 1 minute after open (9:31 ET), Friday 5 minutes before close (15:55 ET)
        self.Schedule.On(self.DateRules.Every(DayOfWeek.Monday).AtMarketOpen(1),
                         self.TimeRules.AfterMarketOpen("SPY", 1, TimeUnit.Minutes),
                         self.OpenIronCondor)
        self.Schedule.On(self.DateRules.Every(DayOfWeek.Friday).AtMarketClose(5),
                         self.TimeRules.BeforeMarketClose("SPY", 5, TimeUnit.Minutes),
                         self.CloseAllPositions)

    def OptionUniverseFilter(self, slice):
        """Filter options: only SPY, expiring this Friday, within 7-30 days."""
        if not slice.HasOptionData:
            return []

        # Get the current Friday expiry
        today = self.Time.Date
        # Find the next Friday
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7
        target_expiry = today + timedelta(days=days_until_friday)

        symbols = []
        for option in slice.OptionData:
            symbol = option.Symbol
            # Check if it's SPY option
            if symbol.Underlying != self.spy:
                continue
            # Check expiry
            if symbol.Expiry.Date != target_expiry:
                continue
            # Only include options with valid bid/ask
            if option.Bid <= 0 or option.Ask <= 0:
                continue
            symbols.append(symbol)

        return symbols

    def OpenIronCondor(self):
        """Open iron condor: sell 0.10 delta call/put, buy 3 strikes further out."""
        # Get current SPY price
        spy_price = self.Securities[self.spy].Price
        if spy_price <= 0:
            self.Log("SPY price not available, skipping.")
            return

        # Get all SPY options expiring this Friday
        today = self.Time.Date
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0:
            days_until_friday = 7
        target_expiry = today + timedelta(days=days_until_friday)

        # Collect all valid options for this expiry
        calls = []
        puts = []

        for symbol in self.Securities:
            if not symbol.HasOptionData:
                continue
            if symbol.Underlying != self.spy:
                continue
            if symbol.Expiry.Date != target_expiry:
                continue

            option_data = self.Securities[symbol]
            if option_data.Bid <= 0 or option_data.Ask <= 0:
                continue

            # Get delta
            delta = self.GetDelta(symbol)
            if delta is None:
                continue

            if symbol.OptionRight == OptionRight.Call:
                calls.append((symbol, delta, option_data.Bid, option_data.Ask))
            elif symbol.OptionRight == OptionRight.Put:
                puts.append((symbol, delta, option_data.Bid, option_data.Ask))

        if not calls or not puts:
            self.Log("No valid calls or puts found, skipping.")
            return

        # Sort calls by delta (ascending) and find closest to 0.10
        calls.sort(key=lambda x: abs(x[1] - 0.10))
        puts.sort(key=lambda x: abs(x[1] - (-0.10)))

        # Get the closest to 0.10 delta call and -0.10 delta put
        sell_call = calls[0]
        sell_put = puts[0]

        # Find the strike prices
        sell_call_strike = sell_call[0].Strike
        sell_put_strike = sell_put[0].Strike

        # Find calls 3 strikes further out (higher strike)
        # Get all unique strikes for calls
        call_strikes = sorted(set(c[0].Strike for c in calls))
        put_strikes = sorted(set(p[0].Strike for p in puts))

        # Find the index of sell_call_strike in call_strikes
        try:
            call_idx = call_strikes.index(sell_call_strike)
        except ValueError:
            self.Log("Sell call strike not found in call strikes list.")
            return

        # Buy call is 3 strikes further out (higher strike)
        buy_call_idx = call_idx + 3
        if buy_call_idx >= len(call_strikes):
            self.Log("Not enough call strikes to buy 3 further out.")
            return
        buy_call_strike = call_strikes[buy_call_idx]

        # Find the index of sell_put_strike in put_strikes
        try:
            put_idx = put_strikes.index(sell_put_strike)
        except ValueError:
            self.Log("Sell put strike not found in put strikes list.")
            return

        # Buy put is 3 strikes further out (lower strike)
        buy_put_idx = put_idx - 3
        if buy_put_idx < 0:
            self.Log("Not enough put strikes to buy 3 further out.")
            return
        buy_put_strike = put_strikes[buy_put_idx]

        # Find the actual option symbols for the buy legs
        buy_call_symbol = None
        buy_put_symbol = None

        for c in calls:
            if c[0].Strike == buy_call_strike:
                buy_call_symbol = c[0]
                break

        for p in puts:
            if p[0].Strike == buy_put_strike:
                buy_put_symbol = p[0]
                break

        if buy_call_symbol is None or buy_put_symbol is None:
            self.Log("Could not find buy leg symbols.")
            return

        # Check that all legs have valid bid/ask
        for symbol in [sell_call[0], sell_put[0], buy_call_symbol, buy_put_symbol]:
            sec = self.Securities[symbol]
            if sec.Bid <= 0 or sec.Ask <= 0:
                self.Log(f"Leg {symbol} has no valid bid/ask, skipping.")
                return

        # Execute the iron condor
        # Sell 1 call (short), sell 1 put (short), buy 1 call (long), buy 1 put (long)
        self.Log(f"Opening Iron Condor: Sell Call {sell_call[0]} @ {sell_call[2]}, "
                 f"Sell Put {sell_put[0]} @ {sell_put[2]}, "
                 f"Buy Call {buy_call_symbol} @ {self.Securities[buy_call_symbol].Bid}, "
                 f"Buy Put {buy_put_symbol} @ {self.Securities[buy_put_symbol].Bid}")

        # Sell the call
        order = self.OrderOption(sell_call[0], -1, OptionStyle.American, OptionRight.Call)
        if order is None or order.Status == OrderStatus.Filled:
            self.open_positions.append((sell_call[0], -1))

        # Sell the put
        order = self.OrderOption(sell_put[0], -1, OptionStyle.American, OptionRight.Put)
        if order is None or order.Status == OrderStatus.Filled:
            self.open_positions.append((sell_put[0], -1))

        # Buy the call
        order = self.OrderOption(buy_call_symbol, 1, OptionStyle.American, OptionRight.Call)
        if order is None or order.Status == OrderStatus.Filled:
            self.open_positions.append((buy_call_symbol, 1))

        # Buy the put
        order = self.OrderOption(buy_put_symbol, 1, OptionStyle.American, OptionRight.Put)
        if order is None or order.Status == OrderStatus.Filled:
            self.open_positions.append((buy_put_symbol, 1))

        self.Log(f"Iron Condor opened with {len(self.open_positions)} legs.")

    def CloseAllPositions(self):
        """Close all open positions."""
        if not self.open_positions:
            self.Log("No open positions to close.")
            return

        self.Log(f"Closing {len(self.open_positions)} positions.")

        for symbol, quantity in self.open_positions:
            if symbol in self.Securities:
                sec = self.Securities[symbol]
                if sec.Bid > 0 and sec.Ask > 0:
                    # Close by ordering opposite quantity
                    close_qty = -quantity
                    self.OrderOption(symbol, close_qty, sec.Style, sec.Right)
                    self.Log(f"Closing {symbol} with quantity {close_qty}")

        self.open_positions = []

    def GetDelta(self, symbol):
        """Get the delta of an option using the Black-Scholes model."""
        try:
            sec = self.Securities[symbol]
            underlying_price = self.Securities[self.spy].Price
            strike = symbol.Strike
            expiry = symbol.Expiry
            days_to_expiry = (expiry.Date - self.Time.Date).days
            if days_to_expiry <= 0:
                return None
            t = days_to_expiry / 365.0
            r = 0.05  # Risk-free rate assumption
            sigma = 0.20  # Volatility assumption

            import math
            d1 = (math.log(underlying_price / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
            d2 = d1 - sigma * math.sqrt(t)

            # Standard normal CDF approximation
            def norm_cdf(x):
                return 0.5 * (1 + math.erf(x / math.sqrt(2)))

            if symbol.OptionRight == OptionRight.Call:
                delta = norm_cdf(d1)
            else:
                delta = norm_cdf(d1) - 1

            return delta
        except Exception as e:
            self.Log(f"Error calculating delta for {symbol}: {e}")
            return None
