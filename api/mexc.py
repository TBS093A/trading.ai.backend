from pymexc import spot
from .abstract import AbstractAPI
from typing import List, Dict, Union, Optional


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

    def _AbstractAPI__pop_available_currency(self, size: float, currency: str = None, asset_type: str = "SPOT"):
        """
            currency availability on account. Currency in that meaning can be base (e.g. BTC) and quote (e.g. USDT)
        """
        try:
            available_assets = self.__spot_client.account_information()
        except Exception as error:
            if self.__DEBUG == False:
                raise error
            if self.__DEBUG == True:
                self.__quote_is_available = False
                return size

        if available_assets["accountType"] == asset_type:
            for asset in available_assets["balances"]:
                if asset["asset"] == currency:
                    if float(asset["free"]) <= float(size):
                        return float(asset["free"])
                    if float(asset["free"]) > float(size):
                        return float(size)
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
        Get kline/candlestick data for a symbol from MEXC.
        
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
        try:
            params = {
                "symbol": f"{base_currency}{quote_currency}",
                "interval": interval,
                "limit": min(limit, 1000)  # MEXC limit is 1000
            }
            
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
                
            klines = self.__spot_client.klines(**params)
            
            # Transform raw kline data into dictionary format
            formatted_klines = []
            for kline in klines:
                formatted_klines.append({
                    "open_time": int(kline[0]),
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                    "close_time": int(kline[6]),
                    "quote_volume": float(kline[7])
                })
                
            return formatted_klines
            
        except Exception as error:
            if self.__DEBUG:
                # Return sample data in debug mode
                return [{
                    "open_time": 1640804880000,
                    "open": 47482.36,
                    "high": 47482.36,
                    "low": 47416.57,
                    "close": 47436.1,
                    "volume": 3.550717,
                    "close_time": 1640804940000,
                    "quote_volume": 168387.3
                }]
            raise error

