from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import asyncpg
import logging

logger = logging.getLogger(__name__)

class AbstractTable(ABC):
    """Abstrakcyjna klasa bazowa dla wszystkich tabel."""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    @abstractmethod
    def create_table(self) -> str:
        """Zwraca string SQL do utworzenia tabeli."""
        pass
    
    @abstractmethod
    async def create(self, **kwargs) -> Optional[int]:
        """Tworzy nowy rekord i zwraca jego ID."""
        pass
    
    @abstractmethod
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera rekord po ID."""
        pass
    
    @abstractmethod
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje rekord o podanym ID."""
        pass
    
    @abstractmethod
    async def delete(self, record_id: int) -> bool:
        """Usuwa rekord o podanym ID."""
        pass
    
    @abstractmethod
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie rekordy z limitem i offsetem."""
        pass
    
    async def execute_query(self, query: str, *args) -> Any:
        """Wykonuje zapytanie SQL."""
        async with self.pool.acquire() as connection:
            try:
                return await connection.execute(query, *args)
            except Exception as e:
                logger.error(f"Błąd podczas wykonywania zapytania: {e}", exc_info=True)
                raise
    
    async def fetch_one(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Pobiera jeden rekord."""
        async with self.pool.acquire() as connection:
            try:
                record = await connection.fetchrow(query, *args)
                return dict(record) if record else None
            except Exception as e:
                logger.error(f"Błąd podczas pobierania rekordu: {e}", exc_info=True)
                return None
    
    async def fetch_all(self, query: str, *args) -> List[Dict[str, Any]]:
        """Pobiera wszystkie rekordy."""
        async with self.pool.acquire() as connection:
            try:
                records = await connection.fetch(query, *args)
                return [dict(record) for record in records]
            except Exception as e:
                logger.error(f"Błąd podczas pobierania rekordów: {e}", exc_info=True)
                return []
    
    async def fetch_val(self, query: str, *args) -> Any:
        """Pobiera pojedynczą wartość."""
        async with self.pool.acquire() as connection:
            try:
                return await connection.fetchval(query, *args)
            except Exception as e:
                logger.error(f"Błąd podczas pobierania wartości: {e}", exc_info=True)
                return None 