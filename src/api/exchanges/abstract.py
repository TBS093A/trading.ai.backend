import requests
import logging
from typing import List, Dict, Union, Optional

from pprint import pprint

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


class AbstractAPI:
    
    EXCHANGE_NAME = ""

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

    def _get_klines(
        self,
        base_currency: str = "BTC",
        quote_currency: str = "USDT",
        interval: str = "1m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[Dict[str, Union[int, float, str]]]:
        """
        Get kline/candlestick data for a symbol.
        
        Args:
            base_currency: Base currency symbol (e.g. BTC)
            quote_currency: Quote currency symbol (e.g. USDT)
            interval: Kline interval (e.g. 1m, 5m, 15m, 1h, 4h, 1d)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Number of records to return (max 1000)
            
        Returns:
            List of dictionaries containing kline data with keys:
            - open_time: Open time in milliseconds
            - open: Open price
            - high: Highest price
            - low: Lowest price
            - close: Close price
            - volume: Trading volume
            - close_time: Close time in milliseconds
            - quote_volume: Quote asset volume
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

    def _get_symbols(
        self,
        symbol: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        permissions: Optional[Union[str, List[str]]] = None,
        show_permission_sets: bool = True,
        symbol_status: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Pobiera informacje o symbolach giełdy (exchange info).
        
        Args:
            symbol: Pojedynczy symbol (np. "BTCUSDT")
            symbols: Lista symboli (np. ["BTCUSDT", "ETHUSDT"])
            permissions: Uprawnienia do filtrowania (np. "SPOT", ["MARGIN", "LEVERAGED"])
            show_permission_sets: Czy pokazywać zestawy uprawnień (domyślnie True)
            symbol_status: Status symbolu do filtrowania ("TRADING", "HALT", "BREAK")
            
        Returns:
            Dict zawierający informacje o giełdzie i symbolach:
            {
                "timezone": "UTC",
                "serverTime": 1565246363776,
                "rateLimits": [...],
                "exchangeFilters": [...],
                "symbols": [
                    {
                        "symbol": "ETHBTC",
                        "status": "TRADING",
                        "baseAsset": "ETH",
                        "baseAssetPrecision": 8,
                        "quoteAsset": "BTC",
                        "quotePrecision": 8,
                        "quoteAssetPrecision": 8,
                        "baseCommissionPrecision": 8,
                        "quoteCommissionPrecision": 8,
                        "orderTypes": ["LIMIT", "MARKET", ...],
                        "icebergAllowed": true,
                        "ocoAllowed": true,
                        "otoAllowed": true,
                        "quoteOrderQtyMarketAllowed": true,
                        "allowTrailingStop": false,
                        "cancelReplaceAllowed": false,
                        "amendAllowed": false,
                        "isSpotTradingAllowed": true,
                        "isMarginTradingAllowed": true,
                        "filters": [...],
                        "permissions": [],
                        "permissionSets": [["SPOT", "MARGIN"]],
                        "defaultSelfTradePreventionMode": "NONE",
                        "allowedSelfTradePreventionModes": ["NONE"]
                    }
                ],
                "sors": [...]
            }
        """
        pass

    def _get_wallet_information(self) -> List[Dict[str, Union[bool, str, float]]]:
        """
        Pobiera informacje o portfelu/koncie.
        
        Returns:
            Lista zawierająca informacje o balansach:
            [
                {
                    "is_enabled": bool,
                    "type": str,
                    "currency": str,
                    "amount": float,
                },
                ...
            ]
        """
        pass

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

    def market_buy(self, coin: str, currency_size: float, used_currency: str = "USDT"):
        """
        Wykonuje zlecenie kupna po cenie rynkowej (market order).
        
        Args:
            coin: Symbol monety do kupna (np. BTC)
            currency_size: Kwota waluty quote do wydania na zakup
            used_currency: Waluta quote (domyślnie USDT)
        """
        
        print("")
        print(f"market_buy:")
        print(f"\tcoin: {coin}")
        print(f"\tquote: {used_currency}")
        print(f"\tcurrency size: {currency_size}")

        api_response = self._market_order_request(
            transaction_side = "BUY",
            coin = coin,
            currency_size = currency_size,
            used_currency = used_currency,
        )

        return {
            "order_approach": "market",
            "api_response": api_response,
        }

    def market_sell(self, coin: str, coin_size: float, used_currency: str = "USDT"):
        """
        Wykonuje zlecenie sprzedaży po cenie rynkowej (market order).
        
        Args:
            coin: Symbol monety do sprzedaży (np. BTC)
            coin_size: Ilość monety do sprzedania
            used_currency: Waluta quote (domyślnie USDT)
        """
        
        print("")
        print(f"market_sell:")
        print(f"\tcoin: {coin}")
        print(f"\tquote: {used_currency}")
        print(f"\tcoin size: {coin_size}")

        api_response = self._market_order_request(
            transaction_side = "SELL",
            coin = coin,
            currency_size = 0.0,  # Dla sprzedaży używamy coin_size zamiast currency_size
            used_currency = used_currency,
        )

        return {
            "order_approach": "market",
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

