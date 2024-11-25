from api.abstract import AbstractAPI
from api.telegram import TelegramAPI
from time import sleep, time
from concurrent.futures import ThreadPoolExecutor

import os
import traceback
import asyncio


class StrategyUtils:

    @staticmethod
    def elapsed_time(transaction_method):
        async def wrapper(*args, **kwargs):

            operation_start_time = time()

            message = await transaction_method(
                *args,
                **kwargs
            )

            operation_end_time = time()

            elapsed_time_sec = operation_end_time - operation_start_time
            elapsed_time_millisec = elapsed_time_sec * 1000

            if type(message) == str:
                message += f"\n\nTotal Transaction Elapsed Time: {elapsed_time_sec:.6f} SEC ({elapsed_time_millisec:.3f} MS)"

            return message
        return wrapper


class AbstractTransactionStrategy:

    def __init__(
        self,
        exchange_api: AbstractAPI,
        telegram_api: TelegramAPI,
        time_between_buys: float,
        time_between_buy_and_sell: float,
        time_between_sells: float,
        DEBUG: bool = False
    ) -> None:
        self.__DEBUG = DEBUG

        self.exchange_api = exchange_api
        self.telegram_api = telegram_api

        self.time_between_buys = time_between_buys
        self.time_between_buy_and_sell = time_between_buy_and_sell
        self.time_between_sells = time_between_sells

        self.__buy_transaction_info = []
        self.__sell_transaction_info = []

    def __prepare_represented_string_for_transactions(self, transactions_list: list) -> str:
        all_transactions = ""
        index = 1
        for single_transaction in transactions_list:
            all_transactions += f"{index} -> {single_transaction}\n\n"
            index += 1
        return all_transactions

    def get_buy_transaction_info(self) -> str:
        return self.__prepare_represented_string_for_transactions(
            transactions_list = self.__buy_transaction_info
        )

    def get_sell_transaction_info(self) -> str:
        return self.__prepare_represented_string_for_transactions(
            transactions_list = self.__sell_transaction_info
        )

    def get_buy_transactions_count(self) -> int:
        return len(self.__buy_transaction_info)

    def get_sell_transactions_count(self) -> int:
        return len(self.__sell_transaction_info)

    def __dict_to_pretty_str(self, ugly_dict: dict, tabs: int = 1) -> str:
        pretty_dict = ""

        for ugly_key, ugly_value in ugly_dict.items():
            pretty_dict = pretty_dict + tabs * "\t" + f"{ ugly_key }: { ugly_value }\n"
        pretty_dict = pretty_dict[:-2]
        return pretty_dict

    def buy(self, coin: str, currency: str, currency_percent_size_to_buy: float):
        try:
            buy_info = self.exchange_api.buy(
                coin = coin,
                currency_percent_size_to_buy = currency_percent_size_to_buy,
                used_currency = currency
            )
            buy_info = self.__dict_to_pretty_str(
                ugly_dict = buy_info
            )
        except Exception as error:
            buy_info = f"Error '{error}' occured here:\n{traceback.format_exc()}"

        self.__buy_transaction_info.append(
            buy_info
        )

        sleep(self.time_between_buys)

    @StrategyUtils.elapsed_time
    async def __buy_strategy(self, coin: str, currency: str):
        return "abstract buy transaction strategy"

    def sell(self, coin: str, currency: str, currency_percent_size_to_sell: float):
        try:
            sell_info = self.exchange_api.sell(
                coin = coin,
                coin_percent_size_to_sell = currency_percent_size_to_sell,
                used_currency = currency
            )
            sell_info = self.__dict_to_pretty_str(
                ugly_dict = sell_info
            )
        except Exception as error:
            sell_info = f"Error '{error}' occured here:\n{traceback.format_exc()}"

        self.__sell_transaction_info.append(
            sell_info
        )

        sleep(self.time_between_sells)

    @StrategyUtils.elapsed_time
    async def __sell_strategy(self, coin: str, currency: str, last_sell_percent: float = 1.0):
        return "abstract sell transaction strategy"

    async def cancel_all_transaction_orders(self, coin: str, currency: str):
        info = self.exchange_api._cancel_all_orders(
            coin = coin,
            used_currency = currency
        )

        message = f"All Orders Canceled For Symbol { coin }-{ currency }\n\nAPI Response:\n\n{ self._prepare_represented_string_for_transactions([info]) }"

        await self.telegram_api.send_as_bot(
            message = message
        )

    async def invoke(
        self,
        coin: str,
        currency: str = "USDT",
        last_sell_percent: float = 1.0,
        buy = True,
        sell = True,
    ):

        if buy:

            message = await self.__buy_strategy(
                coin = coin,
                currency = currency
            )

            if type(message) == str:
                message += f"\n\nWaiting { self.time_between_buy_and_sell }s for sell transactions loop..."

            await self.telegram_api.send_as_bot(
                message = message
            )

        sleep(self.time_between_buy_and_sell)

        if sell:

            message = await self.__sell_strategy(
                coin = coin,
                currency = currency,
                last_sell_percent = last_sell_percent
            )

            await self.telegram_api.send_as_bot(
                message = message
            )

        if self.__DEBUG:

            return {
                "buy_infos": self.__buy_transaction_info,
                "sell_infos": self.__sell_transaction_info
            }


class MockTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        exchange_api: AbstractAPI,
        telegram_api: TelegramAPI,
        time_between_buy_and_sell: int = 1.0,
        DEBUG: bool = False,
    ):
        self.__DEBUG = DEBUG

        super().__init__(
            exchange_api = exchange_api,
            telegram_api = telegram_api,
            time_between_buys = 0.0,
            time_between_buy_and_sell = time_between_buy_and_sell,
            time_between_sells = 0.0,
            DEBUG = DEBUG,
        )

    @StrategyUtils.elapsed_time
    async def _AbstractTransactionStrategy__buy_strategy(self, coin: str, currency: str):
        return f"Buy {coin} by {currency}"

    @StrategyUtils.elapsed_time
    async def _AbstractTransactionStrategy__sell_strategy(self, coin: str, currency: str, last_sell_percent: float = 1.0):
        return f"Sell {coin} by {currency} + last sell percent: {last_sell_percent}"


class DistributedRiskStaticQuoteAndAssetTransactionStrategy(
    AbstractTransactionStrategy
):

    def __init__(
        self,
        exchange_api: AbstractAPI,
        telegram_api: TelegramAPI,
        qoute_currency_amount_per_transaction_used_to_buy: int = 50.0,
        buy_transactions: int = None,
        time_between_buy_and_sell: int = 1.0,
        qoute_currency_amount_per_transaction_used_to_sell: int = 50.0,
        sell_transactions: int = None,
        DEBUG: bool = False,
    ):
        self.__DEBUG = DEBUG

        requests_per_transaction = 1 #each endpoint have independet limit of requests which is equal -> api_transaction_requests_limit["requests"]
        api_transaction_requests_limit = exchange_api.get_api_transaction_requests_limit()

        super().__init__(
            exchange_api = exchange_api,
            telegram_api = telegram_api,
            time_between_buys = api_transaction_requests_limit["in_seconds"] / int(api_transaction_requests_limit["requests"] / requests_per_transaction),
            time_between_buy_and_sell = time_between_buy_and_sell,
            time_between_sells = api_transaction_requests_limit["in_seconds"] / int(api_transaction_requests_limit["requests"] / requests_per_transaction),
            DEBUG = DEBUG,
        )

        self.qoute_currency_amount_per_transaction_used_to_buy = qoute_currency_amount_per_transaction_used_to_buy
        self.buy_transactions = buy_transactions
        self.qoute_currency_amount_per_transaction_used_to_sell = qoute_currency_amount_per_transaction_used_to_sell
        self.sell_transactions = sell_transactions

    @StrategyUtils.elapsed_time
    async def _AbstractTransactionStrategy__buy_strategy(self, coin: str, currency: str):

        first_available_quote = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
            currency = currency
        )

        possible_transactions = int(first_available_quote / self.qoute_currency_amount_per_transaction_used_to_buy)

        if self.buy_transactions == None or self.buy_transactions > possible_transactions:

           self.buy_transactions = possible_transactions

        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() + 4)) as pool:

            tasks = []

            for transaction_no in range(1, self.buy_transactions + 1):
                available_quote = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
                    currency=currency
                )

                buy_percent_per_transaction = self.qoute_currency_amount_per_transaction_used_to_buy / available_quote

                tasks.append(
                    loop.run_in_executor(
                        pool,
                        self.buy,
                        coin,
                        currency,
                        buy_percent_per_transaction
                    )
                )

            await asyncio.gather(*tasks)

        return f"Buy { coin } by { self.buy_transactions } x { self.qoute_currency_amount_per_transaction_used_to_buy } { currency } transactions - used available { first_available_quote } { currency }\n\nBuy Information:\n\n{ self.get_buy_transaction_info() }"

    @StrategyUtils.elapsed_time
    async def _AbstractTransactionStrategy__sell_strategy(self, coin: str, currency: str, last_sell_percent: float = 1.0):

        sell_percent_per_transaction: float = 0.0

        available_size = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
            currency = coin
        )

        actual_coin_price = float(
            self.exchange_api._AbstractAPI__get_bid_and_ask_prices(
                base_currency = coin,
                quote_currency = currency
            )["bid_price"]
        )

        iteration_index = 0

        while True:

            available_size = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
                currency = coin
            )

            actual_coin_price = float(
                self.exchange_api._AbstractAPI__get_bid_and_ask_prices(
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
                await self.cancel_all_transaction_orders(
                    coin = coin,
                    currency = currency
                )

            iteration_index += 1

            loop = asyncio.get_event_loop()

            with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() + 4)) as pool:

                tasks = []

                for transaction_no in range(1, self.sell_transactions + 1):

                    available_size = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
                        currency = coin
                    )

                    actual_coin_price = float(
                        self.exchange_api._AbstractAPI__get_bid_and_ask_prices(
                            base_currency = coin,
                            quote_currency = currency
                        )["bid_price"]
                    )

                    available_quote_in_asset = available_size * actual_coin_price

                    sell_percent_per_transaction = self.qoute_currency_amount_per_transaction_used_to_sell / available_quote_in_asset

                    if sell_percent_per_transaction >= 1.0:

                        break

                    tasks.append(
                        loop.run_in_executor(
                            pool,
                            self.sell,
                            coin,
                            currency,
                            sell_percent_per_transaction
                        )
                    )

                    available_size = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
                        currency = coin
                    )

                tasks.append(
                    loop.run_in_executor(
                        pool,
                        self.sell,
                        coin,
                        currency,
                        last_sell_percent
                    )
                )

                await asyncio.gather(*tasks)

        return f"Sell { coin } by { self.get_sell_transactions_count() } x { sell_percent_per_transaction * 100} { currency } transactions\n\nSell Information:\n\n{ self.get_sell_transaction_info() }"
