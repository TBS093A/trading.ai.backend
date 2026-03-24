import logging
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)


# Kryptowaluty dostępne na Yahoo Finance (ticker format: CODE-USD)
DEFAULT_CRYPTO_TICKERS = [
    "BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT",
    "MATIC", "SHIB", "AVAX", "LTC", "LINK", "UNI", "ATOM",
    "XLM", "ETC", "FIL", "NEAR", "ALGO", "VET", "ICP",
    "APT", "OP", "ARB", "SUI", "SEI", "TIA", "AAVE", "MKR",
    "CRV", "SNX", "COMP", "LDO", "RUNE", "INJ", "FTM", "MANA",
    "SAND", "AXS", "GALA", "ENJ", "CHZ", "BAT", "ZRX", "1INCH",
    "SUSHI", "YFI", "CAKE", "PEPE", "WIF", "BONK", "FLOKI",
    "RENDER", "FET", "AGIX", "OCEAN", "TAO", "WLD", "RNDR",
    "GRT", "AR", "STX", "IMX", "BLUR", "JUP", "PYTH", "W",
    "PENDLE", "ENA", "ETHFI", "ONDO",
]

INTERVAL_MAP = {
    "1m": "1m",
    "2m": "2m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

QUOTE_TO_YAHOO = {
    "USDT": "USD",
    "USD": "USD",
    "BUSD": "USD",
    "EUR": "EUR",
    "GBP": "GBP",
    "JPY": "JPY",
}


class YahooFinanceAPI(AbstractAPI):

    EXCHANGE_NAME = "YAHOO_FINANCE"

    __api_transaction_requests_limit = {"requests": 2000, "in_seconds": 3600}

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _build_yahoo_symbol(base_currency: str, quote_currency: str) -> str:
        yf_quote = QUOTE_TO_YAHOO.get(quote_currency.upper(), quote_currency.upper())
        return f"{base_currency.upper()}-{yf_quote}"

    @staticmethod
    def _default_period_for_interval(yf_interval: str) -> str:
        if yf_interval in ("1m", "2m", "5m", "15m", "30m"):
            return "7d"
        if yf_interval in ("1h", "60m", "90m"):
            return "60d"
        return "1y"

    # ------------------------------------------------------------------
    # _get_klines
    # ------------------------------------------------------------------

    def _get_klines(
        self,
        base_currency: str = "BTC",
        quote_currency: str = "USDT",
        interval: str = "1d",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Union[int, float, str]]]:
        """
        Pobiera kline/candlestick z Yahoo Finance.

        Args:
            base_currency: Waluta bazowa (np. BTC, ETH, AAPL)
            quote_currency: Waluta kwotowana (np. USDT → mapowane na USD)
            interval: Interwał (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
            start_time: Czas startu w milisekundach (epoch ms)
            end_time: Czas końca w milisekundach (epoch ms)
            limit: Maks. liczba rekordów

        Returns:
            Lista dict z kluczami: open_time, open, high, low, close, volume,
            close_time, quote_volume
        """
        try:
            symbol = self._build_yahoo_symbol(base_currency, quote_currency)
            yf_interval = INTERVAL_MAP.get(interval, interval)

            ticker = yf.Ticker(symbol)
            kwargs: dict = {"interval": yf_interval}

            if start_time:
                kwargs["start"] = datetime.fromtimestamp(
                    start_time / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            if end_time:
                kwargs["end"] = datetime.fromtimestamp(
                    end_time / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")

            if not start_time and not end_time:
                kwargs["period"] = self._default_period_for_interval(yf_interval)

            history = ticker.history(**kwargs)

            if history.empty:
                logger.warning(f"Yahoo Finance: brak danych dla {symbol} ({yf_interval})")
                return []

            if len(history) > limit:
                history = history.tail(limit)

            formatted_klines: list = []
            for idx, row in history.iterrows():
                ts = idx
                if hasattr(ts, "timestamp"):
                    open_time_ms = int(ts.timestamp() * 1000)
                else:
                    open_time_ms = int(ts)

                formatted_klines.append({
                    "open_time": open_time_ms,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                    "close_time": open_time_ms,
                    "quote_volume": float(row["Close"]) * float(row["Volume"]),
                })

            return formatted_klines

        except Exception as error:
            logger.error(
                f"Yahoo Finance _get_klines error ({base_currency}/{quote_currency}, "
                f"{interval}): {error}"
            )
            raise

    # ------------------------------------------------------------------
    # _get_symbols
    # ------------------------------------------------------------------

    def _get_symbols(
        self,
        asset_codes: Optional[List[str]] = None,
        permissions: Optional[Union[str, List[str]]] = None,
        show_permission_sets: bool = True,
        symbol_status: Optional[str] = None,
    ) -> List[Dict[str, any]]:
        """
        Pobiera dostępne symbole z Yahoo Finance.

        Przy braku asset_codes pobiera domyślną listę popularnych kryptowalut.
        Waliduje je batchowo przez yf.download() (jedno żądanie HTTP).

        Returns:
            Lista dict: symbol, status, base_asset, quote_asset
        """
        try:
            codes = asset_codes if asset_codes else DEFAULT_CRYPTO_TICKERS
            yahoo_symbols = [f"{code.upper()}-USD" for code in codes]

            data = yf.download(
                yahoo_symbols,
                period="1d",
                progress=False,
                threads=True,
            )

            if data.empty:
                logger.warning("Yahoo Finance: yf.download zwrócił pusty DataFrame")
                return []

            symbols_info: list = []

            if len(yahoo_symbols) == 1:
                if not data["Close"].dropna().empty:
                    base = yahoo_symbols[0].split("-")[0]
                    symbols_info.append({
                        "symbol": yahoo_symbols[0],
                        "status": "TRADING",
                        "base_asset": base,
                        "quote_asset": "USDT",
                    })
            else:
                for yf_sym in yahoo_symbols:
                    try:
                        col = data["Close"][yf_sym] if yf_sym in data["Close"].columns else None
                        if col is not None and not col.dropna().empty:
                            base = yf_sym.split("-")[0]
                            symbols_info.append({
                                "symbol": yf_sym,
                                "status": "TRADING",
                                "base_asset": base,
                                "quote_asset": "USDT",
                            })
                    except (KeyError, TypeError):
                        continue

            logger.info(f"Yahoo Finance: znaleziono {len(symbols_info)} aktywnych symboli")
            return symbols_info

        except Exception as error:
            logger.error(f"Yahoo Finance _get_symbols error: {error}")
            raise
