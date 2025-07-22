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
from .technical_analysis_tests_utils import get_test_data

class TestHarmonicPatternsCalculationWithDatabaseAndAIIntegration(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.__telegram_api = TelegramAPIMock()
        self.__openai_api = OpenaiAPI()
        self.__binance_api = BinanceAPI(
            api_key=os.environ.get("BINANCE_API_KEY", default=""),
            api_secret=os.environ.get("BINANCE_API_SECRET", default="")
        )
        self.__channels = {
            "Test Channel": {
                "id": -1001234567890,
                "username": "test_channel",
                "pumps": []
            }
        }
        self.__ai_ta = AITechnicalAnalysis(
            telegram_api=self.__telegram_api,
            openai_api=self.__openai_api,
            mexc_api=self.__binance_api,
            channels=self.__channels,
            DEBUG=True
        )

    def tearDown(self):
        self.loop.close()

    def test_prepare_klines_data(self):
        """Test przygotowania danych świeczek"""
        async def run_test():
            klines = [
                {"timestamp": 1000, "open": "100", "high": "110", "low": "90", "close": "105", "volume": "1000"},
                {"timestamp": 2000, "open": "105", "high": "115", "low": "95", "close": "110", "volume": "1200"}
            ]
            
            df = self.__ai_ta._prepare_klines_data(klines)
            
            self.assertIsInstance(df, pd.DataFrame)
            self.assertEqual(len(df), 2)
            self.assertTrue(all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']))
            self.assertTrue(all(isinstance(df[col].iloc[0], float) for col in ['open', 'high', 'low', 'close', 'volume']))
        
        self.loop.run_until_complete(run_test())

    def test_generate_technical_chart(self):
        """Test generowania wykresu technicznego"""
        async def run_test():
            df = pd.DataFrame({
                'open': [100, 105],
                'high': [110, 115],
                'low': [90, 95],
                'close': [105, 110],
                'volume': [1000, 1200]
            }, index=pd.date_range('2024-01-01', periods=2))
            
            analysis = {
                "asset": "BTC",
                "quote": "USDT"
            }
            
            chart_base64 = await self.__ai_ta._generate_technical_chart(df, analysis)
            
            self.assertIsInstance(chart_base64, str)
            try:
                # Sprawdź czy string base64 można zdekodować
                decoded = base64.b64decode(chart_base64)
                self.assertTrue(len(decoded) > 0)
            except Exception as e:
                self.fail(f"Nieprawidłowy format base64: {e}")
        
        self.loop.run_until_complete(run_test())

    @unittest.skip("skip real API tests")
    def test_analyze_message(self):
        """Test analizy wiadomości"""
        async def run_test():
            message = "BTC/USDT - Potencjalny wzrost"
            analysis = await self.__ai_ta.analyze_message(message)
            
            self.assertIsInstance(analysis, dict)
            self.assertIn("asset", analysis)
            self.assertIn("quote", analysis)
        
        self.loop.run_until_complete(run_test())

    @unittest.skip("skip real API tests")
    def test_handle_message(self):
        """Test obsługi wiadomości"""
        async def run_test():
            # Symulacja wiadomości z Telegram
            class MockEvent:
                def __init__(self):
                    self.chat_id = -1001234567890
                    self.message = type('Message', (), {
                        'message': 'BTC/USDT - Potencjalny wzrost',
                        'media': None
                    })
            
            event = MockEvent()
            await self.__ai_ta.handle_message(event)
            
            # Sprawdź czy wiadomość została przetworzona
            # (w rzeczywistym teście należałoby sprawdzić odpowiedź z API)
        
        self.loop.run_until_complete(run_test())

if __name__ == '__main__':
    unittest.main()