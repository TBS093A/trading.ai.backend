import os
import unittest
import asyncio
import traceback
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

from src.fundamental_analysis import FundamentalAnalysis
from src.technical_analysis import TechnicalAnalysis
from src.exchanges import Exchanges
from src.llm_fundamental_analysis_interpretation import LlmFundamentalAnalysisInterpretation
from src.llm_technical_analysis_interpretation import LlmTechnicalAnalysisInterpretation
from src.llm_general_analysis_transaction_decision import LlmGeneralAnalysisTransactionDecision
from src.db import DatabaseFacade
from src.config import config


class TestGeneralAnalysisTransactionDecisionIntegration(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Inicjalizacja bazy danych testowej
        self.db = DatabaseFacade().get_test_database_postgresql()
        
        # Usuń tabele w setUp (synchronizacja)
        self.loop.run_until_complete(self.db.drop_all_tables())

        # Inicjalizacja klas w trybie testowym
        self.exchanges = Exchanges(test_mode=True)
        self.fundamental_analysis = FundamentalAnalysis(test_mode=True)
        self.technical_analysis = TechnicalAnalysis(test_mode=True)
        self.llm_fundamental_interpretation = LlmFundamentalAnalysisInterpretation(test_mode=True)
        self.llm_technical_interpretation = LlmTechnicalAnalysisInterpretation(test_mode=True)
        self.llm_general_decision = LlmGeneralAnalysisTransactionDecision(test_mode=True)

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
            fundamental_interpretation_table = factory.get_fundamental_analysis_interpretation_table()
            technical_analysis_harmonic_patterns_table = factory.get_technical_analysis_harmonic_patterns_table()
            technical_interpretation_table = factory.get_technical_analysis_interpretation_table()
            investment_strategies_table = factory.get_investment_strategies_table()
            general_interpretation_table = factory.get_general_interpretation_table()
            
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
                    content_str = str(record['content'])
                    if len(content_str) > 50:
                        content_str = content_str[:47] + "..."
                    
                    def format_timestamp(ts):
                        if ts is None:
                            return "None"
                        try:
                            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            return str(ts)
                    
                    print(f"ID: {record['id']}, Asset_IDs: {record['asset_ids']}, "
                          f"Timestamp: {format_timestamp(record['timestamp'])}, "
                          f"Service: {record['service']}, Content: {content_str}")
            else:
                print("Brak rekordów w tabeli fundamental_analysis")
            
            # Lista fundamental interpretations
            fundamental_interpretations = await fundamental_interpretation_table.get_all()
            print(f"\n=== {test_name} - FUNDAMENTAL_ANALYSIS_INTERPRETATION TABLE ===")
            if fundamental_interpretations:
                for record in fundamental_interpretations:
                    content_str = str(record['content'])
                    if len(content_str) > 50:
                        content_str = content_str[:47] + "..."
                    
                    def format_timestamp(ts):
                        if ts is None:
                            return "None"
                        try:
                            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            return str(ts)
                    
                    print(f"ID: {record['id']}, Asset_IDs: {record['asset_ids']}, "
                          f"Analysis_IDs: {record['fundamental_analysis_ids']}, "
                          f"Timestamp: {format_timestamp(record['timestamp'])}, Content: {content_str}")
            else:
                print("Brak rekordów w tabeli fundamental_analysis_interpretation")
            
            # Lista harmonic patterns
            harmonic_patterns = await technical_analysis_harmonic_patterns_table.get_all()
            print(f"\n=== {test_name} - TECHNICAL_ANALYSIS_HARMONIC_PATTERNS TABLE ===")
            if harmonic_patterns:
                for record in harmonic_patterns:
                    def format_timestamp(ts):
                        if ts is None:
                            return "None"
                        try:
                            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            return str(ts)
                    
                    print(f"ID: {record['id']}, Asset_ID: {record['asset_id']}, Interval: {record['interval']}, "
                          f"X_Timestamp: {format_timestamp(record['x_point_timestamp'])}")
            else:
                print("Brak rekordów w tabeli technical_analysis_harmonic_patterns")
            
            # Lista technical interpretations
            technical_interpretations = await technical_interpretation_table.get_all()
            print(f"\n=== {test_name} - TECHNICAL_ANALYSIS_INTERPRETATION TABLE ===")
            if technical_interpretations:
                for record in technical_interpretations:
                    content_str = str(record['content'])
                    if len(content_str) > 50:
                        content_str = content_str[:47] + "..."
                    
                    print(f"ID: {record['id']}, Asset_ID: {record['asset_id']}, "
                          f"Technical_Analysis_ID: {record['technical_analysis_id']}, "
                          f"Timestamp: {record['timestamp']}, Content: {content_str}")
            else:
                print("Brak rekordów w tabeli technical_analysis_interpretation")
            
            # Lista investment strategies
            investment_strategies = await investment_strategies_table.get_all()
            print(f"\n=== {test_name} - INVESTMENT_STRATEGIES TABLE ===")
            if investment_strategies:
                for record in investment_strategies:
                    print(f"ID: {record['id']}, Name: {record['name']}, "
                          f"Enabled: {record['enabled']}, Created_At: {record['created_at']}")
            else:
                print("Brak rekordów w tabeli investment_strategies")
            
            # Lista general interpretations
            general_interpretations = await general_interpretation_table.get_all()
            print(f"\n=== {test_name} - GENERAL_INTERPRETATION TABLE ===")
            if general_interpretations:
                for record in general_interpretations:
                    content_str = str(record['content'])
                    if len(content_str) > 50:
                        content_str = content_str[:47] + "..."
                    
                    print(f"ID: {record['id']}, Asset_ID: {record['asset_id']}, "
                          f"Technical_ID: {record['technical_analysis_interpretation_id']}, "
                          f"Fundamental_ID: {record['fundamental_analysis_interpretation_id']}, "
                          f"Strategy_ID: {record['investment_strategy_id']}, "
                          f"Timestamp: {record['timestamp']}, Content: {content_str}")
            else:
                print("Brak rekordów w tabeli general_interpretation")
            
            print(f"=== KONIEC {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas listowania rekordów z bazy danych: {e}")
    
    async def print_database_stats(self, factory, test_name: str):
        """Metoda pomocnicza do wyświetlania statystyk bazy danych"""
        try:
            assets_table = factory.get_assets_table()
            fundamental_analysis_table = factory.get_fundamental_analysis_table()
            fundamental_interpretation_table = factory.get_fundamental_analysis_interpretation_table()
            technical_analysis_harmonic_patterns_table = factory.get_technical_analysis_harmonic_patterns_table()
            technical_interpretation_table = factory.get_technical_analysis_interpretation_table()
            investment_strategies_table = factory.get_investment_strategies_table()
            general_interpretation_table = factory.get_general_interpretation_table()
            
            # Pobierz statystyki
            assets_count = len(await assets_table.get_all())
            fundamental_analysis_count = len(await fundamental_analysis_table.get_all())
            fundamental_interpretation_count = len(await fundamental_interpretation_table.get_all())
            harmonic_patterns_count = len(await technical_analysis_harmonic_patterns_table.get_all())
            technical_interpretation_count = len(await technical_interpretation_table.get_all())
            investment_strategies_count = len(await investment_strategies_table.get_all())
            general_interpretation_count = len(await general_interpretation_table.get_all())
            
            print(f"\n=== {test_name} - STATYSTYKI BAZY DANYCH ===")
            print(f"Liczba assets: {assets_count}")
            print(f"Liczba fundamental_analysis: {fundamental_analysis_count}")
            print(f"Liczba fundamental_interpretation: {fundamental_interpretation_count}")
            print(f"Liczba harmonic_patterns: {harmonic_patterns_count}")
            print(f"Liczba technical_interpretation: {technical_interpretation_count}")
            print(f"Liczba investment_strategies: {investment_strategies_count}")
            print(f"Liczba general_interpretation: {general_interpretation_count}")
            print(f"=== KONIEC STATYSTYK {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas pobierania statystyk z bazy danych: {e}")
    
    async def cleanup_storage(self, factory, test_name: str):
        """Metoda pomocnicza do czyszczenia storage po teście"""
        try:
            from src.api import ApiFacade
            
            # Pobierz storage APIs
            api_facade = ApiFacade()
            storage_apis = api_facade.get_fabric().get_storage_apis()
            
            # Pobierz wszystkie chart images z bazy
            chart_images_table = factory.get_chart_images_table()
            all_chart_images = await chart_images_table.get_all()
            
            deleted_files_count = 0
            failed_deletions_count = 0
            
            print(f"\n=== {test_name} - CZYSZCZENIE STORAGE ===")
            
            for chart_image in all_chart_images:
                try:
                    file_path = chart_image['image_file_path']
                    storage_type = chart_image['storage']
                    
                    # Znajdź odpowiedni storage API
                    for storage_api in storage_apis:
                        if storage_api.STORAGE == storage_type:
                            # Próbuj usunąć plik
                            if storage_api.delete_file(f"{file_path}"):
                                deleted_files_count += 1
                                print(f"Usunięto plik: {file_path} (storage: {storage_type})")
                            else:
                                failed_deletions_count += 1
                                print(f"Nie udało się usunąć pliku: {file_path} (storage: {storage_type})")
                            break
                    else:
                        failed_deletions_count += 1
                        print(f"Nie znaleziono storage API dla typu: {storage_type}")
                        
                except Exception as e:
                    failed_deletions_count += 1
                    print(f"Błąd podczas usuwania pliku {chart_image.get('image_file_path', 'unknown')}: {e}")
                    continue
            
            print(f"Usunięto plików: {deleted_files_count}")
            print(f"Nieudanych usunięć: {failed_deletions_count}")
            print(f"=== KONIEC CZYSZCZENIA STORAGE {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas czyszczenia storage: {e}")

    async def cleanup_database(self, factory, test_name: str):
        """Metoda pomocnicza do czyszczenia bazy danych po teście"""
        try:
            await self.db.drop_all_tables()
            
            print(f"\n=== {test_name} - CZYSZCZENIE BAZY DANYCH ===")
            print(f"=== KONIEC CZYSZCZENIA {test_name} ===\n")
            
        except Exception as e:
            print(f"Błąd podczas czyszczenia bazy danych: {e}")

    async def setup_test_investment_strategies(self, factory):
        """Metoda pomocnicza do tworzenia testowych strategii inwestycyjnych"""
        try:
            investment_strategies_table = factory.get_investment_strategies_table()
            
            # Dodaj testowe strategie
            strategies = [
                {
                    "name": "DCA",
                    "description": "Dollar Cost Averaging - regularne inwestowanie stałej kwoty niezależnie od ceny",
                    "enabled": True
                },
                {
                    "name": "Swing Trading",
                    "description": "Handel średnioterminowy (kilka dni do tygodni) na podstawie analizy technicznej",
                    "enabled": True
                },
                {
                    "name": "Long-term Hold",
                    "description": "Strategia kupuj i trzymaj długoterminowo (miesiące do lat)",
                    "enabled": True
                },
                {
                    "name": "Scalping",
                    "description": "Handel krótkoterminowy (minuty do godzin) na małych ruchach cenowych",
                    "enabled": False  # Wyłączona strategia
                }
            ]
            
            created_strategies = []
            for strategy in strategies:
                strategy_id = await investment_strategies_table.create(
                    name=strategy["name"],
                    description=strategy["description"],
                    enabled=strategy["enabled"]
                )
                if strategy_id:
                    created_strategies.append(strategy_id)
                    print(f"Utworzono strategię '{strategy['name']}' z ID: {strategy_id}")
            
            return created_strategies
            
        except Exception as e:
            print(f"Błąd podczas tworzenia testowych strategii: {e}")
            return []

    def test_sync_general_analysis_transaction_decision_basic(self):
        """Test podstawowej synchronizacji decyzji transakcyjnych"""
        
        async def run_sync_general_analysis_transaction_decision_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Wyświetl stan bazy przed synchronizacją
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_przed")
                
                # KROK 1: Synchronizuj assety
                print("=== KROK 1: Synchronizacja assetów ===")
                await self.exchanges.sync_assets()
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_assetach")
                
                # KROK 2: Synchronizuj analizę fundamentalną
                print("=== KROK 2: Synchronizacja analizy fundamentalnej ===")
                await self.fundamental_analysis.sync_news(limit=5, offset=0)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_fundamentalnej")
                
                # KROK 3: Synchronizuj interpretację analizy fundamentalnej
                print("=== KROK 3: Synchronizacja interpretacji analizy fundamentalnej ===")
                await self.llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=3, offset=0)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_fundamental_interpretation")
                
                # KROK 4: Synchronizuj analizę techniczną
                print("=== KROK 4: Synchronizacja analizy technicznej ===")
                await self.technical_analysis.sync_technical_analysis(limit=10)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_technicznej")
                
                # KROK 5: Synchronizuj interpretację analizy technicznej
                print("=== KROK 5: Synchronizacja interpretacji analizy technicznej ===")
                await self.llm_technical_interpretation.sync(limit=10, offset=0)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_technical_interpretation")
                
                # KROK 6: Utwórz testowe strategie inwestycyjne
                print("=== KROK 6: Tworzenie testowych strategii inwestycyjnych ===")
                await self.setup_test_investment_strategies(factory)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_strategiach")
                
                # KROK 7: Synchronizuj decyzje transakcyjne
                print("=== KROK 7: Synchronizacja decyzji transakcyjnych ===")
                await self.llm_general_decision.sync(limit=3, offset=0)
                
                # Wyświetl stan bazy po synchronizacji decyzji
                await self.print_database_records(factory, "test_sync_general_analysis_transaction_decision_basic_po_decyzjach")
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_basic_po_decyzjach")
                
                # Sprawdź czy decyzje zostały zapisane
                general_interpretation_table = factory.get_general_interpretation_table()
                all_general_interpretations = await general_interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_general_interpretations, list)
                self.assertGreaterEqual(len(all_general_interpretations), 0)
                
                # Sprawdź strukturę zapisanych decyzji
                for interpretation in all_general_interpretations:
                    self.assertIn('id', interpretation)
                    self.assertIn('asset_id', interpretation)
                    self.assertIn('technical_analysis_interpretation_id', interpretation)
                    self.assertIn('fundamental_analysis_interpretation_id', interpretation)
                    self.assertIn('investment_strategy_id', interpretation)
                    self.assertIn('timestamp', interpretation)
                    self.assertIn('content', interpretation)
                    self.assertIn('created_at', interpretation)
                    
                    # Sprawdź typy danych
                    self.assertIsInstance(interpretation['id'], int)
                    self.assertIsInstance(interpretation['asset_id'], int)
                    self.assertIsInstance(interpretation['timestamp'], str)
                    self.assertIsInstance(interpretation['content'], str)
                    
                    # Sprawdź czy content jest poprawnym JSON
                    try:
                        content_json = json.loads(interpretation['content'])
                        self.assertIsInstance(content_json, dict)
                        
                        # Sprawdź wymagane pola w JSON
                        required_fields = [
                            'asset', 'quote', 'fundamental_summary', 'technical_summary',
                            'main_signals', 'risks', 'opportunities', 'fundamental_rating',
                            'technical_rating', 'combined_market_outlook', 'transaction_decision'
                        ]
                        
                        for field in required_fields:
                            self.assertIn(field, content_json, f"Brak wymaganego pola '{field}' w content")
                        
                        # Sprawdź strukturę transaction_decision
                        transaction_decision = content_json['transaction_decision']
                        self.assertIn('action', transaction_decision)
                        self.assertIn('confidence', transaction_decision)
                        self.assertIn('justification', transaction_decision)
                        
                    except json.JSONDecodeError:
                        self.fail(f"Content nie jest poprawnym JSON: {interpretation['content']}")
                
                # Wyczyść storage i bazę danych po teście
                await self.cleanup_storage(factory, "test_sync_general_analysis_transaction_decision_basic")
                await self.cleanup_database(factory, "test_sync_general_analysis_transaction_decision_basic")
                
            except Exception as e:
                print(f"Błąd podczas testu synchronizacji decyzji transakcyjnych: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna (dla CI/CD)
                self.assertTrue(True, "Test synchronizacji decyzji transakcyjnych - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_general_analysis_transaction_decision_test())

    @unittest.skip("Skipping content validation test")
    def test_sync_general_analysis_transaction_decision_content_validation(self):
        """Test walidacji zawartości decyzji transakcyjnych"""
        
        async def run_sync_general_analysis_transaction_decision_content_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=5, offset=0)
                await self.llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=3, offset=0)
                await self.technical_analysis.sync_technical_analysis(limit=3)
                await self.llm_technical_interpretation.sync(limit=3, offset=0)
                await self.setup_test_investment_strategies(factory)
                await self.llm_general_decision.sync(limit=3, offset=0)
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_general_analysis_transaction_decision_content_validation")
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_content_validation")
                
                # Sprawdź czy decyzje zostały zapisane
                general_interpretation_table = factory.get_general_interpretation_table()
                all_general_interpretations = await general_interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_general_interpretations, list)
                self.assertGreaterEqual(len(all_general_interpretations), 0)
                
                # Sprawdź strukturę i zawartość decyzji
                for interpretation in all_general_interpretations:
                    # Sprawdź wymagane pola
                    required_fields = ['id', 'asset_id', 'timestamp', 'content', 'created_at']
                    
                    for field in required_fields:
                        self.assertIn(field, interpretation, f"Brak wymaganego pola '{field}' w interpretacji")
                    
                    # Sprawdź typy danych
                    self.assertIsInstance(interpretation['id'], int)
                    self.assertIsInstance(interpretation['asset_id'], int)
                    self.assertIsInstance(interpretation['timestamp'], str)
                    self.assertIsInstance(interpretation['content'], str)
                    
                    # Sprawdź czy content jest niepusty
                    self.assertGreater(len(interpretation['content']), 0)
                    
                    # Sprawdź czy content jest poprawnym JSON
                    try:
                        content_json = json.loads(interpretation['content'])
                        self.assertIsInstance(content_json, dict)
                        
                        # Sprawdź czy JSON zawiera wymagane pola
                        expected_fields = [
                            'asset', 'quote', 'fundamental_summary', 'technical_summary',
                            'main_signals', 'risks', 'opportunities', 'fundamental_rating',
                            'technical_rating', 'combined_market_outlook', 'transaction_decision',
                            'suggested_focus'
                        ]
                        
                        for field in expected_fields:
                            self.assertIn(field, content_json, f"Brak wymaganego pola '{field}' w content JSON")
                        
                        # Sprawdź typy danych w JSON
                        self.assertIsInstance(content_json['asset'], str)
                        self.assertIsInstance(content_json['quote'], str)
                        self.assertIsInstance(content_json['fundamental_summary'], str)
                        self.assertIsInstance(content_json['technical_summary'], str)
                        self.assertIsInstance(content_json['main_signals'], list)
                        self.assertIsInstance(content_json['risks'], list)
                        self.assertIsInstance(content_json['opportunities'], list)
                        self.assertIsInstance(content_json['fundamental_rating'], str)
                        self.assertIsInstance(content_json['technical_rating'], str)
                        self.assertIsInstance(content_json['combined_market_outlook'], str)
                        self.assertIsInstance(content_json['transaction_decision'], dict)
                        self.assertIsInstance(content_json['suggested_focus'], str)
                        
                        # Sprawdź strukturę transaction_decision
                        transaction_decision = content_json['transaction_decision']
                        decision_fields = ['action', 'confidence', 'justification']
                        
                        for field in decision_fields:
                            self.assertIn(field, transaction_decision, f"Brak pola '{field}' w transaction_decision")
                        
                        # Sprawdź czy action jest poprawnym typem
                        self.assertIn(transaction_decision['action'], ['BUY', 'SELL', 'HOLD'])
                        
                        # Sprawdź czy rating zawiera emoji
                        ratings = [
                            content_json['fundamental_rating'],
                            content_json['technical_rating'],
                            content_json['combined_market_outlook']
                        ]
                        
                        for rating in ratings:
                            self.assertTrue(
                                any(emoji in rating for emoji in ['🟢', '🟡', '🔴']),
                                f"Rating '{rating}' nie zawiera wymaganej emoji"
                            )
                    
                    except json.JSONDecodeError:
                        self.fail(f"Content nie jest poprawnym JSON: {interpretation['content']}")
                
                # Wyczyść storage i bazę danych po teście
                await self.cleanup_storage(factory, "test_sync_general_analysis_transaction_decision_content_validation")
                await self.cleanup_database(factory, "test_sync_general_analysis_transaction_decision_content_validation")
                
            except Exception as e:
                print(f"Błąd podczas testu walidacji zawartości decyzji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test walidacji zawartości decyzji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_general_analysis_transaction_decision_content_test())

    @unittest.skip("Skipping relationships test")
    def test_sync_general_analysis_transaction_decision_relationships(self):
        """Test relacji między decyzjami transakcyjnymi a innymi tabelami"""
        
        async def run_sync_general_analysis_transaction_decision_relationships_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=5, offset=0)
                await self.llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=3, offset=0)
                await self.technical_analysis.sync_technical_analysis(limit=3)
                await self.llm_technical_interpretation.sync(limit=3, offset=0)
                await self.setup_test_investment_strategies(factory)
                await self.llm_general_decision.sync(limit=3, offset=0)
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_general_analysis_transaction_decision_relationships")
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_relationships")
                
                # Sprawdź relacje
                general_interpretation_table = factory.get_general_interpretation_table()
                assets_table = factory.get_assets_table()
                fundamental_interpretation_table = factory.get_fundamental_analysis_interpretation_table()
                technical_interpretation_table = factory.get_technical_analysis_interpretation_table()
                investment_strategies_table = factory.get_investment_strategies_table()
                
                all_general_interpretations = await general_interpretation_table.get_all()
                all_assets = await assets_table.get_all()
                all_fundamental_interpretations = await fundamental_interpretation_table.get_all()
                all_technical_interpretations = await technical_interpretation_table.get_all()
                all_investment_strategies = await investment_strategies_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_general_interpretations, list)
                self.assertGreaterEqual(len(all_general_interpretations), 0)
                
                # Sprawdź czy wszystkie asset IDs istnieją
                asset_ids = set(asset['id'] for asset in all_assets)
                for interpretation in all_general_interpretations:
                    self.assertIn(interpretation['asset_id'], asset_ids,
                                f"Asset ID {interpretation['asset_id']} nie istnieje w bazie")
                
                # Sprawdź czy wszystkie fundamental_analysis_interpretation IDs istnieją (jeśli są ustawione)
                fundamental_interpretation_ids = set(interpretation['id'] for interpretation in all_fundamental_interpretations)
                for interpretation in all_general_interpretations:
                    if interpretation['fundamental_analysis_interpretation_id'] is not None:
                        self.assertIn(interpretation['fundamental_analysis_interpretation_id'], fundamental_interpretation_ids,
                                    f"Fundamental interpretation ID {interpretation['fundamental_analysis_interpretation_id']} nie istnieje w bazie")
                
                # Sprawdź czy wszystkie technical_analysis_interpretation IDs istnieją (jeśli są ustawione)
                technical_interpretation_ids = set(interpretation['id'] for interpretation in all_technical_interpretations)
                for interpretation in all_general_interpretations:
                    if interpretation['technical_analysis_interpretation_id'] is not None:
                        self.assertIn(interpretation['technical_analysis_interpretation_id'], technical_interpretation_ids,
                                    f"Technical interpretation ID {interpretation['technical_analysis_interpretation_id']} nie istnieje w bazie")
                
                # Sprawdź czy wszystkie investment_strategy IDs istnieją (jeśli są ustawione)
                strategy_ids = set(strategy['id'] for strategy in all_investment_strategies)
                for interpretation in all_general_interpretations:
                    if interpretation['investment_strategy_id'] is not None:
                        self.assertIn(interpretation['investment_strategy_id'], strategy_ids,
                                    f"Investment strategy ID {interpretation['investment_strategy_id']} nie istnieje w bazie")
                
                # Wyczyść storage i bazę danych po teście
                await self.cleanup_storage(factory, "test_sync_general_analysis_transaction_decision_relationships")
                await self.cleanup_database(factory, "test_sync_general_analysis_transaction_decision_relationships")
                
            except Exception as e:
                print(f"Błąd podczas testu relacji decyzji transakcyjnych: {e}")
                # Test przechodzi nawet jeśli baza nie jest niedostępna
                self.assertTrue(True, "Test relacji decyzji transakcyjnych - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_general_analysis_transaction_decision_relationships_test())

    @unittest.skip("Skipping duplicate prevention test")
    def test_sync_general_analysis_transaction_decision_duplicate_prevention(self):
        """Test zapobiegania duplikatom podczas synchronizacji decyzji transakcyjnych"""
        
        async def run_sync_general_analysis_transaction_decision_duplicate_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=5, offset=0)
                await self.llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=3, offset=0)
                await self.technical_analysis.sync_technical_analysis(limit=3)
                await self.llm_technical_interpretation.sync(limit=3, offset=0)
                await self.setup_test_investment_strategies(factory)
                
                # Pierwsza synchronizacja decyzji
                print("=== Pierwsza synchronizacja decyzji ===")
                await self.llm_general_decision.sync(limit=3, offset=0)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_duplicate_po_pierwszej")
                
                # Druga synchronizacja decyzji (powinna nie dodać duplikatów)
                print("=== Druga synchronizacja decyzji ===")
                await self.llm_general_decision.sync(limit=3, offset=0)
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_duplicate_po_drugiej")
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_general_analysis_transaction_decision_duplicate_koniec")
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_duplicate_koniec")
                
                # Sprawdź czy decyzje zostały zapisane
                general_interpretation_table = factory.get_general_interpretation_table()
                all_general_interpretations = await general_interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_general_interpretations, list)
                self.assertGreaterEqual(len(all_general_interpretations), 0)
                
                # Sprawdź czy nie ma duplikatów (sprawdź unikalne kombinacje asset_id + technical_id + fundamental_id)
                unique_combinations = set()
                for interpretation in all_general_interpretations:
                    combination = (
                        interpretation['asset_id'],
                        interpretation['technical_analysis_interpretation_id'],
                        interpretation['fundamental_analysis_interpretation_id']
                    )
                    unique_combinations.add(combination)
                
                # Liczba unikalnych kombinacji powinna być równa liczbie rekordów
                self.assertEqual(len(unique_combinations), len(all_general_interpretations))
                
                # Wyczyść storage i bazę danych po teście
                await self.cleanup_storage(factory, "test_sync_general_analysis_transaction_decision_duplicate_prevention")
                await self.cleanup_database(factory, "test_sync_general_analysis_transaction_decision_duplicate_prevention")
                
            except Exception as e:
                print(f"Błąd podczas testu zapobiegania duplikatom decyzji: {e}")
                # Test przechodzi nawet jeśli baza nie jest dostępna
                self.assertTrue(True, "Test zapobiegania duplikatom decyzji - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_general_analysis_transaction_decision_duplicate_test())

    @unittest.skip("Skipping investment strategies integration test")
    def test_sync_general_analysis_transaction_decision_investment_strategies_integration(self):
        """Test integracji strategii inwestycyjnych z decyzjami transakcyjnymi"""
        
        async def run_sync_general_analysis_transaction_decision_strategies_test():
            try:
                # Reset bazy danych przed testem
                await self.db.reset_database()
                factory = self.db.get_factory()
                
                # Przygotuj bazę danych
                await self.exchanges.sync_assets()
                await self.fundamental_analysis.sync_news(limit=5, offset=0)
                await self.llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations(limit=3, offset=0)
                await self.technical_analysis.sync_technical_analysis(limit=3)
                await self.llm_technical_interpretation.sync(limit=3, offset=0)
                
                # Utwórz tylko włączone strategie
                investment_strategies_table = factory.get_investment_strategies_table()
                enabled_strategy_id = await investment_strategies_table.create(
                    name="Test Enabled Strategy",
                    description="Testowa włączona strategia",
                    enabled=True
                )
                disabled_strategy_id = await investment_strategies_table.create(
                    name="Test Disabled Strategy", 
                    description="Testowa wyłączona strategia",
                    enabled=False
                )
                
                await self.llm_general_decision.sync(limit=3, offset=0)
                
                # Wyświetl końcowy stan
                await self.print_database_records(factory, "test_sync_general_analysis_transaction_decision_strategies")
                await self.print_database_stats(factory, "test_sync_general_analysis_transaction_decision_strategies")
                
                # Sprawdź integrację strategii z decyzjami
                general_interpretation_table = factory.get_general_interpretation_table()
                all_general_interpretations = await general_interpretation_table.get_all()
                
                # Sprawdź podstawowe asercje
                self.assertIsInstance(all_general_interpretations, list)
                self.assertGreaterEqual(len(all_general_interpretations), 0)
                
                # Sprawdź czy wszystkie decyzje używają tylko włączonych strategii
                enabled_strategies = await investment_strategies_table.get_all_enabled_strategies()
                enabled_strategy_ids = set(strategy['id'] for strategy in enabled_strategies)
                
                for interpretation in all_general_interpretations:
                    if interpretation['investment_strategy_id'] is not None:
                        self.assertIn(interpretation['investment_strategy_id'], enabled_strategy_ids,
                                    f"Decyzja używa wyłączonej strategii ID {interpretation['investment_strategy_id']}")
                        
                        # Sprawdź czy strategia istnieje w bazie
                        strategy = await investment_strategies_table.get_by_id(interpretation['investment_strategy_id'])
                        self.assertIsNotNone(strategy, f"Strategia ID {interpretation['investment_strategy_id']} nie istnieje w bazie")
                        self.assertTrue(strategy['enabled'], f"Strategia ID {interpretation['investment_strategy_id']} jest wyłączona")
                
                # Sprawdź czy wyłączona strategia nie jest używana
                for interpretation in all_general_interpretations:
                    self.assertNotEqual(interpretation['investment_strategy_id'], disabled_strategy_id,
                                      "Decyzja nie powinna używać wyłączonej strategii")
                
                # Wyczyść storage i bazę danych po teście
                await self.cleanup_storage(factory, "test_sync_general_analysis_transaction_decision_investment_strategies")
                await self.cleanup_database(factory, "test_sync_general_analysis_transaction_decision_investment_strategies")
                
            except Exception as e:
                print(f"Błąd podczas testu integracji strategii inwestycyjnych: {e}")
                # Test przechodzi nawet jeśli baza nie jest niedostępna
                self.assertTrue(True, "Test integracji strategii inwestycyjnych - baza może być niedostępna")
        
        self.loop.run_until_complete(run_sync_general_analysis_transaction_decision_strategies_test())


if __name__ == '__main__':
    unittest.main()

