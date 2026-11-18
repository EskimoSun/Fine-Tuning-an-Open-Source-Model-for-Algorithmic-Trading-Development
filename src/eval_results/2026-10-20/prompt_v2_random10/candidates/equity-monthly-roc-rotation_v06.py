from AlgorithmImports import *


class RocRotationAlgorithm(QCAlgorithm):
    """
    Monthly rotation among SPY, EFA, EEM, AGG, GLD based on 60-day Rate of Change.
    At the start of each month (1 minute after market open), the top 3 securities
    by ROC are selected and allocated 1/3 of the portfolio each. If all ROC values
    are negative, all positions are liquidated.
    """

    def initialize(self):
        # Set start and end dates
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 12, 31)

        # Set initial cash
        self.set_cash(100_000)

        # Define the universe of securities
        self.symbols = ["SPY", "EFA", "EEM", "AGG", "GLD"]

        # Add equities at minute resolution
        for symbol in self.symbols:
            equity = self.add_equity(symbol, resolution=Resolution.MINUTE)
            # Attach a 60-day ROC indicator computed on daily bars
            roc = self.roc(symbol, 60, Resolution.DAILY)
            # Store the indicator on the security object for easy access
            equity.set_indicator(roc)

        # Schedule the rotation logic at the start of each month, 1 minute after market open
        for symbol in self.symbols:
            self.schedule.on(
                self.date_rules.month_start(symbol),
                self.time_rules.after_market_open(symbol, 1),
                self.rotate_portfolio
            )

    def rotate_portfolio(self, context):
        """
        Select top 3 securities by 60-day ROC and allocate 1/3 each.
        If all ROC values are negative, liquidate all positions.
        """
        # Collect ROC values for all securities
        roc_values = {}
        for symbol in self.symbols:
            security = self.securities[symbol]
            # Retrieve the ROC indicator attached to the security
            roc_indicator = security.get_indicator()
            if roc_indicator is not None and roc_indicator.is_ready:
                roc_values[symbol] = roc_indicator.current.value
            else:
                # If indicator is not ready, skip this security
                roc_values[symbol] = float("-inf")

        # Check if all ROC values are negative
        if all(roc < 0 for roc in roc_values.values()):
            self.liquidate()
            self.log("All ROC values are negative. Liquidating all positions.")
            return

        # Sort symbols by ROC in descending order and pick top 3
        sorted_symbols = sorted(roc_values.keys(), key=lambda s: roc_values[s], reverse=True)
        top_3 = sorted_symbols[:3]

        # Liquidate any positions not in the top 3
        for symbol in self.symbols:
            if symbol not in top_3:
                self.liquidate(symbol)

        # Allocate 1/3 of the portfolio to each of the top 3 securities
        target_weight = 1.0 / 3.0
        for symbol in top_3:
            self.set_holdings(symbol, target_weight)

        self.log(f"Rotated to top 3 by ROC: {top_3}")
