from AlgorithmImports import *

class BB202DipBuyMidlineExit(QCAlgorithm):
    """
    SPY Bollinger Band (20, 2) dip-buy strategy.
    - Daily check after market open.
    - Buy when price touches/crosses below the lower band.
    - Exit when price crosses back above the middle band (SMA).
    - Runs only during Q4 2024 (Oct 1 - Dec 31, 2024).
    """

    def initialize(self):
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100_000)

        self.spy = self.add_equity("SPY", resolution=Resolution.DAILY)

        self._bb = self.bb(self.spy.symbol, 20, 2, resolution=Resolution.DAILY)

        self._in_position = False

        self.schedule.on(
            self.date_rules.every_day(self.spy.symbol),
            self.time_rules.at(9, 35),
            self.on_daily_check
        )

    def on_daily_check(self):
        if not self._bb.is_ready:
            return

        price = self.spy.price
        lower = self._bb.lower_band.current.value
        middle = self._bb.middle_band.current.value

        if not self._in_position:
            if price <= lower:
                self.set_holdings(self.spy.symbol, 1.0)
                self._in_position = True
                self.log(f"BUY SPY at {price:.2f} (lower band {lower:.2f})")
        else:
            if price >= middle:
                self.liquidate(self.spy.symbol)
                self._in_position = False
                self.log(f"SELL SPY at {price:.2f} (midline {middle:.2f})")
