from AlgorithmImports import *

class BB202DipBuy(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 10, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)
        self.set_warm_up(20, Resolution.DAILY)

        self.spy = self.add_equity("SPY", Resolution.DAILY, DataNormalizationMode.BACKWARDS_RATIO).symbol
        self.bb = self.bb(self.spy, 20, 2, Resolution.DAILY)

        self.in_position = False
        self.entry_price = 0.0

        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.at_market_close(self.spy),
            self.check_signal
        )

    def check_signal(self):
        if not self.bb.is_ready:
            return

        price = self.securities[self.spy].price
        upper = self.bb.upper_band.current.value
        middle = self.bb.middle_band.current.value
        lower = self.bb.lower_band.current.value

        if not self.in_position:
            if price <= lower:
                self.set_holdings(self.spy, 1.0)
                self.in_position = True
                self.entry_price = price
                self.log(f"BUY SPY at {price:.2f} (lower band {lower:.2f})")
        else:
            if price >= middle:
                self.liquidate(self.spy)
                self.in_position = False
                self.log(f"SELL SPY at {price:.2f} (midline {middle:.2f})")
