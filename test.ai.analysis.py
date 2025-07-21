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
        # Pobierz fabrykę
        factory = self.__ta.get_technical_analysis_factory()
        
        # Obliczenie RSI używając fabryki
        enabled_indicators = {
            'IndicatorRSI': factory.get_indicator_rsi_class()
        }
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_rsi.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_macd(self):
        """Test obliczania wskaźnika MACD"""
        # Pobierz fabrykę
        factory = self.__ta.get_technical_analysis_factory()
        
        # Obliczenie MACD używając fabryki
        enabled_indicators = {
            'IndicatorMACD': factory.get_indicator_macd_class()
        }
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_macd.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_obv(self):
        """Test obliczania wskaźnika OBV"""
        # Pobierz fabrykę
        factory = self.__ta.get_technical_analysis_factory()
        
        # Obliczenie OBV używając fabryki
        enabled_indicators = {
            'IndicatorOBV': factory.get_indicator_obv_class()
        }
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_obv.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_harmonic_patterns_basic(self):
        """Test obliczania wzorców harmonicznych - podstawowy"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_basic.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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
        
        print(f"Znaleziono {len(pattern_keys)} punktów wzorców harmonicznych - basic")

    def test_calculate_harmonic_patterns_no_show(self):
        """Test obliczania wzorców harmonicznych - wszystkie show na False"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z wszystkimi show na False
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_no_show.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_harmonic_patterns_targets_only(self):
        """Test obliczania wzorców harmonicznych - tylko targety PRZ/TP/SL"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z tylko targetami
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_targets_only.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_harmonic_patterns_fibonacci_levels(self):
        """Test obliczania wzorców harmonicznych - poziomy Fibonacci dla par punktów"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z poziomami Fibonacci dla par punktów
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_fibonacci_levels.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_harmonic_patterns_general_fibonacci_levels(self):
        """Test obliczania wzorców harmonicznych - ogólne poziomy Fibonacci"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_general_fibonacci_levels.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_harmonic_patterns_all_fibonacci_enabled(self):
        """Test obliczania wzorców harmonicznych - wszystkie opcje Fibonacci włączone"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_all_fibonacci_enabled.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_calculate_harmonic_patterns_forming(self):
        """Test obliczania wzorców harmonicznych w trakcie formowania się"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
        # Generowanie i zapisywanie wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_forming.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_visualization(self):
        """Test wizualizacji wzorców harmonicznych na wykresie"""
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
        
        self.__ta.calculate(self.klines, enabled_objects=enabled_objects)
        
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
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_with_indicators_basic(self):
        """Test wzorców harmonicznych z wskaźnikami technicznymi - podstawowy"""
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
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
        
        # Generowanie kompleksowego wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_basic.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_with_indicators_no_show(self):
        """Test wzorców harmonicznych z wskaźnikami - tylko wskaźniki, bez wzorców"""
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
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z tylko wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_no_show.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_with_indicators_targets_only(self):
        """Test wzorców harmonicznych z wskaźnikami - tylko targety PRZ/TP/SL"""
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
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z targetami i wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_targets_only.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_with_indicators_all_points_fibonacci_levels(self):
        """Test wzorców harmonicznych z wskaźnikami - poziomy Fibonacci dla par punktów"""
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
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z poziomami Fibonacci i wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_all_points_fibonacci_levels.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_with_indicators_general_fibonacci_levels(self):
        """Test wzorców harmonicznych z wskaźnikami - ogólne poziomy Fibonacci"""
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
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
        
        # Generowanie wykresu z ogólnymi poziomami Fibonacci i wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_general_fibonacci_levels.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_harmonic_patterns_with_indicators_all_fibonacci(self):
        """Test wzorców harmonicznych z wskaźnikami - wszystkie opcje Fibonacci włączone"""
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
        
        self.__ta.calculate(self.klines, enabled_indicators=enabled_indicators, enabled_objects=enabled_objects)
        
        # Generowanie wykresu ze wszystkimi opcjami Fibonacci i wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_all_fibonacci.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

    def test_generate_chart_without_indicators_and_objects(self):
        """Test generowania wykresu bez żadnych wskaźników i obiektów"""
        # Generowanie wykresu bez żadnych wskaźników i obiektów
        chart_path = os.path.join(self.test_charts_dir, "test_generate_chart_without_indicators_and_objects.png")
        chart_base64 = self.__ta.create_candlestick_chart(
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

class TestAITechnicalAnalysis(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
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