import os
import unittest
import asyncio

import time
from time import sleep
from datetime import datetime, timedelta, timezone

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI
from api.telegram import TelegramAPIMock, TelegramAPI

from api.abstract_mock import (
    AbstractAPI
)
from api.transactions.strategies import (
    MockTransactionStrategy,
    DistributedRiskStaticQuoteAndAssetTransactionStrategy
)

from pump import (
    Pump,
    regexes,
    exchange_apis,
    const_channels
)


@unittest.skip("skip telegram tests")
class TestTelegram(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.__telegram_api = TelegramAPI()

    def tearDown(self):
        self.loop.close()

    async def __get_messages_static(self, channel_name: str = "Crypto Pump Club", limit: int = 5):

        try:

            await self.__telegram_api.start()

            channel_id = const_channels[channel_name]["id"]
            returned_message = ""
            async for message in self.__telegram_api.yield_last_messages_from_chat(
                chat_id = channel_id,
                limit = limit
            ):
                returned_message = message
                break

            return returned_message

        except Exception as error:

            raise error

        except KeyboardInterrupt as error:

            print(f"closed by user keyboard interrupt:\n\n{error}")

        finally:

            try:

                await self.__telegram_api.stop()

            except Exception as cleanup_error:

                print(f"error at finally cleanup: {cleanup_error}")

    def test_get_messages_static_000(self):
        message = self.loop.run_until_complete(
            self.__get_messages_static(
                channel_name = "Crypto Pump Club",
                limit = 5,
            )
        )

        self.assertTrue(
            type(message.message) == str
        )


@unittest.skip("skip pump real mechanizm tests")
class TestPumpUnits(unittest.TestCase):

    def test_gather_coin_000(self):
        pass

    def test_sleep_to_next_day_000(self):
        pass


@unittest.skip("skip pump real mechanizm tests")
class TestPumpReal(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.__telegram_api = TelegramAPI()

    def tearDown(self):
        self.loop.close()

    async def __prepare_pump_object(self, channel_name: str, channel_username: str, channel_id: int, pumps_list: list[dict], regex_key: str = "single_uppercase_word_without_spaces") -> Pump:

        try:

            await self.__telegram_api.start()

            pump = Pump(
                telegram_api = self.__telegram_api,
                channels = {
                    f"{channel_name}": {
                        "username": f"{channel_username}",
                        "id": channel_id,
                        "pumps": pumps_list,
                        "exchange": AbstractAPI(
                            available_quote = 50,
                            coin_price_at_buy = 0.1,
                            coin_price_at_sell = 1.0,
                        ),
                        "currency": "USDT",
                        "strategy": MockTransactionStrategy,
                        "regex": regexes[regex_key],
                    }
                },
                DEBUG = True
            )

            return pump

        except Exception as error:

            raise error

        except KeyboardInterrupt as error:

            print(f"closed by user keyboard interrupt:\n\n{error}")

        finally:

            try:

                await self.__telegram_api.stop()

            except Exception as cleanup_error:

                print(f"error at finally cleanup: {cleanup_error}")

    @unittest.skip("Skip Test Channels")
    def test_pump_investment_real_000(self):

        channel_name = "Pump Test Channel"

        pump_object = self.loop.run_until_complete(
            self.__prepare_pump_object(
                channel_name = channel_name,
                channel_username = "None",
                channel_id = -1002338823593,
                pumps_list = [
                    {
                        "day": f"wednesday",
                        "time": f"15:17:00",
                        "zone": None,
                        "is_today": False,
                        "is_realised": False,
                    },
                ],
                regex_key = "single_word_without_spaces"
            )
        )

        while True:

            self.loop.run_until_complete(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()[channel_name]["pumps"][0]["is_realised"] == True:

                break

    @unittest.skip("Skip Prod Channels")
    def test_pump_investment_real_001(self):

        channel_name = "Crypto Pump Club"

        pump_object = self.loop.run_until_complete(
            self.__prepare_pump_object(
                channel_name = channel_name,
                channel_username = "cryptoclubpump",
                channel_id = -1001625691880,
                pumps_list = [
                    {
                        "day": "friday",
                        "time": "17:00:00",
                        "zone": timezone(timedelta(0), "GMT"),
                        "is_today": False,
                        "is_realised": False,
                    },
                ],
                regex_key = "single_uppercase_word_without_spaces"
            )
        )

        while True:

            self.loop.run_until_complete(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()[channel_name]["pumps"][0]["is_realised"] == True:

                break


@unittest.skip("skip pump mock mechanizm tests")
class TestPumpMockShortTime(unittest.TestCase):

    def __prepare_pump_object(self, telegram_api_mock: TelegramAPIMock, pumps_list: list[dict], regex_key: str = "single_uppercase_word_without_spaces") -> Pump:
        pump = Pump(
            telegram_api = telegram_api_mock,
            channels = {
                "Test Channel Name": {
                    "username": "test_channel_name",
                    "id": -1,
                    "pumps": pumps_list,
                    "exchange": AbstractAPI(
                        available_quote = 50,
                        coin_price_at_buy = 0.1,
                        coin_price_at_sell = 1.0,
                    ),
                    "currency": "USDT",
                    "strategy": MockTransactionStrategy,
                    "regex": regexes[regex_key],
                }
            },
            DEBUG = True
        )

        return pump

    def test_pump_investment_short_000(self):

        current_time = datetime.now()
        new_time = current_time + timedelta(seconds=20)

        current_day_str = time.strftime("%A").lower()
        new_time_str = new_time.strftime("%H:%M:%S")

        pump_object = self.__prepare_pump_object(
            telegram_api_mock = TelegramAPIMock(
                messages_list_mock = [
                    ""
                    "‼️ 5 MINUTES UNTIL THE PUMP\n\nNext message is the coin name. Buy as fast as possible.",
                    "VTS"
                ],
                sleep = 0.25
            ),
            pumps_list = [
                {
                    "day": f"{current_day_str}",
                    "time": f"{new_time_str}",
                    "zone": None,
                    "is_today": False,
                    "is_realised": False,
                },
            ]
        )

        while True:

            asyncio.run(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()["Test Channel Name"]["pumps"][0]["is_realised"] == True:

                break

    def test_pump_investment_short_001(self):

        current_time = datetime.now()
        new_time = current_time + timedelta(seconds=20)

        current_day_str = time.strftime("%A").lower()
        new_time_str = new_time.strftime("%H:%M:%S")

        pump_object = self.__prepare_pump_object(
            telegram_api_mock = TelegramAPIMock(
                messages_list_mock = [
                    ""
                    "‼️ 5 MINUTES UNTIL THE PUMP\n\nNext message is the coin name. Buy as fast as possible.",
                    "Ozone"
                ],
                sleep = 0.25
            ),
            pumps_list = [
                {
                    "day": f"{current_day_str}",
                    "time": f"{new_time_str}",
                    "zone": None,
                    "is_today": False,
                    "is_realised": False,
                },
            ],
            regex_key = "single_word_without_spaces"
        )

        while True:

            asyncio.run(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()["Test Channel Name"]["pumps"][0]["is_realised"] == True:

                break

    def test_pump_investment_short_002(self):

        zone = timezone(timedelta(0), "GMT")

        current_time = datetime.now(zone)
        new_time = current_time + timedelta(seconds=20)

        current_day_str = time.strftime("%A").lower()
        new_time_str = new_time.strftime("%H:%M:%S")

        pump_object = self.__prepare_pump_object(
            telegram_api_mock = TelegramAPIMock(
                messages_list_mock = [
                    ""
                    "‼️ 5 MINUTES UNTIL THE PUMP\n\nNext message is the coin name. Buy as fast as possible.",
                    "Ozone"
                ],
                sleep = 0.25
            ),
            pumps_list = [
                {
                    "day": f"{current_day_str}",
                    "time": f"{new_time_str}",
                    "zone": zone,
                    "is_today": False,
                    "is_realised": False,
                },
            ],
            regex_key = "single_word_without_spaces"
        )

        while True:

            asyncio.run(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()["Test Channel Name"]["pumps"][0]["is_realised"] == True:

                break

    def test_pump_investment_short_003(self):

        zone = timezone.utc

        current_time = datetime.now(zone)
        new_time = current_time + timedelta(seconds=20)

        current_day_str = time.strftime("%A").lower()
        new_time_str = new_time.strftime("%H:%M:%S")

        pump_object = self.__prepare_pump_object(
            telegram_api_mock = TelegramAPIMock(
                messages_list_mock = [
                    ""
                    "‼️ 5 MINUTES UNTIL THE PUMP\n\nNext message is the coin name. Buy as fast as possible.",
                    "Ozone"
                ],
                sleep = 0.25
            ),
            pumps_list = [
                {
                    "day": f"{current_day_str}",
                    "time": f"{new_time_str}",
                    "zone": zone,
                    "is_today": False,
                    "is_realised": False,
                },
            ],
            regex_key = "single_word_without_spaces"
        )

        while True:

            asyncio.run(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()["Test Channel Name"]["pumps"][0]["is_realised"] == True:

                break


@unittest.skip("skip pump mock mechanizm tests")
class TestPumpMockLongTime(unittest.TestCase):

    def __prepare_pump_object(self, telegram_api_mock: TelegramAPIMock, pumps_list: list[dict], regex_key: str = "single_uppercase_word_without_spaces") -> Pump:
        pump = Pump(
            telegram_api = telegram_api_mock,
            channels = {
                "Test Channel Name": {
                    "username": "test_channel_name",
                    "id": -1,
                    "pumps": pumps_list,
                    "exchange": AbstractAPI(
                        available_quote = 50,
                        coin_price_at_buy = 0.1,
                        coin_price_at_sell = 1.0,
                    ),
                    "currency": "USDT",
                    "strategy": MockTransactionStrategy,
                    "regex": regexes[regex_key],
                }
            },
            DEBUG = True
        )

        return pump

    def test_pump_investment_long_000(self):

        current_time = datetime.now()
        new_time = current_time + timedelta(minutes=32)

        current_day_str = time.strftime("%A").lower()
        new_time_str = new_time.strftime("%H:%M:%S")

        pump_object = self.__prepare_pump_object(
            telegram_api_mock = TelegramAPIMock(
                messages_list_mock = [
                    ""
                    "‼️ 5 MINUTES UNTIL THE PUMP\n\nNext message is the coin name. Buy as fast as possible.",
                    "SVPN"
                ],
                sleep = 0.25
            ),
            pumps_list = [
                {
                    "day": f"{current_day_str}",
                    "time": f"{new_time_str}",
                    "zone": None,
                    "is_today": False,
                    "is_realised": False,
                },
            ]
        )

        while True:

            asyncio.run(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()["Test Channel Name"]["pumps"][0]["is_realised"] == True:

                break

    def test_pump_investment_long_001(self):

        current_time = datetime.now()
        new_time = current_time + timedelta(seconds=180)

        current_day_str = time.strftime("%A").lower()
        new_time_str = new_time.strftime("%H:%M:%S")

        pump_object = self.__prepare_pump_object(
            telegram_api_mock = TelegramAPIMock(
                messages_list_mock = [
                    ""
                    "‼️ 5 MINUTES UNTIL THE PUMP\n\nNext message is the coin name. Buy as fast as possible.",
                    "SVPN"
                ],
                sleep = 0.25
            ),
            pumps_list = [
                {
                    "day": f"{current_day_str}",
                    "time": f"{new_time_str}",
                    "zone": None,
                    "is_today": False,
                    "is_realised": False,
                },
            ]
        )

        while True:

            asyncio.run(
                pump_object._Pump__pump_investment()
            )

            if pump_object.get_channels()["Test Channel Name"]["pumps"][0]["is_realised"] == True:

                break


#@unittest.skip("skip transaction strategies tests")
class TestTransactionStrategies(unittest.TestCase):

    __coin: str = "TEST_ASSET"
    __currency: str = "TEST_QUOTE"

    __telegram_api_mock = TelegramAPIMock()

    async def __distributed_risk_static_quote_and_asset_transaction_strategy(self, available_quote: float, coin_price_at_buy: float, coin_price_at_sell: float):

        used_api = AbstractAPI(
            available_quote = available_quote,
            coin_price_at_buy = coin_price_at_buy,
            coin_price_at_sell = coin_price_at_sell,
        )

        used_strategy = DistributedRiskStaticQuoteAndAssetTransactionStrategy(
            exchange_api = used_api,
            telegram_api = self.__telegram_api_mock,
            DEBUG = True,
            time_between_buy_and_sell = 0.0,
        )

        transaction_infos = await used_strategy.invoke(
            coin = self.__coin,
            currency = self.__currency
        )

        return transaction_infos

    def test_distributed_risk_static_quote_and_asset_transaction_strategy_000(self):

        transaction_info = asyncio.run(
            self.__distributed_risk_static_quote_and_asset_transaction_strategy(
                available_quote = 500.0,
                coin_price_at_buy = 0.0034,
                coin_price_at_sell = 0.034,
            )
        )

    def test_distributed_risk_static_quote_and_asset_transaction_strategy_001(self):

        transaction_info = asyncio.run(
            self.__distributed_risk_static_quote_and_asset_transaction_strategy(
                available_quote = 1000.0,
                coin_price_at_buy = 0.0034,
                coin_price_at_sell = 0.034,
            )
        )

    def test_distributed_risk_static_quote_and_asset_transaction_strategy_002(self):

        transaction_info = asyncio.run(
            self.__distributed_risk_static_quote_and_asset_transaction_strategy(
                available_quote = 250.0,
                coin_price_at_buy = 0.034,
                coin_price_at_sell = 3.4,
            )
        )

    def test_distributed_risk_static_quote_and_asset_transaction_strategy_003(self):

        transaction_info = asyncio.run(
            self.__distributed_risk_static_quote_and_asset_transaction_strategy(
                available_quote = 50.0,
                coin_price_at_buy = 0.034,
                coin_price_at_sell = 3.4,
            )
        )

    def test_distributed_risk_static_quote_and_asset_transaction_strategy_004(self):

        transaction_info = asyncio.run(
            self.__distributed_risk_static_quote_and_asset_transaction_strategy(
                available_quote = 100.0,
                coin_price_at_buy = 0.000032,
                coin_price_at_sell = 0.0067,
            )
        )


@unittest.skip("skip kucoin unit tests")
class TestKucoinAPI(unittest.TestCase):

    __kucoin_api = KucoinAPI(
        api_key = os.environ.get(
            "KUCOIN_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "KUCOIN_API_SECRET",
            default=""
        ),
        api_key_passphrase = os.environ.get(
            "KUCOIN_API_KEY_PASSPHRASE",
            default=""
        )
    )

    def test_capture_api_key_0(self):
        api_key = os.environ.get(
            "KUCOIN_API_KEY",
            default=""
        )
        self.assertNotEqual(
            api_key, ""
        )

    def test_capture_api_key_passphrase_0(self):
        api_key_passphrase = os.environ.get(
            "KUCOIN_API_KEY_PASSPHRASE",
            default=""
        )
        self.assertNotEqual(
            api_key_passphrase, ""
        )

    def test_capture_api_secret_0(self):
        api_secret = os.environ.get(
            "KUCOIN_API_SECRET",
            default=""
        )
        self.assertNotEqual(
            api_secret, ""
        )

    def test_get_available_currency_percent_price_0(self):
        status = self.__kucoin_api._AbstractAPI__get_available_currency_percent_price(
            percent_size = 0.5,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_get_available_currency_percent_price_1(self):
        status = self.__kucoin_api._AbstractAPI__get_available_currency_percent_price(
            percent_size = 1.0,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_assets_check_lot_size_0(self):
        status = self.__kucoin_api._AbstractAPI__get_lot_size(
            base_currency = "BTC",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_1(self):
        status = self.__kucoin_api._AbstractAPI__get_lot_size(
            base_currency = "ETH",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_ask_and_bid_0(self):
        coin = "BTC"
        quote = "USDT"
        status = self.__kucoin_api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_aks_and_bid_1(self):
        coin = "ETH"
        quote = "USDT"
        status = self.__kucoin_api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )


@unittest.skip("skip transactions tests")
class TestKucoinAPITransactions(unittest.TestCase):

    __kucoin_api = KucoinAPI(
        api_key = os.environ.get(
            "KUCOIN_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "KUCOIN_API_SECRET",
            default=""
        ),
        api_key_passphrase = os.environ.get(
            "KUCOIN_API_KEY_PASSPHRASE",
            default=""
        )
    )

    def test_buy_assset_0(self):
        status = self.__kucoin_api.buy(
           coin = "BTC",
           currency_percent_size_to_buy = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_sell_assset_0(self):
        status = self.__kucoin_api.sell(
           coin = "BTC",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

@unittest.skip("skip mexc unit tests")
class TestMexcAPI(unittest.TestCase):

    __api = MexcAPI(
        api_key = os.environ.get(
            "MEXC_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "MEXC_API_SECRET",
            default=""
        ),
        DEBUG = False
    )

    def test_capture_api_key_0(self):
        api_key = os.environ.get(
            "MEXC_API_KEY",
            default=""
        )
        self.assertNotEqual(
            api_key, ""
        )

    def test_capture_api_secret_0(self):
        api_secret = os.environ.get(
            "MEXC_API_SECRET",
            default=""
        )
        self.assertNotEqual(
            api_secret, ""
        )

    def test_get_available_currency_percent_price_0(self):
        status = self.__api._AbstractAPI__get_available_currency_percent_price(
            percent_size = 0.5,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_get_available_currency_percent_price_1(self):
        status = self.__api._AbstractAPI__get_available_currency_percent_price(
            percent_size = 1.0,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_assets_check_lot_size_0(self):
        coin = "OX"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_1(self):
        coin = "LBTC"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_2(self):
        coin = "BTC"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_3(self):
        coin = "ETH"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_4(self):
        coin = "BNB"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_5(self):
        coin = "SOLS"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_6(self):
        coin = "MONKE"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_lot_size(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote }: { status }")
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_ask_and_bid_0(self):
        coin = "OX"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_aks_and_bid_1(self):
        coin = "LBTC"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_ask_and_bid_2(self):
        coin = "BTC"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_ask_and_bid_3(self):
        coin = "ETH"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_ask_and_bid_4(self):
        coin = "BNB"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_ask_and_bid_5(self):
        coin = "SOLS"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )

    def test_assets_ask_and_bid_6(self):
        coin = "MONKE"
        quote = "USDT"
        status = self.__api._AbstractAPI__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = quote
        )
        print(f"{ coin }/{ quote } ask/bid: { status }")
        self.assertTrue(
            "bid_price" in status and "bid_size" in status and "ask_price" in status and "ask_size"
        )


@unittest.skip("skip transactions tests")
class TestMexcAPIBuyTransactions(unittest.TestCase):

    __api = MexcAPI(
        api_key = os.environ.get(
            "MEXC_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "MEXC_API_SECRET",
            default=""
        ),
        DEBUG = True
    )

    def setUp(self):
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        self.loop.close()

    def test_LBTC_transaction_assset_0(self):
        status = self.__api.buy(
            coin = "LBTC",
            currency_percent_size_to_buy = "1.0",
            used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "api_response" in status
        )

    def test_OX_transaction_assset_0(self):
        status = self.__api.buy(
            coin = "OX",
            currency_percent_size_to_buy = "1.0",
            used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "api_response" in status
        )

    def test_PRY_transaction_assset_0(self):
        status = self.__api.buy(
            coin = "PRY",
            currency_percent_size_to_buy = "1.0",
            used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "api_response" in status
        )


@unittest.skip("skip transactions tests")
class TestMexcAPISellTransactions(unittest.TestCase):

    __api = MexcAPI(
        api_key = os.environ.get(
            "MEXC_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "MEXC_API_SECRET",
            default=""
        ),
        DEBUG = True
    )

    def setUp(self):
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        self.loop.close()

    def test_LBTC_transaction_assset_1(self):
        status = self.__api.sell(
           coin = "LBTC",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "api_response" in status
        )

    def test_OX_transaction_assset_1(self):
        status = self.__api.sell(
           coin = "OX",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "api_response" in status
        )

    def test_PRY_transaction_assset_1(self):
        status = self.__api.sell(
           coin = "PRY",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "api_response" in status
        )


if __name__ == '__main__':
    unittest.main()
