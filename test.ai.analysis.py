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
    
    # interval = "1d"
    # start_time = int(datetime(2022, 1, 1).timestamp() * 1000)
    # end_time = int(datetime(2025, 7, 1).timestamp() * 1000)

    # interval = "4h"
    # start_time = int(datetime(2022, 6, 1).timestamp() * 1000)
    # end_time = int(datetime(2022, 9, 1).timestamp() * 1000)

    # interval = "4h"
    # start_time = int(datetime(2022, 3, 1).timestamp() * 1000)
    # end_time = int(datetime(2022, 6, 1).timestamp() * 1000)

    interval = "4h"
    start_time = int(datetime(2021, 1, 1).timestamp() * 1000)
    end_time = int(datetime(2021, 4, 1).timestamp() * 1000)

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

    def test_calculate_harmonic_patterns_basic(self):
        """Test obliczania wzorców harmonicznych - podstawowy"""
        # Obliczenie wzorców harmonicznych (teraz zwraca liczbę wzorców i modyfikuje klines)
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie i zapisywanie wykresu (wzorce są już w klines)
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_basic.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Test Harmonic Patterns Basic - BTC/USDT 1W"
        )
        
        # Sprawdź czy zwrócono liczbę wzorców
        self.assertIsInstance(patterns_count, int)
        self.assertGreaterEqual(patterns_count, 0)
        
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
        
        if patterns_count > 0:
            self.assertTrue(len(pattern_keys) > 0, "Punkty wzorców powinny być dodane do klines")
            
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
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych - basic")

    def test_calculate_harmonic_patterns_no_show(self):
        """Test obliczania wzorców harmonicznych - wszystkie show na False"""
        # Obliczenie wzorców harmonicznych
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie wykresu z wszystkimi show na False
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_no_show.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Test Harmonic Patterns No Show - BTC/USDT 1W",
            show_fibonacci=False,
            show_all_fibo_targets=False,
            show_all_fibonacci_levels=False,
            show_all_retracement_levels=False,
            show_all_extension_levels=False,
            show_patterns=False,
            show_rsi=False,
            show_macd=False,
            show_obv=False
        )
        
        # Sprawdź czy zwrócono liczbę wzorców
        self.assertIsInstance(patterns_count, int)
        self.assertGreaterEqual(patterns_count, 0)
        
        # Sprawdź czy wykres został wygenerowany (powinien być tylko wykres świecowy)
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych - no show (tylko świece)")

    def test_calculate_harmonic_patterns_targets_only(self):
        """Test obliczania wzorców harmonicznych - tylko targety PRZ/TP/SL"""
        # Obliczenie wzorców harmonicznych
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie wykresu z tylko targetami
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_targets_only.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Test Harmonic Patterns Targets Only - BTC/USDT 1W",
            show_fibonacci=False,
            show_all_fibo_targets=True,
            show_all_fibonacci_levels=False,
            show_all_retracement_levels=False,
            show_all_extension_levels=False,
            show_patterns=True,  # Wzorce muszą być widoczne żeby targety miały sens
            show_rsi=False,
            show_macd=False,
            show_obv=False
        )
        
        # Sprawdź czy zwrócono liczbę wzorców
        self.assertIsInstance(patterns_count, int)
        self.assertGreaterEqual(patterns_count, 0)
        
        # Sprawdź czy wykres został wygenerowany
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych - targets only")

    def test_calculate_harmonic_patterns_fibonacci_levels(self):
        """Test obliczania wzorców harmonicznych - poziomy Fibonacci dla par punktów"""
        # Obliczenie wzorców harmonicznych
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie wykresu z poziomami Fibonacci dla par punktów
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_fibonacci_levels.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Test Harmonic Patterns Fibonacci Levels - BTC/USDT 1W",
            show_fibonacci=False,
            show_all_fibo_targets=False,
            show_all_fibonacci_levels=True,
            show_all_retracement_levels=True,
            show_all_extension_levels=True,
            show_patterns=True,  # Wzorce muszą być widoczne
            show_rsi=False,
            show_macd=False,
            show_obv=False
        )
        
        # Sprawdź czy zwrócono liczbę wzorców
        self.assertIsInstance(patterns_count, int)
        self.assertGreaterEqual(patterns_count, 0)
        
        # Sprawdź czy wykres został wygenerowany
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych - fibonacci levels")

    def test_calculate_harmonic_patterns_forming(self):
        """Test obliczania wzorców harmonicznych w trakcie formowania się"""
        # Obliczenie wzorców w trakcie formowania (teraz zwraca liczbę wzorców i modyfikuje klines)
        forming_patterns_count = self.__ta.calculate_harmonic_patterns_forming(self.klines)
        
        # Generowanie i zapisywanie wykresu (wzorce forming są już w klines)
        chart_path = os.path.join(self.test_charts_dir, "test_calculate_harmonic_patterns_forming.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Test Forming Harmonic Patterns - BTC/USDT 1W"
        )
        
        # Sprawdź czy zwrócono liczbę wzorców
        self.assertIsInstance(forming_patterns_count, int)
        self.assertGreaterEqual(forming_patterns_count, 0)
        
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
        
        if forming_patterns_count > 0:
            self.assertTrue(len(forming_pattern_keys) > 0, "Punkty forming wzorców powinny być dodane do klines")
            
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
        
        print(f"Znaleziono {forming_patterns_count} wzorców forming")

    def test_harmonic_patterns_visualization(self):
        """Test wizualizacji wzorców harmonicznych na wykresie"""
        # Obliczenie wszystkich typów wzorców (teraz modyfikują klines)
        formed_patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        forming_patterns_count = self.__ta.calculate_harmonic_patterns_forming(self.klines)
        
        # Wyświetl informacje o wzorcach
        print(f"Znaleziono {formed_patterns_count} uformowanych wzorców")
        print(f"Znaleziono {forming_patterns_count} wzorców w trakcie formowania")
        
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
        
        # Generowanie wykresu z wszystkimi wzorcami (które są już w klines)
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_visualization.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Harmonic Patterns Visualization - BTC/USDT 1W"
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
        total_patterns = formed_patterns_count + forming_patterns_count
        self.assertGreaterEqual(total_patterns, 0)

    def test_harmonic_patterns_with_indicators_basic(self):
        """Test wzorców harmonicznych z wskaźnikami technicznymi - podstawowy"""
        # Obliczenie wskaźników technicznych
        rsi_values = self.__ta.calculate_rsi(self.klines)
        macd_data = self.__ta.calculate_macd(self.klines)
        obv_values = self.__ta.calculate_obv(self.klines)
        
        # Dodanie wskaźników do danych
        for i, rsi in enumerate(rsi_values):
            self.klines[-(len(rsi_values)-i)]['rsi'] = rsi
        
        for i in range(len(macd_data['macd_line'])):
            idx = -(len(macd_data['macd_line'])-i)
            self.klines[idx]['macd'] = macd_data['macd_line'][i]
            self.klines[idx]['signal'] = macd_data['signal_line'][i]
            self.klines[idx]['histogram'] = macd_data['histogram'][i]
        
        for i, obv in enumerate(obv_values):
            self.klines[i]['obv'] = obv
        
        # Obliczenie wzorców harmonicznych (modyfikuje klines)
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie kompleksowego wykresu
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_basic.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Harmonic Patterns + Technical Indicators Basic - BTC/USDT 1W"
        )
        
        # Sprawdź czy wykres został wygenerowany
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        # Sprawdź czy wskaźniki zostały obliczone
        self.assertTrue(len(rsi_values) > 0)
        self.assertTrue(len(macd_data['macd_line']) > 0)
        self.assertTrue(len(obv_values) > 0)
        
        # Sprawdź czy wzorce zostały obliczone
        self.assertIsInstance(patterns_count, int)
        self.assertGreaterEqual(patterns_count, 0)
        print(f"Znaleziono {patterns_count} wzorców harmonicznych z wskaźnikami technicznymi - basic")
        
        # Sprawdź czy wzorce i wskaźniki są razem w klines
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
        if patterns_count > 0:
            self.assertTrue(patterns_found, "Wzorce harmoniczne powinny być w klines")

    def test_harmonic_patterns_with_indicators_no_show(self):
        """Test wzorców harmonicznych z wskaźnikami - tylko wskaźniki, bez wzorców"""
        # Obliczenie wskaźników technicznych
        rsi_values = self.__ta.calculate_rsi(self.klines)
        macd_data = self.__ta.calculate_macd(self.klines)
        obv_values = self.__ta.calculate_obv(self.klines)
        
        # Dodanie wskaźników do danych
        for i, rsi in enumerate(rsi_values):
            self.klines[-(len(rsi_values)-i)]['rsi'] = rsi
        
        for i in range(len(macd_data['macd_line'])):
            idx = -(len(macd_data['macd_line'])-i)
            self.klines[idx]['macd'] = macd_data['macd_line'][i]
            self.klines[idx]['signal'] = macd_data['signal_line'][i]
            self.klines[idx]['histogram'] = macd_data['histogram'][i]
        
        for i, obv in enumerate(obv_values):
            self.klines[i]['obv'] = obv
        
        # Obliczenie wzorców harmonicznych (modyfikuje klines)
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie wykresu z tylko wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_no_show.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Harmonic Patterns + Indicators No Show - BTC/USDT 1W",
            show_fibonacci=False,
            show_all_fibo_targets=False,
            show_all_fibonacci_levels=False,
            show_all_retracement_levels=False,
            show_all_extension_levels=False,
            show_patterns=False,  # Wzorce ukryte
            show_rsi=True,       # Wskaźniki włączone
            show_macd=True,
            show_obv=True
        )
        
        # Sprawdź czy wykres został wygenerowany
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych z wskaźnikami - no show patterns")

    def test_harmonic_patterns_with_indicators_targets_only(self):
        """Test wzorców harmonicznych z wskaźnikami - tylko targety PRZ/TP/SL"""
        # Obliczenie wskaźników technicznych
        rsi_values = self.__ta.calculate_rsi(self.klines)
        macd_data = self.__ta.calculate_macd(self.klines)
        obv_values = self.__ta.calculate_obv(self.klines)
        
        # Dodanie wskaźników do danych
        for i, rsi in enumerate(rsi_values):
            self.klines[-(len(rsi_values)-i)]['rsi'] = rsi
        
        for i in range(len(macd_data['macd_line'])):
            idx = -(len(macd_data['macd_line'])-i)
            self.klines[idx]['macd'] = macd_data['macd_line'][i]
            self.klines[idx]['signal'] = macd_data['signal_line'][i]
            self.klines[idx]['histogram'] = macd_data['histogram'][i]
        
        for i, obv in enumerate(obv_values):
            self.klines[i]['obv'] = obv
        
        # Obliczenie wzorców harmonicznych (modyfikuje klines)
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie wykresu z targetami i wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_targets_only.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Harmonic Patterns + Indicators Targets Only - BTC/USDT 1W",
            show_fibonacci=False,
            show_all_fibo_targets=True,  # Tylko targety
            show_all_fibonacci_levels=False,
            show_all_retracement_levels=False,
            show_all_extension_levels=False,
            show_patterns=True,  # Wzorce muszą być widoczne żeby targety miały sens
            show_rsi=True,       # Wskaźniki włączone
            show_macd=True,
            show_obv=True
        )
        
        # Sprawdź czy wykres został wygenerowany
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych z wskaźnikami - targets only")

    def test_harmonic_patterns_with_indicators_fibonacci_levels(self):
        """Test wzorców harmonicznych z wskaźnikami - poziomy Fibonacci dla par punktów"""
        # Obliczenie wskaźników technicznych
        rsi_values = self.__ta.calculate_rsi(self.klines)
        macd_data = self.__ta.calculate_macd(self.klines)
        obv_values = self.__ta.calculate_obv(self.klines)
        
        # Dodanie wskaźników do danych
        for i, rsi in enumerate(rsi_values):
            self.klines[-(len(rsi_values)-i)]['rsi'] = rsi
        
        for i in range(len(macd_data['macd_line'])):
            idx = -(len(macd_data['macd_line'])-i)
            self.klines[idx]['macd'] = macd_data['macd_line'][i]
            self.klines[idx]['signal'] = macd_data['signal_line'][i]
            self.klines[idx]['histogram'] = macd_data['histogram'][i]
        
        for i, obv in enumerate(obv_values):
            self.klines[i]['obv'] = obv
        
        # Obliczenie wzorców harmonicznych (modyfikuje klines)
        patterns_count = self.__ta.calculate_harmonic_patterns(self.klines)
        
        # Generowanie wykresu z poziomami Fibonacci i wskaźnikami
        chart_path = os.path.join(self.test_charts_dir, "test_harmonic_patterns_with_indicators_fibonacci_levels.png")
        chart_base64 = self.__ta.create_candlestick_chart(
            self.klines, 
            save_path=chart_path, 
            title="Harmonic Patterns + Indicators Fibonacci Levels - BTC/USDT 1W",
            show_fibonacci=False,
            show_all_fibo_targets=False,
            show_all_fibonacci_levels=True,  # Poziomy Fibonacci dla par punktów
            show_all_retracement_levels=True,
            show_all_extension_levels=True,
            show_patterns=True,  # Wzorce muszą być widoczne
            show_rsi=True,       # Wskaźniki włączone
            show_macd=True,
            show_obv=True
        )
        
        # Sprawdź czy wykres został wygenerowany
        self.assertIsInstance(chart_base64, str)
        self.assertTrue(len(chart_base64) > 0)
        self.assertTrue(os.path.exists(chart_path))
        
        print(f"Znaleziono {patterns_count} wzorców harmonicznych z wskaźnikami - fibonacci levels")

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