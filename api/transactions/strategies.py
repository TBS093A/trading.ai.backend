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

    def _dict_to_pretty_str(self, ugly_dict: dict, tabs: int = 1) -> str:
        pretty_dict = ""

        for ugly_key, ugly_value in ugly_dict.items():
            pretty_dict = pretty_dict + tabs * "\t" + f"{ ugly_key }: { ugly_value }\n"
        pretty_dict = pretty_dict[:-2]
        return pretty_dict

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
                buy_info = self._dict_to_pretty_str(
                    ugly_dict = buy_info
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
                last_sell_info = self._dict_to_pretty_str(
                    ugly_dict = last_sell_info
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

        message = f"Buy { coin } by { int(buy_amount * 100) }% of available { currency }\n\nWaiting { self.sell_time_after_buy }s for balanced distributed risk sell loop..."

        if self.__DEBUG == False:

            await self._send_message_to_telegram(
                message = message
            )

        if self.__DEBUG:

            print(
                message
            )

        sleep(self.sell_time_after_buy)

        for repeat_index in range(0, self.sell_repeats):

            self.api.sell(
               coin = coin,
               coin_size = self.sell_percent_per_transaction,
               used_currency = currency
            )

            message = f"Sell { int(self.sell_percent_per_transaction * 100) }% of available { coin } for { currency }\n\nWaiting { self.time_between_sells }s for next repeat... (actual repeat: { repeat_index }/{ self.sell_repeats } )"

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = message
                )

            if self.__DEBUG:

                print(
                    message
                )

            sleep(self.time_between_sells)

        self.api.sell(
            coin = coin,
            coin_size = last_sell_amount,
            used_currency = currency
        )

        message = f"Sell { int(last_sell_amount * 100) }% of available { coin } for { currency }"

        if self.__DEBUG == False:

            await self._send_message_to_telegram(
                message = message
            )

        if self.__DEBUG:

            print(
                message
            )


class DistributedRiskSummationTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method,
        buy_percent_per_transaction: float = 0.1,
        time_between_buys: float = 0.2,
        time_between_buy_and_sell: int = 35,
        sell_percent_per_transaction: float = 0.1,
        time_between_sells: float = 2.0,
        DEBUG: bool = False,
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )
        self.buy_percent_per_transaction = buy_percent_per_transaction
        self.time_between_buys = time_between_buys
        self.time_between_buy_and_sell = time_between_buy_and_sell
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

            while self.buy_percent_per_transaction < buy_amount:

                self.buy_percent_per_transaction += self.buy_percent_per_transaction

                if self.buy_percent_per_transaction >= buy_amount:

                    self.buy_percent_per_transaction = buy_amount

                try:
                    buy_info = self.api.buy(
                        coin = coin,
                        currency_percent_size_to_buy = self.buy_percent_per_transaction,
                        used_currency = currency
                    )
                    buy_info = self._dict_to_pretty_str(
                        ugly_dict = buy_info
                    )
                except Exception as error:
                    buy_info = error

                message = f"Buy { coin } by { int(self.buy_percent_per_transaction * 100) }% of available { currency }\n\nBuy Information:\n\n{ buy_info }\n\nWaiting { self.time_between_buys }s for next buy repeat..."

                if self.__DEBUG == False:

                    await self._send_message_to_telegram(
                        message = message
                    )

                if self.__DEBUG:

                    print(
                        message
                    )

                sleep(self.time_between_buys)

            message = f"Waiting { self.time_between_buy_and_sell }s for sell transactions loop..."

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = message
                )

            if self.__DEBUG:

                print(
                    message
                )

            sleep(self.time_between_buy_and_sell)

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
                    sell_info = self._dict_to_pretty_str(
                        ugly_dict = sell_info
                    )
                except Exception as error:
                    sell_info = error

                message = f"Sell { int(self.sell_percent_per_transaction * 100) }% of available { coin } for { currency }\n\nSell Information:\n\n{ sell_info }\n\nWaiting { self.time_between_sells }s for next repeat..."

                if self.__DEBUG == False:

                    await self._send_message_to_telegram(
                        message = message
                    )

                if self.__DEBUG:

                    print(
                        message
                    )

                sleep(self.time_between_sells)

            try:
                last_sell_info = self.api.sell(
                    coin = coin,
                    coin_percent_size_to_sell = last_sell_amount,
                    used_currency = currency
                )
                last_sell_info = self._dict_to_pretty_str(
                    ugly_dict = last_sell_info
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


class DistributedRiskStaticQuoteAndAssetTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        api: AbstractAPI,
        telegram_client_credentials,
        telegram_sending_method,
        qoute_currency_amount_per_transaction_used_to_buy: int = 50,
        buy_transactions: int = None,
        time_between_buys: float = 0.1,
        time_between_buy_and_sell: int = 15,
        sell_percent_per_transaction: float = 0.025,
        time_between_sells: float = 0.1,
        DEBUG: bool = False,
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )
        self.qoute_currency_amount_per_transaction_used_to_buy = qoute_currency_amount_per_transaction_used_to_buy
        self.buy_transactions = buy_transactions
        self.time_between_buys = time_between_buys
        self.time_between_buy_and_sell = time_between_buy_and_sell
        self.sell_percent_per_transaction = sell_percent_per_transaction
        self.time_between_sells = time_between_sells
        self.__DEBUG = DEBUG

    async def invoke(
        self,
        coin: str,
        currency: str = "USDT",
        last_sell_amount: float = 1.0,
        buy = True,
        sell = True,
    ):

        buy_infos = []
        sell_infos = []

        if buy:

            first_available_quote = self.api._AbstractAPI__get_available_currency_amount_price(
                currency = currency
            )

            possible_transactions = int(first_available_quote / self.qoute_currency_amount_per_transaction_used_to_buy)

            if self.buy_transactions == None or self.buy_transaction > possible_transactions:

               self.buy_transactions = possible_transactions

            for transaction_no in range(1, self.buy_transactions + 1):

                available_quote = self.api._AbstractAPI__get_available_currency_amount_price(
                    currency = currency
                )

                buy_percent_per_transaction = self.qoute_currency_amount_per_transaction_used_to_buy / available_quote

                try:
                    buy_info = self.api.buy(
                        coin = coin,
                        currency_percent_size_to_buy = buy_percent_per_transaction,
                        used_currency = currency
                    )
                    buy_info = self._dict_to_pretty_str(
                        ugly_dict = buy_info
                    )
                except Exception as error:
                    buy_info = error

                buy_infos.append(
                    buy_info
                )

                sleep(self.time_between_buys)

            message = f"Buy { coin } by { self.buy_transactions } x { self.qoute_currency_amount_per_transaction_used_to_buy } { currency } transactions - used available { first_available_quote } { currency }\n\nBuy Information:\n\n{ buy_infos }\n\nWaiting { self.time_between_buy_and_sell }s for sell transactions loop..."

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = message
                )

            if self.__DEBUG:

                print(
                    message
                )

            sleep(self.time_between_buy_and_sell)

        if sell:

            available_percent = 1.0

            dynamic_percent = 0

            available_size = self.api._AbstractAPI__get_available_currency_amount_price(
                currency = coin
            )

            const_size = available_size * self.sell_percent_per_transaction

            while available_percent > 0.0 and available_size > 0.0:

                available_percent -= self.sell_percent_per_transaction

                dynamic_percent = const_size / available_size

                if dynamic_percent >= 1.0:

                    break

                try:
                    sell_info = self.api.sell(
                        coin = coin,
                        coin_percent_size_to_sell = dynamic_percent,
                        used_currency = currency
                    )
                    sell_info = self._dict_to_pretty_str(
                        ugly_dict = sell_info
                    )
                except Exception as error:
                    sell_info = error

                sell_infos.append(
                    sell_info
                )

                available_size = self.api._AbstractAPI__get_available_currency_amount_price(
                    currency = coin
                )

                sleep(self.time_between_sells)

            try:
                last_sell_info = self.api.sell(
                    coin = coin,
                    coin_percent_size_to_sell = last_sell_amount,
                    used_currency = currency
                )
                last_sell_info = self._dict_to_pretty_str(
                    ugly_dict = last_sell_info
                )
            except Exception as error:
                last_sell_info = error

            sell_infos.append(
                last_sell_info
            )

        message = f"Sell { coin } by { len(sell_infos) - 1 } x { self.sell_percent_per_transaction}% { currency } transactions\n\nSell Information:\n\n{ sell_infos }"

        if self.__DEBUG == False:

            await self._send_message_to_telegram(
                message = message
            )

        if self.__DEBUG:

            print(
                message
            )

            return {
                "buy_infos": buy_infos,
                "sell_infos": sell_infos
            }
