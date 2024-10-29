import os
import unittest

from time import sleep

from telethon import TelegramClient

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI

from api.abstract_mock import (
    AbstractAPIMock
)
from api.transactions.strategies import (
    DistributedRiskStaticQuoteAndAssetTransactionStrategy,
    DistributedRiskSummationTransactionStrategy,
    SingleShotAfterTimeTransactionStrategy,
)

from pump import (
    main,
    gather_coin
)
from pump import (
    channels,
    telegram_requests_per_minute_limit,
    sec_time_for_check_messages
)
from pump import (
    telethon_api_id,
    telethon_api_hash,
    telethon_api_phone,
    telethon_bot_token,
    user_id,
    send_as_bot
)


class TestTransactionStrategies(unittest.testcase):

    self.__bot = TelegramClient(
        "bot_session",
        telethon_api_id,
        telethon_api_hash
    ).start(
        bot_token=telethon_bot_token
    )

    self.__coin: str = "TEST_ASSET"
    self.__currency: str = "TEST_QUOTE"

    async def test_distributed_risk_static_quote_and_asset_transaction_strategy_000(self):

        used_api = AbstractAPIMock(
            available_quote = 500.0,
            coin_price_at_buy = 0.0034,
            coin_price_at_sell = 0.034,
        )

        used_strategy = DistributedRiskStaticQuoteAndAssetTransactionStrategy(
            api = used_api,
            telegram_client_credentials = {
                "api_id": telethon_api_id,
                "api_hash": telethon_api_hash,
                "bot_session": self.__bot,
                "user": user_id
            },
            telegram_sending_method = send_as_bot,
            DEBUG = True
        )

        await used_strategy.invoke(
            coin = self.__coin,
            currency = self.__currency
        )

    async def test_distributed_risk_static_quote_and_asset_transaction_strategy_001(self):

        used_api = AbstractAPIMock(
            available_quote = 1000.0,
            coin_price_at_buy = 0.0034,
            coin_price_at_sell = 0.034,
        )

        used_strategy = DistributedRiskStaticQuoteAndAssetTransactionStrategy(
            api = used_api,
            telegram_client_credentials = {
                "api_id": telethon_api_id,
                "api_hash": telethon_api_hash,
                "bot_session": self.__bot,
                "user": user_id
            },
            telegram_sending_method = send_as_bot,
            DEBUG = True
        )

        await used_strategy.invoke(
            coin = self.__coin,
            currency = self.__currency
        )

    async def test_distributed_risk_static_quote_and_asset_transaction_strategy_002(self):

        used_api = AbstractAPIMock(
            available_quote = 250.0,
            coin_price_at_buy = 0.034,
            coin_price_at_sell = 3.4,
        )

        used_strategy = DistributedRiskStaticQuoteAndAssetTransactionStrategy(
            api = used_api,
            telegram_client_credentials = {
                "api_id": telethon_api_id,
                "api_hash": telethon_api_hash,
                "bot_session": self.__bot,
                "user": user_id
            },
            telegram_sending_method = send_as_bot,
            DEBUG = True
        )

        await used_strategy.invoke(
            coin = self.__coin,
            currency = self.__currency
        )

    async def test_distributed_risk_static_quote_and_asset_transaction_strategy_003(self):

        used_api = AbstractAPIMock(
            available_quote = 50.0,
            coin_price_at_buy = 0.034,
            coin_price_at_sell = 3.4,
        )

        used_strategy = DistributedRiskStaticQuoteAndAssetTransactionStrategy(
            api = used_api,
            telegram_client_credentials = {
                "api_id": telethon_api_id,
                "api_hash": telethon_api_hash,
                "bot_session": self.__bot,
                "user": user_id
            },
            telegram_sending_method = send_as_bot,
            DEBUG = True
        )

        await used_strategy.invoke(
            coin = self.__coin,
            currency = self.__currency
        )

    async def test_distributed_risk_static_quote_and_asset_transaction_strategy_004(self):

        used_api = AbstractAPIMock(
            available_quote = 100.0,
            coin_price_at_buy = 0.000032,
            coin_price_at_sell = 0.0067,
        )

        used_strategy = DistributedRiskStaticQuoteAndAssetTransactionStrategy(
            api = used_api,
            telegram_client_credentials = {
                "api_id": telethon_api_id,
                "api_hash": telethon_api_hash,
                "bot_session": self.__bot,
                "user": user_id
            },
            telegram_sending_method = send_as_bot,
            DEBUG = True
        )

        await used_strategy.invoke(
            coin = self.__coin,
            currency = self.__currency
        )


@unittest.skip("skip kucoin unit tests")
class TestKucoinAPI(unittest.testcase):

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


class TestMexcAPI(unittest.TestCase):

    __api = MexcAPI(
        api_key = os.environ.get(
            "MEXC_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "MEXC_API_SECRET",
            default=""
        )
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
class TestMexcAPITransactions(unittest.TestCase):

    __api = MexcAPI(
        api_key = os.environ.get(
            "MEXC_API_KEY",
            default=""
        ),
        api_secret = os.environ.get(
            "MEXC_API_SECRET",
            default=""
        )
    )

    def test_LBTC_transaction_assset_0(self):
        sleep(2)
        status = self.__api.buy(
           coin = "LBTC",
           currency_percent_size_to_buy = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_LBTC_transaction_assset_1(self):
        sleep(2)
        status = self.__api.sell(
           coin = "LBTC",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_OX_transaction_assset_0(self):
        sleep(2)
        status = self.__api.buy(
           coin = "OX",
           currency_percent_size_to_buy = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_OX_transaction_assset_1(self):
        sleep(2)
        status = self.__api.sell(
           coin = "OX",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_MONKE_transaction_assset_0(self):
        sleep(2)
        status = self.__api.buy(
           coin = "MONKE",
           currency_percent_size_to_buy = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_MONKE_transaction_assset_1(self):
        sleep(2)
        status = self.__api.sell(
           coin = "MONKE",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )


if __name__ == '__main__':
    unittest.main()
