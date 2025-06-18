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
from api.mexc import MexcAPI
from api.technical_analysis import TechnicalAnalysis as TA
from ai_analysis import TechnicalAnalysis as AITechnicalAnalysis

class TestTechnicalAnalysis(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.__ta = TA()
        
    def tearDown(self):
        self.loop.close()

    def test_calculate_rsi(self):
        """Test obliczania wskaźnika RSI"""
        # Przygotowanie danych testowych
        klines = [
            {"timestamp": 1000, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"timestamp": 2000, "open": 105, "high": 115, "low": 95, "close": 110, "volume": 1200},
            {"timestamp": 3000, "open": 110, "high": 120, "low": 100, "close": 115, "volume": 1500},
            {"timestamp": 4000, "open": 115, "high": 125, "low": 105, "close": 120, "volume": 1800},
            {"timestamp": 5000, "open": 120, "high": 130, "low": 110, "close": 125, "volume": 2000}
        ]
        
        rsi = self.__ta.calculate_rsi(klines)
        
        self.assertIsInstance(rsi, list)
        self.assertTrue(len(rsi) > 0)
        self.assertTrue(all(0 <= x <= 100 for x in rsi))

    def test_calculate_macd(self):
        """Test obliczania wskaźnika MACD"""
        klines = [
            {"timestamp": 1000, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"timestamp": 2000, "open": 105, "high": 115, "low": 95, "close": 110, "volume": 1200},
            {"timestamp": 3000, "open": 110, "high": 120, "low": 100, "close": 115, "volume": 1500},
            {"timestamp": 4000, "open": 115, "high": 125, "low": 105, "close": 120, "volume": 1800},
            {"timestamp": 5000, "open": 120, "high": 130, "low": 110, "close": 125, "volume": 2000}
        ]
        
        macd = self.__ta.calculate_macd(klines)
        
        self.assertIsInstance(macd, dict)
        self.assertIn("macd_line", macd)
        self.assertIn("signal_line", macd)
        self.assertIn("histogram", macd)
        self.assertTrue(len(macd["macd_line"]) > 0)

    def test_calculate_obv(self):
        """Test obliczania wskaźnika OBV"""
        klines = [
            {"timestamp": 1000, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"timestamp": 2000, "open": 105, "high": 115, "low": 95, "close": 110, "volume": 1200},
            {"timestamp": 3000, "open": 110, "high": 120, "low": 100, "close": 115, "volume": 1500},
            {"timestamp": 4000, "open": 115, "high": 125, "low": 105, "close": 120, "volume": 1800},
            {"timestamp": 5000, "open": 120, "high": 130, "low": 110, "close": 125, "volume": 2000}
        ]
        
        obv = self.__ta.calculate_obv(klines)
        
        self.assertIsInstance(obv, list)
        self.assertTrue(len(obv) > 0)
        self.assertTrue(all(isinstance(x, float) for x in obv))

    def test_calculate_harmonic_patterns(self):
        """Test obliczania wzorców harmonicznych"""
        klines = [
            {"timestamp": 1000, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"timestamp": 2000, "open": 105, "high": 115, "low": 95, "close": 110, "volume": 1200},
            {"timestamp": 3000, "open": 110, "high": 120, "low": 100, "close": 115, "volume": 1500},
            {"timestamp": 4000, "open": 115, "high": 125, "low": 105, "close": 120, "volume": 1800},
            {"timestamp": 5000, "open": 120, "high": 130, "low": 110, "close": 125, "volume": 2000}
        ]
        
        patterns = self.__ta.calculate_harmonic_patterns(klines)
        
        self.assertIsInstance(patterns, list)
        if len(patterns) > 0:
            pattern = patterns[0]
            self.assertIsInstance(pattern.name, str)
            self.assertIsInstance(pattern.xabcd_points, dict)
            self.assertIsInstance(pattern.fibonacci_levels, object)
            self.assertIsInstance(pattern.direction, str)
            self.assertIsInstance(pattern.completion_zone, tuple)

class TestAITechnicalAnalysis(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.__telegram_api = TelegramAPIMock()
        self.__openai_api = OpenaiAPI()
        self.__mexc_api = MexcAPI(
            api_key=os.environ.get("MEXC_API_KEY", default=""),
            api_secret=os.environ.get("MEXC_API_SECRET", default=""),
            DEBUG=True
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
            mexc_api=self.__mexc_api,
            channels=self.__channels,
            DEBUG=True
        )

    def tearDown(self):
        self.loop.close()

    def test_prepare_klines_data(self):
        """Test przygotowania danych świeczek"""
        klines = [
            {"timestamp": 1000, "open": "100", "high": "110", "low": "90", "close": "105", "volume": "1000"},
            {"timestamp": 2000, "open": "105", "high": "115", "low": "95", "close": "110", "volume": "1200"}
        ]
        
        df = self.__ai_ta._prepare_klines_data(klines)
        
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)
        self.assertTrue(all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']))
        self.assertTrue(all(isinstance(df[col].iloc[0], float) for col in ['open', 'high', 'low', 'close', 'volume']))

    def test_generate_technical_chart(self):
        """Test generowania wykresu technicznego"""
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
        
        chart_base64 = self.__ai_ta._generate_technical_chart(df, analysis)
        
        self.assertIsInstance(chart_base64, str)
        try:
            # Sprawdź czy string base64 można zdekodować
            decoded = base64.b64decode(chart_base64)
            self.assertTrue(len(decoded) > 0)
        except Exception as e:
            self.fail(f"Nieprawidłowy format base64: {e}")

    @unittest.skip("skip real API tests")
    async def test_analyze_message(self):
        """Test analizy wiadomości"""
        message = "BTC/USDT - Potencjalny wzrost"
        analysis = await self.__ai_ta.analyze_message(message)
        
        self.assertIsInstance(analysis, dict)
        self.assertIn("asset", analysis)
        self.assertIn("quote", analysis)

    @unittest.skip("skip real API tests")
    async def test_handle_message(self):
        """Test obsługi wiadomości"""
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

if __name__ == '__main__':
    unittest.main()