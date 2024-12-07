import requests
import logging


class AbstractAPI:

    __general_endpoint = ""
    __buy_endpoint = ""
    __sell_endpoint = ""

    __api_transaction_requests_limit = {"requests": 499, "in_seconds": 10}

    def __init__(self, available_quote: float = 500.0, coin_price_at_buy: float = 0.0034, coin_price_at_sell: float = 0.034, available_coin_assets: float = 0.0):
        self.__buy_transaction = {}
        self.__actual_size = 0.0
        self.__actual_price = 0.0
        self.__sell_transactions = {}

        self.available_quote: float = available_quote
        self.coin_price_at_buy: float = coin_price_at_buy
        self.coin_price_at_sell: float = coin_price_at_sell
        self.available_coin_assets: float = available_coin_assets

        self.bid_price = coin_price_at_sell - (coin_price_at_sell / 10)
        self.ask_price = coin_price_at_buy + (coin_price_at_buy / 10)

    def get_api_transaction_requests_limit(self):
        return self.__api_transaction_requests_limit

    def check_quote_is_available(self):
        return self.__quote_is_available

    def check_asset_is_available(self):
        return self.__asset_is_available

    def _cancel_all_orders(self, coin: str, used_currency: str):
        """
            functionality which will define all orders cancel operation
        """
        return {
            "all_orders_canceled": True
        }

    def __get_available_currency_amount_price(self, currency: str = None, asset_type: str = "") -> float:
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        if "QUOTE".lower() in currency.lower():
            return self.available_quote
        if "ASSET".lower() in currency.lower():
            return self.available_coin_assets

    def __pop_available_currency(self, size: float, currency: str = None, asset_type: str = ""):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        if "QUOTE".lower() in currency.lower():
            if self.available_quote > float(size):
                self.available_quote -= float(size)
            elif self.available_quote <= float(size):
                size = self.available_quote
                self.available_quote = 0.0
            elif self.available_quote == 0.0:
                raise Exception(
                    message = "Overbought"
                )
            return size
        if "ASSET".lower() in currency.lower():
            if self.available_asset > float(size):
                self.available_asset -= float(size)
            else:
                size = self.available_asset
                self.available_asset = 0.0
            return size

    def __get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "") -> float:
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        if "QUOTE".lower() in currency.lower():
            return self.available_quote * percent_size
        if "ASSET".lower() in currency.lower():
            return self.available_coin_assets * percent_size

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
            "bid_price": f"{self.bid_price}",
            "bid_size": "",
            "ask_price": f"{self.ask_price}",
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
            "price": f"{self.coin_price_at_sell}"
        }

    def buy(self, coin: str, currency_size_to_buy: float, used_currency: str = "USDT", price_buy_balance_percent: float = 0.1):

        bought_assets_price: float = self.__pop_available_currency(
            size = currency_size_to_buy,
            currency = "QUOTE"
        )

        asset_used_price: float = self.ask_price - self.ask_price * price_buy_balance_percent # bought_assets_price / self.coin_price_at_buy

        bought_assets_size: float = bought_assets_price / asset_used_price

        self.available_coin_assets += bought_assets_size

        return {
            "currency_size_to_buy": currency_size_to_buy,
            "bought_assets_size": bought_assets_size,
            "bought_assets_price": bought_assets_price,
            "available_quote_after": self.available_quote,
            "available_asset_after": self.available_coin_assets,
            "asset_market_price": self.coin_price_at_buy,
            "asset_used_price": asset_used_price,
        }

    def sell(self, coin: str, coin_percent_size_to_sell: float, used_currency: str = "USDT", price_sell_balance_percent: float = 0.1):

        sold_assets_size: float = self.available_coin_assets * coin_percent_size_to_sell

        asset_used_price: float = self.bid_price + self.bid_price * price_sell_balance_percent # self.coin_price_at_sell * sold_assets_size

        sold_assets_price: float = asset_used_price * sold_assets_size

        self.available_quote += sold_assets_price

        self.available_coin_assets -= sold_assets_size

        return {
            "asset_percent_size_to_sell": coin_percent_size_to_sell,
            "sold_assets_size": sold_assets_size,
            "sold_assets_price": sold_assets_price,
            "available_quote_after": self.available_quote,
            "available_asset_after": self.available_coin_assets,
            "asset_market_price": self.coin_price_at_sell,
            "asset_used_price": asset_used_price,
        }


