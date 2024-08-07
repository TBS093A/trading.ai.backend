import requests


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
        general_url="",
        buy_endpoint="",
        sell_endpoint=""
    ) -> None:
        self.general_url = general_url
        self.buy_endpoint = buy_endpoint
        self.sell_endpoint = sell_endpoint


    def api_request(self, request_method: str, headers: dict, *get_parameters, **post_parameters) -> dict:
        response = ""
        if request_method in self.__api_methods:
            try:
                response = requests.request(
                    request_method,
                    self.general_url + self.buy_endpoint,
                    headers = headers,
                    params = get_parameters,
                    json = post_parameters
                )
                return response.json()
            except Exception as error:
                raise error
        raise Exception(
            message="Bad Request Method"
        )

