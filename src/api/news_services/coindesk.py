import requests
from typing import Optional, Dict, Any, List
from .abstract_service import AbstractService
from ...config import config
import json
import logging
from datetime import datetime
import time
import traceback

logger = logging.getLogger(__name__)


class CoinDeskService(AbstractService):
    """
    Serwis do pobierania wiadomości z CoinDesk API
    """
    
    BASE_URL = "https://data-api.coindesk.com/news/v1"
    SERVICE_NAME = "COINDESK"
    
    def __init__(self,
        api_key: str,
        # Podstawowe parametry
        search_string: Optional[str] = None,
        lang: str = "EN",
        source_key: Optional[str] = "coindesk",
        limit: int = 100,
        # Parametry dodatkowe
        loop_waiting_time: int = 2,
    ):
        """
        Inicjalizacja serwisu CoinDesk
        
        Args:
            api_key (str): Klucz API (wymagany)
            search_string (str): String wyszukiwania (opcjonalnie)
                (np. 'Ethereum ecosystem', 'Bitcoin', 'cryptocurrency')
            lang (str): Język wiadomości (domyślnie 'EN')
                ('EN', 'ES', 'FR', 'DE', 'IT', 'PT', 'RU', 'ZH', 'JA', 'KO')
            source_key (str): Klucz źródła (opcjonalnie)
                (np. 'coindesk', 'cryptocompare')
            limit (int): Limit wiadomości (domyślnie 100 i max 100)
            loop_waiting_time (int): Czas oczekiwania pomiędzy zapytaniami (domyślnie 2 sekundy)
        """
        self.api_key = api_key
        self.search_string = search_string
        self.lang = lang
        self.source_key = source_key
        self.limit = min(max(limit, 1), 100)
        self.loop_waiting_time = loop_waiting_time
    
    def _get_news_request(
        self, 
        currencies: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Prywatna metoda do pobierania wiadomości z CoinDesk API

        https://developers.coindesk.com/documentation/data-api/news_v1_search
        
        Args:
            currencies: Lista kryptowalut do filtrowania (opcjonalnie)
                (np. ['BTC', 'ETH']) - używane do wyszukiwania w treści
        
        Returns:
            List[Dict[str, Any]]: Lista obiektów wiadomości, gdzie każdy obiekt zawiera:
                - TYPE (str): Typ obiektu ("121" dla wiadomości)
                - ID (int): Unikalny identyfikator wiadomości
                - GUID (str): Globalny unikalny identyfikator
                - PUBLISHED_ON (int): Timestamp publikacji (Unix timestamp)
                - PUBLISHED_ON_NS (int | None): Nanosekundy timestampu
                - IMAGE_URL (str): URL obrazu okładki
                - TITLE (str): Tytuł artykułu
                - SUBTITLE (str): Podtytuł artykułu
                - AUTHORS (str): Autorzy artykułu
                - URL (str): Link do oryginalnego artykułu
                - SOURCE_ID (int): ID źródła
                - BODY (str): Treść artykułu
                - KEYWORDS (str): Słowa kluczowe oddzielone '|'
                - LANG (str): Język artykułu
                - UPVOTES (int): Liczba głosów pozytywnych
                - DOWNVOTES (int): Liczba głosów negatywnych
                - SCORE (int): Wynik wiadomości
                - SENTIMENT (str): Sentiment artykułu ('POSITIVE', 'NEGATIVE', 'NEUTRAL')
                - STATUS (str): Status wiadomości ('ACTIVE', 'INACTIVE')
                - CREATED_ON (int): Timestamp utworzenia
                - UPDATED_ON (int | None): Timestamp aktualizacji
                - SOURCE_DATA (Dict): Obiekt źródła zawierający:
                    - TYPE (str): Typ źródła ("120")
                    - ID (int): ID źródła
                    - SOURCE_KEY (str): Klucz źródła
                    - NAME (str): Nazwa źródła
                    - IMAGE_URL (str): URL obrazu źródła
                    - URL (str): URL źródła
                    - LANG (str): Język źródła
                    - SOURCE_TYPE (str): Typ źródła
                    - LAUNCH_DATE (int): Data uruchomienia
                    - SORT_ORDER (int): Kolejność sortowania
                    - BENCHMARK_SCORE (int): Wynik benchmarku
                    - STATUS (str): Status źródła
                    - LAST_UPDATED_TS (int): Ostatnia aktualizacja
                    - CREATED_ON (int): Timestamp utworzenia
                    - UPDATED_ON (int): Timestamp aktualizacji
                - CATEGORY_DATA (List[Dict]): Lista kategorii zawierająca:
                    - TYPE (str): Typ kategorii ("122")
                    - ID (int): ID kategorii
                    - NAME (str): Nazwa kategorii
                    - CATEGORY (str): Kategoria
                
        Raises:
            ValueError: Gdy brak klucza API lub nieprawidłowy apikey (401)
            PermissionError: Gdy przekroczono limit zapytań lub brak dostępu (403)
            requests.exceptions.RequestException: Gdy wystąpi błąd połączenia z API, rate limiting (429) lub błąd serwera (500)
            Exception: Gdy wystąpi nieoczekiwany błąd
        """

        try:
            logger.info(f"Pobieram wiadomości z CoinDesk API")
            
            # Budowanie parametrów zapytania
            params = {}
            
            # Wymagany parametr apikey
            if self.api_key:
                params['api_key'] = self.api_key
            else:
                raise ValueError('Brak klucza API - wymagany api_key')
            
            # Parametr search_string (zapytanie wyszukiwania)
            if self.search_string:
                params['search_string'] = self.search_string
                # Jeśli podano waluty, dodaj je do zapytania
                if currencies:
                    currency_query = currencies
                    params['search_string'] = f"{self.search_string} {currency_query}"
            elif currencies:
                # Jeśli nie ma zapytania ale są waluty, użyj walut jako zapytania
                currency_query = currencies
                params['search_string'] = currency_query
            
            # Parametr lang (opcjonalny)
            if self.lang:
                params['lang'] = self.lang
            
            # Parametr source_key (opcjonalny)
            if self.source_key:
                params['source_key'] = self.source_key
            
            # Parametr limit (opcjonalny)
            if self.limit:
                params['limit'] = self.limit
            
            # Endpoint
            endpoint = f"{self.BASE_URL}/search"
            
            # Wykonanie zapytania
            time.sleep(self.loop_waiting_time)
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Pobrano {len(result.get('Data', []))} wiadomości z CoinDesk API")
            logger.info(f"Wynik: {result}")
            
            return result.get('Data', [])
            
        except requests.exceptions.RequestException as e:
            # Obsługa specyficznych kodów błędów HTTP
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 401:
                    raise ValueError(f'Nieautoryzowany - Nieprawidłowy lub brakujący apikey: status_code: {status_code}, text: {e.response.text}')
                elif status_code == 403:
                    raise PermissionError(f'Zabroniony - Przekroczono limit zapytań lub brak dostępu do tego endpointu: status_code: {status_code}, text: {e.response.text}')
                elif status_code == 429:
                    raise requests.exceptions.RequestException(f'Zbyt wiele zapytań - Jesteś ograniczony przez rate limiting: status_code: {status_code}, text: {e.response.text}')
                elif status_code == 500:
                    raise requests.exceptions.RequestException(f'Błąd wewnętrzny serwera - Spróbuj ponownie później: status_code: {status_code}, text: {e.response.text}')
                else:
                    raise requests.exceptions.RequestException(f'Błąd HTTP {status_code}: {str(e)}, text: {e.response.text}')
            else:
                raise requests.exceptions.RequestException(f'Błąd połączenia z API: {str(e)}, traceback: {traceback.format_exc()}')
        except Exception as e:
            raise Exception(f'Nieoczekiwany błąd: {str(e)}, traceback: {traceback.format_exc()}')

    def parse_timestamp(self, item: Dict[str, Any]) -> int:
        """
        Konwertuje timestamp (z api) na timestamp w formie uznawanej przez bazę danych.

        Args:
            item: Słownik zawierający wiadomość

        Returns:
            int: Timestamp
        """
        # Konwertuj PUBLISHED_ON na timestamp
        published_on = item.get('PUBLISHED_ON')
        if published_on:
            # PUBLISHED_ON jest już w formacie Unix timestamp
            return int(published_on)
        else:
            # Użyj aktualnego czasu jeśli brak PUBLISHED_ON
            return int(datetime.now().timestamp())
    
    def item_to_dict(self, item: str) -> Dict[str, Any]:
        """
        Konwertuje item z CoinDesk API na słownik.
        
        Args:
            item: String zawierający wiadomość z CoinDesk API

        Returns:
            Dict[str, Any]: Słownik z danymi wiadomości
        """
        try:
            return json.loads(item)
        except json.JSONDecodeError:
            logger.error(f"Błąd podczas parsowania JSON z CoinDesk: {item}")
            return {} 