import requests
from typing import Optional, Dict, Any, List
from .abstract_service import AbstractService
from ...config import config
import json
import logging
from datetime import datetime

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
        public: bool = False,
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
    ):
        """
        Inicjalizacja serwisu CryptoPanic
        
        Args:
            api_key (str): Klucz API (wymagany)
            public:
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
        """
        self.api_key = api_key
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
    
    def _get_news_request(self, currencies: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Prywatna metoda do pobierania wiadomości kryptowalutowych z CryptoPanic API
        
        Args:
            currencies: Lista walut do filtrowania (opcjonalnie)
                (np. ['BTC', 'ETH'])
        
        https://cryptopanic.com/developers/api/

        pobieranie Dict[str, Any]:
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

        Returns:
            List[Dict[str, Any]]: Lista słowników (results (List[Dict])) - obiektów wiadomości, gdzie każdy obiekt zawiera:
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
            logger.info(f"Pobieram wiadomości z CryptoPanic API")
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
            if currencies:
                params['currencies'] = ','.join(currencies)
            
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
            
            result = response.json()
            logger.info(f"Pobrano {len(result.get('results', []))} wiadomości z CryptoPanic API")
            logger.info(f"Wynik: {result}")
            
            return result['results']
            
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

    def parse_timestamp(self, item: Dict[str, Any]) -> int:
        """
        Konwertuje timestamp (z api) na timestamp w formie uznawanej przez bazę danych.

        Args:
            item: Słownik zawierający wiadomość

        Returns:
            int: Timestamp
        """
        # Konwertuj published_at na timestamp
        published_at = item.get('published_at')
        if published_at:
            # Konwertuj ISO 8601 na Unix timestamp
            dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            return int(dt.timestamp())
        else:
            # Użyj aktualnego czasu jeśli brak published_at
            return int(datetime.now().timestamp())