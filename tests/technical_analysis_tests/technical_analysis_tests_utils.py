import os
import unittest
import asyncio
import traceback
import json
import base64
import io
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

import pandas as pd
import numpy as np
import mplfinance as mpf

from api.telegram import TelegramAPI, TelegramAPIMock
from api.openai import OpenaiAPI
from api.binance import BinanceAPI
from api.technical_analysis_facade import TechnicalAnalysisFacade as TA
from api.postgresql import PostgreSQL
from api.config import config
from ai_analysis import TechnicalAnalysis as AITechnicalAnalysis

# Async test runner
class AsyncTestCase(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        self.loop.close()
    
    def run_async_test(self, coro):
        return self.loop.run_until_complete(coro)

def get_test_data() -> List[Dict[str, Union[int, float, str]]]:
    """
    Pobiera lub wczytuje dane testowe z pliku.
    Jeśli plik nie istnieje, pobiera dane z Binance API.
    """

    base_currency = "BTC"
    quote_currency = "USDT"
    
    interval = "1d"
    start_time = int(datetime(2022, 1, 1).timestamp() * 1000)
    end_time = int(datetime(2025, 7, 1).timestamp() * 1000)

    # interval = "4h"
    # start_time = int(datetime(2022, 6, 1).timestamp() * 1000)
    # end_time = int(datetime(2022, 9, 1).timestamp() * 1000)

    # interval = "4h"
    # start_time = int(datetime(2022, 3, 1).timestamp() * 1000)
    # end_time = int(datetime(2022, 6, 1).timestamp() * 1000)

    # interval = "4h"
    # start_time = int(datetime(2021, 1, 1).timestamp() * 1000)
    # end_time = int(datetime(2021, 4, 1).timestamp() * 1000)

    data_file = f"test_data/{base_currency.lower()}_{quote_currency.lower()}_{interval}_{start_time}_{end_time}_binance.json"
    os.makedirs("test_data", exist_ok=True)
    
    if os.path.exists(data_file):
        with open(data_file, 'r') as f:
            return json.load(f)
    
    # Inicjalizacja Binance API
    binance_api = BinanceAPI(
        api_key=os.environ.get("BINANCE_API_KEY", default=""),
        api_secret=os.environ.get("BINANCE_API_SECRET", default="")
    )
    
    # Pobranie danych
    klines = binance_api._get_klines(
        base_currency=base_currency,
        quote_currency=quote_currency,
        interval=interval,
        start_time=start_time,
        end_time=end_time
    )
    
    # Zapisywanie danych do pliku
    with open(data_file, 'w') as f:
        json.dump(klines, f)
    
    return klines