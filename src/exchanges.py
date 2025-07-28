import logging
from typing import List, Dict, Any, Optional
from .api.exchanges.abstract import AbstractAPI
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class Exchanges:
    """
    Klasa odpowiedzialna za integrację z giełdami i synchronizację assetów.
    Używa wzorca strategii do obsługi różnych giełd.
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy Exchanges
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges: List[AbstractAPI] = self.api_facade.get_exchanges_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
    
    def _clean_asset_code(self, asset_code: str) -> str:
        """
        Czyści kod assetu z niepożądanych znaków.
        
        Args:
            asset_code: Oryginalny kod assetu
            
        Returns:
            str: Wyczyszczony kod assetu
        """
        if not asset_code:
            return asset_code
        
        # Usuń niepożądane znaki: USDT, /, \, -
        cleaned = asset_code.upper()
        cleaned = cleaned.replace('USDT', '')
        cleaned = cleaned.replace('/', '')
        cleaned = cleaned.replace('\\', '')
        cleaned = cleaned.replace('-', '')
        cleaned = cleaned.replace('_', '')
        
        # Usuń białe znaki
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
                
                if 'symbols' in symbols_data:
                    exchange_name = exchange.__class__.__name__
                    all_symbols[exchange_name] = symbols_data
                    logger.info(f"Pobrano {len(symbols_data['symbols'])} symboli z {exchange_name}")
                else:
                    logger.warning(f"Nieprawidłowa odpowiedź z giełdy {exchange.__class__.__name__} - brak pola 'symbols'")
                    
            except Exception as e:
                logger.error(f"Błąd podczas pobierania symboli z giełdy {exchange.__class__.__name__}: {e}")
        
        return all_symbols
    
    async def _sync_exchange_symbols_with_database(self, all_exchange_symbols: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
        """
        Synchronizuje symbole z giełd z bazą danych - dodaje brakujące assety.
        
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
            
            # Zbierz wszystkie unikalne assety ze wszystkich giełd
            all_assets = set()
            for exchange_name, exchange_data in all_exchange_symbols.items():
                for symbol_info in exchange_data['symbols']:
                    base_asset = symbol_info.get('base_asset')
                    if base_asset:
                        all_assets.add(base_asset)
            
            logger.info(f"Znaleziono {len(all_assets)} unikalnych assetów ze wszystkich giełd")
            
            # Znajdź brakujące assety
            found_assets = {}
            assets_table = self.db.get_factory().get_assets_table()
            
            for asset_code in all_assets:
                # Wyczyść asset_code z niepożądanych znaków
                cleaned_asset_code = self._clean_asset_code(asset_code)
                logger.debug(f"Sprawdzam asset: {asset_code} -> wyczyszczony: {cleaned_asset_code}")
                
                # Sprawdź czy asset już istnieje w bazie (używając wyczyszczonego kodu)
                existing_asset = await assets_table.get_by_asset(cleaned_asset_code)
                if existing_asset:
                    found_assets[asset_code] = existing_asset['id']
                    logger.debug(f"Asset {cleaned_asset_code} już istnieje w bazie (ID: {existing_asset['id']})")
                    continue
                
                # Znajdź najlepszy quote asset dla tego base assetu
                quote_asset = 'USDT'  # Domyślny quote asset
                
                for exchange_name, exchange_data in all_exchange_symbols.items():
                    for symbol_info in exchange_data['symbols']:
                        if symbol_info.get('base_asset') == cleaned_asset_code:
                            logger.debug(f"Znaleziono asset {cleaned_asset_code} w symbolu {symbol_info.get('symbol')} na giełdzie {exchange_name}")
                            
                            # Znajdź odpowiedni quote asset (najlepiej USDT, USDC, BTC)
                            quote_asset = symbol_info.get('quote_asset', 'USDT')
                            break
                    
                    if quote_asset != 'USDT':  # Znaleziono quote asset
                        break
                
                # Sprawdź ponownie czy asset nie został dodany w międzyczasie
                existing_asset = await assets_table.get_by_asset(cleaned_asset_code)
                if existing_asset:
                    found_assets[asset_code] = existing_asset['id']
                    logger.debug(f"Asset {cleaned_asset_code} został już dodany w międzyczasie (ID: {existing_asset['id']})")
                    continue
                
                # Dodaj asset do bazy danych
                try:
                    asset_id = await assets_table.create(
                        asset=cleaned_asset_code,
                        quote=quote_asset
                    )
                    
                    if asset_id:
                        found_assets[asset_code] = asset_id
                        logger.info(f"Dodano nowy asset: {cleaned_asset_code}/{quote_asset} (ID: {asset_id})")
                    else:
                        logger.warning(f"Nie udało się dodać assetu: {cleaned_asset_code}")
                        
                except Exception as e:
                    logger.error(f"Błąd podczas dodawania assetu {cleaned_asset_code}: {e}")
            
            logger.info(f"Zakończono synchronizację symboli z giełd. Znaleziono {len(found_assets)} assetów: {found_assets}")
            return found_assets
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji symboli z giełd: {e}")
            return {}
    
    async def sync_assets(self) -> None:
        """
        Synchronizuje wszystkie Assety na linii giełda - baza danych używając wzorca strategii na puli dostępnych giełd.
        
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
