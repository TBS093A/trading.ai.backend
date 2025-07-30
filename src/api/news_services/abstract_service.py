from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class AbstractService(ABC):
    
    @abstractmethod
    def _get_news_request(self, currencies: Optional[List[str]] = None) -> Dict[str, Any]:
        """Metoda do pobierania wiadomości z API.
        
        Args:
            currencies: Lista kodów walut do filtrowania:
                (np. ['BTC', 'ETH'])
        """
        pass
    
    @abstractmethod
    def parse_timestamp(self, item: Dict[str, Any]) -> int:
        """Metoda do konwersji timestamp z API na timestamp w formie uznawanej przez bazę danych.
        
        Args:
            item: Słownik zawierający wiadomość

        Returns:
            int: Timestamp
        """
        pass
    
    @abstractmethod
    def item_to_dict(self, item: str) -> Dict[str, Any]:
        """Metoda do konwersji item z API na słownik.
        
        Args:
            item: String zawierający wiadomość z API

        Returns:
            Dict[str, Any]: Słownik z danymi wiadomości
        """
        pass