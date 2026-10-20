from AlgorithmImports import *


class EsContinuousRollAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.symbol = self.add_future(
            "SP_500_E_MINI",
            resolution=Resolution.MINUTE,
            data_mapping_mode=DataMappingMode.LAST_TRADING_DAY,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            depth=0,
            extended_hours=True,
        )
        self.symbol.set_filter(0, 92)

        self.position_qty = 1

    def on_data(self, data: Slice):
        if self.symbol not in data.futures:
            return

        if not self.portfolio.has_open_positions(self.symbol):
            self.market_order(self.symbol, self.position_qty)

    def on_symbol_changed_events(self, event: SymbolChangedEvent):
        if event.old_symbol != self.symbol:
            return

        self.liquidate(event.old_symbol)
        self.market_order(event.new_symbol, self.position_qty)
