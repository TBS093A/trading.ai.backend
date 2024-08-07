from api.abstract import AbstractAPI

from time import sleep


class AbstractTransactionStrategy:

    def __init__(self, api: AbstractAPI) -> None:
        self.api = api

    def invoke(self):

        pass


class SingleShotTransactionStrategy(
    AbstractTransactionStrategy
):

    def invoke(self, coin: str, currency: str, sell_time_after_buy: int = 30):

        self.api.buy(
           coin = coin,
           currency_size = 1.0,
           used_currency = currency
        )

        sleep(sell_time_after_buy)

        self.api.sell(
           coin = coin,
           coin_size = 1.0,
           used_currency = currency
        )


class DistributedRiskBalancedTransactionStrategy(
    AbstractTransactionStrategy
):

    def invoke(self, coin: str, currency: str, sell_time_after_buy: int = 5, sell_repeats: int = 10, sell_percent_per_transaction: float: 0.25, time_between_sells: int = 1,):

        self.api.buy(
           coin = coin,
           currency_size = 1.0,
           used_currency = currency
        )

        sleep(sell_time_after_buy)

        for repeat_index in range(0, sell_repeats):

            self.api.sell(
               coin = coin,
               coin_size = sell_percent_per_transaction,
               used_currency = currency
            )

            sleep(time_between_sells)

        self.api.sell(
            coin = coin,
            coin_size = 1.0,
            used_currency = currency
        )


class DistributedRiskSummationTransactionStrategy(
    AbstractTransactionStrategy
):

    def invoke(self, coin: str, currency: str, sell_time_after_buy: int = 5, sell_percent_per_transaction: int = 0.05, time_between_sells: int = 1):

        self.api.buy(
           coin = coin,
           currency_size = 1.0,
           used_currency = currency
        )

        sleep(sell_time_after_buy)

        while sell_percent_per_transaction < 1.0:

            sell_percent_per_transaction += sell_percent_per_transaction

            self.api.sell(
               coin = coin,
               coin_size = sell_percent_per_transaction,
               used_currency = currency
            )

            sleep(time_between_sells)

        self.api.sell(
            coin = coin,
            coin_size = 1.0,
            used_currency = currency
        )

