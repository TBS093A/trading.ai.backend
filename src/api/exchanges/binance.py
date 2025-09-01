from binance.spot import Spot
from .abstract import AbstractAPI
from typing import List, Dict, Union, Optional


class BinanceAPI(
    AbstractAPI
):

    EXCHANGE_NAME = "BINANCE"

    __api_transaction_requests_limit = {"requests": 6000, "in_seconds": 60}

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
        Get kline/candlestick data for a symbol from Binance.
        
        Args:
            base_currency: Base currency symbol (e.g. BTC)
            quote_currency: Quote currency symbol (e.g. USDT)
            interval: Kline interval (e.g. 1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
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
            - trades: Number of trades
            - taker_buy_base_volume: Taker buy base asset volume
            - taker_buy_quote_volume: Taker buy quote asset volume
        """
        try:
            params = {
                "symbol": f"{base_currency}{quote_currency}",
                "interval": interval,
                "limit": min(limit, 1000)  # Binance limit is 1000
            }
            
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
                
            klines = self.__spot_client.klines(**params)
            
            # Transform raw kline data into dictionary format
            # Binance response format:
            # [open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base_volume, taker_buy_quote_volume, ignore]
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
                    "quote_volume": float(kline[7]),
                    "trades": int(kline[8]),
                    "taker_buy_base_volume": float(kline[9]),
                    "taker_buy_quote_volume": float(kline[10])
                })
                
            return formatted_klines
            
        except Exception as error:
            raise error

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

    def _get_symbols(
        self,
        asset_codes: Optional[List[str]] = None,
        permissions: Optional[Union[str, List[str]]] = None,
        show_permission_sets: bool = True,
        symbol_status: Optional[str] = None
    ) -> List[Dict[str, any]]:
        """
        Pobiera informacje o symbolach giełdy Binance (exchange info).
        
        Args:
            symbol: Pojedynczy symbol (np. "BTCUSDT")
            symbols: Lista symboli (np. ["BTCUSDT", "ETHUSDT"])
            permissions: Uprawnienia do filtrowania (np. "SPOT", ["MARGIN", "LEVERAGED"])
            show_permission_sets: Czy pokazywać zestawy uprawnień (domyślnie True)
            symbol_status: Status symbolu do filtrowania ("TRADING", "HALT", "BREAK")
            
        Returns:
            List[dict[str, any]] zawierający informacje o giełdzie i symbolach zgodnie z dokumentacją Binance API v3:
                [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "base_asset": "BTC",
                        "quote_asset": "USDT"
                    }
                ]
            
        Raises:
            Exception: Gdy wystąpi błąd podczas pobierania danych z API
        """
        try:
            params = {}
            
            if asset_codes:
                # Parametr symbol (pojedynczy)
                if len(asset_codes) == 1:
                    params['symbol'] = asset_codes[0]
            
                # Parametr symbols (lista)
                if len(asset_codes) > 1:
                    params['symbols'] = asset_codes
            
            # Parametr permissions (pojedynczy lub lista)
            if permissions:
                params['permissions'] = permissions
            
            # Parametr showPermissionSets
            if not show_permission_sets:
                params['showPermissionSets'] = show_permission_sets
            
            # Parametr symbolStatus
            if symbol_status:
                params['symbolStatus'] = symbol_status
            
            # Wywołanie API
            exchange_info = self.__spot_client.exchange_info(**params)

            symbols_info = []
    
            for symbol_from_api in exchange_info["symbols"]:

                
                if asset_codes != None:
                    if symbol_from_api["baseAsset"] not in asset_codes:
                        continue
                
                symbols_info.append({
                    "symbol": symbol_from_api["symbol"],
                    "status": symbol_from_api["status"],
                    "base_asset": symbol_from_api["baseAsset"],
                    "quote_asset": symbol_from_api["quoteAsset"]
                })
                
            return symbols_info
            
        except Exception as error:
            raise Exception(f"Błąd podczas pobierania informacji o symbolach: {error}")

    def _get_wallet_information(self) -> List[Dict[str, Union[str, float]]]:
        """
        Pobiera informacje o portfelu/koncie z Binance.
        
        Returns:
            Lista zawierająca informacje o balansach:
            [
                {
                    "type": str,
                    "currency": str,
                    "amount": float,
                },
                ...
            ]
            
        Note: 
            is_enabled field is calculated automatically by sync layer based on type == "SPOT"
        """
        account_info = self.__spot_client.account()
        
        # Przekształć odpowiedź do żądanego formatu
        wallet_balances = []
        
        for balance in account_info["balances"]:
            wallet_balances.append({
                "type": account_info["accountType"],
                "currency": balance["asset"],
                "amount": float(balance["free"]),
            })
        
        return wallet_balances

