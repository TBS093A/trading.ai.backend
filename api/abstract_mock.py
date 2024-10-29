import requests
import logging


class AbstractAPI:

    __general_endpoint = ""
    __buy_endpoint = ""
    __sell_endpoint = ""

    def __init__(self, available_quote: float = 500.0, coin_price_at_buy: float = 0.0034, coin_price_at_sell: float = 0.034, available_coin_assets: float = 0.0):
        self.__buy_transaction = {}
        self.__actual_size = 0.0
        self.__actual_price = 0.0
        self.__sell_transactions = {}

        self.available_quote: float = available_quote
        self.coin_price_at_buy: float = coin_price_at_buy
        self.coin_price_at_sell: float = coin_price_at_sell
        self.available_coin_assets: float = available_coin_assets

    def __get_available_currency_amount_price(self, currency: str = None, asset_type: str = "") -> float:
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        return self.available_quote

    def __get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "") -> float:
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        return self.available_quote * percent_size

    def buy(self, coin: str, currency_percent_size_to_buy: float, used_currency: str = "USDT", price_buy_balance_percent: float = 0.1):

        bought_assets_price: float = self.available_quote * currency_percent_size_to_buy

        self.available_quote -= bought_assets_price

        self.available_coin_assets += bought_assets_price / self.coin_price_at_buy

        return {
            "coin": coin,
            "currency_percent_size_to_buy": currency_percent_size_to_buy,
            "used_currency": used_currency,
            "price_buy_balance_percent": price_buy_balance_percent,
            "transaction": {
                "bought_assets_price": bought_assets_price,
                "available_quote_after": self.available_quote,
                "available_coin_assets_after": self.available_coin_assets,
                "coin_price": self.coin_price_at_buy
            }
        }

    def sell(self, coin: str, coin_percent_size_to_sell: float, used_currency: str = "USDT", price_sell_balance_percent: float = 0.1):

        sold_assets_price: float = self.available_coin_assets * coin_percent_size_to_sell

        self.available_quote += self.coin_price_at_sell * sold_assets_price

        self.available_coin_assets -= sold_assets_price

        return {
            "coin": coin,
            "coin_percent_size_to_sell": coin_percent_size_to_sell,
            "used_currency": used_currency,
            "price_sell_balance_percent": price_sell_balance_percent,
            "transaction": {
                "sold_assets_price": sold_assets_price,
                "available_quote_after": self.available_quote,
                "available_coin_assets_after": self.available_coin_assets,
                "coin_price": self.coin_price_at_sell
            }
        }


