from api.abstract import AbstractAPI

from time import sleep
import logging


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


class AbstractTransactionStrategy:

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method
    ) -> None:
        self.api = api
        self.__telegram_client_credentials = telegram_client_credentials
        self.__telegram_sending_method = telegram_sending_method

    async def _send_message_to_telegram(self, message: str):
        print(message)
        return await self.__telegram_sending_method(
            **dict(
                self.__telegram_client_credentials,
                **{
                    "message": message
                }
            )
        )

    async def invoke(self):

        pass


class SingleShotTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method,
        sell_time_after_buy: int = 30
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )
        self.sell_time_after_buy = sell_time_after_buy


    async def invoke(
        self,
        coin: str,
        currency: str = "USDT",
        buy_amount: float = 1.0,
        last_sell_amount: float = 1.0
    ):

        self.api.buy(
           coin = coin,
           currency_size = buy_amount,
           used_currency = currency
        )

        await self._send_message_to_telegram(
            message = f"Buy { coin } by { int(buy_amount * 100) }% of available { currency }\n\nWaiting { self.sell_time_after_buy }s for single shot sell..."
        )

        sleep(sell.sell_time_after_buy)

        self.api.sell(
           coin = coin,
           coin_size = last_sell_amount,
           used_currency = currency
        )

        await self._send_message_to_telegram(
            message = f"Sell { int(last_sell_amount * 100) }% of available { coin } for { currency }"
        )


class SingleShotAfterTimeTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method,
        sell_time_after_buy: int = 30,
        DEBUG: bool = False,
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )
        self.sell_time_after_buy = sell_time_after_buy
        self.__DEBUG = DEBUG

    async def invoke(
        self,
        coin: str,
        currency: str = "USDT",
        buy_amount: float = 1.0,
        last_sell_amount: float = 1.0,
        buy = True,
        sell = True,
    ):

        if buy:

            try:
                buy_info = self.api.buy(
                    coin = coin,
                    currency_percent_size_to_buy = buy_amount,
                    used_currency = currency
                )
            except Exception as error:
                buy_info = error

            message = f"Buy { coin } by { int(buy_amount * 100) }% of available { currency }\n\nBuy Information:\n\n{ buy_info }\n\nWaiting { self.sell_time_after_buy }s for single shot risk sell transaction..."

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = message
                )

            if self.__DEBUG:

                print(
                    message
                )

            sleep(self.sell_time_after_buy)

        if sell:

            try:
                last_sell_info = self.api.sell(
                    coin = coin,
                    coin_percent_size_to_sell = last_sell_amount,
                    used_currency = currency
                )
            except Exception as error:
                last_sell_info = error

            message = f"Sell { int(last_sell_amount * 100) }% of available { coin } for { currency }\n\nLast sell information:\n\n{ last_sell_info }"

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = message
                )

            if self.__DEBUG:

                print(
                    message
                )


class DistributedRiskBalancedTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method,
        sell_time_after_buy: int = 5,
        sell_repeats: int = 10,
        sell_percent_per_transaction: float = 0.25,
        time_between_sells: int = 1
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )
        self.sell_time_after_buy = sell_time_after_buy
        self.sell_repeats = sell_repeats
        self.sell_percent_per_transaction = sell_percent_per_transaction
        self.time_between_sells = time_between_sells


    async def invoke(
        self,
        coin: str,
        currency: str = "USDT",
        buy_amount: float = 1.0,
        last_sell_amount: float = 1.0
    ):

        self.api.buy(
           coin = coin,
           currency_size = buy_amount,
           used_currency = currency
        )

        await self._send_message_to_telegram(
            message = f"Buy { coin } by { int(buy_amount * 100) }% of available { currency }\n\nWaiting { self.sell_time_after_buy }s for balanced distributed risk sell loop..."
        )

        sleep(self.sell_time_after_buy)

        for repeat_index in range(0, self.sell_repeats):

            self.api.sell(
               coin = coin,
               coin_size = self.sell_percent_per_transaction,
               used_currency = currency
            )

            await self._send_message_to_telegram(
                message = f"Sell { int(self.sell_percent_per_transaction * 100) }% of available { coin } for { currency }\n\nWaiting { self.time_between_sells }s for next repeat... (actual repeat: { repeat_index }/{ self.sell_repeats } )"
            )

            sleep(self.time_between_sells)

        self.api.sell(
            coin = coin,
            coin_size = last_sell_amount,
            used_currency = currency
        )

        await self._send_message_to_telegram(
            message = f"Sell { int(last_sell_amount * 100) }% of available { coin } for { currency }"
        )


class DistributedRiskSummationTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method,
        sell_time_after_buy: int = 10,
        sell_percent_per_transaction: float = 0.15,
        time_between_sells: int = 20,
        DEBUG: bool = False,
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )
        self.sell_time_after_buy = sell_time_after_buy
        self.sell_percent_per_transaction = sell_percent_per_transaction
        self.time_between_sells = time_between_sells
        self.__DEBUG = DEBUG

    async def invoke(
        self,
        coin: str,
        currency: str = "USDT",
        buy_amount: float = 1.0,
        last_sell_amount: float = 1.0,
        buy = True,
        sell = True,
    ):

        if buy:

            try:
                buy_info = self.api.buy(
                    coin = coin,
                    currency_percent_size_to_buy = buy_amount,
                    used_currency = currency
                )
            except Exception as error:
                buy_info = error

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = f"Buy { coin } by { int(buy_amount * 100) }% of available { currency }\n\nBuy Information:\n\n{ buy_info }\n\nWaiting { self.sell_time_after_buy }s for summation distributed risk sell loop..."
                )

            if self.__DEBUG:

                print(
                    f"Buy { coin } by { int(buy_amount * 100) }% of available { currency }\n\nBuy Information:\n\n{ buy_info }\n\nWaiting { self.sell_time_after_buy }s for summation distributed risk sell loop..."
                )

            sleep(self.sell_time_after_buy)

        if sell:

            while self.sell_percent_per_transaction < 1.0:

                self.sell_percent_per_transaction += self.sell_percent_per_transaction

                if self.sell_percent_per_transaction >= 1.0:

                    break

                try:
                    sell_info = self.api.sell(
                        coin = coin,
                        coin_percent_size_to_sell = self.sell_percent_per_transaction,
                        used_currency = currency
                    )
                except Exception as error:
                    sell_info = error

                if self.__DEBUG == False:

                    await self._send_message_to_telegram(
                        message = f"Sell { int(self.sell_percent_per_transaction * 100) }% of available { coin } for { currency }\n\nSell Information:\n\n{ sell_info }\n\nWaiting { self.time_between_sells }s for next repeat..."
                    )

                if self.__DEBUG:

                    print(
                        f"Sell { int(self.sell_percent_per_transaction * 100) }% of available { coin } for { currency }\n\nSell Information:\n\n{ sell_info }\n\nWaiting { self.time_between_sells }s for next repeat..."
                    )

                sleep(self.time_between_sells)

            try:
                last_sell_info = self.api.sell(
                    coin = coin,
                    coin_percent_size_to_sell = last_sell_amount,
                    used_currency = currency
                )
            except Exception as error:
                last_sell_info = error

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = f"Sell { int(last_sell_amount * 100) }% of available { coin } for { currency }\n\nLast sell information:\n\n{ last_sell_info }"
                )

            if self.__DEBUG:

                print(
                    f"Sell { int(last_sell_amount * 100) }% of available { coin } for { currency }\n\nLast sell information:\n\n{ last_sell_info }"
                )
