from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class UsersTable(AbstractTable):
    """Klasa do zarządzania tabelą Users."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, username: str, password: str, email: str) -> Optional[int]:
        """Tworzy nowego użytkownika i zwraca jego ID."""
        try:
            user_id = await self.fetch_val(
                "INSERT INTO users (username, password, email) VALUES ($1, $2, $3) RETURNING id",
                username, password, email
            )
            logger.info(f"Utworzono użytkownika: {username} z ID: {user_id}")
            return user_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia użytkownika: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera użytkownika po ID."""
        return await self.fetch_one(
            "SELECT id, username, password, email, created_at FROM users WHERE id = $1",
            record_id
        )
    
    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Pobiera użytkownika po nazwie użytkownika."""
        return await self.fetch_one(
            "SELECT id, username, password, email, created_at FROM users WHERE username = $1",
            username
        )
    
    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Pobiera użytkownika po email."""
        return await self.fetch_one(
            "SELECT id, username, password, email, created_at FROM users WHERE email = $1",
            email
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje użytkownika o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'username' in kwargs:
                update_fields.append(f"username = ${param_count}")
                values.append(kwargs['username'])
                param_count += 1
            
            if 'password' in kwargs:
                update_fields.append(f"password = ${param_count}")
                values.append(kwargs['password'])
                param_count += 1
            
            if 'email' in kwargs:
                update_fields.append(f"email = ${param_count}")
                values.append(kwargs['email'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano użytkownika z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji użytkownika: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa użytkownika o podanym ID."""
        try:
            await self.execute_query("DELETE FROM users WHERE id = $1", record_id)
            logger.info(f"Usunięto użytkownika z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania użytkownika: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkich użytkowników z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, username, email, created_at FROM users ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def search_by_username(self, username: str) -> List[Dict[str, Any]]:
        """Wyszukuje użytkowników po nazwie użytkownika."""
        return await self.fetch_all(
            "SELECT id, username, email, created_at FROM users WHERE username ILIKE $1 ORDER BY username",
            f"%{username}%"
        )
    
    async def search_by_email(self, email: str) -> List[Dict[str, Any]]:
        """Wyszukuje użytkowników po email."""
        return await self.fetch_all(
            "SELECT id, username, email, created_at FROM users WHERE email ILIKE $1 ORDER BY email",
            f"%{email}%"
        ) 