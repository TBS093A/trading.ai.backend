import requests

from pprint import pprint


class AbstractAPI:

    __general_endpoint = ""
    __buy_endpoint = ""
    __sell_endpoint = ""

    def buy(self, coin: str, currency_size: float, used_currency: str):
        pass

    def sell(self, coin: str, coin_size: float, used_currency: str):
        pass


class RequestsFactory:

    __api_methods = [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE"
    ]

    def __init__(
        self,
        general_url=""
    ) -> None:
        self.general_url = general_url

    def api_request(self, endpoint: str, request_method: str, headers: dict, get_parameters: dict = {}, post_parameters: dict = {}) -> dict:
        response = ""
        if request_method in self.__api_methods:
            try:
                response = requests.request(
                    request_method,
                    self.general_url + endpoint,
                    headers = headers,
                    params = get_parameters,
                    json = post_parameters
                )
                if int(response.json()["code"][:-3]) >= 400:
                    raise Exception(
                        str(response.json())
                    )
                if "data" not in response.json().keys():
                    raise Exception(
                        str(response.json())
                    )
                return response.json()["data"]
            except Exception as error:
                raise error
        raise Exception(
            "Bad Request Method"
        )

