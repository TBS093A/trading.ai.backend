import time

import base64
import hmac
import hashlib
from uuid import uuid4

from .abstract import AbstractAPI, RequestsFactory


class KucoinAPI(
    AbstractAPI
):

    __general_endpoint = "https://api.kucoin.com"
    __buy_endpoint = "/api/v1/order/test"
    __sell_endpoint = "/api/v1/order/test"

    def __init__(self, api_key: str, api_secret: str, api_key_passphrase: str, api_version="2") -> None:
        self.__api = RequestsFactory(
            general_url = self.__general_endpoint,
            buy_endpoint = self.__buy_endpoint,
            sell_endpoint = self.__sell_endpoint
        )
        self.__api_key = str(api_key)
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

    def __order_request(self, transaction_type: str, coin: str, size: float, used_currency: str, used_endpoint_for_header_creation: str):
        request_method = "POST"
        self.__prepare_headers(
            request_method = request_method,
            endpoint = used_endpoint_for_header_creation,
        )
        post_params = {
            "clientOid": str(uuid4()),
            "side": transaction_type,
            "symbol": f"{ coin }-{ used_currency }",
            "type": "market",
            "size": str(size)
        }
        return self.__api.api_request(
            request_method,
            self.headers,
            *(),
            **post_params
        )


    def __prepare_headers(self, request_method: str, endpoint: str):
        now_time = int(time.time() * 1000)
        self.headers["KC-API-TIMESTAMP"] = str(now_time)

        str_to_signature = str(now_time) + request_method + endpoint

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


    def buy(self, coin: str, currency_size: float, used_currency: str = "USDT"):
        return self.__order_request(
            transaction_type = "buy",
            coin = coin,
            size = currency_size,
            used_currency = used_currency,
            used_endpoint_for_header_creation = self.__buy_endpoint
        )

    def sell(self, coin: str, coin_size: float, used_currency: str = "USDT"):
        return self.__order_request(
            transaction_type = "sell",
            coin = coin,
            size = coin_size,
            used_currency = used_currency,
            used_endpoint_for_header_creation = self.__sell_endpoint
        )

