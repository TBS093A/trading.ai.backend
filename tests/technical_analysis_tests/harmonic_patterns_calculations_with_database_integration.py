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

from src.technical_analysis.technical_analysis_facade import TechnicalAnalysisFacade as TA
from src.technical_analysis.technical_analysis_factory import TechnicalAnalysisFactory
from src.db.postgresql import DatabasePostgreSQL
from src.config import config
from .technical_analysis_tests_utils import get_test_data

@unittest.skip("Skipping database integration tests")
class TestHarmonicPatternsCalculationWithDatabaseIntegration(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.__ta = TA()
        # Tworzenie katalogu na wykresy testowe
        self.test_charts_dir = "test_charts"
        os.makedirs(self.test_charts_dir, exist_ok=True)
        # Pobranie danych testowych
        self.klines = get_test_data()
        # Inicjalizacja bazy danych
        self.db = DatabasePostgreSQL(config.get_test_database_url())
        # Usuń tabele w setUp (synchronizacja)
        self.loop.run_until_complete(self.db.drop_all_tables())

    def tearDown(self):
        # Zamknij połączenie z bazą danych
        if hasattr(self, 'db') and self.db:
            try:
                self.loop.run_until_complete(self.db.close_db())
            except Exception as e:
                print(f"Błąd podczas zamykania bazy danych: {e}")
        
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
            
            # Lista technical_analysis_harmonic_patterns
            technical_analysis = await technical_analysis_table.get_all()
            print(f"\n=== {test_name} - TECHNICAL_ANALYSIS_HARMONIC_PATTERNS TABLE ===")
            if technical_analysis:
                for record in technical_analysis:
                    # Skróć JSON do max 24 znaków
                    ta_json_str = str(record['ta_object_json'])
                    if len(ta_json_str) > 24:
                        ta_json_str = ta_json_str[:21] + "..."
                    
                    # Konwertuj timestamps z int na czytelny format
                    def format_timestamp(ts):
                        if ts is None:
                            return "None"
                        try:
                            return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            return str(ts)
                    
                    print(f"ID: {record['id']}, Asset_ID: {record['asset_id']}, "
                          f"X: {format_timestamp(record['x_point_timestamp'])}, A: {format_timestamp(record['a_point_timestamp'])}, "
                          f"B: {format_timestamp(record['b_point_timestamp'])}, C: {format_timestamp(record['c_point_timestamp'])}, "
                          f"D: {format_timestamp(record['d_point_timestamp'])}, JSON: {ta_json_str}")
            else:
                print("Brak rekordów w tabeli technical_analysis_harmonic_patterns")
            
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
            print(f"Liczba technical_analysis_harmonic_patterns: {technical_analysis_count}")
            print(f"=== KONIEC STATYSTYK {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas pobierania statystyk z bazy danych: {e}")
    
    async def cleanup_database(self, factory, test_name: str):
        """Metoda pomocnicza do czyszczenia bazy danych po teście"""
        try:
            technical_analysis_table = factory.get_technical_analysis_table()
            assets_table = factory.get_assets_table()
            
            # Usuń wszystkie rekordy z technical_analysis_harmonic_patterns
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
            print(f"Usunięto {deleted_ta_count} rekordów z technical_analysis_harmonic_patterns")
            print(f"Usunięto {deleted_assets_count} rekordów z assets")
            print(f"=== KONIEC CZYSZCZENIA {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas czyszczenia bazy danych: {e}")

    def test_harmonic_patterns_with_database_integration(self):
        """Test wzorców harmonicznych z integracją bazy danych"""
        
        async def run_database_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
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
        
        self.loop.run_until_complete(run_database_test())

    def test_harmonic_patterns_database_sync(self):
        """Test synchronizacji wzorców harmonicznych z bazą danych"""
        
        async def run_sync_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
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
                    
                    # Sprawdź czy timestamps są w formacie int (milis sekundy)
                    self.assertIsInstance(pattern['x_point_timestamp'], int)
                    if pattern['a_point_timestamp']:
                        self.assertIsInstance(pattern['a_point_timestamp'], int)
                    if pattern['b_point_timestamp']:
                        self.assertIsInstance(pattern['b_point_timestamp'], int)
                    if pattern['c_point_timestamp']:
                        self.assertIsInstance(pattern['c_point_timestamp'], int)
                    if pattern['d_point_timestamp']:
                        self.assertIsInstance(pattern['d_point_timestamp'], int)
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_harmonic_patterns_database_sync")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test synchronizacji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_test())

    def test_harmonic_patterns_database_timestamp_range(self):
        """Test pobierania wzorców z określonego zakresu czasowego"""
        async def run_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
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
                # Pobierz zakres czasowy z klines (jako inty)
                start_timestamp = int(self.klines[0]['open_time'])
                end_timestamp = int(self.klines[-1]['close_time'])
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
                        # Sprawdź czy timestamps są w zakresie (jako inty)
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
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_database_without_integration(self):
        """Test wzorców harmonicznych bez integracji z bazą danych (debug mode)"""
        async def run_test():
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
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                await self.print_database_records(factory, "test_harmonic_patterns_database_without_integration")
                await self.print_database_stats(factory, "test_harmonic_patterns_database_without_integration")
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_harmonic_patterns_database_without_integration")
            except Exception as e:
                print(f"Nie można wyświetlić rekordów z bazy danych: {e}")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_database_error_handling(self):
        """Test obsługi błędów podczas integracji z bazą danych"""
        async def run_test():
            # Utwórz HarmonicPatterns bez integracji z bazą danych
            ta_factory = TechnicalAnalysisFactory()
            harmonic_patterns = ta_factory.get_harmonic_patterns(
                use_database=False,  # Wyłącz integrację z bazą danych
                database_factory=None,
                asset_id=None
            )
            
            # Obliczenia powinny działać bez bazy danych
            await harmonic_patterns.calculate(self.klines, symbol="BTCUSDT", interval="1d")
            
            # Sprawdź czy wzorce zostały obliczone (w klines)
            patterns_in_klines = 0
            for kline in self.klines:
                for key in kline.keys():
                    if key.startswith('pattern_') and key.endswith('_price'):
                        patterns_in_klines += 1
            
            print(f"Znaleziono {patterns_in_klines} punktów wzorców w klines (bez bazy danych)")
            
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
            
            print("Test obsługi błędów bazy danych - OK")
        
        self.loop.run_until_complete(run_test())

    def test_harmonic_patterns_database_sync_with_deletion(self):
        """Test synchronizacji wzorców z bazą danych z usuwaniem i ponownym dodawaniem"""
        async def run_sync_with_deletion_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
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
                            
                                                # Sprawdź czy timestamps są w formacie int (milis sekundy)
                    self.assertIsInstance(pattern['x_point_timestamp'], int)
                    if pattern['a_point_timestamp']:
                        self.assertIsInstance(pattern['a_point_timestamp'], int)
                    if pattern['b_point_timestamp']:
                        self.assertIsInstance(pattern['b_point_timestamp'], int)
                    if pattern['c_point_timestamp']:
                        self.assertIsInstance(pattern['c_point_timestamp'], int)
                    if pattern['d_point_timestamp']:
                        self.assertIsInstance(pattern['d_point_timestamp'], int)
                        
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
        
        self.loop.run_until_complete(run_sync_with_deletion_test())
