from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TransactionsTable(AbstractTable):
    """Klasa do zarządzania tabelą Transactions."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            exchange TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, asset_id: int, user_id: int, timestamp: str, exchange: str) -> Optional[int]:
        """Tworzy nową transakcję i zwraca jej ID."""
        try:
            transaction_id = await self.fetch_val(
                "INSERT INTO transactions (asset_id, user_id, timestamp, exchange) VALUES ($1, $2, $3, $4) RETURNING id",
                asset_id, user_id, timestamp, exchange
            )
            logger.info(f"Utworzono transakcję z ID: {transaction_id}")
            return transaction_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia transakcji: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera transakcję po ID."""
        return await self.fetch_one("""
        SELECT t.id, t.asset_id, t.user_id, t.timestamp, t.exchange, t.created_at,
               a.asset, a.quote, u.username
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        JOIN users u ON t.user_id = u.id
        WHERE t.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje transakcję o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'user_id' in kwargs:
                update_fields.append(f"user_id = ${param_count}")
                values.append(kwargs['user_id'])
                param_count += 1
            
            if 'timestamp' in kwargs:
                update_fields.append(f"timestamp = ${param_count}")
                values.append(kwargs['timestamp'])
                param_count += 1
            
            if 'exchange' in kwargs:
                update_fields.append(f"exchange = ${param_count}")
                values.append(kwargs['exchange'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE transactions SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano transakcję z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji transakcji: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa transakcję o podanym ID."""
        try:
            await self.execute_query("DELETE FROM transactions WHERE id = $1", record_id)
            logger.info(f"Usunięto transakcję z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania transakcji: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie transakcje z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT t.id, t.asset_id, t.user_id, t.timestamp, t.exchange, t.created_at,
               a.asset, a.quote, u.username
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        JOIN users u ON t.user_id = u.id
        ORDER BY t.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_user_id(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera transakcje użytkownika."""
        return await self.fetch_all("""
        SELECT t.id, t.asset_id, t.user_id, t.timestamp, t.exchange, t.created_at,
               a.asset, a.quote, u.username
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        JOIN users u ON t.user_id = u.id
        WHERE t.user_id = $1
        ORDER BY t.id DESC LIMIT $2 OFFSET $3
        """, user_id, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera transakcje dla asset."""
        return await self.fetch_all("""
        SELECT t.id, t.asset_id, t.user_id, t.timestamp, t.exchange, t.created_at,
               a.asset, a.quote, u.username
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        JOIN users u ON t.user_id = u.id
        WHERE t.asset_id = $1
        ORDER BY t.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_exchange(self, exchange: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera transakcje z określonej giełdy."""
        return await self.fetch_all("""
        SELECT t.id, t.asset_id, t.user_id, t.timestamp, t.exchange, t.created_at,
               a.asset, a.quote, u.username
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        JOIN users u ON t.user_id = u.id
        WHERE t.exchange = $1
        ORDER BY t.id DESC LIMIT $2 OFFSET $3
        """, exchange, limit, offset)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera transakcje z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT t.id, t.asset_id, t.user_id, t.timestamp, t.exchange, t.created_at,
               a.asset, a.quote, u.username
        FROM transactions t
        JOIN assets a ON t.asset_id = a.id
        JOIN users u ON t.user_id = u.id
        WHERE t.timestamp >= $1 AND t.timestamp <= $2
        ORDER BY t.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset) 