import logging
import time
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ticker registry — {yf_ticker: display_name} per kraj / kategoria
# Format base_asset w bazie: <yf_ticker>_<nazwa>_<kraj>
# Każda grupa ma: quote_asset, country, kind
# ---------------------------------------------------------------------------


def _sanitize(name: str) -> str:
    return (
        name.replace(" ", "-")
        .replace("_", "-")
        .replace("&", "and")
        .replace("'", "")
        .replace(",", "")
        .replace(".", "")
        .replace("(", "")
        .replace(")", "")
    )


def _build_base_asset(yf_ticker: str, name: str, country: str) -> str:
    return f"{yf_ticker}_{_sanitize(name)}_{country}"


# ── US Stocks (NYSE / NASDAQ) ── quote: USD, kind: STOCK ──────────────────

US_STOCK_TICKERS = {
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN":  "Amazon",
    "NVDA":  "Nvidia",
    "META":  "Meta-Platforms",
    "TSLA":  "Tesla",
    "AVGO":  "Broadcom",
    "ORCL":  "Oracle",
    "CRM":   "Salesforce",
    "ADBE":  "Adobe",
    "AMD":   "AMD",
    "INTC":  "Intel",
    "CSCO":  "Cisco",
    "QCOM":  "Qualcomm",
    "TXN":   "Texas-Instruments",
    "NFLX":  "Netflix",
    "UBER":  "Uber",
    "ABNB":  "Airbnb",
    "SQ":    "Block",
    "PLTR":  "Palantir",
    "COIN":  "Coinbase",
    "PYPL":  "PayPal",
    "NOW":   "ServiceNow",
    "PANW":  "Palo-Alto-Networks",
    "CRWD":  "CrowdStrike",
    "DDOG":  "Datadog",
    "ZS":    "Zscaler",
    "NET":   "Cloudflare",
    "SNOW":  "Snowflake",
    "SHOP":  "Shopify",
    "JPM":   "JPMorgan-Chase",
    "V":     "Visa",
    "MA":    "Mastercard",
    "BAC":   "Bank-of-America",
    "WFC":   "Wells-Fargo",
    "GS":    "Goldman-Sachs",
    "MS":    "Morgan-Stanley",
    "AXP":   "American-Express",
    "BLK":   "BlackRock",
    "BRK-B": "Berkshire-Hathaway",
    "UNH":   "UnitedHealth",
    "JNJ":   "Johnson-and-Johnson",
    "LLY":   "Eli-Lilly",
    "PFE":   "Pfizer",
    "ABBV":  "AbbVie",
    "MRK":   "Merck",
    "TMO":   "Thermo-Fisher",
    "ABT":   "Abbott",
    "MRNA":  "Moderna",
    "XOM":   "ExxonMobil",
    "CVX":   "Chevron",
    "COP":   "ConocoPhillips",
    "SLB":   "Schlumberger",
    "CAT":   "Caterpillar",
    "DE":    "Deere",
    "HON":   "Honeywell",
    "GE":    "GE-Aerospace",
    "RTX":   "RTX",
    "LMT":   "Lockheed-Martin",
    "BA":    "Boeing",
    "WMT":   "Walmart",
    "COST":  "Costco",
    "HD":    "Home-Depot",
    "LOW":   "Lowes",
    "NKE":   "Nike",
    "SBUX":  "Starbucks",
    "MCD":   "McDonalds",
    "KO":    "Coca-Cola",
    "PEP":   "PepsiCo",
    "PG":    "Procter-and-Gamble",
    "DIS":   "Disney",
    "CMCSA": "Comcast",
}

# ── US ETFy ── quote: USD, kind: ETF ──────────────────────────────────────

US_ETF_TICKERS = {
    "SPY":   "SPDR-SandP-500-ETF",
    "QQQ":   "Invesco-QQQ-ETF",
    "IWM":   "iShares-Russell-2000-ETF",
    "DIA":   "SPDR-Dow-Jones-ETF",
    "VOO":   "Vanguard-SandP-500-ETF",
    "VTI":   "Vanguard-Total-Market-ETF",
    "GLD":   "SPDR-Gold-Trust",
    "SLV":   "iShares-Silver-Trust",
    "TLT":   "iShares-20Y-Treasury-ETF",
    "ARKK":  "ARK-Innovation-ETF",
    "SOXX":  "iShares-Semiconductor-ETF",
    "TQQQ":  "ProShares-UltraPro-QQQ",
    "SQQQ":  "ProShares-UltraPro-Short-QQQ",
}

# ── Japonia (Tokyo) ── quote: JPY, kind: STOCK ────────────────────────────

JP_TICKERS = {
    "7203.T":  "Toyota",
    "6758.T":  "Sony",
    "9984.T":  "SoftBank-Group",
    "6861.T":  "Keyence",
    "8306.T":  "MUFG",
    "6501.T":  "Hitachi",
    "7741.T":  "HOYA",
    "6902.T":  "Denso",
    "4063.T":  "Shin-Etsu-Chemical",
    "8035.T":  "Tokyo-Electron",
    "6367.T":  "Daikin",
    "9433.T":  "KDDI",
    "6098.T":  "Recruit",
    "4519.T":  "Chugai-Pharma",
    "7974.T":  "Nintendo",
    "8001.T":  "Itochu",
    "6594.T":  "Nidec",
    "9432.T":  "NTT",
    "4661.T":  "Oriental-Land",
    "6723.T":  "Renesas",
}

# ── Chiny / Hong Kong ── quote: HKD, kind: STOCK ──────────────────────────

CN_HK_TICKERS = {
    "0700.HK": "Tencent",
    "9988.HK": "Alibaba",
    "9618.HK": "JD-com",
    "3690.HK": "Meituan",
    "1810.HK": "Xiaomi",
    "2318.HK": "Ping-An",
    "0941.HK": "China-Mobile",
    "1398.HK": "ICBC",
    "0939.HK": "CCB",
    "2628.HK": "China-Life",
    "0005.HK": "HSBC-HK",
    "1211.HK": "BYD",
    "9888.HK": "Baidu",
    "9999.HK": "NetEase",
    "2020.HK": "Anta-Sports",
}

# ── Chiny / Shanghai + Shenzhen ── quote: CNY, kind: STOCK ────────────────

CN_MAINLAND_TICKERS = {
    "600519.SS": "Kweichow-Moutai",
    "601318.SS": "Ping-An-A",
    "600036.SS": "China-Merchants-Bank",
    "000858.SZ": "Wuliangye",
    "300750.SZ": "CATL",
}

# ── Niemcy (Xetra) ── quote: EUR, kind: STOCK ─────────────────────────────

DE_TICKERS = {
    "SAP.DE":   "SAP",
    "SIE.DE":   "Siemens",
    "ALV.DE":   "Allianz",
    "DTE.DE":   "Deutsche-Telekom",
    "MBG.DE":   "Mercedes-Benz",
    "BMW.DE":   "BMW",
    "VOW3.DE":  "Volkswagen",
    "BAS.DE":   "BASF",
    "MUV2.DE":  "Munich-Re",
    "AIR.DE":   "Airbus",
    "IFX.DE":   "Infineon",
    "ADS.DE":   "Adidas",
    "RHM.DE":   "Rheinmetall",
    "DB1.DE":   "Deutsche-Boerse",
    "HEN3.DE":  "Henkel",
    "DHL.DE":   "DHL-Group",
    "DTG.DE":   "Daimler-Truck",
    "SHL.DE":   "Siemens-Healthineers",
    "BEI.DE":   "Beiersdorf",
    "MRK.DE":   "Merck-KGaA",
}

# ── Wielka Brytania (London) ── quote: GBP, kind: STOCK ───────────────────

GB_TICKERS = {
    "SHEL.L":  "Shell",
    "AZN.L":   "AstraZeneca",
    "HSBA.L":  "HSBC",
    "ULVR.L":  "Unilever",
    "BP.L":    "BP",
    "GSK.L":   "GSK",
    "RIO.L":   "Rio-Tinto",
    "DGE.L":   "Diageo",
    "LSEG.L":  "London-Stock-Exchange",
    "REL.L":   "RELX",
    "BATS.L":  "BAT",
    "NG.L":    "National-Grid",
    "VOD.L":   "Vodafone",
    "LLOY.L":  "Lloyds",
    "BARC.L":  "Barclays",
    "AAL.L":   "Anglo-American",
    "RR.L":    "Rolls-Royce",
    "BA.L":    "BAE-Systems",
    "CPG.L":   "Compass-Group",
    "ABF.L":   "AB-Foods",
}

# ── Polska (Warszawa) ── quote: PLN, kind: STOCK ──────────────────────────

PL_TICKERS = {
    "PKN.WA":  "PKN-Orlen",
    "PKO.WA":  "PKO-BP",
    "PEO.WA":  "Bank-Pekao",
    "PZU.WA":  "PZU",
    "KGH.WA":  "KGHM",
    "CDR.WA":  "CD-Projekt",
    "LPP.WA":  "LPP",
    "ALE.WA":  "Allegro",
    "DNP.WA":  "Dino-Polska",
    "SPL.WA":  "Santander-PL",
    "JSW.WA":  "JSW",
    "KRU.WA":  "Kruk",
    "CPS.WA":  "Cyfrowy-Polsat",
    "MBK.WA":  "mBank",
    "OPL.WA":  "Orange-Polska",
}

# ── Rosja (Moscow) ── quote: RUB, kind: STOCK ─────────────────────────────

RU_TICKERS = {
    "SBER.ME": "Sberbank",
    "GAZP.ME": "Gazprom",
    "LKOH.ME": "Lukoil",
    "GMKN.ME": "Nornickel",
    "NVTK.ME": "Novatek",
    "ROSN.ME": "Rosneft",
    "YNDX.ME": "Yandex",
    "MTSS.ME": "MTS",
    "MGNT.ME": "Magnit",
    "PLZL.ME": "Polyus",
}

# ── Izrael (Tel Aviv) ── quote: ILS, kind: STOCK ──────────────────────────

IL_TICKERS = {
    "TEVA.TA": "Teva-Pharma",
    "LUMI.TA": "Bank-Leumi",
    "DSCT.TA": "Bank-Discount",
    "NICE.TA": "NICE-Systems",
    "HARL.TA": "Bank-Hapoalim",
    "ICL.TA":  "ICL-Group",
    "BEZQ.TA": "Bezeq",
    "ESLT.TA": "Elbit-Systems",
    "AZRG.TA": "Azrieli-Group",
    "MZTF.TA": "Mizrahi-Tefahot",
}

# ── Francja (Euronext Paris) ── quote: EUR, kind: STOCK ───────────────────

FR_TICKERS = {
    "MC.PA":   "LVMH",
    "OR.PA":   "LOreal",
    "TTE.PA":  "TotalEnergies",
    "SAN.PA":  "Sanofi",
    "AI.PA":   "Air-Liquide",
    "SU.PA":   "Schneider-Electric",
    "BN.PA":   "Danone",
    "CS.PA":   "AXA",
    "RMS.PA":  "Hermes",
    "KER.PA":  "Kering",
    "BNP.PA":  "BNP-Paribas",
    "GLE.PA":  "Societe-Generale",
    "RI.PA":   "Pernod-Ricard",
    "DSY.PA":  "Dassault-Systemes",
    "CAP.PA":  "Capgemini",
    "STM.PA":  "STMicroelectronics",
    "SGO.PA":  "Saint-Gobain",
    "VIE.PA":  "Veolia",
    "DG.PA":   "Vinci",
    "SAF.PA":  "Safran",
}

# ── Szwajcaria (SIX) ── quote: CHF, kind: STOCK ──────────────────────────

CH_TICKERS = {
    "NESN.SW": "Nestle",
    "ROG.SW":  "Roche",
    "NOVN.SW": "Novartis",
    "ABBN.SW": "ABB",
    "ZURN.SW": "Zurich-Insurance",
    "UBSG.SW": "UBS",
    "CSGN.SW": "Credit-Suisse",
    "SREN.SW": "Swiss-Re",
    "GIVN.SW": "Givaudan",
    "SLHN.SW": "Swiss-Life",
    "LONN.SW": "Lonza",
    "SIKA.SW": "Sika",
    "GEBN.SW": "Geberit",
    "SCMN.SW": "Swisscom",
    "PGHN.SW": "Partners-Group",
}

# ── Indeksy ── kind: INDEX ────────────────────────────────────────────────
# (yf_ticker -> (name, quote, country))

INDEX_TICKERS = {
    "^GSPC":     ("SandP-500",       "USD", "US"),
    "^IXIC":     ("NASDAQ-Composite", "USD", "US"),
    "^DJI":      ("Dow-Jones",        "USD", "US"),
    "^RUT":      ("Russell-2000",     "USD", "US"),
    "^VIX":      ("VIX",              "USD", "US"),
    "^N225":     ("Nikkei-225",       "JPY", "JP"),
    "^HSI":      ("Hang-Seng",        "HKD", "CN"),
    "^GDAXI":   ("DAX",              "EUR", "DE"),
    "^FTSE":     ("FTSE-100",         "GBP", "GB"),
    "^FCHI":     ("CAC-40",           "EUR", "FR"),
    "^SSMI":     ("SMI",              "CHF", "CH"),
    "^STOXX50E": ("Euro-Stoxx-50",    "EUR", "EU"),
    "^TA125.TA": ("TA-125",           "ILS", "IL"),
}

# ── Commodity ETFy ── quote: USD, kind: ETF, country: CMDTY ───────────────

CMDTY_ETF_TICKERS = {
    "USO":   "US-Oil-Fund-WTI",
    "BNO":   "US-Brent-Oil-Fund",
    "UCO":   "ProShares-Ultra-Crude-Oil",
    "SCO":   "ProShares-UltraShort-Crude-Oil",
    "XLE":   "Energy-Select-SPDR",
    "OIH":   "VanEck-Oil-Services-ETF",
    "XOP":   "SPDR-Oil-Gas-Exploration",
    "GDX":   "VanEck-Gold-Miners-ETF",
    "GDXJ":  "VanEck-Junior-Gold-Miners",
    "IAU":   "iShares-Gold-Trust",
    "SGOL":  "Aberdeen-Physical-Gold",
    "NUGT":  "Direxion-Gold-Miners-Bull-2x",
    "SIL":   "Global-X-Silver-Miners-ETF",
    "SILJ":  "ETFMG-Junior-Silver-Miners",
    "SIVR":  "Aberdeen-Physical-Silver",
    "PPLT":  "Aberdeen-Physical-Platinum",
    "PALL":  "Aberdeen-Physical-Palladium",
    "UNG":   "US-Natural-Gas-Fund",
    "BOIL":  "ProShares-Ultra-Natural-Gas",
    "KOLD":  "ProShares-UltraShort-Natural-Gas",
    "DBA":   "Invesco-DB-Agriculture",
    "WEAT":  "Teucrium-Wheat-Fund",
    "CORN":  "Teucrium-Corn-Fund",
    "SOYB":  "Teucrium-Soybean-Fund",
    "CANE":  "Teucrium-Sugar-Fund",
    "NIB":   "iPath-Cocoa",
    "JO":    "iPath-Coffee",
    "COW":   "iPath-Livestock",
    "DJP":   "iPath-Bloomberg-Commodity",
    "GSG":   "iShares-GSCI-Commodity",
    "DBC":   "Invesco-DB-Commodity",
    "PDBC":  "Invesco-Optimum-Yield-Commodity",
    "COM":   "Direxion-Broad-Commodity",
    "COPX":  "Global-X-Copper-Miners-ETF",
    "CPER":  "US-Copper-Index-Fund",
    "PICK":  "iShares-Global-Metals-Mining",
    "URA":   "Global-X-Uranium-ETF",
    "URNM":  "Sprott-Uranium-Miners-ETF",
    "LIT":   "Global-X-Lithium-Battery-ETF",
    "WOOD":  "iShares-Global-Timber-ETF",
    "CUT":   "Invesco-Global-Timber-ETF",
    "PHO":   "Invesco-Water-Resources-ETF",
    "FIW":   "First-Trust-Water-ETF",
    "VNQ":   "Vanguard-Real-Estate-ETF",
    "IYR":   "iShares-US-Real-Estate-ETF",
    "XLRE":  "Real-Estate-Select-SPDR",
}

# ── Commodity Futures ── quote: USD, kind: FUTURES, country: CMDTY ─────────

CMDTY_FUTURES_TICKERS = {
    "CL=F":  "WTI-Crude-Oil-Futures",
    "BZ=F":  "Brent-Crude-Oil-Futures",
    "GC=F":  "Gold-Futures",
    "SI=F":  "Silver-Futures",
    "PL=F":  "Platinum-Futures",
    "PA=F":  "Palladium-Futures",
    "HG=F":  "Copper-Futures",
    "NG=F":  "Natural-Gas-Futures",
    "ZC=F":  "Corn-Futures",
    "ZW=F":  "Wheat-Futures",
    "ZS=F":  "Soybean-Futures",
    "KC=F":  "Coffee-Futures",
    "SB=F":  "Sugar-Futures",
    "CC=F":  "Cocoa-Futures",
    "CT=F":  "Cotton-Futures",
    "LBS=F": "Lumber-Futures",
    "LE=F":  "Live-Cattle-Futures",
    "HE=F":  "Lean-Hogs-Futures",
}

# ── Forex (pary walutowe) ── quote: USD, kind: FOREX, country: FX ─────────

FOREX_TICKERS = {
    "EURUSD=X":  "Euro-US-Dollar",
    "GBPUSD=X":  "British-Pound-US-Dollar",
    "USDJPY=X":  "US-Dollar-Japanese-Yen",
    "USDCHF=X":  "US-Dollar-Swiss-Franc",
    "AUDUSD=X":  "Australian-Dollar-US-Dollar",
    "USDCAD=X":  "US-Dollar-Canadian-Dollar",
    "NZDUSD=X":  "New-Zealand-Dollar-US-Dollar",
    "EURGBP=X":  "Euro-British-Pound",
    "EURJPY=X":  "Euro-Japanese-Yen",
    "EURCHF=X":  "Euro-Swiss-Franc",
    "EURPLN=X":  "Euro-Polish-Zloty",
    "GBPJPY=X":  "British-Pound-Japanese-Yen",
    "GBPCHF=X":  "British-Pound-Swiss-Franc",
    "PLNUSD=X":  "Polish-Zloty-US-Dollar",
    "USDPLN=X":  "US-Dollar-Polish-Zloty",
    "USDRUB=X":  "US-Dollar-Russian-Ruble",
    "USDILS=X":  "US-Dollar-Israeli-Shekel",
    "USDCNY=X":  "US-Dollar-Chinese-Yuan",
    "USDHKD=X":  "US-Dollar-Hong-Kong-Dollar",
    "USDTRY=X":  "US-Dollar-Turkish-Lira",
    "USDMXN=X":  "US-Dollar-Mexican-Peso",
    "USDZAR=X":  "US-Dollar-South-African-Rand",
    "USDSGD=X":  "US-Dollar-Singapore-Dollar",
    "USDSEK=X":  "US-Dollar-Swedish-Krona",
    "USDNOK=X":  "US-Dollar-Norwegian-Krone",
    "USDDKK=X":  "US-Dollar-Danish-Krone",
    "USDINR=X":  "US-Dollar-Indian-Rupee",
    "USDKRW=X":  "US-Dollar-South-Korean-Won",
    "USDBRL=X":  "US-Dollar-Brazilian-Real",
}


# ---------------------------------------------------------------------------
# Master registry — budowana automatycznie z powyższych grup
# Tuple: (yf_ticker, display_name, quote_asset, country, kind)
# ---------------------------------------------------------------------------

TICKER_REGISTRY: List[tuple] = []

_BASE_ASSET_TO_YF: Dict[str, str] = {}
_YF_TO_BASE_ASSET: Dict[str, str] = {}
_YF_TO_QUOTE: Dict[str, str] = {}
_YF_TO_KIND: Dict[str, str] = {}
_YF_TO_COUNTRY: Dict[str, str] = {}


def _register_group(
    tickers: Dict[str, str], quote: str, country: str, kind: str
) -> None:
    for yf_ticker, name in tickers.items():
        base = _build_base_asset(yf_ticker, name, country)
        TICKER_REGISTRY.append((yf_ticker, name, quote, country, kind))
        _BASE_ASSET_TO_YF[base] = yf_ticker
        _YF_TO_BASE_ASSET[yf_ticker] = base
        _YF_TO_QUOTE[yf_ticker] = quote
        _YF_TO_KIND[yf_ticker] = kind
        _YF_TO_COUNTRY[yf_ticker] = country


def _register_indexes() -> None:
    for yf_ticker, (name, quote, country) in INDEX_TICKERS.items():
        base = _build_base_asset(yf_ticker, name, country)
        TICKER_REGISTRY.append((yf_ticker, name, quote, country, "INDEX"))
        _BASE_ASSET_TO_YF[base] = yf_ticker
        _YF_TO_BASE_ASSET[yf_ticker] = base
        _YF_TO_QUOTE[yf_ticker] = quote
        _YF_TO_KIND[yf_ticker] = "INDEX"
        _YF_TO_COUNTRY[yf_ticker] = country


# Rejestracja wszystkich grup
_register_group(US_STOCK_TICKERS, "USD", "US", "STOCK")
_register_group(US_ETF_TICKERS, "USD", "US", "ETF")
_register_group(JP_TICKERS, "JPY", "JP", "STOCK")
_register_group(CN_HK_TICKERS, "HKD", "CN", "STOCK")
_register_group(CN_MAINLAND_TICKERS, "CNY", "CN", "STOCK")
_register_group(DE_TICKERS, "EUR", "DE", "STOCK")
_register_group(GB_TICKERS, "GBP", "GB", "STOCK")
_register_group(PL_TICKERS, "PLN", "PL", "STOCK")
_register_group(RU_TICKERS, "RUB", "RU", "STOCK")
_register_group(IL_TICKERS, "ILS", "IL", "STOCK")
_register_group(FR_TICKERS, "EUR", "FR", "STOCK")
_register_group(CH_TICKERS, "CHF", "CH", "STOCK")
_register_indexes()
_register_group(CMDTY_ETF_TICKERS, "USD", "CMDTY", "ETF")
_register_group(CMDTY_FUTURES_TICKERS, "USD", "CMDTY", "FUTURES")
_register_group(FOREX_TICKERS, "USD", "FX", "FOREX")

ALL_YF_TICKERS = [entry[0] for entry in TICKER_REGISTRY]

VALIDATION_BATCH_SIZE = 100
VALIDATION_SLEEP = 1.5


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class YahooFinanceAPI(AbstractAPI):

    EXCHANGE_NAME = "YAHOO_FINANCE"

    __api_transaction_requests_limit = {"requests": 2000, "in_seconds": 3600}

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _resolve_yf_ticker(base_currency: str) -> str:
        """Zamienia base_asset (format DB) na Yahoo Finance ticker."""
        if base_currency in _BASE_ASSET_TO_YF:
            return _BASE_ASSET_TO_YF[base_currency]
        return base_currency

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
        base_currency: str = "AAPL_Apple_US",
        quote_currency: str = "USD",
        interval: str = "1d",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Union[int, float, str]]]:
        """
        Pobiera kline/candlestick z Yahoo Finance.

        base_currency może być w formacie DB (np. AAPL_Apple_US) lub
        bezpośrednim tickerem YF (np. AAPL). Automatycznie rozwiązuje
        przez _resolve_yf_ticker().
        """
        try:
            symbol = self._resolve_yf_ticker(base_currency)
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
        Pobiera symbole z Yahoo Finance.

        Zwraca base_asset w formacie <yf_ticker>_<nazwa>_<kraj>,
        quote_asset = waluta lokalna, plus kind i country do mapowania M2M.
        """
        try:
            if asset_codes:
                yf_tickers = asset_codes
            else:
                yf_tickers = list(ALL_YF_TICKERS)

            symbols_info: list = []

            for i in range(0, len(yf_tickers), VALIDATION_BATCH_SIZE):
                batch = yf_tickers[i : i + VALIDATION_BATCH_SIZE]
                logger.info(
                    f"Yahoo Finance: walidacja batch {i // VALIDATION_BATCH_SIZE + 1} "
                    f"({len(batch)} tickerów)"
                )

                data = yf.download(batch, period="5d", progress=False, threads=True)

                if data.empty:
                    continue

                if len(batch) == 1:
                    yf_sym = batch[0]
                    if not data["Close"].dropna().empty:
                        symbols_info.append(self._build_symbol_info(yf_sym))
                else:
                    for yf_sym in batch:
                        try:
                            col = (
                                data["Close"][yf_sym]
                                if yf_sym in data["Close"].columns
                                else None
                            )
                            if col is not None and not col.dropna().empty:
                                symbols_info.append(self._build_symbol_info(yf_sym))
                        except (KeyError, TypeError):
                            continue

                if i + VALIDATION_BATCH_SIZE < len(yf_tickers):
                    time.sleep(VALIDATION_SLEEP)

            logger.info(
                f"Yahoo Finance: znaleziono {len(symbols_info)} aktywnych symboli "
                f"(z {len(yf_tickers)} sprawdzonych)"
            )
            return symbols_info

        except Exception as error:
            logger.error(f"Yahoo Finance _get_symbols error: {error}")
            raise

    @staticmethod
    def _build_symbol_info(yf_sym: str) -> Dict[str, str]:
        return {
            "symbol": yf_sym,
            "status": "TRADING",
            "base_asset": _YF_TO_BASE_ASSET.get(yf_sym, yf_sym),
            "quote_asset": _YF_TO_QUOTE.get(yf_sym, "USD"),
            "kind": _YF_TO_KIND.get(yf_sym, ""),
            "country": _YF_TO_COUNTRY.get(yf_sym, ""),
        }
