from api.abstract import AbstractAPI
from api.telegram import TelegramAPI
from time import sleep, time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import os
import traceback
import asyncio

import logging


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


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
        pump_time: str,
        pump_time_zone: str,
        time_between_buys: float,
        time_between_buy_and_sell: float,
        time_between_sells: float,
        DEBUG: bool = False
    ) -> None:
        self.__DEBUG = DEBUG

        self.exchange_api = exchange_api
        self.telegram_api = telegram_api

        self.pump_time = pump_time
        self.pump_time_zone = pump_time_zone

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

    def buy(self, coin: str, currency: str, currency_size_to_buy: float):
        try:
            buy_info = self.exchange_api.buy(
                coin = coin,
                currency_size_to_buy = currency_size_to_buy,
                used_currency = currency
            )
            buy_info = self.__dict_to_pretty_str(
                ugly_dict = buy_info
            )
        except Exception as error:
            logging.error(f"'{error}' occured here:\n{traceback.format_exc()}")
            buy_info = f"Error '{error}' occured here:\n{traceback.format_exc()}"

        self.__buy_transaction_info.append(
            buy_info
        )

        sleep(self.time_between_buys)

    async def __wait_between_sell_and_buy_operations(self):
        current_time = datetime.now()

        if self.pump_time_zone != None:

            current_time = datetime.now(
                self.pump_time_zone
            )

        if current_time.second >= int(self.time_between_buy_and_sell):

            sleep_time = 0.0

        if current_time.second < int(self.time_between_buy_and_sell):

            sell_time = current_time.replace(
                hour=int(self.pump_time[:2]),
                minute=int(self.pump_time[3:5]),
                second=int(self.time_between_buy_and_sell)
            )

            time_diff = abs(current_time - sell_time)

            sleep_time = time_diff.total_seconds()

            print(f"Wait {sleep_time}s For Sell Operation...")

            await asyncio.sleep(
                sleep_time
            )


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
            logging.error(f"'{error}' occured here:\n{traceback.format_exc()}")
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
        last_sell_percent: float = 1.0,
        buy = True,
        sell = True,
    ):

        buy_report = None

        sell_report = None

        if buy:

            print(f"Start Buy Operation")

            buy_report = await self.__buy_strategy(
                coin = coin
            )

        await self.__wait_between_sell_and_buy_operations()

        if sell:

            print(f"Start Sell Operation")

            sell_report = await self.__sell_strategy(
                coin = coin,
                last_sell_percent = last_sell_percent
            )

        message = f"Captured Coin: { coin }\n\nBuy Information:\n\n { buy_report }\n\nSell Information:\n\n { sell_report }"

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
        currency: str,
        pump_time: str = None,
        pump_time_zone: str = None,
        quote_currency_amount_per_transaction_used_to_buy: int = 50.0,
        buy_transactions: int = None,
        time_between_buy_and_sell: int = 20.0,
        quote_currency_amount_per_transaction_used_to_sell: int = 50.0,
        sell_transactions: int = None,
        DEBUG: bool = False,
    ):
        self.__DEBUG = DEBUG

        self.currency = currency

        requests_per_transaction = 1 #each endpoint have independet limit of requests which is equal -> api_transaction_requests_limit["requests"]
        api_transaction_requests_limit = exchange_api.get_api_transaction_requests_limit()

        super().__init__(
            exchange_api = exchange_api,
            telegram_api = telegram_api,
            pump_time = pump_time,
            pump_time_zone = pump_time_zone,
            time_between_buys = api_transaction_requests_limit["in_seconds"] / int(api_transaction_requests_limit["requests"] / requests_per_transaction),
            time_between_buy_and_sell = time_between_buy_and_sell,
            time_between_sells = api_transaction_requests_limit["in_seconds"] / int(api_transaction_requests_limit["requests"] / requests_per_transaction),
            DEBUG = DEBUG,
        )

        self.quote_currency_amount_per_transaction_used_to_buy = quote_currency_amount_per_transaction_used_to_buy
        self.quote_currency_amount_per_transaction_used_to_sell = quote_currency_amount_per_transaction_used_to_sell

        if buy_transactions == None:
            self.no_account_updates = False
            self.update_possible_buy_transactions()
        else:
            self.no_account_updates = True
            self.buy_transactions = buy_transactions

        self.sell_transactions = sell_transactions

    def update_possible_buy_transactions(self):
        if self.no_account_updates == False:

            available_quote = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
                currency = self.currency
            )

            self.buy_transactions = int(available_quote / self.quote_currency_amount_per_transaction_used_to_sell)

            print(f"Update Available Qoute  Used To Pump BUY Transactions (Possible Buy Transactions Count) Before Pump:\n\n{self.buy_transactions} x {self.quote_currency_amount_per_transaction_used_to_sell} {self.currency}\n")

    @StrategyUtils.elapsed_time
    async def _AbstractTransactionStrategy__buy_strategy(self, coin: str):

        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() + 4)) as pool:

            tasks = []

            for transaction_no in range(1, self.buy_transactions + 1):

                tasks.append(
                    loop.run_in_executor(
                        pool,
                        self.buy,
                        coin,
                        self.currency,
                        self.quote_currency_amount_per_transaction_used_to_buy
                    )
                )

            await asyncio.gather(*tasks)

        return f"Buy { coin } by { self.buy_transactions } x { self.quote_currency_amount_per_transaction_used_to_buy } { self.currency } transactions\n\nBuy Information:\n\n{ self.get_buy_transaction_info() }"

    @StrategyUtils.elapsed_time
    async def _AbstractTransactionStrategy__sell_strategy(self, coin: str, last_sell_percent: float = 1.0):

        sell_percent_per_transaction: float = 0.0

        available_size = self.exchange_api._AbstractAPI__get_available_currency_amount_price(
            currency = coin
        )

        actual_coin_price = float(
            self.exchange_api._AbstractAPI__get_bid_and_ask_prices(
                base_currency = coin,
                quote_currency = self.currency
            )["bid_price"]
        )

        available_quote_in_asset = available_size * actual_coin_price

        possible_transactions = int(available_quote_in_asset / self.quote_currency_amount_per_transaction_used_to_sell)

        if self.sell_transactions == None or self.sell_transactions > possible_transactions:

            self.sell_transactions = possible_transactions

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
                        quote_currency = self.currency
                    )["bid_price"]
                )

                available_quote_in_asset = available_size * actual_coin_price

                sell_percent_per_transaction = self.quote_currency_amount_per_transaction_used_to_sell / available_quote_in_asset

                if sell_percent_per_transaction >= 1.0:

                    break

                tasks.append(
                    loop.run_in_executor(
                        pool,
                        self.sell,
                        coin,
                        self.currency,
                        sell_percent_per_transaction
                    )
                )

            await asyncio.gather(*tasks)

        self.sell(
            coin,
            self.currency,
            last_sell_percent
        )

        return f"Sell { coin } by { self.get_sell_transactions_count() } x { sell_percent_per_transaction * 100} { self.currency } transactions\n\nSell Information:\n\n{ self.get_sell_transaction_info() }"
