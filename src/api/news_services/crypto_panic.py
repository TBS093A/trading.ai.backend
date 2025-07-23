import requests
from typing import Optional, Dict, Any, List
from .abstract_service import AbstractService
from ...config import config


class CryptoPanicService(AbstractService):
    """
    Serwis do pobierania wiadomości kryptowalutowych z CryptoPanic API
    """
    
    BASE_URL = "https://cryptopanic.com/api/v1"
    
    def __init__(self,
                 currencies: Optional[List[str]] = None,
                 public: bool = True,
                 filter: str = "hot",
                 limit: int = 20,
                 metadata: bool = False):
        """
        Inicjalizacja serwisu CryptoPanic
        
        Args:
            currencies: Lista kodów walut do filtrowania (np. ['BTC', 'ETH'])
            public: Czy używać publicznych endpointów (True) czy prywatnych (False)
            filter: Filtr wiadomości ('hot', 'rising', 'bullish', 'bearish', 'important', 'saved', 'lol')
            limit: Maksymalna liczba wiadomości do pobrania (1-100)
            metadata: Czy zwracać metadane
        """
        # Użyj klucza API z konfiguracji jeśli nie podano
        self.api_key = config.crypto_panic_config.get('api_key')
        self.currencies = currencies or []
        self.public = public
        self.filter = filter
        self.limit = min(max(limit, 1), 100)  # Ograniczenie do 1-100
        self.metadata = metadata
    
    def get_news(self) -> Dict[str, Any]:
        """
        Pobiera wiadomości kryptowalutowe z CryptoPanic API
        
        Returns:
            Słownik z danymi wiadomości lub informacją o błędzie
        """
        try:
            # Budowanie parametrów zapytania
            params = {
                'filter': self.filter,
                'limit': self.limit,
                'metadata': str(self.metadata).lower()
            }
            
            # Dodanie filtrów walut jeśli podano
            if self.currencies:
                params['currencies'] = ','.join(self.currencies)
            
            # Dodanie klucza API jeśli podano
            if self.api_key:
                params['auth_token'] = self.api_key
            
            # Wybór endpointu na podstawie flagi public
            if self.public:
                endpoint = f"{self.BASE_URL}/posts/"
            else:
                endpoint = f"{self.BASE_URL}/posts/private/"
            
            # Wykonanie zapytania
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Błąd połączenia z API: {str(e)}',
                'status': 'error'
            }
        except Exception as e:
            return {
                'error': f'Nieoczekiwany błąd: {str(e)}',
                'status': 'error'
            }
    
    def get_news_by_id(self, news_id: int) -> Dict[str, Any]:
        """
        Pobiera konkretną wiadomość po ID
        
        Args:
            news_id: ID wiadomości
            
        Returns:
            Słownik z danymi wiadomości lub informacją o błędzie
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
            return {
                'error': f'Błąd połączenia z API: {str(e)}',
                'status': 'error'
            }
        except Exception as e:
            return {
                'error': f'Nieoczekiwany błąd: {str(e)}',
                'status': 'error'
            }
