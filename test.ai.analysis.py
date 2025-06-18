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

def get_test_data() -> List[Dict[str, Union[int, float, str]]]:
    """
    Pobiera lub wczytuje dane testowe z pliku.
    Jeśli plik nie istnieje, pobiera dane z MEXC API.
    """
    data_file = "test_data/btc_usdt_1w.json"
    os.makedirs("test_data", exist_ok=True)
    
    if os.path.exists(data_file):
        with open(data_file, 'r') as f:
            return json.load(f)
    
    # Inicjalizacja MEXC API w trybie debug
    mexc_api = MexcAPI(
        api_key="",
        api_secret="",
        DEBUG=True
    )
    
    # Konwersja dat na timestampy
    start_time = int(datetime(2021, 5, 1).timestamp() * 1000)
    end_time = int(datetime(2026, 6, 1).timestamp() * 1000)
    
    # Pobranie danych
    klines = mexc_api._get_klines(
        base_currency="BTC",
        quote_currency="USDT",
        interval="1W",
        start_time=start_time,
        end_time=end_time
    )
    
    # Zapisywanie danych do pliku
    with open(data_file, 'w') as f:
        json.dump(klines, f)
    
    return klines

class TestTechnicalAnalysis(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.__ta = TA()
        # Tworzenie katalogu na wykresy testowe
        self.test_charts_dir = "test_charts"
        os.makedirs(self.test_charts_dir, exist_ok=True)
        # Pobranie danych testowych
        self.klines = get_test_data()
        
    def tearDown(self):
        self.loop.close()

    def test_calculate_rsi(self):
        """Test obliczania wskaźnika RSI"""
        # Obliczenie RSI
        rsi_values = self.__ta.calculate_rsi(self.klines)
        
        # Dodanie RSI do danych
        for i, rsi in enumerate(rsi_values):
            self.klines[-(len(rsi_values)-i)]['rsi'] = rsi
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_rsi.png")
        self.__ta.create_candlestick_chart(self.klines, save_path=chart_path, title="Test RSI - BTC/USDT 1W")
        
        self.assertIsInstance(rsi_values, list)
        self.assertTrue(len(rsi_values) > 0)
        self.assertTrue(all(0 <= x <= 100 for x in rsi_values))
        self.assertTrue(os.path.exists(chart_path))

    def test_calculate_macd(self):
        """Test obliczania wskaźnika MACD"""
        # Obliczenie MACD
        macd_data = self.__ta.calculate_macd(self.klines)
        
        # Dodanie MACD do danych
        for i in range(len(macd_data['macd_line'])):
            idx = -(len(macd_data['macd_line'])-i)
            self.klines[idx]['macd'] = macd_data['macd_line'][i]
            self.klines[idx]['signal'] = macd_data['signal_line'][i]
            self.klines[idx]['histogram'] = macd_data['histogram'][i]
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_macd.png")
        self.__ta.create_candlestick_chart(self.klines, save_path=chart_path, title="Test MACD - BTC/USDT 1W")
        
        self.assertIsInstance(macd_data, dict)
        self.assertIn("macd_line", macd_data)
        self.assertIn("signal_line", macd_data)
        self.assertIn("histogram", macd_data)
        self.assertTrue(len(macd_data["macd_line"]) > 0)
        self.assertTrue(os.path.exists(chart_path))

    def test_calculate_obv(self):
        """Test obliczania wskaźnika OBV"""
        # Obliczenie OBV
        obv_values = self.__ta.calculate_obv(self.klines)
        
        # Dodanie OBV do danych
        for i, obv in enumerate(obv_values):
            self.klines[i]['obv'] = obv
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_obv.png")
        self.__ta.create_candlestick_chart(self.klines, save_path=chart_path, title="Test OBV - BTC/USDT 1W")
        
        self.assertIsInstance(obv_values, list)
        self.assertTrue(len(obv_values) > 0)
        self.assertTrue(all(isinstance(x, float) for x in obv_values))
        self.assertTrue(os.path.exists(chart_path))

    def test_calculate_harmonic_patterns(self):
        """Test obliczania wzorców harmonicznych"""
        # Obliczenie wzorców harmonicznych
        patterns = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Dodanie wzorców i poziomów Fibonacciego do danych
        if patterns:
            pattern = patterns[0]
            for point_name, price in pattern.xabcd_points.items():
                self.klines[-1][f'pattern_{point_name}'] = price
            
            for level_name, level_price in pattern.fibonacci_levels.retracement.items():
                self.klines[-1][f'fib_{level_name}'] = level_price
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns.png")
        self.__ta.create_candlestick_chart(self.klines, save_path=chart_path, title="Test Harmonic Patterns - BTC/USDT 1W")
        
        self.assertIsInstance(patterns, list)
        if len(patterns) > 0:
            pattern = patterns[0]
            self.assertIsInstance(pattern.name, str)
            self.assertIsInstance(pattern.xabcd_points, dict)
            self.assertIsInstance(pattern.fibonacci_levels, object)
            self.assertIsInstance(pattern.direction, str)
            self.assertIsInstance(pattern.completion_zone, tuple)
        self.assertTrue(os.path.exists(chart_path))

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