"""
Tabela użytkowników systemu.

Zawiera informacje o użytkownikach włącznie z:
- username - unikalna nazwa użytkownika
- password_hash - hash hasła w bcrypt
- avatar - blob z avatarem użytkownika (opcjonalny)
- role - rola użytkownika (user lub administrator)
"""

from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
import bcrypt

logger = logging.getLogger(__name__)


class UsersTable(AbstractTable):
    """Klasa do zarządzania tabelą Users."""
    
    # Definicje ról użytkowników
    ROLE_USER = 'user'
    ROLE_ADMINISTRATOR = 'administrator'
    VALID_ROLES = [ROLE_USER, ROLE_ADMINISTRATOR]
    
    # ID administratora systemowego
    ADMIN_USER_ID = 0
    
    def create_table(self) -> str:
        """Tworzy tabelę users z odpowiednią strukturą."""
        return """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            avatar BYTEA,
            role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'administrator')),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        """
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hashuje hasło używając bcrypt.
        
        Args:
            password: Hasło w postaci plain text
            
        Returns:
            str: Hash hasła
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Weryfikuje hasło względem hasha.
        
        Args:
            password: Hasło w postaci plain text
            password_hash: Hash hasła z bazy danych
            
        Returns:
            bool: True jeśli hasło jest poprawne
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception as e:
            logger.error(f"Błąd podczas weryfikacji hasła: {e}")
            return False
    
    async def create(
        self,
        username: str,
        password: str,
        role: str = ROLE_USER,
        avatar: Optional[bytes] = None,
        is_active: bool = True
    ) -> Optional[int]:
        """
        Tworzy nowego użytkownika i zwraca jego ID.
        
        Args:
            username: Nazwa użytkownika
            password: Hasło (będzie zahashowane)
            role: Rola użytkownika (user lub administrator)
            avatar: Opcjonalny avatar jako bytes
            is_active: Czy użytkownik jest aktywny
            
        Returns:
            Optional[int]: ID nowego użytkownika lub None w przypadku błędu
        """
        if role not in self.VALID_ROLES:
            logger.error(f"Nieprawidłowa rola: {role}. Dozwolone: {self.VALID_ROLES}")
            return None
        
        try:
            password_hash = self.hash_password(password)
            
            user_id = await self.fetch_val(
                """
                INSERT INTO users (username, password_hash, avatar, role, is_active) 
                VALUES ($1, $2, $3, $4, $5) 
                RETURNING id
                """,
                username, password_hash, avatar, role, is_active
            )
            logger.info(f"Utworzono użytkownika: {username} z ID: {user_id}, rola: {role}")
            return user_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia użytkownika: {e}", exc_info=True)
            return None
    
    async def create_with_id(
        self,
        user_id: int,
        username: str,
        password: str,
        role: str = ROLE_USER,
        avatar: Optional[bytes] = None,
        is_active: bool = True
    ) -> Optional[int]:
        """
        Tworzy nowego użytkownika z określonym ID (dla administratora systemowego).
        
        Args:
            user_id: ID użytkownika do przypisania
            username: Nazwa użytkownika
            password: Hasło (będzie zahashowane)
            role: Rola użytkownika (user lub administrator)
            avatar: Opcjonalny avatar jako bytes
            is_active: Czy użytkownik jest aktywny
            
        Returns:
            Optional[int]: ID nowego użytkownika lub None w przypadku błędu
        """
        if role not in self.VALID_ROLES:
            logger.error(f"Nieprawidłowa rola: {role}. Dozwolone: {self.VALID_ROLES}")
            return None
        
        try:
            password_hash = self.hash_password(password)
            
            # Użyj INSERT ... ON CONFLICT DO UPDATE aby nadpisać istniejące dane
            result = await self.fetch_one(
                """
                INSERT INTO users (id, username, password_hash, avatar, role, is_active) 
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO UPDATE SET
                    username = EXCLUDED.username,
                    password_hash = EXCLUDED.password_hash,
                    avatar = COALESCE(EXCLUDED.avatar, users.avatar),
                    role = EXCLUDED.role,
                    is_active = EXCLUDED.is_active,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                user_id, username, password_hash, avatar, role, is_active
            )
            
            # Upewnij się że sekwencja jest zsynchronizowana
            await self.execute_query(
                "SELECT setval('users_id_seq', GREATEST((SELECT MAX(id) FROM users), 1))"
            )
            
            if result:
                logger.info(f"Utworzono użytkownika: {username} z ID: {user_id}, rola: {role}")
                return user_id
            else:
                logger.error(f"Nie udało się utworzyć użytkownika: {username}")
                return None
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia użytkownika z ID: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera użytkownika po ID."""
        return await self.fetch_one(
            """
            SELECT id, username, password_hash, avatar, role, is_active, created_at, updated_at 
            FROM users 
            WHERE id = $1
            """,
            record_id
        )
    
    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Pobiera użytkownika po nazwie."""
        return await self.fetch_one(
            """
            SELECT id, username, password_hash, avatar, role, is_active, created_at, updated_at 
            FROM users 
            WHERE username = $1
            """,
            username
        )
    
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Autentykuje użytkownika na podstawie loginu i hasła.
        
        Args:
            username: Nazwa użytkownika
            password: Hasło w postaci plain text
            
        Returns:
            Optional[Dict[str, Any]]: Dane użytkownika (bez hasła) jeśli autentykacja udana
        """
        user = await self.get_by_username(username)
        
        if not user:
            logger.warning(f"Próba logowania na nieistniejące konto: {username}")
            return None
        
        if not user.get('is_active', False):
            logger.warning(f"Próba logowania na zablokowane konto: {username}")
            return None
        
        if not self.verify_password(password, user['password_hash']):
            logger.warning(f"Nieprawidłowe hasło dla użytkownika: {username}")
            return None
        
        # Usuń hash hasła z wyniku
        user_data = dict(user)
        del user_data['password_hash']
        
        logger.info(f"Pomyślna autentykacja użytkownika: {username}")
        return user_data
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje użytkownika o podanym ID."""
        try:
            update_fields = []
            params = []
            param_counter = 1
            
            if 'username' in kwargs:
                update_fields.append(f"username = ${param_counter}")
                params.append(kwargs['username'])
                param_counter += 1
            
            if 'password' in kwargs:
                update_fields.append(f"password_hash = ${param_counter}")
                params.append(self.hash_password(kwargs['password']))
                param_counter += 1
            
            if 'avatar' in kwargs:
                update_fields.append(f"avatar = ${param_counter}")
                params.append(kwargs['avatar'])
                param_counter += 1
            
            if 'role' in kwargs:
                if kwargs['role'] not in self.VALID_ROLES:
                    logger.error(f"Nieprawidłowa rola: {kwargs['role']}")
                    return False
                update_fields.append(f"role = ${param_counter}")
                params.append(kwargs['role'])
                param_counter += 1
            
            if 'is_active' in kwargs:
                update_fields.append(f"is_active = ${param_counter}")
                params.append(kwargs['is_active'])
                param_counter += 1
            
            if not update_fields:
                return False
            
            # Zawsze aktualizuj updated_at
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            params.append(record_id)
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ${param_counter}"
            
            await self.execute_query(query, *params)
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
        results = await self.fetch_all(
            """
            SELECT id, username, role, is_active, created_at, updated_at 
            FROM users 
            ORDER BY id 
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
        return results
    
    async def get_administrators(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkich administratorów."""
        return await self.fetch_all(
            """
            SELECT id, username, role, is_active, created_at, updated_at 
            FROM users 
            WHERE role = 'administrator' 
            ORDER BY id 
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
    
    async def admin_exists(self, admin_id: int = ADMIN_USER_ID) -> bool:
        """
        Sprawdza czy administrator o podanym ID istnieje.
        
        Args:
            admin_id: ID administratora do sprawdzenia (domyślnie 0)
            
        Returns:
            bool: True jeśli administrator istnieje
        """
        result = await self.fetch_one(
            "SELECT id FROM users WHERE id = $1 AND role = 'administrator'",
            admin_id
        )
        return result is not None
    
    async def count_users(self) -> int:
        """Zwraca liczbę wszystkich użytkowników."""
        result = await self.fetch_val("SELECT COUNT(*) FROM users")
        return result or 0
    
    async def count_administrators(self) -> int:
        """Zwraca liczbę wszystkich administratorów."""
        result = await self.fetch_val("SELECT COUNT(*) FROM users WHERE role = 'administrator'")
        return result or 0

