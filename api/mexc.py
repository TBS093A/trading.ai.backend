from pymexc import spot
from .abstract import AbstractAPI


class MexcAPI(
    AbstractAPI
):
    __api_transaction_requests_limit = {"requests": 499, "in_seconds": 10}

    def __init__(self, api_key: str, api_secret: str, DEBUG: bool = False) -> None:
        self.__api_key = api_key
        self.__api_secret = api_secret

        self.__spot_client = spot.HTTP(
            api_key = self.__api_key,
            api_secret = self.__api_secret
        )

        self.__DEBUG = DEBUG

        super().__init__()

    def _market_order_request(self, transaction_side: str, coin: str, currency_size: float, used_currency: str):
        if self.__DEBUG == False:
            return self.__spot_client.new_order(
                symbol = f"{ coin }{ used_currency }",
                side = transaction_side,
                order_type = "MARKET",
                quantity = currency_size
            )
        if self.__DEBUG == True:
            return {
                "DEBUG": self.__DEBUG
            }

    def _limit_order_request(self, transaction_side: str, coin: str, coin_size: float, coin_price: float, used_currency: str):
        if self.__DEBUG == False:
            return self.__spot_client.new_order(
                symbol = f"{ coin }{ used_currency }",
                side = transaction_side,
                order_type = "LIMIT",
                quantity = coin_size,
                price = coin_price,
            )
        if self.__DEBUG == True:
            return {
                "DEBUG": self.__DEBUG
            }

    def _cancel_all_orders(self, coin: str, used_currency: str):
        if self.__DEBUG == False:
            return self.__spot_client.cancel_all_open_orders(
                symbol = f"{ coin }{ used_currency }"
            )
        if self.__DEBUG == True:
            return {
                "DEBUG": self.__DEBUG
            }

    def _AbstractAPI__get_available_currency_amount_price(self, currency: str = None, asset_type: str = "SPOT"):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        try:
            available_assets = self.__spot_client.account_information()
        except Exception as error:
            if self.__DEBUG == False:
                raise error
            if self.__DEBUG == True:
                return 250.0

        if available_assets["accountType"] == asset_type:
            for asset in available_assets["balances"]:
                if asset["asset"] == currency:
                    return float(asset["free"])
        return 0.0

    def _AbstractAPI__get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "SPOT"):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        try:
            available_assets = self.__spot_client.account_information()
        except Exception as error:
            if self.__DEBUG == False:
                raise error
            if self.__DEBUG == True:
                return 50.0

        if available_assets["accountType"] == asset_type:
            for asset in available_assets["balances"]:
                if asset["asset"] == currency:
                    return str(
                        float(asset["free"]) * float(percent_size)
                    )
        return 0.0

    def _AbstractAPI__get_lot_size(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
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
        symbol_info = self.__spot_client.exchange_info(
            symbol = f"{ base_currency }{ quote_currency }"
        )

        for symbol in symbol_info["symbols"]:
            if symbol["baseAsset"] == base_currency:
                if symbol["quoteAsset"] == quote_currency:

                    base_size_precision = float(symbol["baseSizePrecision"])

                    if base_size_precision == 0:
                        base_size_precision = 1

                    return {
                        "base_asset_precision": symbol["baseAssetPrecision"],
                        "base_commission_precision": symbol["baseCommissionPrecision"],
                        "base_size_precision": str(base_size_precision),

                        "quote_precision": symbol["quotePrecision"],
                        "quote_asset_precision": symbol["quoteAssetPrecision"],
                        "quote_commission_precision": symbol["quoteCommissionPrecision"],
                        "quote_amount_precision": symbol["quoteAmountPrecision"],
                        "quote_max_amount": symbol["maxQuoteAmount"],
                        "is_spot_trading_allowed": str(symbol["isSpotTradingAllowed"]).lower() == "true",
                        "is_margin_trading_allowed": str(symbol["isMarginTradingAllowed"]).lower() == "true"
                    }

    def _AbstractAPI__get_bid_and_ask_prices(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
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
        symbol = self.__spot_client.ticker_book_price(
            symbol = f"{ base_currency }{ quote_currency }"
        )

        if symbol["symbol"] == f"{ base_currency }{ quote_currency }":
            return {
                "bid_price": symbol["bidPrice"],
                "bid_size": symbol["bidQty"],
                "ask_price": symbol["askPrice"],
                "ask_size": symbol["askQty"]
            }

    def _AbstractAPI__get_ticker(self, base_currency: str = "BTC", quote_currency: str = "USDT"):
        """
            current information about symbol:

                {
                    "price"        - current market price
                }
        """
        return self.__spot_client.ticker_price(
            symbol = f"{ base_currency }{ quote_currency }"
        )

