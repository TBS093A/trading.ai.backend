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

        super().__init__()

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

        str_to_signature = str(server_time) + str(request_method).upper() + str(endpoint) + str(get_parameters_str) + str(post_parameters_json)

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

    def __get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "trade"):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
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

    def __get_lot_size(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        """
            particular symbol (base/quote where base can be - BTC and quote - USDT) details like:

                {
                    "base_asset_precision": base asset precision (e.g. mexc) / size increment unit (e.g. kucoin)
                }

            rest of fields is useless - because of computing that in code. rest of useless fields:

                {
                    "quote_asset_precision": quote asset precision (e.g. mexc) / price increment unit (e.g. kucoin)

                    and etc.
                }
        """
        symbol_list = self._ordinary_request(
            used_endpoint = self.__lot_size_check
        )
        for symbol in symbol_list:
            if symbol["baseCurrency"] == base_currency:
                if symbol["quoteCurrency"] == quote_currency:
                    return {
                        "base_min_size": symbol["baseMinSize"],
                        "base_max_size": symbol["baseMaxSize"],
                        "base_asset_precision": symbol["baseIncrement"],

                        "quote_min_size": symbol["quoteMinSize"],
                        "quote_max_size": symbol["quoteMaxSize"],
                        "quote_asset_precision": symbol["quoteIncrement"],

                        "price_limit_rate": symbol["priceLimitRate"],
                        "price_asset_precision": symbol["priceIncrement"],
                    }

    def __get_ticker(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        """
            current information about symbol:

                {
                    "sequence":     - it looks like date time in seconds (?)
                    "price":        - current market price
                    "size":         - current market size
                    "bestAsk":      - best sell price
                    "bestAskSize":  - best sell size
                    "bestBid":      - best buy price
                    "bestBidSize":  - best buy size
                    "time":         - date time in seconds
                }

        """
        return self._ordinary_request(
            used_endpoint = self.__get_ticker,
            get_params = {
                "symbol": f"{ base_currency }-{ quote_currency }"
            }
        )

    def __get_bid_and_ask_prices(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        """
            best available buy / sell prices, where:

                bid - best available buy price (the lowest)
                ask - best available sell price (the highest)

            returned dict looks like that:

                {
                    "bid_price"     - best available buy price
                    "bid_size"      - best available buy size
                    "ask_price"     - best available sell price
                    "ask_size"      - best available sell size
                }
        """
        symbol = self.__get_ticker(
            base_currency = base_currency,
            quote_currency = quote_currency
        )
        return {
            "bid_price": symbol["bestBid"],
            "bid_size": symbol["bestBidSize"],
            "ask_price": symbol["bestAsk"],
            "ask_size": symbol["bestAskSize"]
        }
