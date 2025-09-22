import logging
import traceback
from typing import List, Dict, Any, Optional
from .api.exchanges.abstract import AbstractAPI
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class Exchanges:
    """
    Klasa odpowiedzialna za integrację z giełdami i synchronizację assetów.
    Używa wzorca strategii do obsługi różnych giełd.
    Filtruje assety tylko do tych z quote=USDT, aby ograniczyć ilość zbędnych symboli.
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy Exchanges
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges: List[AbstractAPI] = self.api_facade.get_fabric().get_exchanges_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
    
    def _clean_asset_code(self, asset_code: str) -> str:
        """
        Czyści kod assetu z niepożądanych znaków.
        Zostawia tylko litery i cyfry, usuwa wszystkie inne znaki.
        
        Args:
            asset_code: Oryginalny kod assetu
            
        Returns:
            str: Wyczyszczony kod assetu zawierający tylko litery i cyfry
        """
        if not asset_code:
            return asset_code
        
        # Konwertuj na wielkie litery
        cleaned = asset_code.upper()
        
        # Usuń wszystkie znaki, które nie są literami ani cyframi
        import re
        cleaned = re.sub(r'[^A-Z0-9]', '', cleaned)
        
        # Usuń białe znaki (dodatkowe zabezpieczenie)
        cleaned = cleaned.strip()
        
        logger.debug(f"Wyczyszczono asset_code: '{asset_code}' -> '{cleaned}'")
        
        return cleaned
    
    async def _get_all_symbols_from_exchanges(self) -> Dict[str, Dict[str, Any]]:
        """
        Pobiera wszystkie symbole ze wszystkich giełd używając wzorca strategii.
        
        Returns:
            Dict[str, Dict[str, Any]]: Słownik z symbolami z wszystkich giełd
        """
        all_symbols = {}
        
        for exchange in self.exchanges:
            try:
                logger.info(f"Pobieram symbole z giełdy: {exchange.__class__.__name__}")
                symbols_data = exchange._get_symbols()

                if symbols_data is not None:
                    if len(symbols_data) > 0:
                        exchange_name = exchange.__class__.__name__
                        all_symbols[exchange_name] = symbols_data
                        logger.info(f"Pobrano {len(symbols_data)} symboli z {exchange_name}")
                    else:
                        logger.warning(f"Nieprawidłowa odpowiedź z giełdy {exchange.__class__.__name__} - brak symboli")
                else:
                    logger.warning(f"Nieprawidłowa odpowiedź z giełdy {exchange.__class__.__name__} - brak danych")
            except Exception as e:
                logger.error(f"Błąd podczas pobierania symboli z giełdy {exchange.__class__.__name__}: {e}")
                logger.error(traceback.format_exc())
        
        return all_symbols
    
    async def _sync_exchange_symbols_with_database(self, all_exchange_symbols: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
        """
        Synchronizuje symbole z giełd z bazą danych - dodaje brakujące assety i exchanges.
        
        Args:
            all_exchange_symbols: Słownik z symbolami ze wszystkich giełd
            
        Returns:
            Dict[str, int]: Słownik mapujący kod assetu na jego ID w bazie danych
        """
        if not all_exchange_symbols:
            logger.warning("Brak symboli z giełd - nie można synchronizować z bazą danych")
            return {}
        
        try:
            logger.info(f"Rozpoczynam synchronizację symboli z giełd z bazą danych")
            
            # KROK 1: Synchronizuj exchanges
            logger.info("=== KROK 1: Synchronizacja exchanges ===")
            exchanges_to_create = []
            for exchange_name in all_exchange_symbols.keys():
                exchanges_to_create.append({
                    'name': exchange_name,
                    'display_name': exchange_name,
                    'is_active': True
                })
            
            exchanges_table = self.db.get_factory().get_exchanges_table()
            created_exchanges = await exchanges_table.create_many(exchanges_to_create)
            logger.info(f"Zsynchronizowano {len(created_exchanges)} exchanges")
            
            # KROK 2: Zbierz wszystkie unikalne assety ze wszystkich giełd (tylko z quote=USDT)
            logger.info("=== KROK 2: Przygotowanie assetów (filtrowanie po quote=USDT) ===")
            all_assets = set()
            asset_exchange_mapping = {}  # Mapowanie asset_code -> lista exchanges
            filtered_symbols_count = 0
            total_symbols_count = 0
            
            for exchange_name, exchange_data in all_exchange_symbols.items():
                for symbol_info in exchange_data:
                    total_symbols_count += 1
                    base_asset = symbol_info.get('base_asset')
                    quote_asset = symbol_info.get('quote_asset')
                    
                    # Filtruj tylko symbole z quote_asset = 'USDT'
                    if base_asset and quote_asset == 'USDT':
                        filtered_symbols_count += 1
                        all_assets.add(base_asset)
                        if base_asset not in asset_exchange_mapping:
                            asset_exchange_mapping[base_asset] = []
                        asset_exchange_mapping[base_asset].append(exchange_name)
            
            logger.info(f"Przefiltrowano {filtered_symbols_count} symboli z quote=USDT z łącznej liczby {total_symbols_count} symboli")
            
            logger.info(f"Znaleziono {len(all_assets)} unikalnych assetów ze wszystkich giełd")
            
            # Przygotuj listę assetów do sprawdzenia w bazie danych
            assets_to_check = []
            asset_quote_mapping = {}  # Mapowanie asset_code -> quote_asset
            
            for asset_code in all_assets:
                # Wyczyść asset_code z niepożądanych znaków
                cleaned_asset_code = self._clean_asset_code(asset_code)
                logger.debug(f"Przygotowuję asset: {asset_code} -> wyczyszczony: {cleaned_asset_code}")
                
                # Wszystkie assety mają quote_asset = 'USDT' (dzięki filtrowaniu)
                quote_asset = 'USDT'
                
                # Dodaj do listy do sprawdzenia
                assets_to_check.append({
                    'asset': cleaned_asset_code,
                    'quote': quote_asset
                })
                
                # Zapisz mapowanie dla późniejszego użycia
                asset_quote_mapping[asset_code] = {
                    'cleaned_asset': cleaned_asset_code,
                    'quote': quote_asset
                }
            
            # KROK 3: Sprawdź które assety już istnieją w bazie danych
            logger.info("=== KROK 3: Sprawdzanie istniejących assetów ===")
            assets_table = self.db.get_factory().get_assets_table()
            existing_assets = await assets_table.check_many(assets_to_check)
            
            logger.info(f"Sprawdzono {len(assets_to_check)} assetów, znaleziono {len(existing_assets)} istniejących")
            
            # Przygotuj listę assetów do utworzenia (tylko te, które nie istnieją)
            assets_to_create = []
            found_assets = {}
            added_assets_to_db = 0
            
            for asset_code, asset_info in asset_quote_mapping.items():
                cleaned_asset = asset_info['cleaned_asset']
                quote_asset = asset_info['quote']
                asset_key = f"{cleaned_asset}/{quote_asset}"
                
                if asset_key in existing_assets:
                    # Asset już istnieje
                    found_assets[asset_code] = existing_assets[asset_key]
                    continue
                else:
                    # Asset nie istnieje - dodaj do listy do utworzenia
                    assets_to_create.append({
                        'asset': cleaned_asset,
                        'quote': quote_asset
                    })
            
            # KROK 4: Utwórz wszystkie brakujące assety jednym zapytaniem
            logger.info("=== KROK 4: Tworzenie nowych assetów ===")
            if assets_to_create:
                logger.info(f"Tworzę {len(assets_to_create)} nowych assetów jednym zapytaniem")
                created_assets = await assets_table.create_many(assets_to_create)
                
                # Dodaj utworzone assety do słownika wyników
                for asset_code, asset_info in asset_quote_mapping.items():
                    cleaned_asset = asset_info['cleaned_asset']
                    quote_asset = asset_info['quote']
                    asset_key = f"{cleaned_asset}/{quote_asset}"
                    
                    if asset_key in created_assets:
                        found_assets[asset_code] = created_assets[asset_key]
                        added_assets_to_db += 1
            else:
                logger.info("Wszystkie assety już istnieją w bazie danych")
            
            # KROK 5: Utwórz relacje asset-exchange
            logger.info("=== KROK 5: Tworzenie relacji asset-exchange ===")
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            asset_exchange_relations = []
            added_relations = 0
            
            for asset_code, asset_id in found_assets.items():
                exchanges_for_asset = asset_exchange_mapping.get(asset_code, [])
                for exchange_name in exchanges_for_asset:
                    if exchange_name in created_exchanges:
                        exchange_id = created_exchanges[exchange_name]
                        asset_exchange_relations.append({
                            'asset_id': asset_id,
                            'exchange_id': exchange_id
                        })
            
            if asset_exchange_relations:
                logger.info(f"Tworzę {len(asset_exchange_relations)} relacji asset-exchange")
                created_relations = await asset_exchanges_table.create_many(asset_exchange_relations)
                added_relations = len(created_relations)
                logger.info(f"Utworzono {added_relations} nowych relacji asset-exchange")
            else:
                logger.info("Brak nowych relacji asset-exchange do utworzenia")
            
            logger.info(f"Zakończono synchronizację symboli z giełd. Znaleziono {len(found_assets)} assetów, dodano {added_assets_to_db} assetów do bazy danych, utworzono {added_relations} relacji asset-exchange")
            return found_assets
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji symboli z giełd: {e}")
            logger.error(traceback.format_exc())
            return {}
    
    async def sync_assets(self) -> None:
        """
        Synchronizuje wszystkie Assety na linii giełda - baza danych używając wzorca strategii na puli dostępnych giełd.
        Filtruje assety tylko do tych z quote=USDT, aby ograniczyć ilość zbędnych symboli i skupić się na głównych parach krypto.
        
        Returns:
            None
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # KROK 1: Pobierz wszystkie symbole ze wszystkich giełd
            logger.info("=== KROK 1: Pobieranie symboli ze wszystkich giełd ===")
            all_exchange_symbols = await self._get_all_symbols_from_exchanges()
            
            if not all_exchange_symbols:
                logger.warning("Nie udało się pobrać symboli z żadnej giełdy - kontynuuję bez synchronizacji symboli")
            
            # KROK 2: Synchronizuj symbole z bazą danych
            logger.info("=== KROK 2: Synchronizacja symboli z bazą danych ===")
            if all_exchange_symbols:
                synced_assets = await self._sync_exchange_symbols_with_database(all_exchange_symbols)
                logger.info(f"Zsynchronizowano {len(synced_assets)} assetów z giełd")
            else:
                logger.info("Pominięto synchronizację symboli - brak dostępnych giełd")

            logger.info("=== Synchronizacja zakończona ===")
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji z bazą danych: {e}", exc_info=True)
            return None
