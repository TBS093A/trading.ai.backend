import logging
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kryptowaluty — na Yahoo Finance ticker format: CODE-USD
# ---------------------------------------------------------------------------
CRYPTO_TICKERS = {
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
}

# ---------------------------------------------------------------------------
# Akcje — bezpośredni ticker (S&P 500, NASDAQ, blue-chips globalne)
# ---------------------------------------------------------------------------
STOCK_TICKERS = [
    # US — Tech / Mega-Cap
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "INTC", "CSCO", "QCOM", "TXN",
    "NFLX", "SHOP", "SNOW", "UBER", "ABNB", "SQ", "PLTR", "COIN",
    "PYPL", "NOW", "PANW", "CRWD", "DDOG", "ZS", "NET", "MDB",
    "TEAM", "WDAY", "VEEV", "HUBS", "TTD", "ROKU", "SNAP", "PINS",
    "RBLX", "U", "HOOD", "RIVN", "LCID", "NIO", "XPEV", "LI",
    # US — Finanse
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK",
    "SCHW", "C", "BRK-B", "SPGI", "MCO", "ICE", "CME",
    # US — Healthcare / Pharma
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT",
    "DHR", "BMY", "AMGN", "GILD", "ISRG", "MDT", "VRTX", "REGN",
    "MRNA", "BIIB",
    # US — Przemysł / Energia / Materiały
    "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "PSX",
    "CAT", "DE", "HON", "GE", "RTX", "LMT", "BA", "UPS", "FDX",
    "MMM",
    # US — Consumer / Retail
    "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD",
    "KO", "PEP", "PG", "CL", "PM", "MO", "DIS", "CMCSA",
    # EU / Global
    "ASML", "SAP", "NVO", "TM", "SONY", "TSM", "BABA", "JD",
    "PDD", "TCEHY", "BIDU", "SE", "GRAB", "MELI",
]

# ---------------------------------------------------------------------------
# ETF-y — bezpośredni ticker
# ---------------------------------------------------------------------------
ETF_TICKERS = [
    # Indeksowe US
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV",
    # Sektorowe
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY", "XLRE",
    "XLC", "XLB",
    # Rynki zagraniczne / EM
    "EEM", "EFA", "VWO", "IEMG", "FXI", "KWEB", "INDA",
    # Obligacje
    "TLT", "IEF", "SHY", "BND", "HYG", "LQD", "AGG",
    # Surowce / Złoto
    "GLD", "SLV", "USO", "UNG", "PDBC", "DBA",
    # Volatility / Leverage
    "SQQQ", "TQQQ", "SOXL", "SOXS", "ARKK", "ARKG",
    # Tematyczne
    "BOTZ", "ROBO", "HACK", "SOXX", "SMH", "BLOK", "BITO",
]

# ---------------------------------------------------------------------------
# Indeksy — format ^CODE
# ---------------------------------------------------------------------------
INDEX_TICKERS = [
    "^GSPC",   # S&P 500
    "^IXIC",   # NASDAQ Composite
    "^DJI",    # Dow Jones
    "^RUT",    # Russell 2000
    "^VIX",    # CBOE Volatility
    "^FTSE",   # FTSE 100
    "^GDAXI",  # DAX
    "^N225",   # Nikkei 225
    "^HSI",    # Hang Seng
    "^STOXX50E",  # Euro Stoxx 50
]

# ---------------------------------------------------------------------------
# Surowce / Futures — format CODE=F
# ---------------------------------------------------------------------------
COMMODITY_TICKERS = [
    "GC=F",    # Gold
    "SI=F",    # Silver
    "CL=F",    # Crude Oil WTI
    "BZ=F",    # Brent Crude
    "NG=F",    # Natural Gas
    "HG=F",    # Copper
    "PL=F",    # Platinum
    "ZC=F",    # Corn
    "ZW=F",    # Wheat
    "ZS=F",    # Soybeans
]

# ---------------------------------------------------------------------------
# Forex — format CODE=X
# ---------------------------------------------------------------------------
FOREX_TICKERS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X",
    "USDCAD=X", "NZDUSD=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
    "USDPLN=X", "USDTRY=X", "USDBRL=X", "USDMXN=X", "USDINR=X",
    "USDCNY=X", "USDSGD=X", "USDHKD=X", "USDKRW=X", "DX-Y.NYB",
]

# ---------------------------------------------------------------------------
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


def _yahoo_symbol_for(base: str) -> str:
    """Zwraca pełny ticker Yahoo Finance na podstawie kodu assetu."""
    base_upper = base.upper()
    if base_upper in CRYPTO_TICKERS:
        return f"{base_upper}-USD"
    return base_upper


def _base_from_yahoo_symbol(yf_sym: str) -> str:
    """Wyciąga bazowy kod assetu z tickera Yahoo Finance."""
    if yf_sym.endswith("-USD"):
        return yf_sym[:-4]
    if yf_sym.startswith("^"):
        return yf_sym
    if "=F" in yf_sym:
        return yf_sym
    if "=X" in yf_sym:
        return yf_sym
    return yf_sym


class YahooFinanceAPI(AbstractAPI):

    EXCHANGE_NAME = "YAHOO_FINANCE"

    __api_transaction_requests_limit = {"requests": 2000, "in_seconds": 3600}

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _build_yahoo_symbol(base_currency: str, quote_currency: str) -> str:
        """Konwertuje parę (base, quote) na ticker Yahoo Finance.

        Krypto → CODE-USD, indeksy/futures/forex → bez zmian, akcje/ETF → ticker.
        """
        base = base_currency.upper()
        if base in CRYPTO_TICKERS:
            yf_quote = QUOTE_TO_YAHOO.get(quote_currency.upper(), quote_currency.upper())
            return f"{base}-{yf_quote}"
        return base

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

        Obsługuje kryptowaluty (BTC-USD), akcje (AAPL), ETF-y (SPY),
        indeksy (^GSPC), surowce (GC=F) i forex (EURUSD=X).
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

    @staticmethod
    def _build_default_yahoo_symbols() -> List[str]:
        """Buduje pełną listę tickerów Yahoo Finance ze wszystkich kategorii."""
        symbols: list = []
        symbols.extend(f"{c}-USD" for c in sorted(CRYPTO_TICKERS))
        symbols.extend(STOCK_TICKERS)
        symbols.extend(ETF_TICKERS)
        symbols.extend(INDEX_TICKERS)
        symbols.extend(COMMODITY_TICKERS)
        symbols.extend(FOREX_TICKERS)
        return symbols

    def _get_symbols(
        self,
        asset_codes: Optional[List[str]] = None,
        permissions: Optional[Union[str, List[str]]] = None,
        show_permission_sets: bool = True,
        symbol_status: Optional[str] = None,
    ) -> List[Dict[str, any]]:
        """
        Pobiera dostępne symbole z Yahoo Finance — krypto, akcje, ETF-y,
        indeksy, surowce, forex.

        Waliduje batchowo przez yf.download() (jedno żądanie HTTP na batch).
        """
        try:
            if asset_codes:
                yahoo_symbols = [_yahoo_symbol_for(code) for code in asset_codes]
            else:
                yahoo_symbols = self._build_default_yahoo_symbols()

            symbols_info: list = []
            batch_size = 100

            for i in range(0, len(yahoo_symbols), batch_size):
                batch = yahoo_symbols[i : i + batch_size]
                logger.info(
                    f"Yahoo Finance: walidacja batch {i // batch_size + 1} "
                    f"({len(batch)} tickerów)"
                )

                data = yf.download(
                    batch,
                    period="5d",
                    progress=False,
                    threads=True,
                )

                if data.empty:
                    continue

                if len(batch) == 1:
                    if not data["Close"].dropna().empty:
                        base = _base_from_yahoo_symbol(batch[0])
                        symbols_info.append({
                            "symbol": batch[0],
                            "status": "TRADING",
                            "base_asset": base,
                            "quote_asset": "USDT",
                        })
                else:
                    for yf_sym in batch:
                        try:
                            col = (
                                data["Close"][yf_sym]
                                if yf_sym in data["Close"].columns
                                else None
                            )
                            if col is not None and not col.dropna().empty:
                                base = _base_from_yahoo_symbol(yf_sym)
                                symbols_info.append({
                                    "symbol": yf_sym,
                                    "status": "TRADING",
                                    "base_asset": base,
                                    "quote_asset": "USDT",
                                })
                        except (KeyError, TypeError):
                            continue

            logger.info(
                f"Yahoo Finance: znaleziono {len(symbols_info)} aktywnych symboli "
                f"(z {len(yahoo_symbols)} sprawdzonych)"
            )
            return symbols_info

        except Exception as error:
            logger.error(f"Yahoo Finance _get_symbols error: {error}")
            raise
