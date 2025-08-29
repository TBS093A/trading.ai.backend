from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class InvestmentStrategiesTable(AbstractTable):
    """Klasa do zarządzania tabelą InvestmentStrategies."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS investment_strategies (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            description TEXT NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, name: str, description: str, enabled: bool = True) -> Optional[int]:
        """Tworzy nową strategię inwestycyjną i zwraca jej ID."""
        try:
            strategy_id = await self.fetch_val(
                "INSERT INTO investment_strategies (name, description, enabled) VALUES ($1, $2, $3) RETURNING id",
                name, description, enabled
            )
            logger.info(f"Utworzono strategię inwestycyjną z ID: {strategy_id}")
            return strategy_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia strategii inwestycyjnej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera strategię inwestycyjną po ID."""
        return await self.fetch_one(
            "SELECT id, name, description, enabled, created_at FROM investment_strategies WHERE id = $1",
            record_id
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje strategię inwestycyjną o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'name' in kwargs:
                update_fields.append(f"name = ${param_count}")
                values.append(kwargs['name'])
                param_count += 1
            
            if 'description' in kwargs:
                update_fields.append(f"description = ${param_count}")
                values.append(kwargs['description'])
                param_count += 1
            
            if 'enabled' in kwargs:
                update_fields.append(f"enabled = ${param_count}")
                values.append(kwargs['enabled'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE investment_strategies SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano strategię inwestycyjną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji strategii inwestycyjnej: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa strategię inwestycyjną o podanym ID."""
        try:
            await self.execute_query("DELETE FROM investment_strategies WHERE id = $1", record_id)
            logger.info(f"Usunięto strategię inwestycyjną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania strategii inwestycyjnej: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie strategie inwestycyjne z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, name, description, enabled, created_at FROM investment_strategies ORDER BY id DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def get_all_enabled_strategies(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie włączone strategie inwestycyjne z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, name, description, enabled, created_at FROM investment_strategies WHERE enabled = TRUE ORDER BY id DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Pobiera strategię inwestycyjną po nazwie."""
        return await self.fetch_one(
            "SELECT id, name, description, enabled, created_at FROM investment_strategies WHERE name = $1",
            name
        )
    
    async def enable_strategy(self, record_id: int) -> bool:
        """Włącza strategię inwestycyjną."""
        return await self.update(record_id, enabled=True)
    
    async def disable_strategy(self, record_id: int) -> bool:
        """Wyłącza strategię inwestycyjną."""
        return await self.update(record_id, enabled=False)
    
    async def search_by_name(self, name_pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje strategie po wzorcu nazwy."""
        return await self.fetch_all(
            "SELECT id, name, description, enabled, created_at FROM investment_strategies WHERE name ILIKE $1 ORDER BY id DESC LIMIT $2 OFFSET $3",
            f"%{name_pattern}%", limit, offset
        )
    
    async def search_by_description(self, description_pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje strategie po wzorcu opisu."""
        return await self.fetch_all(
            "SELECT id, name, description, enabled, created_at FROM investment_strategies WHERE description ILIKE $1 ORDER BY id DESC LIMIT $2 OFFSET $3",
            f"%{description_pattern}%", limit, offset
        )
    
    async def count_all(self) -> int:
        """Zwraca liczbę wszystkich strategii."""
        result = await self.fetch_val("SELECT COUNT(*) FROM investment_strategies")
        return result or 0
    
    async def count_enabled(self) -> int:
        """Zwraca liczbę włączonych strategii."""
        result = await self.fetch_val("SELECT COUNT(*) FROM investment_strategies WHERE enabled = TRUE")
        return result or 0
