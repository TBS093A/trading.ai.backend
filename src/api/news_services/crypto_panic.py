import requests
from typing import Optional, Dict, Any, List
from .abstract_service import AbstractService
from ...config import config
from ...db.database_facade import DatabaseFacade
import json
import logging
from datetime import datetime
from ...api.exchanges.abstract import AbstractAPI

logger = logging.getLogger(__name__)


class CryptoPanicService(AbstractService):
    """
    Serwis do pobierania wiadomości kryptowalutowych z CryptoPanic API
    """
    
    BASE_URL = "https://cryptopanic.com/api/developer/v2"
    SERVICE_NAME = "CRYPTO_PANIC"
    
    def __init__(self,
        api_key: str,
        # public
        currencies: Optional[List[str]] = None,
        public: bool = True,
        filter: Optional[str] = None,
        regions: Optional[List[str]] = None,
        kind: str = "all",
        # private
        following: bool = False,
        last_pull: Optional[str] = None,
        panic_period: Optional[str] = None,
        panic_sort: Optional[str] = None,
        size: int = 20,
        with_content: bool = False,
        # additional
        used_exchange: AbstractAPI = None,
        test_mode: bool = False
    ):
        """
        Inicjalizacja serwisu CryptoPanic
        
        Args:
            api_key (str): Klucz API (wymagany)
            public:
                currencies: (opcjonalnie) Lista kodów walut do filtrowania:
                    (np. ['BTC', 'ETH'])
                public: (opcjonalnie) Czy używać publicznych endpointów:
                    (True) czy prywatnych (False)
                filter: (opcjonalnie) Filtr wiadomości:
                    ('rising', 'hot', 'bullish', 'bearish', 'important', 'saved', 'lol')
                regions: (opcjonalnie) Lista regionów do filtrowania:
                    ('en', 'de', 'nl', 'es', 'fr', 'it', 'pt', 'ru', 'tr', 'ar', 'cn', 'jp', 'ko')
                kind: (opcjonalnie) Rodzaj wiadomości:
                    ('news', 'media', 'all') - domyślnie 'all'
            private:
                following: (opcjonalnie) Czy filtrować tylko źródła które obserwujesz
                    (True, False)
            enterprise:
                last_pull: (opcjonalnie) Limit wyszukiwania do ostatniego pull time
                    (ISO date)
                panic_period: (opcjonalnie) Okres panic score:
                    ('1h', '6h', '24h')
                panic_sort: (opcjonalnie) Sortowanie po panic score:
                    ('asc', 'desc')
                size: (opcjonalnie) Liczba elementów na stronę:
                    (1-500)
                with_content: (opcjonalnie) Czy filtrować tylko wiadomości z pełną treścią:
                    (True, False)
            used_exchange: (opcjonalnie) Giełda do pobierania symboli:
                (BinanceAPI, KucoinAPI, etc.)
            test_mode: (opcjonalnie) Czy uruchamiać w trybie testowym:
                (True, False)
        """
        self.api_key = api_key
        self.currencies = currencies or []
        self.public = public
        self.filter = filter
        self.regions = regions or ['en']  # Domyślnie angielski
        self.kind = kind
        self.following = following
        self.last_pull = last_pull
        self.panic_period = panic_period
        self.panic_sort = panic_sort
        self.size = min(max(size, 1), 500)  # Ograniczenie do 1-500
        self.with_content = with_content
        self.used_exchange = used_exchange
        self.test_mode = test_mode
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = self.db_facade.get_database_postgresql()
        if self.test_mode:
            self.db = DatabaseFacade.get_test_database_postgresql()
    
    def __get_news_request(self) -> Dict[str, Any]:
        """
        Prywatna metoda do pobierania wiadomości kryptowalutowych z CryptoPanic API
        
        https://cryptopanic.com/developers/api/

        Returns:
            Dict[str, Any]: Słownik zawierający:
                - next (str | None): URL następnej strony wyników (lub None)
                - previous (str | None): URL poprzedniej strony wyników (lub None)
                - results (List[Dict]): Lista obiektów wiadomości, gdzie każdy obiekt zawiera:
                    - id (int): Unikalny identyfikator posta
                    - slug (str): Przyjazny dla URL krótki tytuł
                    - title (str): Pełny tytuł posta
                    - description (str): Krótkie podsumowanie
                    - published_at (str): Data publikacji (ISO 8601)
                    - created_at (str): Data utworzenia w systemie (ISO 8601)
                    - kind (str): Typ zawartości ("news", "media", "blog", "twitter", "reddit")
                    - source (Dict): Obiekt źródła zawierający:
                        - title (str): Nazwa wydawcy
                        - region (str): Kod języka (np. "en", "fr")
                        - domain (str): Domena wydawcy
                        - type (str): Typ źródła ("feed", "blog", "twitter", "media", "reddit")
                    - original_url (str): Link do oryginalnego artykułu
                    - url (str): Link do artykułu na CryptoPanic
                    - image (str): URL obrazu okładki
                    - instruments (List[Dict]): Lista instrumentów (kryptowalut) zawierająca:
                        - code (str): Kod tickera (np. "BTC")
                        - title (str): Pełna nazwa instrumentu
                        - slug (str): Przyjazny dla URL identyfikator
                        - url (str): Link do strony instrumentu
                        - market_cap_usd (float): Kapitalizacja rynkowa w USD
                        - price_in_usd (float): Aktualna cena w USD
                        - price_in_btc (float): Aktualna cena w BTC
                        - price_in_eth (float): Aktualna cena w ETH
                        - price_in_eur (float): Aktualna cena w EUR
                        - market_rank (int): Globalna pozycja rynkowa
                    - votes (Dict): Obiekt głosów zawierający:
                        - negative (int): Liczba negatywnych głosów
                        - positive (int): Liczba pozytywnych głosów
                        - important (int): Liczba głosów "ważne"
                        - liked (int): Liczba głosów "lubię"
                        - disliked (int): Liczba głosów "nie lubię"
                        - lol (int): Liczba reakcji "lol"
                        - toxic (int): Liczba reakcji "toksyczne"
                        - saved (int): Liczba zapisań posta
                        - comments (int): Liczba komentarzy
                    - panic_score (int): Własnościowy wynik ważności wiadomości (0-100)
                    - panic_score_1h (int): Wynik ważności w pierwszej godzinie (0-100)
                    - author (str): Nazwa autora artykułu
                    - content (Dict): Obiekt zawartości zawierający:
                        - original (str | None): Surowy HTML oryginalnego artykułu
                        - clean (str | None): Oczyszczona wersja tekstowa
                        
        Raises:
            ValueError: Gdy brak klucza API lub nieprawidłowy auth_token (401)
            PermissionError: Gdy przekroczono limit zapytań lub brak dostępu (403)
            requests.exceptions.RequestException: Gdy wystąpi błąd połączenia z API, rate limiting (429) lub błąd serwera (500)
            Exception: Gdy wystąpi nieoczekiwany błąd
        """
        try:
            # Budowanie parametrów zapytania
            params = {}
            
            # Wymagany parametr auth_token
            if self.api_key:
                params['auth_token'] = self.api_key
            else:
                raise ValueError('Brak klucza API - wymagany auth_token')
            
            # Parametr public (opcjonalny)
            if self.public:
                params['public'] = 'true'
            
            # Parametr currencies (opcjonalny)
            if self.currencies:
                params['currencies'] = ','.join(self.currencies)
            
            # Parametr regions (opcjonalny)
            if self.regions:
                params['regions'] = ','.join(self.regions)
            
            # Parametr filter (opcjonalny)
            if self.filter:
                params['filter'] = self.filter
            
            # Parametr kind (opcjonalny)
            if self.kind != "all":
                params['kind'] = self.kind
            
            # Parametr following (opcjonalny, tylko dla prywatnego API)
            if self.following and not self.public:
                params['following'] = 'true'
            
            # Parametry Enterprise (opcjonalne)
            if self.last_pull:
                params['last_pull'] = self.last_pull
            
            if self.panic_period:
                params['panic_period'] = self.panic_period
                # panic_sort wymaga panic_period
                if self.panic_sort:
                    params['panic_sort'] = self.panic_sort
            
            # Parametr size (opcjonalny, tylko Enterprise)
            if self.size != 20:
                params['size'] = self.size
            
            # Parametr with_content (opcjonalny, tylko Enterprise)
            if self.with_content:
                params['with_content'] = 'true'
            
            # Endpoint
            endpoint = f"{self.BASE_URL}/posts/"
            
            # Wykonanie zapytania
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Obsługa specyficznych kodów błędów HTTP
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 401:
                    raise ValueError('Nieautoryzowany - Nieprawidłowy lub brakujący auth_token')
                elif status_code == 403:
                    raise PermissionError('Zabroniony - Przekroczono limit zapytań lub brak dostępu do tego endpointu')
                elif status_code == 429:
                    raise requests.exceptions.RequestException('Zbyt wiele zapytań - Jesteś ograniczony przez rate limiting')
                elif status_code == 500:
                    raise requests.exceptions.RequestException('Błąd wewnętrzny serwera - Spróbuj ponownie później')
                else:
                    raise requests.exceptions.RequestException(f'Błąd HTTP {status_code}: {str(e)}')
            else:
                raise requests.exceptions.RequestException(f'Błąd połączenia z API: {str(e)}')
        except Exception as e:
            raise Exception(f'Nieoczekiwany błąd: {str(e)}')
    
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
        
        return cleaned
    
    async def _find_and_add_missing_assets(self, asset_codes: List[str]) -> Dict[str, int]:
        """
        Znajduje i dodaje brakujące assety z giełdy do bazy danych.
        
        Args:
            asset_codes: Lista kodów assetów do znalezienia
            
        Returns:
            Dict[str, int]: Słownik mapujący kod assetu na jego ID w bazie danych
        """
        if not self.used_exchange:
            logger.warning("Brak skonfigurowanej giełdy - nie można dodać brakujących assetów")
            return {}
        
        try:
            # Pobierz wszystkie symbole z giełdy
            exchange_symbols = self.used_exchange._get_symbols()
            
            if 'symbols' not in exchange_symbols:
                logger.warning("Nieprawidłowa odpowiedź z giełdy - brak pola 'symbols'")
                return {}
            
            # Znajdź brakujące assety
            found_assets = {}
            assets_table = self.db.get_factory().get_assets_table()
            
            for asset_code in asset_codes:
                # Wyczyść asset_code z niepożądanych znaków
                cleaned_asset_code = self._clean_asset_code(asset_code)
                
                # Sprawdź czy asset już istnieje w bazie (używając wyczyszczonego kodu)
                existing_asset = await assets_table.get_by_asset(cleaned_asset_code)
                if existing_asset:
                    found_assets[asset_code] = existing_asset['id']
                    continue
                
                # Szukaj w symbolach giełdy (używając wyczyszczonego kodu)
                asset_found_in_exchange = False
                for symbol_info in exchange_symbols['symbols']:
                    if symbol_info.get('baseAsset') == cleaned_asset_code:
                        # Znajdź odpowiedni quote asset (najlepiej USDT, USDC, BTC)
                        quote_asset = symbol_info.get('quoteAsset', 'USDT')
                        
                        # Sprawdź czy quote asset jest popularny
                        popular_quotes = ['USDT', 'USDC', 'BTC', 'ETH', 'USD']
                        if quote_asset not in popular_quotes:
                            # Szukaj lepszego quote assetu dla tego base assetu
                            for other_symbol in exchange_symbols['symbols']:
                                if (other_symbol.get('baseAsset') == cleaned_asset_code and 
                                    other_symbol.get('quoteAsset') in popular_quotes):
                                    quote_asset = other_symbol.get('quoteAsset')
                                    break
                        
                        # Dodaj asset do bazy danych
                        try:
                            asset_id = await assets_table.create(
                                asset=cleaned_asset_code,
                                quote=quote_asset
                            )
                            
                            if asset_id:
                                found_assets[asset_code] = asset_id
                                logger.info(f"Dodano nowy asset z giełdy: {cleaned_asset_code}/{quote_asset} (ID: {asset_id})")
                            else:
                                logger.warning(f"Nie udało się dodać assetu: {cleaned_asset_code}")
                                
                        except Exception as e:
                            logger.error(f"Błąd podczas dodawania assetu {cleaned_asset_code}: {e}")
                        
                        asset_found_in_exchange = True
                        break  # Znaleziono asset, przejdź do następnego
                
                # Jeśli nie znaleziono w giełdzie, dodaj z domyślnym quote USDT
                if not asset_found_in_exchange:
                    try:
                        asset_id = await assets_table.create(
                            asset=cleaned_asset_code,
                            quote='USDT'
                        )
                        
                        if asset_id:
                            found_assets[asset_code] = asset_id
                            logger.info(f"Dodano nowy asset z domyślnym quote: {cleaned_asset_code}/USDT (ID: {asset_id})")
                        else:
                            logger.warning(f"Nie udało się dodać assetu z domyślnym quote: {cleaned_asset_code}")
                            
                    except Exception as e:
                        logger.error(f"Błąd podczas dodawania assetu z domyślnym quote {cleaned_asset_code}: {e}")
            
            return found_assets
            
        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania assetów z giełdy: {e}")
            return {}
    
    async def sync_db(self) -> List[int]:
        """
        Synchronizuje wiadomości z CryptoPanic API z bazą danych.
            
        Returns:
            List[int]: Lista ID zapisanych wiadomości
        """
        try:
            # Pobierz wiadomości z API
            news_data = self.__get_news_request()
            
            if 'results' not in news_data:
                logger.warning("Brak wyników w odpowiedzi API")
                return []
            
            # Pobierz tabelę fundamental_analysis
            factory = self.db.get_factory()
            fundamental_analysis_table = factory.get_fundamental_analysis_table()
            
            saved_ids = []
            missing_assets = set()  # Zbierz wszystkie brakujące assety
            
            # Pierwszy przebieg - zbierz wszystkie brakujące assety
            for news_item in news_data['results']:
                instruments = news_item.get('instruments', [])
                for instrument in instruments:
                    asset_code = instrument.get('code')
                    if asset_code:
                        # Wyczyść asset_code i sprawdź czy asset istnieje w bazie
                        cleaned_asset_code = self._clean_asset_code(asset_code)
                        asset_result = await self.db.get_factory().get_assets_table().get_by_asset(cleaned_asset_code)
                        if not asset_result:
                            missing_assets.add(asset_code)  # Zachowaj oryginalny kod do mapowania
            
            # Dodaj brakujące assety z giełdy
            if missing_assets and self.used_exchange:
                logger.info(f"Znaleziono {len(missing_assets)} brakujących assetów: {list(missing_assets)}")
                found_assets = await self._find_and_add_missing_assets(list(missing_assets))
                logger.info(f"Dodano {len(found_assets)} nowych assetów z giełdy")
            
            # Drugi przebieg - przetwórz wiadomości
            for news_item in news_data['results']:
                try:
                    # Konwertuj published_at na timestamp
                    published_at = news_item.get('published_at')
                    if published_at:
                        # Konwertuj ISO 8601 na Unix timestamp
                        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        timestamp = int(dt.timestamp())
                    else:
                        # Użyj aktualnego czasu jeśli brak published_at
                        timestamp = int(datetime.now().timestamp())
                    
                    # Pobierz asset_id z instruments
                    instruments = news_item.get('instruments', [])
                    asset_ids = []
                    
                    for instrument in instruments:
                        asset_code = instrument.get('code')
                        if asset_code:
                            # Wyczyść asset_code i znajdź asset_id na podstawie wyczyszczonego kodu
                            cleaned_asset_code = self._clean_asset_code(asset_code)
                            asset_result = await self.db.get_factory().get_assets_table().get_by_asset(cleaned_asset_code)
                            if asset_result:
                                asset_ids.append(asset_result['id'])
                    
                    # Sprawdź czy wiadomość już istnieje
                    exists = await fundamental_analysis_table.check_analysis_exists(
                        asset_ids=asset_ids,
                        timestamp=timestamp,
                        service=self.SERVICE_NAME
                    )
                    
                    if not exists:
                        # Zapisz wiadomość do bazy danych
                        analysis_id = await fundamental_analysis_table.create(
                            asset_ids=asset_ids,
                            timestamp=timestamp,
                            content=news_item,  # Cały JSON jako content
                            link=news_item.get('url'),  # URL z results
                            service=self.SERVICE_NAME
                        )
                        
                        if analysis_id:
                            saved_ids.append(analysis_id)
                            logger.info(f"Zapisano wiadomość z ID: {analysis_id}")
                        else:
                            logger.error(f"Nie udało się zapisać wiadomości: {news_item.get('title', 'Unknown')}")
                    else:
                        logger.debug(f"Wiadomość już istnieje: {news_item.get('title', 'Unknown')}")
                        
                except Exception as e:
                    logger.error(f"Błąd podczas przetwarzania wiadomości: {e}")
                    continue
            
            logger.info(f"Zapisano {len(saved_ids)} nowych wiadomości")
            return saved_ids
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji z bazą danych: {e}", exc_info=True)
            return []
    
    def get_news_by_id(self, news_id: int) -> Dict[str, Any]:
        """
        Pobiera konkretną wiadomość po ID
        
        Args:
            news_id (int): ID wiadomości
            
        Returns:
            Dict[str, Any]: Obiekt wiadomości zawierający te same pola co w __get_news_request(),
                           ale bez paginacji (next, previous, results)
                           
        Raises:
            ValueError: Gdy brak klucza API lub nieprawidłowy auth_token (401)
            PermissionError: Gdy przekroczono limit zapytań lub brak dostępu (403)
            requests.exceptions.RequestException: Gdy wystąpi błąd połączenia z API, rate limiting (429) lub błąd serwera (500)
            Exception: Gdy wystąpi nieoczekiwany błąd
        """
        try:
            params = {}
            if self.api_key:
                params['auth_token'] = self.api_key
            
            endpoint = f"{self.BASE_URL}/posts/{news_id}/"
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Obsługa specyficznych kodów błędów HTTP
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 401:
                    raise ValueError('Nieautoryzowany - Nieprawidłowy lub brakujący auth_token')
                elif status_code == 403:
                    raise PermissionError('Zabroniony - Przekroczono limit zapytań lub brak dostępu do tego endpointu')
                elif status_code == 429:
                    raise requests.exceptions.RequestException('Zbyt wiele zapytań - Jesteś ograniczony przez rate limiting')
                elif status_code == 500:
                    raise requests.exceptions.RequestException('Błąd wewnętrzny serwera - Spróbuj ponownie później')
                else:
                    raise requests.exceptions.RequestException(f'Błąd HTTP {status_code}: {str(e)}')
            else:
                raise requests.exceptions.RequestException(f'Błąd połączenia z API: {str(e)}')
        except Exception as e:
            raise Exception(f'Nieoczekiwany błąd: {str(e)}')
