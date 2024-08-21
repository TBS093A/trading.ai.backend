import time

import base64
import hmac
import hashlib
import json
from uuid import uuid4
import urllib.parse

from .abstract import AbstractAPI, RequestsFactory


class KucoinAPI(
    AbstractAPI
):

    __general_url = "https://api.kucoin.com"
    __buy_endpoint = "/api/v1/orders"
    __sell_endpoint = "/api/v1/orders"
    __assets_availability = "/api/v1/accounts"
    __server_timestamp = "/api/v1/timestamp"
    __lot_size_check = "/api/v1/symbols"
    __all_orders = "/api/v1/limit/orders"
    __get_ticker = "/api/v1/market/orderbook/level1"

    def __init__(self, api_key: str, api_secret: str, api_key_passphrase: str, api_version="2") -> None:
        self.__api = RequestsFactory(
            general_url = self.__general_url
        )
        self.__api_key = api_key
        self.__api_secret = api_secret
        self.__api_key_passphrase = api_key_passphrase
        self.headers = {
            "KC-API-KEY": self.__api_key,
            "KC-API-SIGN": "",
            "KC-API-TIMESTAMP": "",
            "KC-API-PASSPHRASE": "",
            "KC-API-KEY-VERSION": api_version,
            "Content-Type": "application/json"
        }

        self.__buy_transaction = {}
        self.__actual_size = 0.0
        self.__actual_price = 0.0
        self.__sell_transactions = {}

    def _ordinary_request_without_headers(self, used_endpoint: str, request_method: str = "GET", get_params: dict = {}, post_params: dict = {}):
        return self.__api.api_request(
            used_endpoint,
            request_method,
            {
                "Content-Type": "application/json"
            },
            get_parameters = get_params,
            post_parameters = post_params
        )


    def _ordinary_request(self, used_endpoint: str, request_method: str = "GET", get_params: dict = {}, post_params: dict = {}):
        self._prepare_headers(
            request_method = request_method,
            endpoint = used_endpoint,
            get_params = get_params,
            post_params = post_params
        )
        return self.__api.api_request(
            used_endpoint,
            request_method,
            self.headers,
            get_parameters = get_params,
            post_parameters = post_params
        )

    def _market_order_request(self, transaction_side: str, coin: str, currency_size: float, used_currency: str, used_endpoint: str, request_method: str = "POST"):
        post_params = {
            "clientOid": str(uuid4()),
            "side": transaction_side,
            "symbol": f"{ coin }-{ used_currency }",
            "type": "market",
            "size": str(currency_size)
        }
        self._prepare_headers(
            request_method = request_method,
            endpoint = used_endpoint,
            post_params = post_params
        )
        return self.__api.api_request(
            used_endpoint,
            request_method,
            self.headers,
            post_parameters = post_params
        )

    def _limit_order_request(self, transaction_side: str, coin: str, coin_size: float, coin_price: float, used_currency: str, used_endpoint: str, request_method: str = "POST"):
        post_params = {
            "clientOid": str(uuid4()),
            "side": transaction_side,
            "symbol": f"{ coin }-{ used_currency }",
            "type": "limit",
            "size": str(coin_size),
            "price": str(coin_price)
        }
        self._prepare_headers(
            request_method = request_method,
            endpoint = used_endpoint,
            post_params = post_params
        )
        return self.__api.api_request(
            used_endpoint,
            request_method,
            self.headers,
            post_parameters = post_params
        )

    def _prepare_headers(self, request_method: str, endpoint: str, get_params: dict = {}, post_params: dict = {}, is_v1_api: bool = False):
        server_time = self._ordinary_request_without_headers(
            used_endpoint = self.__server_timestamp
        )

        self.headers["KC-API-TIMESTAMP"] = str(server_time)

        get_parameters_str = ""
        if len(get_params) > 0:
            get_parameters_str = "?" + urllib.parse.urlencode(get_params)

        post_parameters_json = ""
        if len(post_params) > 0:
            post_parameters_json = json.dumps(post_params)

        str_to_signature = str(server_time) + request_method.upper() + endpoint + get_parameters_str + post_parameters_json

        signature = base64.b64encode(
            hmac.new(
                self.__api_secret.encode('utf-8'),
                str_to_signature.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        self.headers["KC-API-SIGN"] = signature

        if is_v1_api == False:

            passphrase = base64.b64encode(
                hmac.new(
                    self.__api_secret.encode('utf-8'),
                    self.__api_key_passphrase.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode("utf-8")

            self.headers["KC-API-PASSPHRASE"] = passphrase

        if is_v1_api == True:

            self.headers["KC-API-PASSPHRASE"] = self.__api_key_passphrase

    def __truncate_float(self, value: float, precision: float) -> float:
        factor = int(1 / precision)
        truncated_value = int(value * factor) / factor
        return truncated_value

    def __truncate_to_four_significant_digits(self, number: float, mode: str = "truncate") -> float:
        full_number = format(number, '.16f')
        num_str = full_number.split('.')

        if len(num_str) > 1:
            integer_part = num_str[0]
            decimal_part = num_str[1]

            non_zero_start = 0
            for i, digit in enumerate(decimal_part):
                if digit != '0':
                    non_zero_start = i
                    break

            truncated_decimal_part = decimal_part[non_zero_start:non_zero_start + 4]

            truncated_number_str = integer_part + '.' + decimal_part[:non_zero_start] + truncated_decimal_part

            return float(truncated_number_str)

        return number

    def get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "trade"):
        available_assets = self._ordinary_request(
            used_endpoint = self.__assets_availability
        )

        for asset in available_assets:
            if asset["currency"] == currency:
                if asset["type"] == asset_type:
                    return str(
                        float(asset["available"]) * float(percent_size)
                    )
        return 0.0

    def get_lot_size(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        symbol_list = self._ordinary_request(
            used_endpoint = self.__lot_size_check
        )
        for symbol in symbol_list:
            if symbol["baseCurrency"] == base_currency:
                if symbol["quoteCurrency"] == quote_currency:
                    return {
                        "base_min_size": symbol["baseMinSize"],
                        "base_max_size": symbol["baseMaxSize"],
                        "base_increment": symbol["baseIncrement"],

                        "quote_min_size": symbol["quoteMinSize"],
                        "quote_max_size": symbol["quoteMaxSize"],
                        "quote_increment": symbol["quoteIncrement"],

                        "price_limit_rate": symbol["priceLimitRate"],
                        "price_increment": symbol["priceIncrement"],
                    }

    def get_ticker(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        return self._ordinary_request(
            used_endpoint = self.__get_ticker,
            get_params = {
                "symbol": f"{ base_currency }-{ quote_currency }"
            }
        )

    def buy(self, coin: str, currency_percent_size_to_buy: float, used_currency: str = "USDT"):

        # get available usdt amount for compute how much coin size will be buy
        # it will be good for small shitcoins beacuse BTC always gets all usdt
        # if size is 1.0 - shitcoin should get smaller amount than 500$

        symbol_lot_size = self.get_lot_size(
            base_currency = coin,
            quote_currency = used_currency
        )

        ticker_data = self.get_ticker(
            base_currency = coin,
            quote_currency = used_currency
        )

        available_currency_assets = self.get_available_currency_percent_price(
            percent_size = currency_percent_size_to_buy,
            currency = used_currency
        )

        coin_buy_proportion = (float(available_currency_assets) / float(ticker_data["price"]))

        self.__actual_price = float(ticker_data["price"])

        print("pre-buy:")
        print(f"\tcoin_buy_size / coin_buy_proportion ({coin_buy_proportion}) = (available_currency_assets ({available_currency_assets}) / ticker_data['price'] ({ticker_data['price']}))")


        coin_size_to_buy = self.__truncate_float(
            value = coin_buy_proportion,
            precision = float(symbol_lot_size["base_increment"])
        )

        self.__actual_size = coin_size_to_buy

        print()
        print("buy:")
        print(f"\tcoin: {coin}")
        print(f"\tcoin buy size: {coin_size_to_buy}")
        print(f"\tused currency: {used_currency}")
        print(f"\tused endpoint: {self.__buy_endpoint}")

        transaction_dict = self._market_order_request(
            transaction_side = "buy",
            coin = coin,
            currency_size = coin_size_to_buy,
            used_currency = used_currency,
            used_endpoint = self.__buy_endpoint
        )

        transaction_dict = dict(
            {
                "side": "buy",
                "coin": coin,
                "coin_price_at_buy": ticker_data["price"],
                "coin_buy_size": coin_size_to_buy,
                "currency_used_to_buy_percent": float(currency_percent_size_to_buy) * 100,
                "currency_used_to_buy": available_currency_assets,
                "used_currency": used_currency,
            },
            **transaction_dict
        )

        return transaction_dict

    def sell(self, coin: str, coin_percent_size_to_sell: float, used_currency: str = "USDT", price_sell_balance_percent: float = 0.1):

        symbol_lot_size = self.get_lot_size(
            base_currency = coin,
            quote_currency = used_currency,
        )

        available_coin_assets = self.get_available_currency_percent_price(
            percent_size = coin_percent_size_to_sell,
            currency = coin
        )

        coin_sell_proportion = float(available_coin_assets)

        print()
        print("pre-sell")
        print(f"\tcoin_sell_size / coin_sell_proportion ({coin_sell_proportion}) = available_coin_assets ({available_coin_assets})")

        coin_sell_size = self.__truncate_float(
            value = coin_sell_proportion,
            precision = float(symbol_lot_size["base_increment"])
        )

        self.__actual_size = float(available_coin_assets) - float(coin_sell_size)

        ticker_data = self.get_ticker(
            base_currency = coin,
            quote_currency = used_currency
        )

        price_one_houndred_percent = float(ticker_data["price"])
        price_percent_balance = float(
            format(
                price_one_houndred_percent * float(price_sell_balance_percent),
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        coin_high_limit_price = float(
            format(
                price_one_houndred_percent + price_percent_balance,
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        self.__actual_price = float(ticker_data["price"])

        coin_low_limit_price = float(
            format(
                price_one_houndred_percent - price_percent_balance,
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        print(f"\tself.__actual_size ({self.__actual_size}) = ticker_data['price'] ({ticker_data['price']})")

        print(f"\tcoin_low_limit_price ({coin_low_limit_price}) = ticker_data['price'] ({ticker_data['price']}) - price_percent_balance ({price_percent_balance})")

        print(f"\tcoin_high_limit_price ({coin_high_limit_price}) = ticker_data['price'] ({ticker_data['price']}) + price_percent_balance ({price_percent_balance})")

        coin_price = self.__truncate_float(
            value = coin_low_limit_price,
            precision = float(symbol_lot_size["price_increment"])
        )

        print()
        print("sell:")
        print(f"\tcoin: {coin}")
        print(f"\tcoin sell size: {coin_sell_size}")
        print(f"\tcoin price: {coin_price}")
        print(f"\tused currency: {used_currency}")
        print(f"\tused endpoint: {self.__sell_endpoint}")

        transaction_dict = self._limit_order_request(
            transaction_side = "sell",
            coin = coin,
            coin_size = coin_sell_size,
            coin_price = coin_price,
            used_currency = used_currency,
            used_endpoint = self.__sell_endpoint
        )

        pretty_coin_sell_size = format(
            coin_sell_size,
            f".{len(str(int(1 / float(symbol_lot_size['base_increment']))))}f"
        )

        pretty_coin_sell_percent = float(coin_percent_size_to_sell) * 100

        pretty_price_sell_balance_percent = float(price_sell_balance_percent) * 100

        pretty_sell_profit = float(ticker_data["price"]) * coin_sell_size

        pretty_coin_size_availability_after_sell = format(
            float(
                self.get_available_currency_percent_price(
                    percent_size = 1.0,
                    currency = coin
                )
            ),
            f".{len(str(int(1 / float(symbol_lot_size['base_increment']))))}f"
        )

        transaction_dict = dict(
            {
                "side": "sell",
                "coin": coin,
                "coin_price_at_sell": ticker_data["price"],
                "coin_used_price_at_sell": coin_price,
                "coin_sell_size": pretty_coin_sell_size,
                "coin_sell_percent": pretty_coin_sell_percent,
                "coin_price_sell_balance_percent": pretty_price_sell_balance_percent,
                "coin_price_percent_balance": price_percent_balance,
                "coin_size_availability_after_sell": pretty_coin_size_availability_after_sell,
                "sell_profit": pretty_sell_profit,
                "used_currency": used_currency,
            },
            **transaction_dict
        )

        return transaction_dict

