from abc import ABC, abstractmethod
from typing import Dict, Any, List

class AbstractService(ABC):
    
    @abstractmethod
    def __get_news_request(self) -> Dict[str, Any]:
        """Prywatna metoda do pobierania wiadomości z API."""
        pass
    
    @abstractmethod
    async def sync_db(self, asset_id: int, limit: int = 100) -> List[int]:
        """
        Synchronizuje wiadomości z bazą danych.
        
        Args:
            asset_id: ID asset w bazie danych
            limit: Maksymalna liczba wiadomości do pobrania
            
        Returns:
            List[int]: Lista ID zapisanych wiadomości
        """
        pass