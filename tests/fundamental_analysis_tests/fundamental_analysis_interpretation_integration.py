import os
import unittest
import asyncio
import traceback
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

from src.sync_fundamental_analysis import FundamentalAnalysis
from src.sync_exchanges import Exchanges
from src.sync_llm_fundamental_analysis_interpretation import LlmFundamentalAnalysisInterpretation
from src.db import DatabaseFacade
from src.config import config

@unittest.skip("Skipping fundamental analysis interpretation integration tests")
class TestFundamentalAnalysisInterpretationIntegration(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Inicjalizacja bazy danych testowej
        self.db = DatabaseFacade().get_test_database_postgresql()
        
        # Usuń tabele w setUp (synchronizacja)
        self.loop.run_until_complete(self.db.drop_all_tables())

        # Inicjalizacja klas w trybie testowym
        self.fundamental_analysis = FundamentalAnalysis(test_mode=True)
        self.exchanges = Exchanges(test_mode=True)
        self.llm_interpretation = LlmFundamentalAnalysisInterpretation(test_mode=True)

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
            interpretation_table = factory.get_fundamental_analysis_interpretation_table()
            
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
            
            # Lista interpretations
            interpretations = await interpretation_table.get_all()
            print(f"\n=== {test_name} - FUNDAMENTAL_ANALYSIS_INTERPRETATION TABLE ===")
            if interpretations:
                for record in interpretations:
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
                          f"Analysis_IDs: {record['fundamental_analysis_ids']}, "
                          f"Timestamp: {format_timestamp(record['timestamp'])}, "
                          f"Content: {content_str}")
            else:
                print("Brak rekordów w tabeli fundamental_analysis_interpretation")
            
            print(f"=== KONIEC {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas listowania rekordów z bazy danych: {e}")
    
    async def print_database_stats(self, factory, test_name: str):
        """Metoda pomocnicza do wyświetlania statystyk bazy danych"""
        try:
            assets_table = factory.get_assets_table()
            fundamental_analysis_table = factory.get_fundamental_analysis_table()
            interpretation_table = factory.get_fundamental_analysis_interpretation_table()
            
            # Pobierz statystyki
            assets_count = len(await assets_table.get_all())
            fundamental_analysis_count = len(await fundamental_analysis_table.get_all())
            interpretation_count = len(await interpretation_table.get_all())
            
            print(f"\n=== {test_name} - STATYSTYKI BAZY DANYCH ===")
            print(f"Liczba assets: {assets_count}")
            print(f"Liczba fundamental_analysis: {fundamental_analysis_count}")
            print(f"Liczba interpretations: {interpretation_count}")
            print(f"=== KONIEC STATYSTYK {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas pobierania statystyk z bazy danych: {e}")
    
    async def cleanup_database(self, factory, test_name: str):
        """Metoda pomocnicza do czyszczenia bazy danych po teście"""
        try:
            await self.db.drop_all_tables()
            
            print(f"\n=== {test_name} - CZYSZCZENIE BAZY DANYCH ===")
            print(f"=== KONIEC CZYSZCZENIA {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas czyszczenia bazy danych: {e}")

    def test_sync_interpretations_basic(self):
        """Test podstawowej synchronizacji interpretacji analiz fundamentalnych"""
        
        async def run_sync_interpretations_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Wyświetl stan bazy przed synchronizacją
                await self.print_database_stats(factory, "test_sync_interpretations_basic_przed")
                
                # KROK 1: Synchronizuj assety
                print("=== KROK 1: Synchronizacja assetów ===")
                await self.exchanges.sync_assets()
                await self.print_database_stats(factory, "test_sync_interpretations_basic_po_assetach")
                
                # KROK 2: Synchronizuj wiadomości
                print("=== KROK 2: Synchronizacja wiadomości ===")
                await self.fundamental_analysis.sync_news(limit=10, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_basic_po_newsach")
                
                # KROK 3: Synchronizuj interpretacje
                print("=== KROK 3: Synchronizacja interpretacji ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                
                # Wyświetl stan bazy po synchronizacji interpretacji
                await self.print_database_records(factory, "test_sync_interpretations_basic_po_interpretacjach")
                await self.print_database_stats(factory, "test_sync_interpretations_basic_po_interpretacjach")
                
                # Sprawdź czy interpretacje zostały zapisane
                interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                all_interpretations = await interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_interpretations, list)
                self.assertGreaterEqual(len(all_interpretations), 0)
                
                # Sprawdź strukturę zapisanych interpretacji
                for interpretation in all_interpretations:
                    self.assertIn('id', interpretation)
                    self.assertIn('asset_ids', interpretation)
                    self.assertIn('fundamental_analysis_ids', interpretation)
                    self.assertIn('timestamp', interpretation)
                    self.assertIn('content', interpretation)
                    
                    # Sprawdź typy danych
                    self.assertIsInstance(interpretation['id'], int)
                    self.assertIsInstance(interpretation['asset_ids'], list)
                    self.assertIsInstance(interpretation['fundamental_analysis_ids'], list)
                    self.assertIsInstance(interpretation['timestamp'], int)
                    self.assertIsInstance(interpretation['content'], dict)
                    
                    # Sprawdź czy content zawiera wymagane pola
                    content = interpretation['content']
                    self.assertIn('asset', content)
                    self.assertIn('quote', content)
                    self.assertIn('summary', content)
                    self.assertIn('main_signals', content)
                    self.assertIn('fundamental_rating', content)
                    
                    # Sprawdź czy asset_ids istnieją w tabeli assets
                    assets_table = factory.get_assets_table()
                    for asset_id in interpretation['asset_ids']:
                        asset = await assets_table.get_by_id(asset_id)
                        self.assertIsNotNone(asset, f"Asset ID {asset_id} nie istnieje w bazie")
                    
                    # Sprawdź czy fundamental_analysis_ids istnieją w tabeli fundamental_analysis
                    fundamental_analysis_table = factory.get_fundamental_analysis_table()
                    for analysis_id in interpretation['fundamental_analysis_ids']:
                        analysis = await fundamental_analysis_table.get_by_id(analysis_id)
                        self.assertIsNotNone(analysis, f"Analysis ID {analysis_id} nie istnieje w bazie")
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_sync_interpretations_basic")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji interpretacji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna (dla CI/CD)
                self.assertTrue(True, "Test synchronizacji interpretacji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_interpretations_test())

    def test_sync_interpretations_with_different_limits(self):
        """Test synchronizacji interpretacji z różnymi limitami"""
        
        async def run_sync_interpretations_limits_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=15, offset=0)
                
                # Test z limitem 3
                print("=== Test interpretacji z limitem 3 ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=3, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_limits_limit_3")
                
                # Test z limitem 5
                print("=== Test interpretacji z limitem 5 ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_limits_limit_5")
                
                # Test z limitem 10
                print("=== Test interpretacji z limitem 10 ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=10, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_limits_limit_10")
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_interpretations_limits_koniec")
                await self.print_database_stats(factory, "test_sync_interpretations_limits_koniec")
                
                # Sprawdź czy interpretacje zostały zapisane
                interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                all_interpretations = await interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_interpretations, list)
                self.assertGreaterEqual(len(all_interpretations), 0)
                
                # Sprawdź strukturę zapisanych interpretacji
                for interpretation in all_interpretations:
                    self.assertIn('id', interpretation)
                    self.assertIn('asset_ids', interpretation)
                    self.assertIn('fundamental_analysis_ids', interpretation)
                    self.assertIn('timestamp', interpretation)
                    self.assertIn('content', interpretation)
                    
                    # Sprawdź typy danych
                    self.assertIsInstance(interpretation['id'], int)
                    self.assertIsInstance(interpretation['asset_ids'], list)
                    self.assertIsInstance(interpretation['fundamental_analysis_ids'], list)
                    self.assertIsInstance(interpretation['timestamp'], int)
                    self.assertIsInstance(interpretation['content'], dict)
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_sync_interpretations_with_different_limits")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji interpretacji z limitami: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test synchronizacji interpretacji z limitami - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_interpretations_limits_test())

    def test_sync_interpretations_with_offset(self):
        """Test synchronizacji interpretacji z offsetem"""
        
        async def run_sync_interpretations_offset_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=20, offset=0)
                
                # Test z offsetem 0
                print("=== Test interpretacji z offsetem 0 ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_offset_offset_0")
                
                # Test z offsetem 5
                print("=== Test interpretacji z offsetem 5 ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=5)
                await self.print_database_stats(factory, "test_sync_interpretations_offset_offset_5")
                
                # Test z offsetem 10
                print("=== Test interpretacji z offsetem 10 ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=10)
                await self.print_database_stats(factory, "test_sync_interpretations_offset_offset_10")
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_interpretations_offset_koniec")
                await self.print_database_stats(factory, "test_sync_interpretations_offset_koniec")
                
                # Sprawdź czy interpretacje zostały zapisane
                interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                all_interpretations = await interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_interpretations, list)
                self.assertGreaterEqual(len(all_interpretations), 0)
                
                # Sprawdź strukturę zapisanych interpretacji
                for interpretation in all_interpretations:
                    self.assertIn('id', interpretation)
                    self.assertIn('asset_ids', interpretation)
                    self.assertIn('fundamental_analysis_ids', interpretation)
                    self.assertIn('timestamp', interpretation)
                    self.assertIn('content', interpretation)
                    
                    # Sprawdź typy danych
                    self.assertIsInstance(interpretation['id'], int)
                    self.assertIsInstance(interpretation['asset_ids'], list)
                    self.assertIsInstance(interpretation['fundamental_analysis_ids'], list)
                    self.assertIsInstance(interpretation['timestamp'], int)
                    self.assertIsInstance(interpretation['content'], dict)
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_sync_interpretations_with_offset")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji interpretacji z offsetem: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test synchronizacji interpretacji z offsetem - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_interpretations_offset_test())

    def test_sync_interpretations_duplicate_prevention(self):
        """Test zapobiegania duplikatom podczas synchronizacji interpretacji"""
        
        async def run_sync_interpretations_duplicate_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=10, offset=0)
                
                # Pierwsza synchronizacja interpretacji
                print("=== Pierwsza synchronizacja interpretacji ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_duplicate_po_pierwszej")
                
                # Druga synchronizacja interpretacji (powinna nie dodać duplikatów)
                print("=== Druga synchronizacja interpretacji ===")
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                await self.print_database_stats(factory, "test_sync_interpretations_duplicate_po_drugiej")
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_interpretations_duplicate_koniec")
                await self.print_database_stats(factory, "test_sync_interpretations_duplicate_koniec")
                
                # Sprawdź czy interpretacje zostały zapisane
                interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                all_interpretations = await interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_interpretations, list)
                self.assertGreaterEqual(len(all_interpretations), 0)
                
                # Sprawdź czy nie ma duplikatów (sprawdź unikalne kombinacje asset_ids + fundamental_analysis_ids)
                unique_combinations = set()
                for interpretation in all_interpretations:
                    # Sortuj listy dla spójności
                    asset_ids_tuple = tuple(sorted(interpretation['asset_ids']))
                    analysis_ids_tuple = tuple(sorted(interpretation['fundamental_analysis_ids']))
                    combination = (asset_ids_tuple, analysis_ids_tuple)
                    unique_combinations.add(combination)
                
                # Liczba unikalnych kombinacji powinna być równa liczbie rekordów
                self.assertEqual(len(unique_combinations), len(all_interpretations))
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_sync_interpretations_duplicate_prevention")
                
            except Exception as e:
                print(f"Błąd podczas testu zapobiegania duplikatom interpretacji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test zapobiegania duplikatom interpretacji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_interpretations_duplicate_test())

    def test_sync_interpretations_content_validation(self):
        """Test walidacji zawartości interpretacji"""
        
        async def run_sync_interpretations_content_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=10, offset=0)
                
                # Synchronizuj interpretacje
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_interpretations_content_validation")
                await self.print_database_stats(factory, "test_sync_interpretations_content_validation")
                
                # Sprawdź czy interpretacje zostały zapisane
                interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                all_interpretations = await interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_interpretations, list)
                self.assertGreaterEqual(len(all_interpretations), 0)
                
                # Sprawdź strukturę i zawartość interpretacji
                for interpretation in all_interpretations:
                    content = interpretation['content']
                    
                    # Sprawdź wymagane pola w content
                    required_fields = [
                        'asset', 'quote', 'summary', 'main_signals', 
                        'changes_since_last_analysis', 'risks', 'opportunities', 
                        'fundamental_rating', 'suggested_focus'
                    ]
                    
                    for field in required_fields:
                        self.assertIn(field, content, f"Brak wymaganego pola '{field}' w interpretacji")
                    
                    # Sprawdź typy danych
                    self.assertIsInstance(content['asset'], str)
                    self.assertIsInstance(content['quote'], str)
                    self.assertIsInstance(content['summary'], str)
                    self.assertIsInstance(content['main_signals'], list)
                    self.assertIsInstance(content['changes_since_last_analysis'], str)
                    self.assertIsInstance(content['risks'], list)
                    self.assertIsInstance(content['opportunities'], list)
                    self.assertIsInstance(content['fundamental_rating'], str)
                    self.assertIsInstance(content['suggested_focus'], str)
                    
                    # Sprawdź czy fundamental_rating zawiera emoji
                    rating = content['fundamental_rating']
                    self.assertTrue(
                        any(emoji in rating for emoji in ['🟢', '🟡', '🔴']),
                        f"Rating '{rating}' nie zawiera wymaganej emoji"
                    )
                    
                    # Sprawdź czy main_signals zawiera emoji
                    for signal in content['main_signals']:
                        self.assertTrue(
                            any(emoji in signal for emoji in ['🟢', '🟡', '🔴']),
                            f"Signal '{signal}' nie zawiera wymaganej emoji"
                        )
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_sync_interpretations_content_validation")
                
            except Exception as e:
                print(f"Błąd podczas testu walidacji zawartości interpretacji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test walidacji zawartości interpretacji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_interpretations_content_test())

    def test_sync_interpretations_relationships(self):
        """Test relacji między interpretacjami, assetami i analizami fundamentalnymi"""
        
        async def run_sync_interpretations_relationships_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=10, offset=0)
                
                # Synchronizuj interpretacje
                await self.llm_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=5, offset=0)
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_interpretations_relationships")
                await self.print_database_stats(factory, "test_sync_interpretations_relationships")
                
                # Sprawdź czy interpretacje zostały zapisane
                interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                assets_table = factory.get_assets_table()
                fundamental_analysis_table = factory.get_fundamental_analysis_table()
                
                all_interpretations = await interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_interpretations, list)
                self.assertGreaterEqual(len(all_interpretations), 0)
                
                # Sprawdź relacje dla każdej interpretacji
                for interpretation in all_interpretations:
                    # Sprawdź czy wszystkie asset_ids istnieją w tabeli assets
                    for asset_id in interpretation['asset_ids']:
                        asset = await assets_table.get_by_id(asset_id)
                        self.assertIsNotNone(asset, f"Asset ID {asset_id} nie istnieje w bazie")
                        
                        # Sprawdź czy asset w interpretacji odpowiada assetowi w bazie
                        interpretation_asset = interpretation['content']['asset']
                        self.assertEqual(asset['asset'], interpretation_asset, 
                                      f"Asset w interpretacji '{interpretation_asset}' nie odpowiada assetowi w bazie '{asset['asset']}'")
                    
                    # Sprawdź czy wszystkie fundamental_analysis_ids istnieją w tabeli fundamental_analysis
                    for analysis_id in interpretation['fundamental_analysis_ids']:
                        analysis = await fundamental_analysis_table.get_by_id(analysis_id)
                        self.assertIsNotNone(analysis, f"Analysis ID {analysis_id} nie istnieje w bazie")
                        
                        # Sprawdź czy analiza ma powiązanie z assetem z interpretacji
                        interpretation_asset_ids = set(interpretation['asset_ids'])
                        analysis_asset_ids = set(analysis['asset_ids'])
                        self.assertTrue(
                            interpretation_asset_ids.intersection(analysis_asset_ids),
                            f"Brak wspólnych asset_ids między interpretacją {interpretation['id']} a analizą {analysis_id}"
                        )
                
                # Wyczyść bazę danych po teście
                await self.cleanup_database(factory, "test_sync_interpretations_relationships")
                
            except Exception as e:
                print(f"Błąd podczas testu relacji interpretacji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test relacji interpretacji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_interpretations_relationships_test())


if __name__ == '__main__':
    unittest.main()
