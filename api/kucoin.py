import time

import base64
import hmac
import hashlib
import json
from uuid import uuid4

from .abstract import AbstractAPI, RequestsFactory


class KucoinAPI(
    AbstractAPI
):

    __general_url = "https://api.kucoin.com"
    __buy_endpoint = "/api/v1/orders"
    __sell_endpoint = "/api/v1/orders"
    __assets_availability = "/api/v1/accounts"
    __server_timestamp = "/api/v1/timestamp"

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

    def __ordinary_request_without_headers(self, used_endpoint: str, request_method: str = "GET", get_params: dict = {}, post_params: dict = {}):
        return self.__api.api_request(
            used_endpoint,
            request_method,
            {
                "Content-Type": "application/json"
            },
            get_parameters = get_params,
            post_parameters = post_params
        )


    def __ordinary_request(self, used_endpoint: str, request_method: str = "GET", get_params: dict = {}, post_params: dict = {}):
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

    def __market_order_request(self, transaction_side: str, coin: str, currency_size: float, used_currency: str, used_endpoint: str, request_method: str = "POST"):
        post_params = {
            "clientOid": str(uuid4()),
            "side": transaction_side,
            "symbol": f"{ coin }-{ used_currency }",
            "type": "market",
            "size": str(used_currency)
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

    def __limit_order_request(self, transaction_side: str, coin: str, coin_size: float, coin_price: float, used_currency: str, used_endpoint: str, request_method: str = "POST"):
        post_params = {
            "clientOid": str(uuid4()),
            "side": transaction_side,
            "symbol": f"{ coin }-{ used_currency }",
            "type": "market",
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

    def _prepare_headers(self, request_method: str, endpoint: str, get_params: dict = {}, post_params: dict = {}):
        server_time = self.__ordinary_request_without_headers(
            used_endpoint = self.__server_timestamp
        )["data"]

        local_time = int(time.time() * 1000)

        now_time = local_time

        self.headers["KC-API-TIMESTAMP"] = str(now_time)

        get_parameters_str = ""
        if len(get_params.keys()) > 0:
            get_parameters_str = "?"
            for key, value in get_params.items():
                get_parameters_str += f"{ key }={ value }&"
            get_parameters_str = get_parameters_str[:-1]

        post_parameters_json = ""
        if len(post_params) > 0:
            post_parameters_json = json.dumps(post_params)

        str_to_signature = str(now_time) + request_method + endpoint + get_parameters_str + post_parameters_json

        signature = base64.b64encode(
            hmac.new(
                self.__api_secret.encode('utf-8'),
                str_to_signature.encode('utf-8'),
                hashlib.sha256
            ).digest()
        )

        self.headers["KC-API-SIGN"] = signature

        passphrase = base64.b64encode(
            hmac.new(
                self.__api_secret.encode('utf-8'),
                self.__api_key_passphrase.encode('utf-8'),
                hashlib.sha256
            ).digest()
        )

        self.headers["KC-API-PASSPHRASE"] = passphrase

    def check_assets_availability(self, currency: str = None, asset_type: str = None):
        get_params = {}
        if currency != None and type(currency) == str:
            get_params["currency"] = currency
        if asset_type != None and type(asset_type) == str:
            get_params["type"] = asset_type
        return self.__ordinary_request(
            used_endpoint = self.__assets_availability,
            get_params = get_params
        )

    def buy(self, coin: str, currency_percent_size_to_buy: float, used_currency: str = "USDT"):
        return self.__market_order_request(
            transaction_side = "buy",
            coin = coin,
            currency_size = currency_percent_size_to_buy,
            used_currency = used_currency,
            used_endpoint = self.__buy_endpoint
        )

    def sell(self, coin: str, coin_percent_size_to_sell: float, used_currency: str = "USDT"):
        available_assets = self.check_assets_availability(
            currency = used_currency
        )

        return self.__limit_order_request(
            transaction_side = "sell",
            coin = coin,
            coin_size = coin_percent_size_to_sell,
            coin_price = 0,
            used_currency = used_currency,
            used_endpoint = self.__sell_endpoint
        )

