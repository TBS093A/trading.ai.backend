import requests
import logging

from pprint import pprint

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


class AbstractAPI:

    __general_endpoint = ""
    __buy_endpoint = ""
    __sell_endpoint = ""

    __api_transaction_requests_limit = {"requests": 499, "in_seconds": 10}

    def __init__(self):
        self.__buy_transaction = {}
        self.__actual_size = 0.0
        self.__actual_price = 0.0
        self.__sell_transactions = {}

    def get_api_transaction_requests_limit(self):
        return self.__api_transaction_requests_limit

    def _market_order_request(self, transaction_side: str, coin: str, currency_size: float, used_currency: str):
        """
            functionality which will define market order creation
        """
        pass

    def _limit_order_request(self, transaction_side: str, coin: str, coin_size: float, coin_price: float, used_currency: str):
        """
            functionality which will define limit order creation
        """
        pass

    def _cancel_all_orders(self, coin: str, used_currency: str):
        """
            functionality which will define all orders cancel operation
        """
        pass

    def __truncate_float(self, value: float, precision: float) -> float:
        if precision > 1 and type(precision) == int:
            precision = float("0." + (precision - 1) * "0" + "1")
        factor = int(1 / precision)
        return int(value * factor) / factor

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

    def __get_available_currency_amount_price(self, currency: str = None, asset_type: str = "") -> float:
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        return 0.0

    def __pop_available_currency(self, size: float, currency: str = None, asset_type: str = ""):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        return 0.0

    def __get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "") -> float:
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        return 0.0

    def __get_lot_size(self, base_currency: str = "BTC", quote_currency: str = "USDT") -> dict:
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
        return {
            "base_asset_precision": "",
        }

    def __get_bid_and_ask_prices(self, base_currency: str = "BTC", quote_currency: str = "USDT") -> dict:
        """
            best available buy / sell prices, where:

                bid - best available buy price (the lowest)
                ask - best available sell price (the highest)

            returned dict must contains all of these keys:

                {
                    "bid_price"     - best available buy price
                    "bid_size"      - best available buy size
                    "ask_price"     - best available sell price
                    "ask_size"      - best available sell size
                }
        """
        return {
            "bid_price": "",
            "bid_size": "",
            "ask_price": "",
            "ask_size": ""
        }

    def __get_ticker(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        """
            current price of symbol where dict should looks like that:

                {
                    "price"        - current market price
                }
        """
        return {
            "price": ""
        }

    def __prepare_coin_price_to_buy(self, price_buy_balance_percent: float, coin_ask_price: dict) -> float:

        price_one_houndred_percent = float(coin_ask_price)

        price_percent_balance = float(
            format(
                price_one_houndred_percent * float(price_buy_balance_percent),
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        return float(
            format(
                price_one_houndred_percent + price_percent_balance,
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

    def __prepare_coin_size_to_buy(self, available_currency_assets: float, coin_price: float, symbol_lot_size: dict) -> float:

        coin_buy_proportion = float(
            int(
                float(available_currency_assets) / float(coin_price)
            )
        )

        return float(
            int(
                self.__truncate_float(
                    value = coin_buy_proportion,
                    precision = int(symbol_lot_size["base_asset_precision"])
                )
            )
        )

    def buy(self, coin: str, currency_size_to_buy: float, used_currency: str = "USDT", price_buy_balance_percent: float = 0.1):

        #gather data

        best_ticker_data = self.__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = used_currency
        )

        symbol_lot_size = self.__get_lot_size(
            base_currency = coin,
            quote_currency = used_currency
        )

        available_currency_assets = int(
            float(
                self.__pop_available_currency(
                    size = currency_size_to_buy,
                    currency = used_currency
                )
            )
        )

        #compute

        coin_price = self.__prepare_coin_price_to_buy(
            price_buy_balance_percent = price_buy_balance_percent,
            coin_ask_price = best_ticker_data["ask_price"]
        )

        coin_size = self.__prepare_coin_size_to_buy(
            available_currency_assets = available_currency_assets,
            coin_price = coin_price,
            symbol_lot_size = symbol_lot_size
        )

        #transaction request

        approach = "limit"

        print("")
        print(f"buy ({approach}):")
        print(f"\tcoin: {coin}")
        print(f"\tquote: {used_currency}")
        print(f"\tquantity (size): {coin_size}")
        print(f"\tprice: {coin_price}")

        api_response = self._limit_order_request(
            transaction_side = "BUY",
            coin = coin,
            coin_size = coin_size,
            coin_price = coin_price,
            used_currency = used_currency,
        )

        return {
            "order_approach": approach,
            "bought_asset_price": coin_price * coin_size,
            "bought_asset_size": coin_size,
            "asset_price": coin_price,
            "possible_prices_and_sizes": best_ticker_data,
            "api_response": api_response,
        }

    def __prepare_coin_size_to_sell(self, available_coin_assets: float, symbol_lot_size: dict) -> float:

        coin_sell_proportion = float(available_coin_assets)

        return self.__truncate_float(
            value = coin_sell_proportion,
            precision = int(symbol_lot_size["base_asset_precision"])
        )


    def __prepare_coin_price_to_sell(self, price_sell_balance_percent: float, coin_bid_price: dict) -> float:

        price_one_houndred_percent = float(coin_bid_price)

        price_percent_balance = float(
            format(
                price_one_houndred_percent * float(price_sell_balance_percent),
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

        return float(
            format(
                price_one_houndred_percent - price_percent_balance,
                f".{len(str(price_one_houndred_percent))}f"
            )
        )

    def sell(self, coin: str, coin_percent_size_to_sell: float, used_currency: str = "USDT", price_sell_balance_percent: float = 0.1):

        #gather data

        symbol_lot_size = self.__get_lot_size(
            base_currency = coin,
            quote_currency = used_currency,
        )

        best_ticker_data = self.__get_bid_and_ask_prices(
            base_currency = coin,
            quote_currency = used_currency
        )

        available_coin_assets = self.__get_available_currency_percent_price(
            percent_size = coin_percent_size_to_sell,
            currency = coin
        )

        #compute

        coin_size = self.__prepare_coin_size_to_sell(
            available_coin_assets = available_coin_assets,
            symbol_lot_size = symbol_lot_size
        )

        coin_price = self.__prepare_coin_price_to_sell(
            price_sell_balance_percent = price_sell_balance_percent,
            coin_bid_price = best_ticker_data["bid_price"]
        )

        #transaction request

        approach = "limit"

        print("")
        print(f"sell ({approach}):")
        print(f"\tcoin: {coin}")
        print(f"\tquote: {used_currency}")
        print(f"\tquantity (size): {coin_size}")
        print(f"\tprice: {coin_price}")

        api_response = self._limit_order_request(
            transaction_side = "SELL",
            coin = coin,
            coin_size = coin_size,
            coin_price = coin_price,
            used_currency = used_currency,
        )

        return {
            "order_approach": approach,
            "sold_asset_price": coin_size * coin_price,
            "sold_asset_size": coin_size,
            "asset_price": coin_price,
            "possible_prices_and_sizes": best_ticker_data,
            "api_response": api_response,
        }


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
                response = None
                url = str(self.general_url) + str(endpoint)
                if len(get_parameters.keys()) == 0 and len(post_parameters.keys()) == 0:
                    response = requests.request(
                        request_method,
                        url,
                        headers = headers
                )
                if len(get_parameters.keys()) > 0 and len(post_parameters.keys()) == 0:
                    response = requests.request(
                        request_method,
                        url,
                        headers = headers,
                        params = get_parameters
                )
                if len(get_parameters.keys()) == 0 and len(post_parameters.keys()) > 0:
                    response = requests.request(
                        request_method,
                        url,
                        headers = headers,
                        json = post_parameters
                    )
                if len(get_parameters.keys()) > 0 and len(post_parameters.keys()) > 0:
                    response = requests.request(
                        request_method,
                        url,
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
                raise Exception(
                    f"{error} \nused params:\n\tget: {get_parameters}\n\tpost: {post_parameters}"
                )
        raise Exception(
            "Bad Request Method"
        )

