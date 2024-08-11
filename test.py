import os
import unittest

from api.kucoin import KucoinAPI


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

    def test_capture_api_key(self):
        api_key = os.environ.get(
            "KUCOIN_API_KEY",
            default=""
        )
        self.assertNotEqual(
            api_key, ""
        )

    def test_capture_api_key_passphrase(self):
        api_key_passphrase = os.environ.get(
            "KUCOIN_API_KEY_PASSPHRASE",
            default=""
        )
        self.assertNotEqual(
            api_key_passphrase, ""
        )

    def test_capture_api_secret(self):
        api_secret = os.environ.get(
            "KUCOIN_API_SECRET",
            default=""
        )
        self.assertNotEqual(
            api_secret, ""
        )

    def test_assets_check_availability(self):
        status = self.__kucoin_api.check_assets_availability()
        print(status)
        self.assertTrue(
            "200" in status["code"]
        )

    def test_assets_check_availability(self):
        status = self.__kucoin_api.check_assets_availability(
            currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "200" in status["code"]
        )

    def test_buy_assset(self):
        status = self.__kucoin_api.buy(
           coin = "BTC",
           currency_percent_size_to_buy = "1",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "200" in status["code"]
        )

    def test_sell_assset(self):
        status = self.__kucoin_api.sell(
           coin = "BTC",
           coin_percent_size_to_sell = "1",
           used_currency = "USDT"
        )
        print(status)
        self.assertTrue(
            "200" in status["code"]
        )

if __name__ == '__main__':
    unittest.main()
