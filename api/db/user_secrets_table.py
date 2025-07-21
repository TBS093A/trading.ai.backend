from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class UserSecretsTable(AbstractTable):
    """Klasa do zarządzania tabelą UserSecrets."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS user_secrets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, key)
        );
        """
    
    async def create(self, user_id: int, key: str, value: str) -> Optional[int]:
        """Tworzy nowy secret użytkownika i zwraca jego ID."""
        try:
            secret_id = await self.fetch_val(
                "INSERT INTO user_secrets (user_id, key, value) VALUES ($1, $2, $3) RETURNING id",
                user_id, key, value
            )
            logger.info(f"Utworzono secret dla użytkownika {user_id}, klucz: {key}")
            return secret_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia secret: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera secret po ID."""
        return await self.fetch_one(
            "SELECT id, user_id, key, value, created_at FROM user_secrets WHERE id = $1",
            record_id
        )
    
    async def get_by_user_and_key(self, user_id: int, key: str) -> Optional[Dict[str, Any]]:
        """Pobiera secret po user_id i key."""
        return await self.fetch_one(
            "SELECT id, user_id, key, value, created_at FROM user_secrets WHERE user_id = $1 AND key = $2",
            user_id, key
        )
    
    async def get_value_by_user_and_key(self, user_id: int, key: str) -> Optional[str]:
        """Pobiera wartość secret po user_id i key."""
        return await self.fetch_val(
            "SELECT value FROM user_secrets WHERE user_id = $1 AND key = $2",
            user_id, key
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje secret o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'user_id' in kwargs:
                update_fields.append(f"user_id = ${param_count}")
                values.append(kwargs['user_id'])
                param_count += 1
            
            if 'key' in kwargs:
                update_fields.append(f"key = ${param_count}")
                values.append(kwargs['key'])
                param_count += 1
            
            if 'value' in kwargs:
                update_fields.append(f"value = ${param_count}")
                values.append(kwargs['value'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE user_secrets SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano secret z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji secret: {e}", exc_info=True)
            return False
    
    async def update_or_create(self, user_id: int, key: str, value: str) -> bool:
        """Aktualizuje secret lub tworzy nowy jeśli nie istnieje."""
        try:
            await self.execute_query("""
            INSERT INTO user_secrets (user_id, key, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, key) DO UPDATE
            SET value = EXCLUDED.value, created_at = CURRENT_TIMESTAMP
            """, user_id, key, value)
            logger.info(f"Zaktualizowano/utworzono secret dla użytkownika {user_id}, klucz: {key}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji/tworzenia secret: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa secret o podanym ID."""
        try:
            await self.execute_query("DELETE FROM user_secrets WHERE id = $1", record_id)
            logger.info(f"Usunięto secret z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania secret: {e}", exc_info=True)
            return False
    
    async def delete_by_user_and_key(self, user_id: int, key: str) -> bool:
        """Usuwa secret po user_id i key."""
        try:
            await self.execute_query("DELETE FROM user_secrets WHERE user_id = $1 AND key = $2", user_id, key)
            logger.info(f"Usunięto secret dla użytkownika {user_id}, klucz: {key}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania secret: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie secrety z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, user_id, key, created_at FROM user_secrets ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def get_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie secrety użytkownika."""
        return await self.fetch_all(
            "SELECT id, user_id, key, value, created_at FROM user_secrets WHERE user_id = $1 ORDER BY key",
            user_id
        )
    
    async def get_keys_by_user_id(self, user_id: int) -> List[str]:
        """Pobiera wszystkie klucze secretów użytkownika."""
        records = await self.fetch_all(
            "SELECT key FROM user_secrets WHERE user_id = $1 ORDER BY key",
            user_id
        )
        return [record['key'] for record in records] 