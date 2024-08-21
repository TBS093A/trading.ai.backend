import os
import unittest

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI


@unittest.skip("skip kucoin tests")
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
        status = self.__kucoin_api.get_available_currency_percent_price(
            percent_size = 0.5,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_get_available_currency_percent_price_1(self):
        status = self.__kucoin_api.get_available_currency_percent_price(
            percent_size = 1.0,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_assets_check_lot_size_0(self):
        status = self.__kucoin_api.get_lot_size(
            base_currency = "BTC",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_increment" in status
        )

    def test_assets_check_lot_size_1(self):
        status = self.__kucoin_api.get_lot_size(
            base_currency = "ETH",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_increment" in status
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

@unittest.skip("skip mexc tests")
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
        status = self.__api.get_available_currency_percent_price(
            percent_size = 0.5,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_get_available_currency_percent_price_1(self):
        status = self.__api.get_available_currency_percent_price(
            percent_size = 1.0,
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            type(float(status)) == float
        )

    def test_assets_check_lot_size_0(self):
        status = self.__api.get_lot_size(
            base_currency = "ZZZ",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_1(self):
        status = self.__api.get_lot_size(
            base_currency = "BTC",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_assets_check_lot_size_2(self):
        status = self.__api.get_lot_size(
            base_currency = "ETH",
            quote_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "base_asset_precision" in status
        )

    def test_buy_assset_0(self):
        status = self.__api.buy(
           coin = "ZZZ",
           currency_percent_size_to_buy = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )

    def test_sell_assset_0(self):
        status = self.__api.sell(
           coin = "ZZZ",
           coin_percent_size_to_sell = "1.0",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "orderId" in status
        )


if __name__ == '__main__':
    unittest.main()
