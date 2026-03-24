import logging
import time
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf
from yfinance import EquityQuery, FundQuery

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)

SCREEN_PAGE_SIZE = 250
SCREEN_SLEEP_BETWEEN_PAGES = 1.5
SCREEN_SLEEP_BETWEEN_TYPES = 3.0


class YahooFinanceAPI(AbstractAPI):

    EXCHANGE_NAME = "YAHOO_FINANCE"

    __api_transaction_requests_limit = {"requests": 2000, "in_seconds": 3600}

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _default_period_for_interval(interval: str) -> str:
        if interval in ("1m", "2m", "5m", "15m", "30m"):
            return "7d"
        if interval in ("1h", "60m", "90m"):
            return "60d"
        return "1y"

    # ------------------------------------------------------------------
    # _get_klines
    # ------------------------------------------------------------------

    def _get_klines(
        self,
        base_currency: str = "BTC-USD",
        quote_currency: str = "USDT",
        interval: str = "1d",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Union[int, float, str]]]:
        """
        Pobiera kline/candlestick z Yahoo Finance.

        base_currency to bezpośredni ticker Yahoo Finance (np. AAPL, BTC-USD,
        ^GSPC, GC=F, EURUSD=X). Parametry lecą prosto do yfinance.
        """
        try:
            symbol = base_currency
            ticker = yf.Ticker(symbol)
            kwargs: dict = {"interval": interval}

            if start_time:
                kwargs["start"] = datetime.fromtimestamp(
                    start_time / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            if end_time:
                kwargs["end"] = datetime.fromtimestamp(
                    end_time / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d")

            if not start_time and not end_time:
                kwargs["period"] = self._default_period_for_interval(interval)

            history = ticker.history(**kwargs)

            if history.empty:
                logger.warning(f"Yahoo Finance: brak danych dla {symbol} ({interval})")
                return []

            if len(history) > limit:
                history = history.tail(limit)

            formatted_klines: list = []
            for idx, row in history.iterrows():
                ts = idx
                open_time_ms = int(ts.timestamp() * 1000) if hasattr(ts, "timestamp") else int(ts)

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
            logger.error(f"Yahoo Finance _get_klines error ({base_currency}, {interval}): {error}")
            raise

    # ------------------------------------------------------------------
    # _get_symbols  (yf.screen — dynamicznie, jak Binance exchange_info)
    # ------------------------------------------------------------------

    @staticmethod
    def _screen_paginated(
        query,
        label: str,
        seen: set,
    ) -> List[Dict[str, any]]:
        """Paginuje przez yf.screen() i zwraca wszystkie symbole."""
        symbols: list = []
        offset = 0

        while True:
            try:
                resp = yf.screen(query, size=SCREEN_PAGE_SIZE, offset=offset)

                quotes = resp.get("quotes", [])
                total = resp.get("total", 0)

                if not quotes:
                    break

                for q in quotes:
                    sym = q.get("symbol")
                    if sym and sym not in seen:
                        seen.add(sym)
                        symbols.append({
                            "symbol": sym,
                            "status": "TRADING",
                            "base_asset": sym,
                            "quote_asset": "USDT",
                        })

                offset += SCREEN_PAGE_SIZE
                if offset >= total:
                    break

                time.sleep(SCREEN_SLEEP_BETWEEN_PAGES)

            except Exception as e:
                logger.warning(f"Yahoo Finance screen ({label}, offset={offset}): {e}")
                break

        return symbols

    def _get_symbols(
        self,
        asset_codes: Optional[List[str]] = None,
        permissions: Optional[Union[str, List[str]]] = None,
        show_permission_sets: bool = True,
        symbol_status: Optional[str] = None,
    ) -> List[Dict[str, any]]:
        """
        Pobiera wszystkie dostępne symbole z Yahoo Finance przez yf.screen().

        Dynamicznie odpytuje Yahoo Finance Screener (EquityQuery + FundQuery)
        i paginuje po 250 wyników — analogicznie do Binance exchange_info().
        Ticker Yahoo Finance = base_asset (1:1, bez konwersji).
        """
        try:
            if asset_codes:
                return [
                    {
                        "symbol": code,
                        "status": "TRADING",
                        "base_asset": code,
                        "quote_asset": "USDT",
                    }
                    for code in asset_codes
                ]

            all_symbols: list = []
            seen: set = set()

            # Equities — wszystkie akcje z ceną > 0
            logger.info("Yahoo Finance screen: pobieranie EQUITY...")
            eq_query = EquityQuery("gt", ["intradayprice", 0])
            eq_symbols = self._screen_paginated(eq_query, "EQUITY", seen)
            all_symbols.extend(eq_symbols)
            logger.info(f"Yahoo Finance screen: EQUITY → {len(eq_symbols)} symboli")

            time.sleep(SCREEN_SLEEP_BETWEEN_TYPES)

            # Funds / ETF — wszystkie fundusze z ceną > 0
            logger.info("Yahoo Finance screen: pobieranie FUND/ETF...")
            fund_query = FundQuery("gt", ["intradayprice", 0])
            fund_symbols = self._screen_paginated(fund_query, "FUND", seen)
            all_symbols.extend(fund_symbols)
            logger.info(f"Yahoo Finance screen: FUND/ETF → {len(fund_symbols)} symboli")

            logger.info(f"Yahoo Finance screen: łącznie {len(all_symbols)} unikalnych symboli")
            return all_symbols

        except Exception as error:
            logger.error(f"Yahoo Finance _get_symbols error: {error}")
            raise
