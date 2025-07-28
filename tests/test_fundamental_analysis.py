import os
import unittest
import asyncio
import traceback
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

from src.fundamental_analysis import FundamentalAnalysis
from src.api.news_services.crypto_panic import CryptoPanicService
from src.api.exchanges.binance import BinanceAPI
from src.db.postgresql import DatabasePostgreSQL
from src.config import config


class TestFundamentalAnalysis(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Inicjalizacja bazy danych
        self.db = DatabasePostgreSQL(config.get_test_database_url())
        
        # Usuń tabele w setUp (synchronizacja)
        self.loop.run_until_complete(self.db.drop_all_tables())

        # pobierz konfigurację API
        self.binance_config = config.binance_config
        self.crypto_panic_config = config.crypto_panic_config
        
        # Inicjalizacja Binance API (test mode)
        self.binance_api = BinanceAPI(
            api_key=self.binance_config['api_key'],
            api_secret=self.binance_config['api_secret']
        )
        
        # Inicjalizacja FundamentalAnalysis
        self.fundamental_analysis = FundamentalAnalysis(test_mode=True)
        
        # Dodaj giełdę
        self.fundamental_analysis.add_exchange(self.binance_api)
        
        # Inicjalizacja CryptoPanic Service
        self.crypto_panic_service = CryptoPanicService(
            api_key=self.crypto_panic_config['api_key'],
            currencies=['BTC', 'ETH'],  # Konkretne waluty
            public=True,
            filter='hot',
            size=10,  # Mała liczba dla testów
            test_mode=True
        )
        
        # Dodaj serwis wiadomości
        self.fundamental_analysis.add_news_service(self.crypto_panic_service)

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
            fundamental_analysis_table = factory.get_fundamental_analysis_table()
            
            # Lista assets
            assets = await assets_table.get_all()
            print(f"\n=== {test_name} - ASSETS TABLE ===")
            if assets:
                for asset in assets:
                    print(f"ID: {asset['id']}, Asset: {asset['asset']}, Quote: {asset['quote']}")
            else:
                print("Brak rekordów w tabeli assets")
            
            # Lista fundamental_analysis
            fundamental_analysis = await fundamental_analysis_table.get_all()
            print(f"\n=== {test_name} - FUNDAMENTAL_ANALYSIS TABLE ===")
            if fundamental_analysis:
                for record in fundamental_analysis:
                    # Skróć JSON do max 50 znaków
                    content_str = str(record['content'])
                    if len(content_str) > 50:
                        content_str = content_str[:47] + "..."
                    
                    # Konwertuj timestamps z int na czytelny format
                    def format_timestamp(ts):
                        if ts is None:
                            return "None"
                        try:
                            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            return str(ts)
                    
                    print(f"ID: {record['id']}, Asset_IDs: {record['asset_ids']}, "
                          f"Timestamp: {format_timestamp(record['timestamp'])}, "
                          f"Service: {record['service']}, Link: {record['link']}, "
                          f"Content: {content_str}")
            else:
                print("Brak rekordów w tabeli fundamental_analysis")
            
            print(f"=== KONIEC {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas listowania rekordów z bazy danych: {e}")
    
    async def cleanup_database(self, factory, test_name: str):
        """Metoda pomocnicza do czyszczenia bazy danych"""
        try:
            assets_table = factory.get_assets_table()
            fundamental_analysis_table = factory.get_fundamental_analysis_table()
            
            # Usuń wszystkie rekordy
            await fundamental_analysis_table.delete_all()
            await assets_table.delete_all()
            
            print(f"Wyczyszczono bazę danych dla testu: {test_name}")
            
        except Exception as e:
            print(f"Błąd podczas czyszczenia bazy danych: {e}")
    
    def test_fundamental_analysis_basic_sync(self):
        """Test podstawowej synchronizacji z FundamentalAnalysis"""
        
        async def run_basic_sync_test():
            try:
                # Inicjalizuj bazę danych
                await self.db.init_db()
                factory = self.db.get_factory()
                
                print("=== TEST: Podstawowa synchronizacja z FundamentalAnalysis ===")
                
                # Wyczyść bazę danych przed testem
                await self.cleanup_database(factory, "basic_sync")
                
                # Wykonaj synchronizację
                results = await self.fundamental_analysis.sync_all_services(limit=10)
                
                print(f"Wyniki synchronizacji: {results}")
                
                # Sprawdź wyniki
                self.assertIsInstance(results, dict)
                self.assertIn('CRYPTO_PANIC', results)
                
                # Wyświetl rekordy z bazy danych
                await self.print_database_records(factory, "basic_sync")
                
                # Sprawdź czy zostały zapisane wiadomości
                fundamental_analysis_table = factory.get_fundamental_analysis_table()
                records = await fundamental_analysis_table.get_all()
                
                print(f"Liczba zapisanych rekordów: {len(records)}")
                
                # Sprawdź czy zostały dodane assety
                assets_table = factory.get_assets_table()
                assets = await assets_table.get_all()
                
                print(f"Liczba assetów w bazie: {len(assets)}")
                
                # Podstawowe asercje
                self.assertIsInstance(results['CRYPTO_PANIC'], list)
                
                print("=== TEST ZAKOŃCZONY SUKCESEM ===\n")
                
            except Exception as e:
                print(f"Błąd podczas testu: {e}")
                traceback.print_exc()
                raise
        
        self.loop.run_until_complete(run_basic_sync_test())
    
    def test_fundamental_analysis_single_service_sync(self):
        """Test synchronizacji pojedynczego serwisu"""
        
        async def run_single_service_test():
            try:
                # Inicjalizuj bazę danych
                await self.db.init_db()
                factory = self.db.get_factory()
                
                print("=== TEST: Synchronizacja pojedynczego serwisu ===")
                
                # Wyczyść bazę danych przed testem
                await self.cleanup_database(factory, "single_service")
                
                # Wykonaj synchronizację pojedynczego serwisu
                results = await self.fundamental_analysis.sync_single_service(
                    service=self.crypto_panic_service,
                    limit=5
                )
                
                print(f"Wyniki synchronizacji pojedynczego serwisu: {results}")
                
                # Sprawdź wyniki
                self.assertIsInstance(results, list)
                
                # Wyświetl rekordy z bazy danych
                await self.print_database_records(factory, "single_service")
                
                print("=== TEST ZAKOŃCZONY SUKCESEM ===\n")
                
            except Exception as e:
                print(f"Błąd podczas testu: {e}")
                traceback.print_exc()
                raise
        
        self.loop.run_until_complete(run_single_service_test())
    
    def test_fundamental_analysis_multiple_services(self):
        """Test z wieloma serwisami wiadomości"""
        
        async def run_multiple_services_test():
            try:
                # Inicjalizuj bazę danych
                await self.db.init_db()
                factory = self.db.get_factory()
                
                print("=== TEST: Wiele serwisów wiadomości ===")
                
                # Wyczyść bazę danych przed testem
                await self.cleanup_database(factory, "multiple_services")
                
                # Dodaj drugi serwis CryptoPanic z innymi parametrami
                crypto_panic_rising = CryptoPanicService(
                    api_key=self.crypto_panic_config['api_key'],
                    currencies=['BTC', 'ETH'],
                    public=True,
                    filter='rising',  # Inny filtr
                    size=5,
                    test_mode=True
                )
                
                self.fundamental_analysis.add_news_service(crypto_panic_rising)
                
                # Wykonaj synchronizację wszystkich serwisów
                results = await self.fundamental_analysis.sync_all_services(limit=10)
                
                print(f"Wyniki synchronizacji wielu serwisów: {results}")
                
                # Sprawdź wyniki
                self.assertIsInstance(results, dict)
                self.assertIn('CRYPTO_PANIC', results)
                
                # Wyświetl rekordy z bazy danych
                await self.print_database_records(factory, "multiple_services")
                
                print("=== TEST ZAKOŃCZONY SUKCESEM ===\n")
                
            except Exception as e:
                print(f"Błąd podczas testu: {e}")
                traceback.print_exc()
                raise
        
        self.loop.run_until_complete(run_multiple_services_test())
    
    def test_fundamental_analysis_asset_creation(self):
        """Test tworzenia assetów z giełd"""
        
        async def run_asset_creation_test():
            try:
                # Inicjalizuj bazę danych
                await self.db.init_db()
                factory = self.db.get_factory()
                
                print("=== TEST: Tworzenie assetów z giełd ===")
                
                # Wyczyść bazę danych przed testem
                await self.cleanup_database(factory, "asset_creation")
                
                # Sprawdź początkową liczbę assetów
                assets_table = factory.get_assets_table()
                initial_assets = await assets_table.get_all()
                print(f"Początkowa liczba assetów: {len(initial_assets)}")
                
                # Wykonaj synchronizację
                results = await self.fundamental_analysis.sync_all_services(limit=10)
                
                # Sprawdź końcową liczbę assetów
                final_assets = await assets_table.get_all()
                print(f"Końcowa liczba assetów: {len(final_assets)}")
                
                # Wyświetl nowe assety
                if len(final_assets) > len(initial_assets):
                    new_assets = final_assets[len(initial_assets):]
                    print("Nowe assety:")
                    for asset in new_assets:
                        print(f"  - {asset['asset']}/{asset['quote']} (ID: {asset['id']})")
                
                # Wyświetl rekordy z bazy danych
                await self.print_database_records(factory, "asset_creation")
                
                print("=== TEST ZAKOŃCZONY SUKCESEM ===\n")
                
            except Exception as e:
                print(f"Błąd podczas testu: {e}")
                traceback.print_exc()
                raise
        
        self.loop.run_until_complete(run_asset_creation_test())


if __name__ == "__main__":
    unittest.main() 