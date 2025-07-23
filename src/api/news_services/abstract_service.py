from abc import ABC, abstractmethod
from typing import Dict, Any, List

class AbstractService(ABC):
    
    @abstractmethod
    def _get_news_request(self) -> Dict[str, Any]:
        """Metoda do pobierania wiadomości z API."""
        pass
    
    @abstractmethod
    async def sync_db(self, limit: int = 100) -> List[int]:
        """
        Synchronizuje wiadomości z bazą danych.
        
        Args:
            limit: Maksymalna liczba wiadomości do pobrania
            
        Returns:
            List[int]: Lista ID zapisanych wiadomości
        """
        pass