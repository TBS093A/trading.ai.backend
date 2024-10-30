from api.abstract import AbstractAPI

from time import sleep, time
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

    def _prepare_represented_string_for_transactions(self, transactions_list: list) -> str:
        all_transactions = ""
        index = 1
        for single_transaction in transactions_list:
            all_transactions += f"{index} -> {single_transaction}\n\n"
            index += 1
        return all_transactions

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
        qoute_currency_amount_per_transaction_used_to_buy: int = 50.0,
        buy_transactions: int = None,
        time_between_buy_and_sell: int = 1.0,
        qoute_currency_amount_per_transaction_used_to_sell: int = 50.0,
        sell_transactions: int = None,
        DEBUG: bool = False,
    ):
        super().__init__(
            api = api,
            telegram_client_credentials = telegram_client_credentials,
            telegram_sending_method = telegram_sending_method
        )

        requests_per_transaction = 1 #each endpoint have independet limit of requests which is equal -> api_transaction_requests_limit["requests"]
        api_transaction_requests_limit = api.get_api_transaction_requests_limit()
        self.qoute_currency_amount_per_transaction_used_to_buy = qoute_currency_amount_per_transaction_used_to_buy
        self.buy_transactions = buy_transactions
        self.time_between_buys = api_transaction_requests_limit["in_seconds"] / int(api_transaction_requests_limit["requests"] / requests_per_transaction)
        self.time_between_buy_and_sell = time_between_buy_and_sell
        self.qoute_currency_amount_per_transaction_used_to_sell = qoute_currency_amount_per_transaction_used_to_sell
        self.sell_transactions = sell_transactions
        self.time_between_sells = api_transaction_requests_limit["in_seconds"] / int(api_transaction_requests_limit["requests"] / requests_per_transaction)
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

            buy_start_time = time()

            first_available_quote = self.api._AbstractAPI__get_available_currency_amount_price(
                currency = currency
            )

            possible_transactions = int(first_available_quote / self.qoute_currency_amount_per_transaction_used_to_buy)

            if self.buy_transactions == None or self.buy_transactions > possible_transactions:

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

            buy_end_time = time()

            elapsed_time_sec = buy_end_time - buy_start_time
            elapsed_time_millisec = elapsed_time_sec * 1000

            message = f"Buy { coin } by { self.buy_transactions } x { self.qoute_currency_amount_per_transaction_used_to_buy } { currency } transactions - used available { first_available_quote } { currency }\n\nBuy Information:\n\n{ self._prepare_represented_string_for_transactions(buy_infos) }\n\nTotal Buy Transaction Elapsed Time: {elapsed_time_sec:.6f} SEC ({elapsed_time_millisec:.3f} MS)\n\nWaiting { self.time_between_buy_and_sell }s for sell transactions loop..."

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

            sell_start_time = time()

            available_size = self.api._AbstractAPI__get_available_currency_amount_price(
                currency = coin
            )

            actual_coin_price = float(
                self.api._AbstractAPI__get_bid_and_ask_prices(
                    base_currency = coin,
                    quote_currency = currency
                )["bid_price"]
            )

            iteration_index = 0

            while True:

                available_size = self.api._AbstractAPI__get_available_currency_amount_price(
                    currency = coin
                )

                actual_coin_price = float(
                    self.api._AbstractAPI__get_bid_and_ask_prices(
                        base_currency = coin,
                        quote_currency = currency
                    )["bid_price"]
                )

                available_quote_in_asset = available_size * actual_coin_price

                if available_quote_in_asset < self.qoute_currency_amount_per_transaction_used_to_sell:

                    break

                possible_transactions = int(available_quote_in_asset / self.qoute_currency_amount_per_transaction_used_to_sell)

                if self.sell_transactions == None or self.sell_transactions > possible_transactions:

                    self.sell_transactions = possible_transactions

                if iteration_index > 0:
                    info = self.api._cancel_all_orders(
                        coin = coin,
                        used_currency = currency
                    )

                    message = f"All Orders Canceled For Symbol { coin }-{ currency }\n\nAPI Response:\n\n{ self._prepare_represented_string_for_transactions([info]) }"

                    if self.__DEBUG == False:

                        await self._send_message_to_telegram(
                            message = message
                        )

                    if self.__DEBUG:

                        print(
                            message
                        )

                iteration_index += 1

                for transaction_no in range(1, self.sell_transactions + 1):

                    available_size = self.api._AbstractAPI__get_available_currency_amount_price(
                        currency = coin
                    )

                    actual_coin_price = float(
                        self.api._AbstractAPI__get_bid_and_ask_prices(
                            base_currency = coin,
                            quote_currency = currency
                        )["bid_price"]
                    )

                    available_quote_in_asset = available_size * actual_coin_price

                    sell_percent_per_transaction = self.qoute_currency_amount_per_transaction_used_to_sell / available_quote_in_asset

                    if sell_percent_per_transaction >= 1.0:

                        break

                    try:
                        sell_info = self.api.sell(
                            coin = coin,
                            coin_percent_size_to_sell = sell_percent_per_transaction,
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

            sell_end_time = time()

            elapsed_time_sec = sell_end_time - sell_start_time
            elapsed_time_millisec = elapsed_time_sec * 1000

            message = f"Sell { coin } by { len(sell_infos) } x { sell_percent_per_transaction * 100}% { currency } transactions\n\nSell Information:\n\n{ self._prepare_represented_string_for_transactions(sell_infos) }\n\nTotal Sell Transactions Elapsed Time: {elapsed_time_sec:.6f} SEC ({elapsed_time_millisec:.3f} MS)"

            if self.__DEBUG == False:

                await self._send_message_to_telegram(
                    message = message
                )

            if self.__DEBUG:

                print(
                    message
                )

        if self.__DEBUG:

            return {
                "buy_infos": buy_infos,
                "sell_infos": sell_infos
            }
