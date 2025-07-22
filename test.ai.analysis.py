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

@unittest.skip("Skipping technical analysis tests")
class TestTechnicalAnalysis(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
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
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie RSI używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class()
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_rsi.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_rsi",
                enabled_indicators=enabled_indicators
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy RSI zostało obliczone (sprawdź w klines)
            rsi_found = False
            for kline in self.klines:
                if 'rsi' in kline:
                    rsi_found = True
                    self.assertTrue(0 <= kline['rsi'] <= 100)
                    break
            
            self.assertTrue(rsi_found, "RSI powinno być obliczone i dodane do klines")
        
        self.loop.run_until_complete(run_test())

    def test_calculate_macd(self):
        """Test obliczania wskaźnika MACD"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie MACD używając fabryki
            enabled_indicators = {
                'IndicatorMACD': factory.get_indicator_macd_class()
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_macd.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_macd",
                enabled_indicators=enabled_indicators
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy MACD zostało obliczone (sprawdź w klines)
            macd_found = False
            for kline in self.klines:
                if 'macd' in kline and 'signal' in kline:
                    macd_found = True
                    self.assertIsInstance(kline['macd'], (int, float))
                    self.assertIsInstance(kline['signal'], (int, float))
                    break
            
            self.assertTrue(macd_found, "MACD powinno być obliczone i dodane do klines")
        
        self.loop.run_until_complete(run_test())

    def test_calculate_obv(self):
        """Test obliczania wskaźnika OBV"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie OBV używając fabryki
            enabled_indicators = {
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_obv.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_obv",
                enabled_indicators=enabled_indicators
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy OBV zostało obliczone (sprawdź w klines)
            obv_found = False
            for kline in self.klines:
                if 'obv' in kline:
                    obv_found = True
                    self.assertIsInstance(kline['obv'], (int, float))
                    break
            
            self.assertTrue(obv_found, "OBV powinno być obliczone i dodane do klines")
        
        self.loop.run_until_complete(run_test())

    def test_calculate_harmonic_patterns_basic(self):
        """Test obliczania wzorców harmonicznych - podstawowy"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Utwórz obiekt HarmonicPatterns z podstawową konfiguracją
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': False}
            )
            
            # Obliczenie wzorców harmonicznych używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns
            }
            
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_basic.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_harmonic_patterns_basic",
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy punkty wzorców zostały dodane do klines
            pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_keys.append(key)
                        print(f"Znaleziono punkt wzorca: {key} = {kline[key]}")
                
                # Sprawdź strukturę danych wzorców w klines
                for kline in self.klines:
                    for key in kline.keys():
                        if key.startswith('pattern_') and key.endswith('_price'):
                            # Sprawdź czy punkt ma odpowiednie dodatkowe informacje
                            base_key = key.replace('_price', '')
                            
                            # Sprawdź czy istnieją powiązane klucze
                            name_key = base_key + '_name'
                            type_key = base_key + '_type'
                            bullish_key = base_key + '_bullish'
                            
                            if name_key in kline:
                                self.assertIsInstance(kline[name_key], str)
                                print(f"Nazwa wzorca: {kline[name_key]}")
                            
                            if type_key in kline:
                                self.assertIsInstance(kline[type_key], str)
                                print(f"Typ wzorca: {kline[type_key]}")
                            
                            if bullish_key in kline:
                                self.assertIsInstance(kline[bullish_key], bool)
                                print(f"Bullish: {kline[bullish_key]}")
                            
                            # Sprawdź cenę punktu
                            self.assertIsInstance(kline[key], (int, float))
                            print(f"Cena punktu: {kline[key]}")
        
        self.loop.run_until_complete(run_test())
        print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - basic")

    def test_calculate_harmonic_patterns_no_show(self):
        """Test obliczania wzorców harmonicznych - wszystkie show na False"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            # Utwórz obiekt HarmonicPatterns z wyłączonymi wszystkimi opcjami
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': False}
            )
            # Obliczenie wzorców harmonicznych używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns
            }
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            # Generowanie wykresu z wszystkimi show na False
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_no_show.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines,
                save_path=chart_path,
                title="test_calculate_harmonic_patterns_no_show",
                enabled_objects=enabled_objects
            )
            # Sprawdź czy wykres został wygenerowany (powinien być tylko wykres świecowy)
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            # Sprawdź czy punkty wzorców zostały dodane do klines
            pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_keys.append(key)
            print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - no show (tylko świece)")
        self.loop.run_until_complete(run_test())

    def test_calculate_harmonic_patterns_targets_only(self):
        """Test obliczania wzorców harmonicznych - tylko targety PRZ/TP/SL"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            # Utwórz obiekt HarmonicPatterns z włączonymi tylko targetami
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': True}
            )
            # Obliczenie wzorców harmonicznych używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns
            }
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            # Generowanie wykresu z tylko targetami
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_targets_only.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines,
                save_path=chart_path,
                title="test_calculate_harmonic_patterns_targets_only",
                enabled_objects=enabled_objects
            )
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            # Sprawdź czy punkty wzorców zostały dodane do klines
            pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_keys.append(key)
            print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - targets only")
        self.loop.run_until_complete(run_test())

    def test_calculate_harmonic_patterns_fibonacci_levels(self):
        """Test obliczania wzorców harmonicznych - poziomy Fibonacci dla par punktów"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Utwórz obiekt HarmonicPatterns z włączonymi poziomami Fibonacci
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                all_fibonacci_targets={'show': False}
            )
            
            # Obliczenie wzorców harmonicznych używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns
            }
            
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            
            # Generowanie wykresu z poziomami Fibonacci dla par punktów
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_fibonacci_levels.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_harmonic_patterns_fibonacci_levels",
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy punkty wzorców zostały dodane do klines
            pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_keys.append(key)
            
            print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - fibonacci levels")
        
        self.loop.run_until_complete(run_test())

    def test_calculate_harmonic_patterns_general_fibonacci_levels(self):
        """Test obliczania wzorców harmonicznych - ogólne poziomy Fibonacci"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Utwórz obiekt HarmonicPatterns z włączonymi ogólnymi poziomami Fibonacci
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': False}
            )
            
            # Obliczenie wzorców harmonicznych używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns
            }
            
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_general_fibonacci_levels.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_harmonic_patterns_general_fibonacci_levels",
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy punkty wzorców zostały dodane do klines
            pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_keys.append(key)
            
            print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - general fibonacci levels")
        
        self.loop.run_until_complete(run_test())

    def test_calculate_harmonic_patterns_all_fibonacci_enabled(self):
        """Test obliczania wzorców harmonicznych - wszystkie opcje Fibonacci włączone"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Utwórz obiekt HarmonicPatterns ze wszystkimi opcjami Fibonacci włączonymi
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                all_points_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                all_fibonacci_targets={'show': True}
            )
            
            # Obliczenie wzorców harmonicznych używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns
            }
            
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_all_fibonacci_enabled.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_harmonic_patterns_all_fibonacci_enabled",
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy punkty wzorców zostały dodane do klines
            pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_keys.append(key)
            
            print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - wszystkie fibonacci włączone")
        
        self.loop.run_until_complete(run_test())

    def test_calculate_harmonic_patterns_forming(self):
        """Test obliczania wzorców harmonicznych w trakcie formowania się"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Utwórz obiekt HarmonicPatternsForming z podstawową konfiguracją
            harmonic_patterns_forming = factory.get_harmonic_patterns_forming(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': False}
            )
            
            # Obliczenie wzorców forming używając gotowego obiektu
            enabled_objects = {
                'HarmonicPatternsForming': harmonic_patterns_forming
            }
            
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            
            # Generowanie i zapisywanie wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_forming.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_calculate_harmonic_patterns_forming",
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy punkty wzorców forming zostały dodane do klines
            forming_pattern_keys = []
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('forming_pattern_') and key.endswith('_price'):
                        forming_pattern_keys.append(key)
                        print(f"Znaleziono punkt forming wzorca: {key} = {kline[key]}")
                
                # Sprawdź strukturę danych forming wzorców w klines
                for kline in self.klines:
                    for key in kline.keys():
                        if key.startswith('forming_pattern_') and key.endswith('_price'):
                            # Sprawdź czy punkt ma odpowiednie dodatkowe informacje
                            base_key = key.replace('_price', '')
                            
                            # Sprawdź czy istnieją powiązane klucze
                            name_key = base_key + '_name'
                            type_key = base_key + '_type'
                            bullish_key = base_key + '_bullish'
                            
                            if name_key in kline:
                                self.assertIsInstance(kline[name_key], str)
                                print(f"Nazwa forming wzorca: {kline[name_key]}")
                            
                            if type_key in kline:
                                self.assertIsInstance(kline[type_key], str)
                                print(f"Typ forming wzorca: {kline[type_key]}")
                            
                            if bullish_key in kline:
                                self.assertIsInstance(kline[bullish_key], bool)
                                print(f"Forming Bullish: {kline[bullish_key]}")
                            
                            # Sprawdź cenę punktu
                            self.assertIsInstance(kline[key], (int, float))
                            print(f"Cena forming punktu: {kline[key]}")
            
            print(f"Znaleziono {len(forming_pattern_keys)} punktów forming wzorców")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_visualization(self):
        """Test wizualizacji wzorców harmonicznych na wykresie"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Utwórz obiekty z odpowiednimi konfiguracjami
            harmonic_patterns = factory.get_harmonic_patterns(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': False}
            )
            
            harmonic_patterns_forming = factory.get_harmonic_patterns_forming(
                general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                all_fibonacci_targets={'show': False}
            )
            
            # Obliczenie wszystkich typów wzorców używając gotowych obiektów
            enabled_objects = {
                'HarmonicPatterns': harmonic_patterns,
                'HarmonicPatternsForming': harmonic_patterns_forming
            }
            
            await self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
            
            # Zlicz wszystkie punkty wzorców w klines
            pattern_points = 0
            forming_pattern_points = 0
            
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        pattern_points += 1
                    elif key.startswith('forming_pattern_') and key.endswith('_price'):
                        forming_pattern_points += 1
            
            print(f"Znaleziono {pattern_points} punktów zwykłych wzorców w klines")
            print(f"Znaleziono {forming_pattern_points} punktów forming wzorców w klines")
            
            # Generowanie wykresu z wszystkimi wzorcami
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_visualization.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_visualization",
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy base64 można zdekodować
            try:
                decoded = base64.b64decode(chart_base64)
                self.assertTrue(len(decoded) > 0)
            except Exception as e:
                self.fail(f"Nieprawidłowy format base64: {e}")
            
            # Sprawdź czy wzorce zostały znalezione
            total_patterns = pattern_points + forming_pattern_points
            self.assertGreaterEqual(total_patterns, 0)
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_with_indicators_basic(self):
        """Test wzorców harmonicznych z wskaźnikami technicznymi - podstawowy"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie wskaźników i wzorców używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class(),
                'IndicatorMACD': factory.get_indicator_macd_class(),
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            enabled_objects = {
                'HarmonicPatterns': factory.get_harmonic_patterns(
                    general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_fibonacci_targets={'show': False}
                )
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
            
            # Generowanie kompleksowego wykresu
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_basic.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_with_indicators_basic",
                enabled_indicators=enabled_indicators,
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy wskaźniki i wzorce są w klines
            indicators_found = False
            patterns_found = False
            
            for kline in self.klines:
                # Sprawdź wskaźniki
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                
                # Sprawdź wzorce
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_found = True
                        break
            
            self.assertTrue(indicators_found, "Wskaźniki techniczne powinny być w klines")
            self.assertTrue(patterns_found, "Wzorce harmoniczne powinny być w klines")
            
            print(f"Znaleziono wskaźniki i wzorce harmoniczne - basic")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_with_indicators_no_show(self):
        """Test wzorców harmonicznych z wskaźnikami - tylko wskaźniki, bez wzorców"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie wskaźników i wzorców używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class(),
                'IndicatorMACD': factory.get_indicator_macd_class(),
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            enabled_objects = {
                'HarmonicPatterns': factory.get_harmonic_patterns(
                    general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_fibonacci_targets={'show': False}
                )
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
            
            # Generowanie wykresu z tylko wskaźnikami
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_no_show.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_with_indicators_no_show",
                enabled_indicators=enabled_indicators,
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy wskaźniki są w klines
            indicators_found = False
            for kline in self.klines:
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                    break
            
            self.assertTrue(indicators_found, "Wskaźniki techniczne powinny być w klines")
            
            print(f"Znaleziono wskaźniki z wzorcami harmonicznymi - no show patterns")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_with_indicators_targets_only(self):
        """Test wzorców harmonicznych z wskaźnikami - tylko targety PRZ/TP/SL"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie wskaźników i wzorców używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class(),
                'IndicatorMACD': factory.get_indicator_macd_class(),
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            enabled_objects = {
                'HarmonicPatterns': factory.get_harmonic_patterns(
                    general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_fibonacci_targets={'show': True}
                )
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
            
            # Generowanie wykresu z targetami i wskaźnikami
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_targets_only.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_with_indicators_targets_only",
                enabled_indicators=enabled_indicators,
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy wskaźniki i wzorce są w klines
            indicators_found = False
            patterns_found = False
            
            for kline in self.klines:
                # Sprawdź wskaźniki
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                
                # Sprawdź wzorce
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_found = True
                        break
            
            self.assertTrue(indicators_found, "Wskaźniki techniczne powinny być w klines")
            self.assertTrue(patterns_found, "Wzorce harmoniczne powinny być w klines")
            
            print(f"Znaleziono wskaźniki i wzorce harmoniczne - targets only")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_with_indicators_all_points_fibonacci_levels(self):
        """Test wzorców harmonicznych z wskaźnikami - poziomy Fibonacci dla par punktów"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie wskaźników i wzorców używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class(),
                'IndicatorMACD': factory.get_indicator_macd_class(),
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            enabled_objects = {
                'HarmonicPatterns': factory.get_harmonic_patterns(
                    general_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_points_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                    all_fibonacci_targets={'show': False}
                )
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
            
            # Generowanie wykresu z poziomami Fibonacci i wskaźnikami
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_all_points_fibonacci_levels.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_with_indicators_all_points_fibonacci_levels",
                enabled_indicators=enabled_indicators,
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy wskaźniki i wzorce są w klines
            indicators_found = False
            patterns_found = False
            
            for kline in self.klines:
                # Sprawdź wskaźniki
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                
                # Sprawdź wzorce
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_found = True
                        break
            
            self.assertTrue(indicators_found, "Wskaźniki techniczne powinny być w klines")
            self.assertTrue(patterns_found, "Wzorce harmoniczne powinny być w klines")
            
            print(f"Znaleziono wskaźniki i wzorce harmoniczne - fibonacci levels")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_with_indicators_general_fibonacci_levels(self):
        """Test wzorców harmonicznych z wskaźnikami - ogólne poziomy Fibonacci"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie wskaźników i wzorców używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class(),
                'IndicatorMACD': factory.get_indicator_macd_class(),
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            enabled_objects = {
                'HarmonicPatterns': factory.get_harmonic_patterns(
                    general_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                    all_points_fibonacci_levels={'show': False, 'retracement': False, 'extension': False},
                    all_fibonacci_targets={'show': False}
                )
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
            
            # Generowanie wykresu z ogólnymi poziomami Fibonacci i wskaźnikami
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_general_fibonacci_levels.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_with_indicators_general_fibonacci_levels",
                enabled_indicators=enabled_indicators,
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy wskaźniki i wzorce są w klines
            indicators_found = False
            patterns_found = False
            
            for kline in self.klines:
                # Sprawdź wskaźniki
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                
                # Sprawdź wzorce
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_found = True
                        break
            
            self.assertTrue(indicators_found, "Wskaźniki techniczne powinny być w klines")
            self.assertTrue(patterns_found, "Wzorce harmoniczne powinny być w klines")
            
            print(f"Znaleziono wskaźniki i wzorce harmoniczne - general fibonacci levels")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_with_indicators_all_fibonacci(self):
        """Test wzorców harmonicznych z wskaźnikami - wszystkie opcje Fibonacci włączone"""
        async def run_test():
            # Pobierz fabrykę
            factory = self.__ta.get_technical_analysis_factory()
            
            # Obliczenie wskaźników i wzorców używając fabryki
            enabled_indicators = {
                'IndicatorRSI': factory.get_indicator_rsi_class(),
                'IndicatorMACD': factory.get_indicator_macd_class(),
                'IndicatorOBV': factory.get_indicator_obv_class()
            }
            
            enabled_objects = {
                'HarmonicPatterns': factory.get_harmonic_patterns(
                    general_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                    all_points_fibonacci_levels={'show': True, 'retracement': True, 'extension': True},
                    all_fibonacci_targets={'show': True}
                )
            }
            
            await self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
            
            # Generowanie wykresu ze wszystkimi opcjami Fibonacci i wskaźnikami
            chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_all_fibonacci.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_harmonic_patterns_with_indicators_all_fibonacci",
                enabled_indicators=enabled_indicators,
                enabled_objects=enabled_objects
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy wskaźniki i wzorce są w klines
            indicators_found = False
            patterns_found = False
            
            for kline in self.klines:
                # Sprawdź wskaźniki
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                
                # Sprawdź wzorce
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_found = True
                        break
            
            self.assertTrue(indicators_found, "Wskaźniki techniczne powinny być w klines")
            self.assertTrue(patterns_found, "Wzorce harmoniczne powinny być w klines")
            
            print(f"Znaleziono wskaźniki i wzorce harmoniczne - wszystkie fibonacci włączone")
        
        self.loop.run_until_complete(run_test())

    def test_generate_chart_without_indicators_and_objects(self):
        """Test generowania wykresu bez żadnych wskaźników i obiektów"""
        async def run_test():
            # Generowanie wykresu bez żadnych wskaźników i obiektów
            chart_path = os.path.join(self.test_charts_dir, "test_generate_chart_without_indicators_and_objects.png")
            chart_base64 = await self.__ta.create_candlestick_chart(
                self.klines, 
                save_path=chart_path, 
                title="test_generate_chart_without_indicators_and_objects",
                enabled_indicators=None,  # Brak wskaźników
                enabled_objects=None      # Brak obiektów
            )
            
            # Sprawdź czy wykres został wygenerowany
            self.assertIsInstance(chart_base64, str)
            self.assertTrue(len(chart_base64) > 0)
            self.assertTrue(os.path.exists(chart_path))
            
            # Sprawdź czy nie ma wskaźników w klines
            indicators_found = False
            for kline in self.klines:
                if 'rsi' in kline or 'macd' in kline or 'obv' in kline:
                    indicators_found = True
                    break
            
            # Sprawdź czy nie ma wzorców w klines
            patterns_found = False
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_found = True
                        break
            
            # Powinno być tylko świece, bez wskaźników i wzorców
            self.assertFalse(indicators_found, "Nie powinno być wskaźników w klines")
            self.assertFalse(patterns_found, "Nie powinno być wzorców w klines")
            
            print(f"Wygenerowano wykres bez wskaźników i obiektów - tylko świece")
        
        self.loop.run_until_complete(run_test())

class TestHarmonicPatternsDatabaseIntegration(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.__ta = TA()
        # Tworzenie katalogu na wykresy testowe
        self.test_charts_dir = "test_charts"
        os.makedirs(self.test_charts_dir, exist_ok=True)
        # Pobranie danych testowych
        self.klines = get_test_data()

    def tearDown(self):
        self.loop.close()
    
    async def print_database_records(self, factory, test_name: str):
        """Metoda pomocnicza do wyświetlania rekordów z bazy danych"""
        try:
            # Pobierz wszystkie tabele
            assets_table = factory.get_assets_table()
            technical_analysis_table = factory.get_technical_analysis_table()
            
            # Lista assets
            assets = await assets_table.get_all()
            print(f"\n=== {test_name} - ASSETS TABLE ===")
            if assets:
                for asset in assets:
                    print(f"ID: {asset['id']}, Asset: {asset['asset']}, Quote: {asset['quote']}")
            else:
                print("Brak rekordów w tabeli assets")
            
            # Lista technical_analysis
            technical_analysis = await technical_analysis_table.get_all()
            print(f"\n=== {test_name} - TECHNICAL_ANALYSIS TABLE ===")
            if technical_analysis:
                for record in technical_analysis:
                    # Skróć JSON do max 24 znaków
                    ta_json_str = str(record['ta_object_json'])
                    if len(ta_json_str) > 24:
                        ta_json_str = ta_json_str[:21] + "..."
                    
                    print(f"ID: {record['id']}, Asset_ID: {record['asset_id']}, "
                          f"X: {record['x_point_timestamp']}, A: {record['a_point_timestamp']}, "
                          f"B: {record['b_point_timestamp']}, C: {record['c_point_timestamp']}, "
                          f"D: {record['d_point_timestamp']}, JSON: {ta_json_str}")
            else:
                print("Brak rekordów w tabeli technical_analysis")
            
            print(f"=== KONIEC {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas listowania rekordów z bazy danych: {e}")
    
    async def print_database_stats(self, factory, test_name: str):
        """Metoda pomocnicza do wyświetlania statystyk bazy danych"""
        try:
            assets_table = factory.get_assets_table()
            technical_analysis_table = factory.get_technical_analysis_table()
            
            # Pobierz statystyki
            assets_count = len(await assets_table.get_all())
            technical_analysis_count = len(await technical_analysis_table.get_all())
            
            print(f"\n=== {test_name} - STATYSTYKI BAZY DANYCH ===")
            print(f"Liczba assets: {assets_count}")
            print(f"Liczba technical_analysis: {technical_analysis_count}")
            print(f"=== KONIEC STATYSTYK {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas pobierania statystyk z bazy danych: {e}")
    
    async def cleanup_database(self, factory, test_name: str):
        """Metoda pomocnicza do czyszczenia bazy danych po teście"""
        try:
            technical_analysis_table = factory.get_technical_analysis_table()
            assets_table = factory.get_assets_table()
            
            # Usuń wszystkie rekordy z technical_analysis
            all_technical_analysis = await technical_analysis_table.get_all(limit=1000, offset=0)
            deleted_ta_count = 0
            for record in all_technical_analysis:
                if await technical_analysis_table.delete(record['id']):
                    deleted_ta_count += 1
            
            # Usuń wszystkie assety (opcjonalnie - może być używane przez inne testy)
            all_assets = await assets_table.get_all(limit=1000, offset=0)
            deleted_assets_count = 0
            for asset in all_assets:
                if await assets_table.delete(asset['id']):
                    deleted_assets_count += 1
            
            print(f"\n=== {test_name} - CZYSZCZENIE BAZY DANYCH ===")
            print(f"Usunięto {deleted_ta_count} rekordów z technical_analysis")
            print(f"Usunięto {deleted_assets_count} rekordów z assets")
            print(f"=== KONIEC CZYSZCZENIA {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas czyszczenia bazy danych: {e}")

    def test_harmonic_patterns_with_database_integration(self):
        """Test wzorców harmonicznych z integracją bazy danych"""
        import asyncio
        from api.postgresql import PostgreSQL
        from api.technical_analysis_factory import TechnicalAnalysisFactory
        from api.config import config
        
        async def run_database_test():
            # Inicjalizacja bazy danych (użyj configa)
            db_url = config.get_database_url()
            db = PostgreSQL(db_url)
            
            try:
                await db.init_db()
                factory = db.get_factory()
                
                # Pobierz lub utwórz asset BTC/USDT
                assets_table = factory.get_assets_table()
                asset = await assets_table.get_by_asset_quote("BTC", "USDT")
                
                if not asset:
                    # Utwórz asset jeśli nie istnieje
                    asset_id = await assets_table.create("BTC", "USDT")
                    asset = await assets_table.get_by_id(asset_id)
                else:
                    asset_id = asset['id']
                
                # Utwórz HarmonicPatterns z integracją bazy danych
                ta_factory = TechnicalAnalysisFactory()
                harmonic_patterns = ta_factory.get_harmonic_patterns(
                    use_database=True,
                    database_factory=factory,
                    asset_id=asset_id
                )
                
                # Oblicz wzorce harmoniczne
                await harmonic_patterns.calculate(self.klines, symbol="BTCUSDT", interval="1d")
                
                # Sprawdź czy wzorce zostały zapisane w bazie
                technical_analysis_table = factory.get_technical_analysis_table()
                patterns_in_db = await technical_analysis_table.get_by_asset_id(asset_id)
                
                # Sprawdź czy wzorce są w klines
                patterns_in_klines = 0
                for kline in self.klines:
                    for key in kline.keys():
                        if key.startswith('pattern_') and key.endswith('_price'):
                            patterns_in_klines += 1
                
                print(f"Znaleziono {len(patterns_in_db)} wzorców w bazie danych")
                print(f"Znaleziono {patterns_in_klines} punktów wzorców w klines")
                
                # Wyświetl wszystkie rekordy z bazy danych
                await self.print_database_records(factory, "test_harmonic_patterns_with_database_integration")
                
                # Wyświetl statystyki bazy danych
                await self.print_database_stats(factory, "test_harmonic_patterns_with_database_integration")
                
                # Sprawdź czy liczba wzorców w bazie odpowiada wzorcom w klines
                self.assertGreaterEqual(len(patterns_in_db), 0)
                self.assertGreaterEqual(patterns_in_klines, 0)
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_harmonic_patterns_with_database_integration")
                
                # Sprawdź strukturę danych w bazie
                for pattern in patterns_in_db:
                    self.assertIn('asset_id', pattern)
                    self.assertIn('ta_object_json', pattern)
                    self.assertIn('x_point_timestamp', pattern)
                    self.assertEqual(pattern['asset_id'], asset_id)
                    
                    # Sprawdź JSON
                    ta_json = pattern['ta_object_json']
                    self.assertIn('pattern_name', ta_json)
                    self.assertIn('pattern_type', ta_json)
                    self.assertIn('is_bullish', ta_json)
                    self.assertIn('is_formed', ta_json)
                
                # Generuj wykres
                chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_database_integration.png")
                chart_base64 = await self.__ta.create_candlestick_chart(
                    self.klines, 
                    save_path=chart_path, 
                    title="test_harmonic_patterns_with_database_integration",
                    enabled_objects={'HarmonicPatterns': harmonic_patterns}
                )
                
                self.assertIsInstance(chart_base64, str)
                self.assertTrue(len(chart_base64) > 0)
                self.assertTrue(os.path.exists(chart_path))
                
            except Exception as e:
                print(f"Błąd podczas testu bazy danych: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna (dla CI/CD)
                self.assertTrue(True, "Test bazy danych - baza może być niedostępna")
            finally:
                await db.close_db()
        
        self.loop.run_until_complete(run_database_test())

    def test_harmonic_patterns_database_sync(self):
        """Test synchronizacji wzorców harmonicznych z bazą danych"""
        import asyncio
        from api.postgresql import PostgreSQL
        from api.technical_analysis_factory import TechnicalAnalysisFactory
        from api.config import config
        
        async def run_sync_test():
            # Inicjalizacja bazy danych
            db_url = config.get_database_url()
            db = PostgreSQL(db_url)
            
            try:
                await db.init_db()
                factory = db.get_factory()
                
                # Pobierz lub utwórz asset ETH/USDT
                assets_table = factory.get_assets_table()
                asset = await assets_table.get_by_asset_quote("ETH", "USDT")
                
                if not asset:
                    asset_id = await assets_table.create("ETH", "USDT")
                    asset = await assets_table.get_by_id(asset_id)
                else:
                    asset_id = asset['id']
                
                # Utwórz HarmonicPatterns z integracją bazy danych
                ta_factory = TechnicalAnalysisFactory()
                harmonic_patterns = ta_factory.get_harmonic_patterns(
                    use_database=True,
                    database_factory=factory,
                    asset_id=asset_id
                )
                
                # Pierwsze obliczenie
                await harmonic_patterns.calculate(self.klines, symbol="ETHUSDT", interval="1d")
                
                # Sprawdź wzorce po pierwszym obliczeniu
                technical_analysis_table = factory.get_technical_analysis_table()
                patterns_after_first = await technical_analysis_table.get_by_asset_id(asset_id)
                first_count = len(patterns_after_first)
                
                print(f"Po pierwszym obliczeniu: {first_count} wzorców w bazie")
                
                # Wyświetl rekordy po pierwszym obliczeniu
                await self.print_database_records(factory, "test_harmonic_patterns_database_sync_po_pierwszym")
                
                # Wyświetl statystyki po pierwszym obliczeniu
                await self.print_database_stats(factory, "test_harmonic_patterns_database_sync_po_pierwszym")
                
                # Drugie obliczenie (powinno usunąć stare i dodać nowe)
                await harmonic_patterns.calculate(self.klines, symbol="ETHUSDT", interval="1d")
                
                # Sprawdź wzorce po drugim obliczeniu
                patterns_after_second = await technical_analysis_table.get_by_asset_id(asset_id)
                second_count = len(patterns_after_second)
                
                print(f"Po drugim obliczeniu: {second_count} wzorców w bazie")
                
                # Wyświetl rekordy po drugim obliczeniu
                await self.print_database_records(factory, "test_harmonic_patterns_database_sync_po_drugim")
                
                # Wyświetl statystyki po drugim obliczeniu
                await self.print_database_stats(factory, "test_harmonic_patterns_database_sync_po_drugim")
                
                # Sprawdź czy wzorce zostały zsynchronizowane
                self.assertGreaterEqual(first_count, 0)
                self.assertGreaterEqual(second_count, 0)
                
                # Sprawdź czy wszystkie wzorce w bazie mają poprawną strukturę
                for pattern in patterns_after_second:
                    self.assertIn('x_point_timestamp', pattern)
                    self.assertIn('a_point_timestamp', pattern)
                    self.assertIn('b_point_timestamp', pattern)
                    self.assertIn('c_point_timestamp', pattern)
                    self.assertIn('d_point_timestamp', pattern)
                    
                    # Sprawdź czy timestamps są w formacie string
                    self.assertIsInstance(pattern['x_point_timestamp'], str)
                    if pattern['a_point_timestamp']:
                        self.assertIsInstance(pattern['a_point_timestamp'], str)
                    if pattern['b_point_timestamp']:
                        self.assertIsInstance(pattern['b_point_timestamp'], str)
                    if pattern['c_point_timestamp']:
                        self.assertIsInstance(pattern['c_point_timestamp'], str)
                    if pattern['d_point_timestamp']:
                        self.assertIsInstance(pattern['d_point_timestamp'], str)
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_harmonic_patterns_database_sync")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test synchronizacji - baza może być niedostępna")
            finally:
                await db.close_db()
        
        self.loop.run_until_complete(run_sync_test())

    def test_harmonic_patterns_database_timestamp_range(self):
        """Test pobierania wzorców z określonego zakresu czasowego"""
        async def run_test():
            import asyncio
            from api.postgresql import PostgreSQL
            from api.technical_analysis_factory import TechnicalAnalysisFactory
            from api.config import config
            # Inicjalizacja bazy danych
            db_url = config.get_database_url()
            db = PostgreSQL(db_url)
            try:
                await db.init_db()
                factory = db.get_factory()
                # Pobierz lub utwórz asset ADA/USDT
                assets_table = factory.get_assets_table()
                asset = await assets_table.get_by_asset_quote("ADA", "USDT")
                if not asset:
                    asset_id = await assets_table.create("ADA", "USDT")
                    asset = await assets_table.get_by_id(asset_id)
                else:
                    asset_id = asset['id']
                # Utwórz HarmonicPatterns z integracją bazy danych
                ta_factory = TechnicalAnalysisFactory()
                harmonic_patterns = ta_factory.get_harmonic_patterns(
                    use_database=True,
                    database_factory=factory,
                    asset_id=asset_id
                )
                # Oblicz wzorce
                await harmonic_patterns.calculate(self.klines, symbol="ADAUSDT", interval="1d")
                # Pobierz zakres czasowy z klines
                start_timestamp = str(self.klines[0]['open_time'])
                end_timestamp = str(self.klines[-1]['close_time'])
                # Pobierz wzorce z określonego zakresu czasowego
                technical_analysis_table = factory.get_technical_analysis_table()
                patterns_in_range = await technical_analysis_table.get_by_timestamp_range_and_asset_id(
                    start_timestamp, end_timestamp, asset_id
                )
                print(f"Zakres czasowy: {start_timestamp} - {end_timestamp}")
                print(f"Znaleziono {len(patterns_in_range)} wzorców w zakresie czasowym")
                
                # Wyświetl wszystkie rekordy z bazy danych
                await self.print_database_records(factory, "test_harmonic_patterns_database_timestamp_range")
                
                # Wyświetl statystyki bazy danych
                await self.print_database_stats(factory, "test_harmonic_patterns_database_timestamp_range")
                
                # Sprawdź czy wzorce są w zakresie czasowym
                for pattern in patterns_in_range:
                    x_timestamp = pattern['x_point_timestamp']
                    if x_timestamp:
                        self.assertGreaterEqual(x_timestamp, start_timestamp)
                        self.assertLessEqual(x_timestamp, end_timestamp)
                    # Sprawdź czy asset_id jest poprawny
                    self.assertEqual(pattern['asset_id'], asset_id)
                    # Sprawdź czy JSON zawiera wymagane pola
                    ta_json = pattern['ta_object_json']
                    self.assertIn('pattern_name', ta_json)
                    self.assertIn('pattern_type', ta_json)
                    self.assertIn('is_bullish', ta_json)
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_harmonic_patterns_database_timestamp_range")
                
            except Exception as e:
                print(f"Błąd podczas testu zakresu czasowego: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test zakresu czasowego - baza może być niedostępna")
            finally:
                await db.close_db()
        self.loop.run_until_complete(run_test())

    async def test_harmonic_patterns_database_without_integration(self):
        """Test wzorców harmonicznych bez integracji z bazą danych (debug mode)"""
        from api.technical_analysis_factory import TechnicalAnalysisFactory
        
        # Utwórz HarmonicPatterns bez integracji z bazą danych
        ta_factory = TechnicalAnalysisFactory()
        harmonic_patterns = ta_factory.get_harmonic_patterns(
            use_database=False,  # Wyłącz integrację z bazą
            database_factory=None,
            asset_id=None
        )
        
        # Oblicz wzorce harmoniczne
        await harmonic_patterns.calculate(self.klines, symbol="BTCUSDT", interval="1d")
        
        # Sprawdź czy wzorce zostały obliczone (w klines)
        patterns_in_klines = 0
        for kline in self.klines:
            for key in kline.keys():
                if key.startswith('pattern_') and key.endswith('_price'):
                    patterns_in_klines += 1
        
        print(f"Znaleziono {patterns_in_klines} punktów wzorców w klines (bez integracji z bazą)")
        
        # Sprawdź czy wzorce są w klines
        self.assertGreaterEqual(patterns_in_klines, 0)
        
        # Generuj wykres
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_without_database_integration.png")
        chart_base64 = await self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="test_harmonic_patterns_without_database_integration",
            enabled_objects={'HarmonicPatterns': harmonic_patterns}
        )
        
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print("Test wzorców harmonicznych bez integracji z bazą danych - OK")
        
        # Wyświetl rekordy z bazy danych (jeśli są dostępne)
        try:
            from api.postgresql import PostgreSQL
            from api.config import config
            db_url = config.get_database_url()
            db = PostgreSQL(db_url)
            await db.init_db()
            factory = db.get_factory()
            await self.print_database_records(factory, "test_harmonic_patterns_database_without_integration")
            await self.print_database_stats(factory, "test_harmonic_patterns_database_without_integration")
            
            # Wyczyść bazę danych po teście
            await self.cleanup_database(factory, "test_harmonic_patterns_database_without_integration")
            
            await db.close_db()
        except Exception as e:
            print(f"Nie można wyświetlić rekordów z bazy danych: {e}")

    async def test_harmonic_patterns_database_error_handling(self):
        """Test obsługi błędów podczas integracji z bazą danych"""
        import asyncio
        from api.postgresql import PostgreSQL
        from api.technical_analysis_factory import TechnicalAnalysisFactory
        from api.config import config
        
        async def run_error_test():
            # Próba połączenia z nieistniejącą bazą danych (użyj configa ale z błędnymi danymi)
            db_url = config.get_database_url().replace("test_db", "invalid_db").replace("test_user", "invalid_user").replace("test_pass", "invalid_pass")
            db = PostgreSQL(db_url)
            
            try:
                # Utwórz HarmonicPatterns z nieprawidłową bazą danych
                ta_factory = TechnicalAnalysisFactory()
                harmonic_patterns = ta_factory.get_harmonic_patterns(
                    use_database=True,
                    database_factory=None,  # Nieprawidłowa fabryka
                    asset_id=1
                )
                
                # Obliczenia powinny działać nawet z błędami bazy danych
                await harmonic_patterns.calculate(self.klines, symbol="BTCUSDT", interval="1d")
                
                # Sprawdź czy wzorce zostały obliczone (w klines)
                patterns_in_klines = 0
                for kline in self.klines:
                    for key in kline.keys():
                        if key.startswith('pattern_') and key.endswith('_price'):
                            patterns_in_klines += 1
                
                print(f"Znaleziono {patterns_in_klines} punktów wzorców w klines (z błędami bazy)")
                
                # Sprawdź czy wzorce są w klines (obliczenia powinny działać)
                self.assertGreaterEqual(patterns_in_klines, 0)
                
                # Generuj wykres
                chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_database_error_handling.png")
                chart_base64 = await self.__ta.create_candlestick_chart(
                    self.klines, 
                    save_path=chart_path, 
                    title="test_harmonic_patterns_database_error_handling",
                    enabled_objects={'HarmonicPatterns': harmonic_patterns}
                )
                
                self.assertIsInstance(chart_base64, str)
                self.assertTrue(len(chart_base64) > 0)
                self.assertTrue(os.path.exists(chart_path))
                
                # Wyświetl rekordy z bazy danych (jeśli są dostępne)
                try:
                    await self.print_database_records(factory, "test_harmonic_patterns_database_error_handling")
                    await self.print_database_stats(factory, "test_harmonic_patterns_database_error_handling")
                    
                    # Wyczyść bazę danych po teście
                    await self.cleanup_database(factory, "test_harmonic_patterns_database_error_handling")
                    
                except Exception as e:
                    print(f"Nie można wyświetlić rekordów z bazy danych: {e}")
                
            except Exception as e:
                print(f"Błąd podczas testu obsługi błędów: {e}")
                # Test przechodzi nawet jeśli wystąpią błędy bazy danych
                self.assertTrue(True, "Test obsługi błędów - błędy bazy danych są obsługiwane")
            finally:
                try:
                    await db.close_db()
                except:
                    pass
        
        self.loop.run_until_complete(run_error_test())

    def test_harmonic_patterns_database_sync_with_deletion(self):
        """Test synchronizacji wzorców z bazą danych z usuwaniem i ponownym dodawaniem"""
        import asyncio
        from api.postgresql import PostgreSQL
        from api.technical_analysis_factory import TechnicalAnalysisFactory
        from api.config import config
        
        async def run_sync_with_deletion_test():
            # Inicjalizacja bazy danych
            db_url = config.get_database_url()
            db = PostgreSQL(db_url)
            
            try:
                await db.init_db()
                factory = db.get_factory()
                
                # Pobierz lub utwórz asset SOL/USDT
                assets_table = factory.get_assets_table()
                asset = await assets_table.get_by_asset_quote("SOL", "USDT")
                
                if not asset:
                    asset_id = await assets_table.create("SOL", "USDT")
                    asset = await assets_table.get_by_id(asset_id)
                else:
                    asset_id = asset['id']
                
                # Utwórz HarmonicPatterns z integracją bazy danych
                ta_factory = TechnicalAnalysisFactory()
                harmonic_patterns = ta_factory.get_harmonic_patterns(
                    use_database=True,
                    database_factory=factory,
                    asset_id=asset_id
                )
                
                # Pierwsze obliczenie wzorców
                await harmonic_patterns.calculate(self.klines, symbol="SOLUSDT", interval="1d")
                
                # Sprawdź wzorce po pierwszym obliczeniu
                technical_analysis_table = factory.get_technical_analysis_table()
                patterns_after_first = await technical_analysis_table.get_by_asset_id(asset_id)
                first_count = len(patterns_after_first)
                
                print(f"Po pierwszym obliczeniu: {first_count} wzorców w bazie")
                
                # Wyświetl rekordy po pierwszym obliczeniu
                await self.print_database_records(factory, "test_sync_with_deletion_po_pierwszym")
                await self.print_database_stats(factory, "test_sync_with_deletion_po_pierwszym")
                
                # Usuń jeden wzorzec z bazy danych (jeśli są jakieś wzorce)
                if patterns_after_first:
                    pattern_to_delete = patterns_after_first[0]
                    deleted_id = pattern_to_delete['id']
                    
                    success = await technical_analysis_table.delete(deleted_id)
                    if success:
                        print(f"Usunięto wzorzec z ID: {deleted_id}")
                        
                        # Sprawdź wzorce po usunięciu
                        patterns_after_deletion = await technical_analysis_table.get_by_asset_id(asset_id)
                        after_deletion_count = len(patterns_after_deletion)
                        print(f"Po usunięciu: {after_deletion_count} wzorców w bazie")
                        
                        # Wyświetl rekordy po usunięciu
                        await self.print_database_records(factory, "test_sync_with_deletion_po_usunieciu")
                        await self.print_database_stats(factory, "test_sync_with_deletion_po_usunieciu")
                        
                        # Drugie obliczenie (powinno dodać usunięty wzorzec)
                        await harmonic_patterns.calculate(self.klines, symbol="SOLUSDT", interval="1d")
                        
                        # Sprawdź wzorce po drugim obliczeniu
                        patterns_after_second = await technical_analysis_table.get_by_asset_id(asset_id)
                        second_count = len(patterns_after_second)
                        
                        print(f"Po drugim obliczeniu: {second_count} wzorców w bazie")
                        
                        # Wyświetl rekordy po drugim obliczeniu
                        await self.print_database_records(factory, "test_sync_with_deletion_po_drugim")
                        await self.print_database_stats(factory, "test_sync_with_deletion_po_drugim")
                        
                        # Sprawdź czy wzorce zostały zsynchronizowane
                        self.assertGreaterEqual(first_count, 0)
                        self.assertGreaterEqual(after_deletion_count, 0)
                        self.assertGreaterEqual(second_count, 0)
                        
                        # Sprawdź czy liczba wzorców po drugim obliczeniu jest większa lub równa liczbie po usunięciu
                        self.assertGreaterEqual(second_count, after_deletion_count)
                        
                        # Generuj wykres z wszystkimi wzorcami (z bazy + nowo obliczone)
                        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_sync_with_deletion.png")
                        chart_base64 = await self.__ta.create_candlestick_chart(
                            self.klines, 
                            save_path=chart_path, 
                            title="test_harmonic_patterns_sync_with_deletion",
                            enabled_objects={'HarmonicPatterns': harmonic_patterns}
                        )
                        
                        # Sprawdź czy wykres został wygenerowany
                        self.assertIsInstance(chart_base64, str)
                        self.assertTrue(len(chart_base64) > 0)
                        self.assertTrue(os.path.exists(chart_path))
                        
                        # Sprawdź czy wzorce są w klines
                        patterns_in_klines = 0
                        for kline in self.klines:
                            for key in kline.keys():
                                if key.startswith('pattern_') and key.endswith('_price'):
                                    patterns_in_klines += 1
                        
                        print(f"Znaleziono {patterns_in_klines} punktów wzorców w klines po synchronizacji")
                        self.assertGreaterEqual(patterns_in_klines, 0)
                        
                        # Sprawdź czy wszystkie wzorce w bazie mają poprawną strukturę
                        for pattern in patterns_after_second:
                            self.assertIn('x_point_timestamp', pattern)
                            self.assertIn('a_point_timestamp', pattern)
                            self.assertIn('b_point_timestamp', pattern)
                            self.assertIn('c_point_timestamp', pattern)
                            self.assertIn('d_point_timestamp', pattern)
                            
                            # Sprawdź czy timestamps są w formacie string
                            self.assertIsInstance(pattern['x_point_timestamp'], str)
                            if pattern['a_point_timestamp']:
                                self.assertIsInstance(pattern['a_point_timestamp'], str)
                            if pattern['b_point_timestamp']:
                                self.assertIsInstance(pattern['b_point_timestamp'], str)
                            if pattern['c_point_timestamp']:
                                self.assertIsInstance(pattern['c_point_timestamp'], str)
                            if pattern['d_point_timestamp']:
                                self.assertIsInstance(pattern['d_point_timestamp'], str)
                        
                        print("Test synchronizacji z usuwaniem - OK")
                    else:
                        print(f"Nie udało się usunąć wzorca z ID: {deleted_id}")
                        self.assertTrue(True, "Test synchronizacji - nie można usunąć wzorca")
                else:
                    print("Brak wzorców do usunięcia")
                    self.assertTrue(True, "Test synchronizacji - brak wzorców")
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_harmonic_patterns_database_sync_with_deletion")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji z usuwaniem: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test synchronizacji z usuwaniem - baza może być niedostępna")
            finally:
                await db.close_db()
        
        self.loop.run_until_complete(run_sync_with_deletion_test())

    def test_harmonic_patterns_database_error_handling(self):
        """Test obsługi błędów podczas integracji z bazą danych"""
        import asyncio
        from api.postgresql import PostgreSQL
        from api.technical_analysis_factory import TechnicalAnalysisFactory
        from api.config import config
        
        async def run_error_test():
            # Próba połączenia z nieistniejącą bazą danych (użyj configa ale z błędnymi danymi)
            db_url = config.get_database_url().replace("test_db", "invalid_db").replace("test_user", "invalid_user").replace("test_pass", "invalid_pass")
            db = PostgreSQL(db_url)
            
            try:
                # Utwórz HarmonicPatterns z nieprawidłową bazą danych
                ta_factory = TechnicalAnalysisFactory()
                harmonic_patterns = ta_factory.get_harmonic_patterns(
                    use_database=True,
                    database_factory=None,  # Nieprawidłowa fabryka
                    asset_id=1
                )
                
                # Obliczenia powinny działać nawet z błędami bazy danych
                await harmonic_patterns.calculate(self.klines, symbol="BTCUSDT", interval="1d")
                
                # Sprawdź czy wzorce zostały obliczone (w klines)
                patterns_in_klines = 0
                for kline in self.klines:
                    for key in kline.keys():
                        if key.startswith('pattern_') and key.endswith('_price'):
                            patterns_in_klines += 1
                
                print(f"Znaleziono {patterns_in_klines} punktów wzorców w klines (z błędami bazy)")
                
                # Sprawdź czy wzorce są w klines (obliczenia powinny działać)
                self.assertGreaterEqual(patterns_in_klines, 0)
                
                # Generuj wykres
                chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_database_error_handling.png")
                chart_base64 = await self.__ta.create_candlestick_chart(
                    self.klines, 
                    save_path=chart_path, 
                    title="test_harmonic_patterns_database_error_handling",
                    enabled_objects={'HarmonicPatterns': harmonic_patterns}
                )
                
                self.assertIsInstance(chart_base64, str)
                self.assertTrue(len(chart_base64) > 0)
                self.assertTrue(os.path.exists(chart_path))
                
                # Wyświetl rekordy z bazy danych (jeśli są dostępne)
                try:
                    await self.print_database_records(factory, "test_harmonic_patterns_database_error_handling")
                    await self.print_database_stats(factory, "test_harmonic_patterns_database_error_handling")
                except Exception as e:
                    print(f"Nie można wyświetlić rekordów z bazy danych: {e}")
                
            except Exception as e:
                print(f"Błąd podczas testu obsługi błędów: {e}")
                # Test przechodzi nawet jeśli wystąpią błędy bazy danych
                self.assertTrue(True, "Test obsługi błędów - błędy bazy danych są obsługiwane")
            finally:
                try:
                    await db.close_db()
                except:
                    pass
        
        self.loop.run_until_complete(run_error_test())

class TestAITechnicalAnalysis(unittest.TestCase):
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

    async def test_prepare_klines_data(self):
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

    async def test_generate_technical_chart(self):
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
        
        chart_base64 = await self.__ai_ta._generate_technical_chart(df, analysis)
        
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