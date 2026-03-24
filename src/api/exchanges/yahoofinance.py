import logging
import time
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tickery per giełda/kraj — format Yahoo Finance
# US: bez sufiksu, reszta: TICKER.SUFFIX
# ---------------------------------------------------------------------------

US_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "INTC", "CSCO", "QCOM", "TXN",
    "NFLX", "UBER", "ABNB", "SQ", "PLTR", "COIN", "PYPL", "NOW",
    "PANW", "CRWD", "DDOG", "ZS", "NET", "SNOW", "SHOP",
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "BRK-B",
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "MRNA",
    "XOM", "CVX", "COP", "SLB",
    "CAT", "DE", "HON", "GE", "RTX", "LMT", "BA",
    "WMT", "COST", "HD", "LOW", "NKE", "SBUX", "MCD",
    "KO", "PEP", "PG", "DIS", "CMCSA",
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI",
    "GLD", "SLV", "TLT", "ARKK", "SOXX", "TQQQ", "SQQQ",
]

JP_TICKERS = [
    "7203.T",   # Toyota
    "6758.T",   # Sony
    "9984.T",   # SoftBank Group
    "6861.T",   # Keyence
    "8306.T",   # MUFG
    "6501.T",   # Hitachi
    "7741.T",   # HOYA
    "6902.T",   # Denso
    "4063.T",   # Shin-Etsu Chemical
    "8035.T",   # Tokyo Electron
    "6367.T",   # Daikin
    "9433.T",   # KDDI
    "6098.T",   # Recruit
    "4519.T",   # Chugai Pharma
    "7974.T",   # Nintendo
    "8001.T",   # Itochu
    "6594.T",   # Nidec
    "9432.T",   # NTT
    "4661.T",   # Oriental Land (Disney)
    "6723.T",   # Renesas
]

CN_TICKERS = [
    # Hong Kong
    "0700.HK",  # Tencent
    "9988.HK",  # Alibaba
    "9618.HK",  # JD.com
    "3690.HK",  # Meituan
    "1810.HK",  # Xiaomi
    "2318.HK",  # Ping An
    "0941.HK",  # China Mobile
    "1398.HK",  # ICBC
    "0939.HK",  # CCB
    "2628.HK",  # China Life
    "0005.HK",  # HSBC
    "1211.HK",  # BYD
    "9888.HK",  # Baidu
    "9999.HK",  # NetEase
    "2020.HK",  # Anta Sports
    # Shanghai / Shenzhen
    "600519.SS",  # Kweichow Moutai
    "601318.SS",  # Ping An (A)
    "600036.SS",  # China Merchants Bank
    "000858.SZ",  # Wuliangye
    "300750.SZ",  # CATL
]

DE_TICKERS = [
    "SAP.DE",    # SAP
    "SIE.DE",    # Siemens
    "ALV.DE",    # Allianz
    "DTE.DE",    # Deutsche Telekom
    "MBG.DE",    # Mercedes-Benz
    "BMW.DE",    # BMW
    "VOW3.DE",   # Volkswagen
    "BAS.DE",    # BASF
    "MUV2.DE",   # Munich Re
    "AIR.DE",    # Airbus
    "IFX.DE",    # Infineon
    "ADS.DE",    # Adidas
    "RHM.DE",    # Rheinmetall
    "DB1.DE",    # Deutsche Börse
    "HEN3.DE",   # Henkel
    "DHL.DE",    # DHL Group
    "DTG.DE",    # Daimler Truck
    "SHL.DE",    # Siemens Healthineers
    "BEI.DE",    # Beiersdorf
    "MRK.DE",    # Merck KGaA
]

GB_TICKERS = [
    "SHEL.L",   # Shell
    "AZN.L",    # AstraZeneca
    "HSBA.L",   # HSBC
    "ULVR.L",   # Unilever
    "BP.L",     # BP
    "GSK.L",    # GSK
    "RIO.L",    # Rio Tinto
    "DGE.L",    # Diageo
    "LSEG.L",   # London Stock Exchange
    "REL.L",    # RELX
    "BATS.L",   # BAT
    "NG.L",     # National Grid
    "VOD.L",    # Vodafone
    "LLOY.L",   # Lloyds
    "BARC.L",   # Barclays
    "AAL.L",    # Anglo American
    "RR.L",     # Rolls-Royce
    "BA.L",     # BAE Systems
    "CPG.L",    # Compass Group
    "ABF.L",    # AB Foods
]

PL_TICKERS = [
    "PKN.WA",   # PKN Orlen
    "PKO.WA",   # PKO BP
    "PEO.WA",   # Bank Pekao
    "PZU.WA",   # PZU
    "KGH.WA",   # KGHM
    "CDR.WA",   # CD Projekt
    "LPP.WA",   # LPP
    "ALE.WA",   # Allegro
    "DNP.WA",   # Dino Polska
    "SPL.WA",   # Santander PL
    "JSW.WA",   # JSW
    "KRU.WA",   # Kruk
    "CPS.WA",   # Cyfrowy Polsat
    "MBK.WA",   # mBank
    "OPL.WA",   # Orange Polska
]

RU_TICKERS = [
    "SBER.ME",  # Sberbank
    "GAZP.ME",  # Gazprom
    "LKOH.ME",  # Lukoil
    "GMKN.ME",  # Nornickel
    "NVTK.ME",  # Novatek
    "ROSN.ME",  # Rosneft
    "YNDX.ME",  # Yandex
    "MTSS.ME",  # MTS
    "MGNT.ME",  # Magnit
    "PLZL.ME",  # Polyus
]

IL_TICKERS = [
    "TEVA.TA",    # Teva Pharma
    "LUMI.TA",    # Bank Leumi
    "DSCT.TA",    # Bank Discount
    "NICE.TA",    # NICE Systems
    "HARL.TA",    # Bank Hapoalim
    "ICL.TA",     # ICL Group
    "BEZQ.TA",    # Bezeq
    "ESLT.TA",    # Elbit Systems
    "AZRG.TA",    # Azrieli Group
    "MZTF.TA",    # Mizrahi Tefahot
]

FR_TICKERS = [
    "MC.PA",     # LVMH
    "OR.PA",     # L'Oréal
    "TTE.PA",    # TotalEnergies
    "SAN.PA",    # Sanofi
    "AI.PA",     # Air Liquide
    "SU.PA",     # Schneider Electric
    "BN.PA",     # Danone
    "CS.PA",     # AXA
    "RMS.PA",    # Hermès
    "KER.PA",    # Kering
    "BNP.PA",    # BNP Paribas
    "GLE.PA",    # Société Générale
    "RI.PA",     # Pernod Ricard
    "DSY.PA",    # Dassault Systèmes
    "CAP.PA",    # Capgemini
    "STM.PA",    # STMicroelectronics (Euronext)
    "SGO.PA",    # Saint-Gobain
    "VIE.PA",    # Veolia
    "DG.PA",     # Vinci
    "SAF.PA",    # Safran
]

CH_TICKERS = [
    "NESN.SW",  # Nestlé
    "ROG.SW",   # Roche
    "NOVN.SW",  # Novartis
    "ABBN.SW",  # ABB
    "ZURN.SW",  # Zurich Insurance
    "UBSG.SW",  # UBS
    "CSGN.SW",  # Credit Suisse (legacy)
    "SREN.SW",  # Swiss Re
    "GIVN.SW",  # Givaudan
    "SLHN.SW",  # Swiss Life
    "LONN.SW",  # Lonza
    "SIKA.SW",  # Sika
    "GEBN.SW",  # Geberit
    "SCMN.SW",  # Swisscom
    "PGHN.SW",  # Partners Group
]

CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "ADA-USD",
    "SOL-USD", "DOGE-USD", "DOT-USD", "AVAX-USD", "LTC-USD",
    "LINK-USD", "UNI-USD", "ATOM-USD", "MATIC-USD", "SHIB-USD",
    "XLM-USD", "ETC-USD", "NEAR-USD", "APT-USD", "ARB-USD",
    "OP-USD", "SUI-USD", "AAVE-USD", "INJ-USD", "FTM-USD",
    "RENDER-USD", "FET-USD", "GRT-USD", "PEPE-USD", "WIF-USD",
]

INDEX_TICKERS = [
    "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX",      # US
    "^N225",                                           # Japan
    "^HSI",                                            # Hong Kong
    "^GDAXI",                                          # Germany
    "^FTSE",                                           # UK
    "^FCHI",                                           # France (CAC 40)
    "^SSMI",                                           # Switzerland (SMI)
    "^STOXX50E",                                       # Euro Stoxx 50
    "^TA125.TA",                                       # Israel TA-125
]

COMMODITY_ETF_TICKERS = [
    # Ropa naftowa
    "USO",    # United States Oil Fund (WTI)
    "BNO",    # United States Brent Oil Fund
    "UCO",    # ProShares Ultra Bloomberg Crude Oil (2x)
    "SCO",    # ProShares UltraShort Bloomberg Crude Oil (-2x)
    "XLE",    # Energy Select Sector SPDR (spółki naftowe)
    "OIH",    # VanEck Oil Services ETF
    "XOP",    # SPDR S&P Oil & Gas Exploration & Production
    # Złoto
    "GDX",    # VanEck Gold Miners ETF
    "GDXJ",   # VanEck Junior Gold Miners ETF
    "IAU",    # iShares Gold Trust
    "SGOL",   # Aberdeen Standard Physical Gold Shares
    "NUGT",   # Direxion Daily Gold Miners Bull 2x
    # Srebro
    "SIL",    # Global X Silver Miners ETF
    "SILJ",   # ETFMG Prime Junior Silver Miners ETF
    "SIVR",   # Aberdeen Standard Physical Silver Shares
    # Platyna / Pallad
    "PPLT",   # Aberdeen Standard Physical Platinum Shares
    "PALL",   # Aberdeen Standard Physical Palladium Shares
    # Gaz ziemny
    "UNG",    # United States Natural Gas Fund
    "BOIL",   # ProShares Ultra Bloomberg Natural Gas (2x)
    "KOLD",   # ProShares UltraShort Bloomberg Natural Gas (-2x)
    # Surowce rolne
    "DBA",    # Invesco DB Agriculture Fund (zboża, cukier, kawa)
    "WEAT",   # Teucrium Wheat Fund
    "CORN",   # Teucrium Corn Fund
    "SOYB",   # Teucrium Soybean Fund
    "CANE",   # Teucrium Sugar Fund
    "NIB",    # iPath Bloomberg Cocoa (kakao)
    "JO",     # iPath Bloomberg Coffee (kawa)
    "COW",    # iPath Bloomberg Livestock (bydło)
    # Surowce szerokie / multi-commodity
    "DJP",    # iPath Bloomberg Commodity Index
    "GSG",    # iShares S&P GSCI Commodity
    "DBC",    # Invesco DB Commodity Index
    "PDBC",   # Invesco Optimum Yield Diversified Commodity
    "COM",    # Direxion Auspice Broad Commodity Strategy
    # Miedź / metale przemysłowe
    "COPX",   # Global X Copper Miners ETF
    "CPER",   # United States Copper Index Fund
    "PICK",   # iShares MSCI Global Metals & Mining
    # Uran
    "URA",    # Global X Uranium ETF
    "URNM",   # Sprott Uranium Miners ETF
    # Lit / baterie
    "LIT",    # Global X Lithium & Battery Tech ETF
    # Drewno
    "WOOD",   # iShares Global Timber & Forestry ETF
    "CUT",    # Invesco MSCI Global Timber ETF
    # Woda
    "PHO",    # Invesco Water Resources ETF
    "FIW",    # First Trust Water ETF
    # Nieruchomości (REIT)
    "VNQ",    # Vanguard Real Estate ETF
    "IYR",    # iShares U.S. Real Estate ETF
    "XLRE",   # Real Estate Select Sector SPDR
    # Kontrakty futures (direct commodities via Yahoo)
    "CL=F",   # WTI Crude Oil Futures
    "BZ=F",   # Brent Crude Oil Futures
    "GC=F",   # Gold Futures
    "SI=F",   # Silver Futures
    "PL=F",   # Platinum Futures
    "PA=F",   # Palladium Futures
    "HG=F",   # Copper Futures
    "NG=F",   # Natural Gas Futures
    "ZC=F",   # Corn Futures
    "ZW=F",   # Wheat Futures
    "ZS=F",   # Soybean Futures
    "KC=F",   # Coffee Futures
    "SB=F",   # Sugar Futures
    "CC=F",   # Cocoa Futures
    "CT=F",   # Cotton Futures
    "LBS=F",  # Lumber Futures
    "LE=F",   # Live Cattle Futures
    "HE=F",   # Lean Hogs Futures
]

ALL_TICKERS = (
    US_TICKERS + JP_TICKERS + CN_TICKERS + DE_TICKERS
    + GB_TICKERS + PL_TICKERS + RU_TICKERS + IL_TICKERS
    + FR_TICKERS + CH_TICKERS + CRYPTO_TICKERS + INDEX_TICKERS
    + COMMODITY_ETF_TICKERS
)

VALIDATION_BATCH_SIZE = 100
VALIDATION_SLEEP = 1.5


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

        base_currency to bezpośredni ticker Yahoo Finance (np. AAPL, 7203.T,
        BTC-USD, ^GSPC, PKN.WA). Parametry lecą prosto do yfinance.
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
        Pobiera symbole z Yahoo Finance — giełdy: US, JP, CN/HK, DE, GB,
        PL, RU, IL, FR, CH + crypto + indeksy.

        Waliduje batchowo przez yf.download(). Ticker = base_asset (1:1).
        """
        try:
            yahoo_symbols = list(asset_codes) if asset_codes else list(ALL_TICKERS)

            symbols_info: list = []

            for i in range(0, len(yahoo_symbols), VALIDATION_BATCH_SIZE):
                batch = yahoo_symbols[i : i + VALIDATION_BATCH_SIZE]
                logger.info(
                    f"Yahoo Finance: walidacja batch {i // VALIDATION_BATCH_SIZE + 1} "
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

                if i + VALIDATION_BATCH_SIZE < len(yahoo_symbols):
                    time.sleep(VALIDATION_SLEEP)

            logger.info(
                f"Yahoo Finance: znaleziono {len(symbols_info)} aktywnych symboli "
                f"(z {len(yahoo_symbols)} sprawdzonych)"
            )
            return symbols_info

        except Exception as error:
            logger.error(f"Yahoo Finance _get_symbols error: {error}")
            raise
