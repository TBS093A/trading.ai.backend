from binance.spot import Spot
from .abstract import AbstractAPI


class BinanceAPI(
    AbstractAPI
):

    def __init__(self, api_key: str, api_secret: str) -> None:
        self.__api_key = api_key
        self.__api_secret = api_secret

        self.__spot_client = Spot(
            api_key = self.__api_key,
            api_secret = self.__api_secret
        )

        super().__init__()

    def _market_order_request(self, transaction_side: str, coin: str, currency_size: float, used_currency: str):
        return self.__spot_client.new_order(
            symbol = f"{ coin }{ used_currency }",
            side = transaction_side,
            type = "MARKET",
            quantity = currency_size
        )

    def _limit_order_request(self, transaction_side: str, coin: str, coin_size: float, coin_price: float, used_currency: str):
        return self.__spot_client.new_order(
            symbol = f"{ coin }{ used_currency }",
            side = transaction_side,
            type = "LIMIT",
            quantity = coin_size,
            price = coin_price,
        )


    def _AbstractAPI__get_available_currency_percent_price(self, percent_size: float, currency: str = None, asset_type: str = "assets"):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)

            where asset_type can be "assets" (BTC/USDC/USDT) or "positions" (opened positions on symbols like BTCUSDT or etc.)

            docs:

               https://binance-docs.github.io/apidocs/futures/en/#account-information-v3-user_data
        """
        available_assets = self.__spot_client.account()

        for asset in available_assets[asset_type]:
            if available_assets["asset"] == currency:
                return str(
                    float(asset["availableBalance"]) * float(percent_size)
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
                    "symbol":      - position symbol (like BTCUSDT)
                    "time":        - date time in seconds
                }

            docs:

                https://binance-docs.github.io/apidocs/futures/en/#symbol-price-ticker
        """
        return self.__spot_client.ticker_price(
            symbol = f"{ base_currency }{ quote_currency }"
        )

