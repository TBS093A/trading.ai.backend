from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class ExchangesTable(AbstractTable):
    """Klasa do zarządzania tabelą Exchanges."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS exchanges (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            display_name TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, name: str, display_name: Optional[str] = None, is_active: bool = True) -> Optional[int]:
        """Tworzy nowy exchange i zwraca jego ID."""
        try:
            exchange_id = await self.fetch_val(
                "INSERT INTO exchanges (name, display_name, is_active) VALUES ($1, $2, $3) RETURNING id",
                name, display_name, is_active
            )
            logger.info(f"Utworzono exchange: {name} z ID: {exchange_id}")
            return exchange_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia exchange: {e}", exc_info=True)
            return None
    
    async def check_many(self, exchange_names: List[str]) -> Dict[str, int]:
        """
        Sprawdza które exchanges już istnieją w bazie danych.
        
        Args:
            exchange_names: Lista nazw exchanges do sprawdzenia
            
        Returns:
            Dict[str, int]: Słownik mapujący nazwę exchange na jego ID (tylko dla istniejących)
        """
        if not exchange_names:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            conditions = []
            params = []
            param_counter = 1
            
            for name in exchange_names:
                conditions.append(f"name = ${param_counter}")
                params.append(name)
                param_counter += 1
            
            query = f"""
                SELECT id, name 
                FROM exchanges 
                WHERE {' OR '.join(conditions)}
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            existing_exchanges = {}
            for result in results:
                existing_exchanges[result['name']] = result['id']
            
            logger.info(f"Sprawdzono {len(exchange_names)} exchanges, znaleziono {len(existing_exchanges)} istniejących")
            return existing_exchanges
            
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania wielu exchanges: {e}", exc_info=True)
            return {}
    
    async def create_many(self, exchanges: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Tworzy wiele exchanges jednym zapytaniem i zwraca ich ID.
        
        Args:
            exchanges: Lista słowników z kluczami 'name', 'display_name', 'is_active'
            
        Returns:
            Dict[str, int]: Słownik mapujący nazwę exchange na jego ID
        """
        if not exchanges:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            for exchange in exchanges:
                name = exchange.get('name')
                display_name = exchange.get('display_name')
                is_active = exchange.get('is_active', True)
                
                values_list.append(f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2})")
                params.extend([name, display_name, is_active])
                param_counter += 3
            
            query = f"""
                INSERT INTO exchanges (name, display_name, is_active) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (name) DO NOTHING
                RETURNING id, name
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_exchanges = {}
            for result in results:
                created_exchanges[result['name']] = result['id']
            
            logger.info(f"Utworzono {len(created_exchanges)} nowych exchanges z {len(exchanges)} prób")
            return created_exchanges
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu exchanges: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera exchange po ID."""
        return await self.fetch_one(
            "SELECT id, name, display_name, is_active, created_at FROM exchanges WHERE id = $1",
            record_id
        )
    
    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Pobiera exchange po nazwie."""
        return await self.fetch_one(
            "SELECT id, name, display_name, is_active, created_at FROM exchanges WHERE name = $1",
            name
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje exchange o podanym ID."""
        try:
            update_fields = []
            params = []
            param_counter = 1
            
            if 'name' in kwargs:
                update_fields.append(f"name = ${param_counter}")
                params.append(kwargs['name'])
                param_counter += 1
            
            if 'display_name' in kwargs:
                update_fields.append(f"display_name = ${param_counter}")
                params.append(kwargs['display_name'])
                param_counter += 1
            
            if 'is_active' in kwargs:
                update_fields.append(f"is_active = ${param_counter}")
                params.append(kwargs['is_active'])
                param_counter += 1
            
            if not update_fields:
                return False
            
            params.append(record_id)
            query = f"UPDATE exchanges SET {', '.join(update_fields)} WHERE id = ${param_counter}"
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano exchange z ID: {record_id}")
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji exchange: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa exchange o podanym ID."""
        try:
            await self.execute_query("DELETE FROM exchanges WHERE id = $1", record_id)
            logger.info(f"Usunięto exchange z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania exchange: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie exchanges z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, name, display_name, is_active, created_at FROM exchanges ORDER BY name LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def get_active(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie aktywne exchanges."""
        return await self.fetch_all(
            "SELECT id, name, display_name, is_active, created_at FROM exchanges WHERE is_active = TRUE ORDER BY name LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def search_by_name(self, name: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje exchanges po nazwie."""
        return await self.fetch_all(
            "SELECT id, name, display_name, is_active, created_at FROM exchanges WHERE name ILIKE $1 ORDER BY name LIMIT $2 OFFSET $3",
            f"%{name}%", limit, offset
        ) 