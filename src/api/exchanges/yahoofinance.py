import logging
import time
from typing import List, Dict, Union, Optional
from datetime import datetime, timezone

import yfinance as yf

from .abstract import AbstractAPI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ticker registry — zagnieżdżona struktura per kraj / region
#
# Każda grupa:  { "quote": <waluta>, "country": <kod>, "assets": { <kind>: { <yf_ticker>: <display_name> } } }
#
# base_asset w bazie  = yf_ticker  (np. AAPL, 7203.T, PKN.WA)
# full_name  w bazie  = display_name (np. Apple, Toyota, PKN Orlen)
# kind       w bazie  = klucz sektora (np. IT, DEFENSE, ETF_OIL, FUTURES_GOLD)
# ---------------------------------------------------------------------------


# ── USA ─────────────────────────────────────────────────────────────────────

US = {
    "quote": "USD",
    "country": "US",
    "assets": {
        "IT": {
            "AAPL":  "Apple",
            "MSFT":  "Microsoft",
            "GOOGL": "Alphabet",
            "AMZN":  "Amazon",
            "NVDA":  "Nvidia",
            "META":  "Meta-Platforms",
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
            "NOW":   "ServiceNow",
            "PANW":  "Palo-Alto-Networks",
            "CRWD":  "CrowdStrike",
            "DDOG":  "Datadog",
            "ZS":    "Zscaler",
            "NET":   "Cloudflare",
            "SNOW":  "Snowflake",
            "SHOP":  "Shopify",
            "PLTR":  "Palantir",
            "UBER":  "Uber",
            "ABNB":  "Airbnb",
        },
        "FINANCE": {
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
            "COIN":  "Coinbase",
            "PYPL":  "PayPal",
            "SQ":    "Block",
        },
        "HEALTHCARE": {
            "UNH":   "UnitedHealth",
            "JNJ":   "Johnson-and-Johnson",
            "LLY":   "Eli-Lilly",
            "PFE":   "Pfizer",
            "ABBV":  "AbbVie",
            "MRK":   "Merck",
            "TMO":   "Thermo-Fisher",
            "ABT":   "Abbott",
            "MRNA":  "Moderna",
        },
        "ENERGY": {
            "XOM":   "ExxonMobil",
            "CVX":   "Chevron",
            "COP":   "ConocoPhillips",
            "SLB":   "Schlumberger",
        },
        "DEFENSE": {
            "RTX":   "RTX",
            "LMT":   "Lockheed-Martin",
            "BA":    "Boeing",
        },
        "INDUSTRIAL": {
            "CAT":   "Caterpillar",
            "DE":    "Deere",
            "HON":   "Honeywell",
            "GE":    "GE-Aerospace",
        },
        "CONSUMER": {
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
        },
        "AUTOMOTIVE": {
            "TSLA":  "Tesla",
        },
        "ETF_INDEX": {
            "SPY":   "SPDR-SandP-500-ETF",
            "QQQ":   "Invesco-QQQ-ETF",
            "IWM":   "iShares-Russell-2000-ETF",
            "DIA":   "SPDR-Dow-Jones-ETF",
            "VOO":   "Vanguard-SandP-500-ETF",
            "VTI":   "Vanguard-Total-Market-ETF",
            "TQQQ":  "ProShares-UltraPro-QQQ",
            "SQQQ":  "ProShares-UltraPro-Short-QQQ",
        },
        "ETF_TECH": {
            "ARKK":  "ARK-Innovation-ETF",
            "SOXX":  "iShares-Semiconductor-ETF",
        },
        "ETF_BONDS": {
            "TLT":   "iShares-20Y-Treasury-ETF",
        },
        "INDEX": {
            "^GSPC":  "SandP-500",
            "^IXIC":  "NASDAQ-Composite",
            "^DJI":   "Dow-Jones",
            "^RUT":   "Russell-2000",
            "^VIX":   "VIX",
        },
    },
}

# ── Japonia ──────────────────────────────────────────────────────────────────

JP = {
    "quote": "JPY",
    "country": "JP",
    "assets": {
        "IT": {
            "6758.T":  "Sony",
            "6861.T":  "Keyence",
            "8035.T":  "Tokyo-Electron",
            "6723.T":  "Renesas",
            "6594.T":  "Nidec",
        },
        "FINANCE": {
            "8306.T":  "MUFG",
        },
        "HEALTHCARE": {
            "7741.T":  "HOYA",
            "4519.T":  "Chugai-Pharma",
        },
        "AUTOMOTIVE": {
            "7203.T":  "Toyota",
            "6902.T":  "Denso",
        },
        "CHEMICALS": {
            "4063.T":  "Shin-Etsu-Chemical",
        },
        "INDUSTRIAL": {
            "6367.T":  "Daikin",
        },
        "TELECOM": {
            "9433.T":  "KDDI",
            "9432.T":  "NTT",
        },
        "CONGLOMERATE": {
            "9984.T":  "SoftBank-Group",
            "6501.T":  "Hitachi",
            "8001.T":  "Itochu",
        },
        "MEDIA": {
            "7974.T":  "Nintendo",
        },
        "CONSUMER": {
            "6098.T":  "Recruit",
            "4661.T":  "Oriental-Land",
        },
        "INDEX": {
            "^N225":   "Nikkei-225",
        },
    },
}

# ── Chiny / Hong Kong ───────────────────────────────────────────────────────

CN_HK = {
    "quote": "HKD",
    "country": "CN",
    "assets": {
        "IT": {
            "0700.HK": "Tencent",
            "9988.HK": "Alibaba",
            "9618.HK": "JD-com",
            "3690.HK": "Meituan",
            "9888.HK": "Baidu",
            "9999.HK": "NetEase",
        },
        "FINANCE": {
            "2318.HK": "Ping-An",
            "1398.HK": "ICBC",
            "0939.HK": "CCB",
            "2628.HK": "China-Life",
            "0005.HK": "HSBC-HK",
        },
        "CONSUMER": {
            "1810.HK": "Xiaomi",
            "2020.HK": "Anta-Sports",
        },
        "TELECOM": {
            "0941.HK": "China-Mobile",
        },
        "AUTOMOTIVE": {
            "1211.HK": "BYD",
        },
        "INDEX": {
            "^HSI":    "Hang-Seng",
        },
    },
}

# ── Chiny / Shanghai + Shenzhen ─────────────────────────────────────────────

CN_MAINLAND = {
    "quote": "CNY",
    "country": "CN",
    "assets": {
        "CONSUMER": {
            "600519.SS": "Kweichow-Moutai",
            "000858.SZ": "Wuliangye",
        },
        "FINANCE": {
            "601318.SS": "Ping-An-A",
            "600036.SS": "China-Merchants-Bank",
        },
        "INDUSTRIAL": {
            "300750.SZ": "CATL",
        },
    },
}

# ── Niemcy (Xetra) ──────────────────────────────────────────────────────────

DE = {
    "quote": "EUR",
    "country": "DE",
    "assets": {
        "IT": {
            "SAP.DE":   "SAP",
            "IFX.DE":   "Infineon",
        },
        "FINANCE": {
            "ALV.DE":   "Allianz",
            "MUV2.DE":  "Munich-Re",
            "DB1.DE":   "Deutsche-Boerse",
        },
        "TELECOM": {
            "DTE.DE":   "Deutsche-Telekom",
        },
        "AUTOMOTIVE": {
            "MBG.DE":   "Mercedes-Benz",
            "BMW.DE":   "BMW",
            "VOW3.DE":  "Volkswagen",
            "DTG.DE":   "Daimler-Truck",
        },
        "CHEMICALS": {
            "BAS.DE":   "BASF",
        },
        "DEFENSE": {
            "RHM.DE":   "Rheinmetall",
            "AIR.DE":   "Airbus",
        },
        "CONSUMER": {
            "ADS.DE":   "Adidas",
            "HEN3.DE":  "Henkel",
            "BEI.DE":   "Beiersdorf",
        },
        "INDUSTRIAL": {
            "SIE.DE":   "Siemens",
            "DHL.DE":   "DHL-Group",
        },
        "HEALTHCARE": {
            "SHL.DE":   "Siemens-Healthineers",
            "MRK.DE":   "Merck-KGaA",
        },
        "INDEX": {
            "^GDAXI":  "DAX",
        },
    },
}

# ── Wielka Brytania (London) ─────────────────────────────────────────────────

GB = {
    "quote": "GBP",
    "country": "GB",
    "assets": {
        "ENERGY": {
            "SHEL.L":  "Shell",
            "BP.L":    "BP",
        },
        "HEALTHCARE": {
            "AZN.L":   "AstraZeneca",
            "GSK.L":   "GSK",
        },
        "FINANCE": {
            "HSBA.L":  "HSBC",
            "LSEG.L":  "London-Stock-Exchange",
            "LLOY.L":  "Lloyds",
            "BARC.L":  "Barclays",
        },
        "CONSUMER": {
            "ULVR.L":  "Unilever",
            "DGE.L":   "Diageo",
            "BATS.L":  "BAT",
            "ABF.L":   "AB-Foods",
            "CPG.L":   "Compass-Group",
        },
        "MINING": {
            "RIO.L":   "Rio-Tinto",
            "AAL.L":   "Anglo-American",
        },
        "INDUSTRIAL": {
            "REL.L":   "RELX",
            "NG.L":    "National-Grid",
        },
        "TELECOM": {
            "VOD.L":   "Vodafone",
        },
        "DEFENSE": {
            "RR.L":    "Rolls-Royce",
            "BA.L":    "BAE-Systems",
        },
        "INDEX": {
            "^FTSE":   "FTSE-100",
        },
    },
}

# ── Polska (Warszawa) ───────────────────────────────────────────────────────

PL = {
    "quote": "PLN",
    "country": "PL",
    "assets": {
        "ENERGY": {
            "PKN.WA":  "PKN-Orlen",
            "JSW.WA":  "JSW",
        },
        "FINANCE": {
            "PKO.WA":  "PKO-BP",
            "PEO.WA":  "Bank-Pekao",
            "PZU.WA":  "PZU",
            "SPL.WA":  "Santander-PL",
            "MBK.WA":  "mBank",
            "KRU.WA":  "Kruk",
        },
        "MINING": {
            "KGH.WA":  "KGHM",
        },
        "IT": {
            "CDR.WA":  "CD-Projekt",
        },
        "CONSUMER": {
            "LPP.WA":  "LPP",
            "ALE.WA":  "Allegro",
            "DNP.WA":  "Dino-Polska",
        },
        "TELECOM": {
            "CPS.WA":  "Cyfrowy-Polsat",
            "OPL.WA":  "Orange-Polska",
        },
    },
}

# ── Rosja (Moscow) ───────────────────────────────────────────────────────────

RU = {
    "quote": "RUB",
    "country": "RU",
    "assets": {
        "FINANCE": {
            "SBER.ME": "Sberbank",
        },
        "ENERGY": {
            "GAZP.ME": "Gazprom",
            "LKOH.ME": "Lukoil",
            "NVTK.ME": "Novatek",
            "ROSN.ME": "Rosneft",
        },
        "MINING": {
            "GMKN.ME": "Nornickel",
            "PLZL.ME": "Polyus",
        },
        "IT": {
            "YNDX.ME": "Yandex",
        },
        "TELECOM": {
            "MTSS.ME": "MTS",
        },
        "CONSUMER": {
            "MGNT.ME": "Magnit",
        },
    },
}

# ── Izrael (Tel Aviv) ────────────────────────────────────────────────────────

IL = {
    "quote": "ILS",
    "country": "IL",
    "assets": {
        "HEALTHCARE": {
            "TEVA.TA": "Teva-Pharma",
        },
        "FINANCE": {
            "LUMI.TA": "Bank-Leumi",
            "DSCT.TA": "Bank-Discount",
            "HARL.TA": "Bank-Hapoalim",
            "MZTF.TA": "Mizrahi-Tefahot",
            "AZRG.TA": "Azrieli-Group",
        },
        "IT": {
            "NICE.TA": "NICE-Systems",
        },
        "MINING": {
            "ICL.TA":  "ICL-Group",
        },
        "TELECOM": {
            "BEZQ.TA": "Bezeq",
        },
        "DEFENSE": {
            "ESLT.TA": "Elbit-Systems",
        },
        "INDEX": {
            "^TA125.TA": "TA-125",
        },
    },
}

# ── Francja (Euronext Paris) ─────────────────────────────────────────────────

FR = {
    "quote": "EUR",
    "country": "FR",
    "assets": {
        "LUXURY": {
            "MC.PA":   "LVMH",
            "RMS.PA":  "Hermes",
            "KER.PA":  "Kering",
        },
        "CONSUMER": {
            "OR.PA":   "LOreal",
            "BN.PA":   "Danone",
            "RI.PA":   "Pernod-Ricard",
        },
        "ENERGY": {
            "TTE.PA":  "TotalEnergies",
        },
        "HEALTHCARE": {
            "SAN.PA":  "Sanofi",
        },
        "INDUSTRIAL": {
            "AI.PA":   "Air-Liquide",
            "SU.PA":   "Schneider-Electric",
            "SGO.PA":  "Saint-Gobain",
            "VIE.PA":  "Veolia",
            "DG.PA":   "Vinci",
        },
        "FINANCE": {
            "CS.PA":   "AXA",
            "BNP.PA":  "BNP-Paribas",
            "GLE.PA":  "Societe-Generale",
        },
        "IT": {
            "DSY.PA":  "Dassault-Systemes",
            "CAP.PA":  "Capgemini",
            "STM.PA":  "STMicroelectronics",
        },
        "DEFENSE": {
            "SAF.PA":  "Safran",
        },
        "INDEX": {
            "^FCHI":   "CAC-40",
        },
    },
}

# ── Szwajcaria (SIX) ─────────────────────────────────────────────────────────

CH = {
    "quote": "CHF",
    "country": "CH",
    "assets": {
        "CONSUMER": {
            "NESN.SW": "Nestle",
        },
        "HEALTHCARE": {
            "ROG.SW":  "Roche",
            "NOVN.SW": "Novartis",
            "LONN.SW": "Lonza",
        },
        "INDUSTRIAL": {
            "ABBN.SW": "ABB",
            "SIKA.SW": "Sika",
            "GEBN.SW": "Geberit",
        },
        "FINANCE": {
            "ZURN.SW": "Zurich-Insurance",
            "UBSG.SW": "UBS",
            "CSGN.SW": "Credit-Suisse",
            "SREN.SW": "Swiss-Re",
            "SLHN.SW": "Swiss-Life",
            "PGHN.SW": "Partners-Group",
        },
        "CHEMICALS": {
            "GIVN.SW": "Givaudan",
        },
        "TELECOM": {
            "SCMN.SW": "Swisscom",
        },
        "INDEX": {
            "^SSMI":   "SMI",
        },
    },
}

# ── UE (paneuropejskie indeksy) ──────────────────────────────────────────────

EU = {
    "quote": "EUR",
    "country": "EU",
    "assets": {
        "INDEX": {
            "^STOXX50E": "Euro-Stoxx-50",
        },
    },
}

# ── Commodities (ETF + Futures) ──────────────────────────────────────────────

COMMODITIES = {
    "quote": "USD",
    "country": None,
    "assets": {
        "ETF_OIL": {
            "USO":   "US-Oil-Fund-WTI",
            "BNO":   "US-Brent-Oil-Fund",
            "UCO":   "ProShares-Ultra-Crude-Oil",
            "SCO":   "ProShares-UltraShort-Crude-Oil",
            "XLE":   "Energy-Select-SPDR",
            "OIH":   "VanEck-Oil-Services-ETF",
            "XOP":   "SPDR-Oil-Gas-Exploration",
        },
        "ETF_GOLD": {
            "GLD":   "SPDR-Gold-Trust",
            "GDX":   "VanEck-Gold-Miners-ETF",
            "GDXJ":  "VanEck-Junior-Gold-Miners",
            "IAU":   "iShares-Gold-Trust",
            "SGOL":  "Aberdeen-Physical-Gold",
            "NUGT":  "Direxion-Gold-Miners-Bull-2x",
        },
        "ETF_SILVER": {
            "SLV":   "iShares-Silver-Trust",
            "SIL":   "Global-X-Silver-Miners-ETF",
            "SILJ":  "ETFMG-Junior-Silver-Miners",
            "SIVR":  "Aberdeen-Physical-Silver",
        },
        "ETF_PLATINUM": {
            "PPLT":  "Aberdeen-Physical-Platinum",
        },
        "ETF_PALLADIUM": {
            "PALL":  "Aberdeen-Physical-Palladium",
        },
        "ETF_NATGAS": {
            "UNG":   "US-Natural-Gas-Fund",
            "BOIL":  "ProShares-Ultra-Natural-Gas",
            "KOLD":  "ProShares-UltraShort-Natural-Gas",
        },
        "ETF_AGRICULTURE": {
            "DBA":   "Invesco-DB-Agriculture",
            "WEAT":  "Teucrium-Wheat-Fund",
            "CORN":  "Teucrium-Corn-Fund",
            "SOYB":  "Teucrium-Soybean-Fund",
            "CANE":  "Teucrium-Sugar-Fund",
            "NIB":   "iPath-Cocoa",
            "JO":    "iPath-Coffee",
            "COW":   "iPath-Livestock",
        },
        "ETF_MULTI_COMMODITY": {
            "DJP":   "iPath-Bloomberg-Commodity",
            "GSG":   "iShares-GSCI-Commodity",
            "DBC":   "Invesco-DB-Commodity",
            "PDBC":  "Invesco-Optimum-Yield-Commodity",
            "COM":   "Direxion-Broad-Commodity",
        },
        "ETF_COPPER": {
            "COPX":  "Global-X-Copper-Miners-ETF",
            "CPER":  "US-Copper-Index-Fund",
            "PICK":  "iShares-Global-Metals-Mining",
        },
        "ETF_URANIUM": {
            "URA":   "Global-X-Uranium-ETF",
            "URNM":  "Sprott-Uranium-Miners-ETF",
        },
        "ETF_LITHIUM": {
            "LIT":   "Global-X-Lithium-Battery-ETF",
        },
        "ETF_TIMBER": {
            "WOOD":  "iShares-Global-Timber-ETF",
            "CUT":   "Invesco-Global-Timber-ETF",
        },
        "ETF_WATER": {
            "PHO":   "Invesco-Water-Resources-ETF",
            "FIW":   "First-Trust-Water-ETF",
        },
        "ETF_REAL_ESTATE": {
            "VNQ":   "Vanguard-Real-Estate-ETF",
            "IYR":   "iShares-US-Real-Estate-ETF",
            "XLRE":  "Real-Estate-Select-SPDR",
        },
        "FUTURES_OIL": {
            "CL=F":  "WTI-Crude-Oil-Futures",
            "BZ=F":  "Brent-Crude-Oil-Futures",
        },
        "FUTURES_GOLD": {
            "GC=F":  "Gold-Futures",
        },
        "FUTURES_SILVER": {
            "SI=F":  "Silver-Futures",
        },
        "FUTURES_PLATINUM": {
            "PL=F":  "Platinum-Futures",
        },
        "FUTURES_PALLADIUM": {
            "PA=F":  "Palladium-Futures",
        },
        "FUTURES_COPPER": {
            "HG=F":  "Copper-Futures",
        },
        "FUTURES_NATGAS": {
            "NG=F":  "Natural-Gas-Futures",
        },
        "FUTURES_CORN": {
            "ZC=F":  "Corn-Futures",
        },
        "FUTURES_WHEAT": {
            "ZW=F":  "Wheat-Futures",
        },
        "FUTURES_SOYBEAN": {
            "ZS=F":  "Soybean-Futures",
        },
        "FUTURES_COFFEE": {
            "KC=F":  "Coffee-Futures",
        },
        "FUTURES_SUGAR": {
            "SB=F":  "Sugar-Futures",
        },
        "FUTURES_COCOA": {
            "CC=F":  "Cocoa-Futures",
        },
        "FUTURES_COTTON": {
            "CT=F":  "Cotton-Futures",
        },
        "FUTURES_LUMBER": {
            "LBS=F": "Lumber-Futures",
        },
        "FUTURES_CATTLE": {
            "LE=F":  "Live-Cattle-Futures",
        },
        "FUTURES_HOGS": {
            "HE=F":  "Lean-Hogs-Futures",
        },
    },
}

# ── Forex ────────────────────────────────────────────────────────────────────

FOREX_GROUP = {
    "quote": "USD",
    "country": None,
    "assets": {
        "FOREX": {
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
        },
    },
}


# ---------------------------------------------------------------------------
# Master registry — budowana automatycznie z zagnieżdżonych grup
# Tuple: (yf_ticker, display_name, quote_asset, country, kind)
# ---------------------------------------------------------------------------

ALL_GROUPS = [US, JP, CN_HK, CN_MAINLAND, DE, GB, PL, RU, IL, FR, CH, EU, COMMODITIES, FOREX_GROUP]

TICKER_REGISTRY: List[tuple] = []

_YF_TO_NAME: Dict[str, str] = {}
_YF_TO_QUOTE: Dict[str, str] = {}
_YF_TO_KIND: Dict[str, str] = {}
_YF_TO_COUNTRY: Dict[str, str] = {}


def _register_country_group(group: dict) -> None:
    quote = group["quote"]
    country = group["country"]
    for kind, tickers in group["assets"].items():
        for yf_ticker, name in tickers.items():
            TICKER_REGISTRY.append((yf_ticker, name, quote, country, kind))
            _YF_TO_NAME[yf_ticker] = name
            _YF_TO_QUOTE[yf_ticker] = quote
            _YF_TO_KIND[yf_ticker] = kind
            _YF_TO_COUNTRY[yf_ticker] = country


for _group in ALL_GROUPS:
    _register_country_group(_group)

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
        base_currency: str = "AAPL",
        quote_currency: str = "USD",
        interval: str = "1d",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Union[int, float, str]]]:
        """
        Pobiera kline/candlestick z Yahoo Finance.

        base_currency to bezpośredni ticker YF (np. AAPL, 7203.T,
        PKN.WA, GC=F, EURUSD=X).
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
        Pobiera symbole z Yahoo Finance.

        base_asset = yf_ticker, full_name = display name,
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
            "base_asset": yf_sym,
            "quote_asset": _YF_TO_QUOTE.get(yf_sym, "USD"),
            "full_name": _YF_TO_NAME.get(yf_sym, ""),
            "kind": _YF_TO_KIND.get(yf_sym, ""),
            "country": _YF_TO_COUNTRY.get(yf_sym, ""),
        }
