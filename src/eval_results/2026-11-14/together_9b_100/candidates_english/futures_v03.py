# region imports
from AlgorithmImports import *
# endregion

class EsRollAlgorithm(QCAlgorithm):
    _size = 1
    _symbol: Symbol = Symbol.create("ES", Market.USA, FuturesContract.Indices.SP_500_E_MINI)

    def initialize(self) -> None:
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.settings.automatic_indicator_warm_up = True
        self._symbol = self.add_future(self._symbol, self._get_mapping).symbol
        self.schedule.on(self.date_rules.every_day(self._symbol), self.time_rules.after_market_open(self._symbol, 1), self._rebalance)

    def _get_mapping(self, mapping: FuturesMap) -> None:
        mapping.data_normalization_mode = DataNormalizationMode.BACKWARDS_RATIO
        mapping.contract_depth = 3650

    def _rebalance(self) -> None:
        if not self.portfolio.invested:
            self.set_holdings(self._symbol, self._size)
        contract = self.securities[self._symbol].contract
        next_contract = self._symbol.get_next_contract(contract).symbol
        if next_contract != self._symbol:
            self.liquidate(self._symbol, tag=f"Rollover {self._symbol} -> {next_contract}")
            self.set_holdings(next_contract, self._size)
