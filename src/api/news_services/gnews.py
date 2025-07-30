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


class GNewsService(AbstractService):
    """
    Serwis do pobierania wiadomości z GNews API
    """
    
    BASE_URL = "https://gnews.io/api/v4"
    SERVICE_NAME = "GNEWS"
    
    def __init__(self,
        api_key: str,
        # Podstawowe parametry
        lang: str = "en",
        country: Optional[str] = None,
        max_articles: int = 100,
        # Parametry wyszukiwania
        q: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sortby: str = "publishedAt",
        # Parametry top headlines
        topic: Optional[str] = None,
        # Parametry dodatkowe
        expand: bool = False,
        in_: Optional[str] = None,
        # Parametry dodatkowe
        loop_waiting_time: int = 2
    ):
        """
        Inicjalizacja serwisu GNews
        
        Args:
            api_key (str): Klucz API (wymagany)
            lang (str): Język wiadomości (domyślnie 'en')
                ('ar', 'zh', 'nl', 'en', 'fr', 'de', 'he', 'it', 'no', 'pt', 'ro', 'ru', 'sv', 'ud')
            country (str): Kod kraju (opcjonalnie)
                ('au', 'br', 'ca', 'cn', 'eg', 'fr', 'de', 'gr', 'hk', 'in', 'ie', 'il', 'it', 'jp', 'nl', 'no', 'pk', 'pe', 'ph', 'pt', 'ro', 'ru', 'sg', 'es', 'se', 'ch', 'tw', 'ua', 'gb', 'us')
            max_articles (int): Maksymalna liczba artykułów (1-100, domyślnie 10)
            q (str): Zapytanie wyszukiwania (opcjonalnie)
            from_date (str): Data początkowa w formacie YYYY-MM-DD (opcjonalnie)
            to_date (str): Data końcowa w formacie YYYY-MM-DD (opcjonalnie)
            sortby (str): Sortowanie wyników
                ('publishedAt', 'relevance', 'popularity') - domyślnie 'publishedAt'
            topic (str): Temat dla top headlines (opcjonalnie)
                ('breaking-news', 'world', 'nation', 'business', 'technology', 'entertainment', 'sports', 'science', 'health')
            expand (bool): Czy rozszerzyć odpowiedź o dodatkowe pola (domyślnie False)
            in_ (str): Pole do wyszukiwania (opcjonalnie)
                ('title', 'description', 'content') - domyślnie wszystkie
        """
        self.api_key = api_key
        self.lang = lang
        self.country = country
        self.max_articles = min(max(max_articles, 1), 100)  # Ograniczenie do 1-100
        self.q = q
        self.from_date = from_date
        self.to_date = to_date
        self.sortby = sortby
        self.topic = topic
        self.expand = expand
        self.in_ = in_
        self.loop_waiting_time = loop_waiting_time
    
    def _get_news_request(
        self, 
        currencies: Optional[List[str]] = None, 
        forex_currencies: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Prywatna metoda do pobierania wiadomości z GNews API

        https://docs.gnews.io/endpoints/search-endpoint
        
        Args:
            currencies: Lista kryptowalut do filtrowania (opcjonalnie)
                (np. ['BTC', 'ETH']) - używane do wyszukiwania w treści
            forex_currencies: Lista aktyw forex do filtrowania (opcjonalnie)
                (np. ['EUR', 'USD']) - używane do wyszukiwania w treści
            loop_waiting_time: Czas oczekiwania pomiędzy zapytaniami (domyślnie 2 sekundy)
        
        Returns:
            List[Dict[str, Any]]: Lista obiektów wiadomości, gdzie każdy obiekt zawiera:
                - title (str): Tytuł artykułu
                - description (str): Krótki opis artykułu
                - content (str): Treść artykułu
                - url (str): Link do oryginalnego artykułu
                - image (str): URL obrazu okładki
                - publishedAt (str): Data publikacji (ISO 8601)
                - source (Dict): Obiekt źródła zawierający:
                    - name (str): Nazwa wydawcy
                    - url (str): URL źródła
                - language (str): Język artykułu
                - relevance_score (int): Wynik trafności (0-100)
                - sentiment (str): Sentiment artykułu ('positive', 'negative', 'neutral')
                
        Raises:
            ValueError: Gdy brak klucza API lub nieprawidłowy apikey (401)
            PermissionError: Gdy przekroczono limit zapytań lub brak dostępu (403)
            requests.exceptions.RequestException: Gdy wystąpi błąd połączenia z API, rate limiting (429) lub błąd serwera (500)
            Exception: Gdy wystąpi nieoczekiwany błąd
        """

        if currencies:
            currencies = self.__format_query_for_crypto_currencies(currencies)
        if forex_currencies:
            forex_currencies = self.__format_query_for_forex_currencies(forex_currencies)

        try:
            logger.info(f"Pobieram wiadomości z GNews API")
            
            # Budowanie parametrów zapytania
            params = {}
            
            # Wymagany parametr apikey
            if self.api_key:
                params['apikey'] = self.api_key
            else:
                raise ValueError('Brak klucza API - wymagany apikey')
            
            # Parametr lang (opcjonalny)
            if self.lang:
                params['lang'] = self.lang
            
            # Parametr country (opcjonalny)
            if self.country:
                params['country'] = self.country
            
            # Parametr max (opcjonalny)
            if self.max_articles != 10:
                params['max'] = self.max_articles
            
            # Parametr q (zapytanie wyszukiwania)
            if self.q:
                params['q'] = self.q
                # Jeśli podano waluty, dodaj je do zapytania
                if currencies:
                    currency_query = currencies
                    params['q'] = f"{self.q} AND ({currency_query})"
                if forex_currencies:
                    forex_query = forex_currencies
                    params['q'] = f"{self.q} AND ({forex_query})"
            elif currencies:
                # Jeśli nie ma zapytania ale są waluty, użyj walut jako zapytania
                currency_query = currencies
                params['q'] = currency_query
            elif forex_currencies:
                # Jeśli nie ma zapytania ale są waluty, użyj walut jako zapytania
                forex_query = forex_currencies
                params['q'] = forex_query
            
            # Parametry dat (opcjonalne)
            if self.from_date:
                params['from'] = self.from_date
            
            if self.to_date:
                params['to'] = self.to_date
            
            # Parametr sortby (opcjonalny)
            if self.sortby != "publishedAt":
                params['sortby'] = self.sortby
            
            # Parametr expand (opcjonalny)
            if self.expand:
                params['expand'] = 'true'
            
            # Parametr in (opcjonalny)
            if self.in_:
                params['in'] = self.in_
            
            # Wybór endpointu na podstawie parametrów
            if self.topic:
                # Top headlines endpoint
                endpoint = f"{self.BASE_URL}/top-headlines"
                params['topic'] = self.topic
            else:
                # Search endpoint - wymaga parametru q
                endpoint = f"{self.BASE_URL}/search"
                # Jeśli brak zapytania i walut, użyj domyślnego zapytania dla kryptowalut
                if not self.q and not currencies:
                    params['q'] = "cryptocurrency OR bitcoin OR ethereum"
            
            # Wykonanie zapytania
            time.sleep(self.loop_waiting_time)
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Pobrano {len(result.get('articles', []))} wiadomości z GNews API")
            logger.info(f"Wynik: {result}")
            
            return result.get('articles', [])
            
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
                raise requests.exceptions.RequestException(f'Błąd połączenia z API: {str(e)}, text: {e.response.text}')
        except Exception as e:
            raise Exception(f'Nieoczekiwany błąd: {str(e)}, traceback: {traceback.format_exc()}')

    def __format_query_for_crypto_currencies(self, currencies: List[str]) -> str:
        """
        Formatuje zapytanie dla kryptowalut
        """
        return ' OR '.join(
            [f"crypto coin {currency}" for currency in currencies]
        )

    def __format_query_for_forex_currencies(self, currencies: List[str]) -> str:
        """
        Formatuje zapytanie dla walut forex
        """
        return ' OR '.join(
            [f"stock exchange {currency}" for currency in currencies]
        )

    def parse_timestamp(self, item: Dict[str, Any]) -> int:
        """
        Konwertuje timestamp (z api) na timestamp w formie uznawanej przez bazę danych.

        Args:
            item: Słownik zawierający wiadomość

        Returns:
            int: Timestamp
        """
        # Konwertuj publishedAt na timestamp
        published_at = item.get('publishedAt')
        if published_at:
            # Konwertuj ISO 8601 UTC na Unix timestamp
            # Format: "2022-09-28T08:14:24Z" (UTC)
            dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            return int(dt.timestamp())
        else:
            # Użyj aktualnego czasu jeśli brak publishedAt
            return int(datetime.now().timestamp())
    
    def item_to_dict(self, item: str) -> Dict[str, Any]:
        """
        Konwertuje item z GNews API na słownik.
        
        Args:
            item: String zawierający wiadomość z GNews API

        Returns:
            Dict[str, Any]: Słownik z danymi wiadomości
        """
        try:
            return json.loads(item)
        except json.JSONDecodeError:
            logger.error(f"Błąd podczas parsowania JSON z GNews: {item}")
            return {}
