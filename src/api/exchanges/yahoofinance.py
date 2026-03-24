import logging
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domyślne tickery Yahoo Finance — wszystkie kategorie
# Ticker = base_asset (przechowywany w bazie 1:1)
# ---------------------------------------------------------------------------

CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "ADA-USD",
    "SOL-USD", "DOGE-USD", "DOT-USD", "MATIC-USD", "SHIB-USD",
    "AVAX-USD", "LTC-USD", "LINK-USD", "UNI-USD", "ATOM-USD",
    "XLM-USD", "ETC-USD", "FIL-USD", "NEAR-USD", "ALGO-USD",
    "VET-USD", "ICP-USD", "APT-USD", "OP-USD", "ARB-USD",
    "SUI-USD", "SEI-USD", "TIA-USD", "AAVE-USD", "MKR-USD",
    "CRV-USD", "SNX-USD", "COMP-USD", "LDO-USD", "RUNE-USD",
    "INJ-USD", "FTM-USD", "MANA-USD", "SAND-USD", "AXS-USD",
    "GALA-USD", "ENJ-USD", "CHZ-USD", "BAT-USD", "ZRX-USD",
    "1INCH-USD", "SUSHI-USD", "YFI-USD", "CAKE-USD", "PEPE-USD",
    "WIF-USD", "BONK-USD", "FLOKI-USD", "RENDER-USD", "FET-USD",
    "AGIX-USD", "OCEAN-USD", "TAO-USD", "WLD-USD", "RNDR-USD",
    "GRT-USD", "AR-USD", "STX-USD", "IMX-USD", "BLUR-USD",
    "JUP-USD", "PYTH-USD", "W-USD", "PENDLE-USD", "ENA-USD",
    "ETHFI-USD", "ONDO-USD",
]

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

ETF_TICKERS = [
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV",
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY", "XLRE",
    "XLC", "XLB",
    "EEM", "EFA", "VWO", "IEMG", "FXI", "KWEB", "INDA",
    "TLT", "IEF", "SHY", "BND", "HYG", "LQD", "AGG",
    "GLD", "SLV", "USO", "UNG", "PDBC", "DBA",
    "SQQQ", "TQQQ", "SOXL", "SOXS", "ARKK", "ARKG",
    "BOTZ", "ROBO", "HACK", "SOXX", "SMH", "BLOK", "BITO",
]

INDEX_TICKERS = [
    "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX",
    "^FTSE", "^GDAXI", "^N225", "^HSI", "^STOXX50E",
]

COMMODITY_TICKERS = [
    "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F",
    "HG=F", "PL=F", "ZC=F", "ZW=F", "ZS=F",
]

FOREX_TICKERS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X",
    "USDCAD=X", "NZDUSD=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
    "USDPLN=X", "USDTRY=X", "USDBRL=X", "USDMXN=X", "USDINR=X",
    "USDCNY=X", "USDSGD=X", "USDHKD=X", "USDKRW=X", "DX-Y.NYB",
]

ALL_DEFAULT_TICKERS = (
    CRYPTO_TICKERS + STOCK_TICKERS + ETF_TICKERS
    + INDEX_TICKERS + COMMODITY_TICKERS + FOREX_TICKERS
)


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
        ^GSPC, GC=F, EURUSD=X). interval i pozostałe parametry lecą prosto
        do yfinance bez żadnych mapowań.
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
        Pobiera dostępne symbole z Yahoo Finance — krypto, akcje, ETF-y,
        indeksy, surowce, forex.

        Ticker Yahoo Finance = base_asset (1:1, bez konwersji).
        Waliduje batchowo przez yf.download().
        """
        try:
            yahoo_symbols = list(asset_codes) if asset_codes else list(ALL_DEFAULT_TICKERS)

            symbols_info: list = []
            batch_size = 100

            for i in range(0, len(yahoo_symbols), batch_size):
                batch = yahoo_symbols[i : i + batch_size]
                logger.info(
                    f"Yahoo Finance: walidacja batch {i // batch_size + 1} "
                    f"({len(batch)} tickerów)"
                )

                data = yf.download(batch, period="5d", progress=False, threads=True)

                if data.empty:
                    continue

                if len(batch) == 1:
                    if not data["Close"].dropna().empty:
                        symbols_info.append({
                            "symbol": batch[0],
                            "status": "TRADING",
                            "base_asset": batch[0],
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
                                symbols_info.append({
                                    "symbol": yf_sym,
                                    "status": "TRADING",
                                    "base_asset": yf_sym,
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
