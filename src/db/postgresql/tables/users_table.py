from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class UsersTable(AbstractTable):
    """Klasa do zarządzania tabelą Users z obsługą Telegram workflow."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT UNIQUE,
            
            -- Telegram-specific fields
            telegram_id BIGINT UNIQUE,
            telegram_username TEXT,
            telegram_first_name TEXT,
            telegram_last_name TEXT,
            telegram_phone TEXT,
            
            -- Permission system
            permission_level TEXT DEFAULT 'user' CHECK (permission_level IN ('guest', 'user', 'trader', 'admin', 'super_admin')),
            is_active BOOLEAN DEFAULT TRUE,
            is_banned BOOLEAN DEFAULT FALSE,
            
            -- Audit fields
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP WITH TIME ZONE,
            last_login TIMESTAMP WITH TIME ZONE,
            
            -- Metadata
            settings JSONB DEFAULT '{}',
            preferences JSONB DEFAULT '{}',
            stats JSONB DEFAULT '{}'
        );
        
        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_users_permission_level ON users(permission_level);
        CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
        CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity);
        
        -- Trigger for updated_at
        CREATE OR REPLACE FUNCTION update_users_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS trigger_update_users_updated_at ON users;
        CREATE TRIGGER trigger_update_users_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION update_users_updated_at();
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
    
    # ===================
    # TELEGRAM METHODS
    # ===================
    
    async def create_telegram_user(self, telegram_id: int, telegram_username: Optional[str] = None,
                                 telegram_first_name: Optional[str] = None, telegram_last_name: Optional[str] = None,
                                 telegram_phone: Optional[str] = None, permission_level: str = 'user') -> Optional[int]:
        """
        Tworzy nowego użytkownika Telegram.
        
        Args:
            telegram_id: ID Telegram użytkownika
            telegram_username: Username Telegram (bez @)
            telegram_first_name: Imię użytkownika
            telegram_last_name: Nazwisko użytkownika
            telegram_phone: Numer telefonu
            permission_level: Poziom uprawnień
            
        Returns:
            Optional[int]: ID utworzonego użytkownika lub None w przypadku błędu
        """
        try:
            user_id = await self.fetch_val(
                """
                INSERT INTO users (
                    telegram_id, telegram_username, telegram_first_name, 
                    telegram_last_name, telegram_phone, permission_level,
                    last_login, last_activity
                ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    telegram_username = EXCLUDED.telegram_username,
                    telegram_first_name = EXCLUDED.telegram_first_name,
                    telegram_last_name = EXCLUDED.telegram_last_name,
                    telegram_phone = EXCLUDED.telegram_phone,
                    last_login = CURRENT_TIMESTAMP,
                    last_activity = CURRENT_TIMESTAMP
                RETURNING id
                """,
                telegram_id, telegram_username, telegram_first_name, 
                telegram_last_name, telegram_phone, permission_level
            )
            logger.info(f"Utworzono/zaktualizowano użytkownika Telegram: {telegram_id} z ID: {user_id}")
            return user_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia użytkownika Telegram: {e}", exc_info=True)
            return None
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Pobiera użytkownika po Telegram ID.
        
        Args:
            telegram_id: ID Telegram użytkownika
            
        Returns:
            Optional[Dict[str, Any]]: Dane użytkownika lub None
        """
        return await self.fetch_one(
            """
            SELECT id, username, email, telegram_id, telegram_username,
                   telegram_first_name, telegram_last_name, telegram_phone,
                   permission_level, is_active, is_banned,
                   created_at, updated_at, last_activity, last_login,
                   settings, preferences, stats
            FROM users 
            WHERE telegram_id = $1
            """,
            telegram_id
        )
    
    async def update_telegram_info(self, telegram_id: int, **kwargs) -> bool:
        """
        Aktualizuje informacje Telegram użytkownika.
        
        Args:
            telegram_id: ID Telegram użytkownika
            **kwargs: Pola do aktualizacji
            
        Returns:
            bool: True jeśli aktualizacja się udała
        """
        try:
            update_fields = []
            values = []
            param_count = 1
            
            allowed_fields = {
                'telegram_username': 'telegram_username',
                'telegram_first_name': 'telegram_first_name', 
                'telegram_last_name': 'telegram_last_name',
                'telegram_phone': 'telegram_phone',
                'permission_level': 'permission_level',
                'is_active': 'is_active',
                'is_banned': 'is_banned',
                'settings': 'settings',
                'preferences': 'preferences',
                'stats': 'stats'
            }
            
            for field, db_field in allowed_fields.items():
                if field in kwargs:
                    update_fields.append(f"{db_field} = ${param_count}")
                    values.append(kwargs[field])
                    param_count += 1
            
            if not update_fields:
                return False
            
            # Dodaj last_activity update
            update_fields.append(f"last_activity = ${param_count}")
            values.append(datetime.now())
            param_count += 1
            
            values.append(telegram_id)
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE telegram_id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano użytkownika Telegram z ID: {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji użytkownika Telegram: {e}", exc_info=True)
            return False
    
    async def update_last_activity(self, telegram_id: int) -> bool:
        """
        Aktualizuje ostatnią aktywność użytkownika.
        
        Args:
            telegram_id: ID Telegram użytkownika
            
        Returns:
            bool: True jeśli aktualizacja się udała
        """
        try:
            await self.execute_query(
                "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE telegram_id = $1",
                telegram_id
            )
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji last_activity: {e}")
            return False
    
    # ===================
    # PERMISSION METHODS
    # ===================
    
    async def set_permission_level(self, telegram_id: int, permission_level: str) -> bool:
        """
        Ustawia poziom uprawnień użytkownika.
        
        Args:
            telegram_id: ID Telegram użytkownika
            permission_level: Nowy poziom uprawnień
            
        Returns:
            bool: True jeśli aktualizacja się udała
        """
        valid_levels = ['guest', 'user', 'trader', 'admin', 'super_admin']
        if permission_level not in valid_levels:
            logger.error(f"Nieprawidłowy poziom uprawnień: {permission_level}")
            return False
        
        try:
            await self.execute_query(
                "UPDATE users SET permission_level = $1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $2",
                permission_level, telegram_id
            )
            logger.info(f"Zmieniono poziom uprawnień użytkownika {telegram_id} na {permission_level}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas zmiany uprawnień: {e}", exc_info=True)
            return False
    
    async def ban_user(self, telegram_id: int, banned: bool = True) -> bool:
        """
        Banuje/odbanowuje użytkownika.
        
        Args:
            telegram_id: ID Telegram użytkownika
            banned: True jeśli ma być zbanowany, False jeśli odbanowany
            
        Returns:
            bool: True jeśli operacja się udała
        """
        try:
            await self.execute_query(
                "UPDATE users SET is_banned = $1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $2",
                banned, telegram_id
            )
            action = "zbanowano" if banned else "odbanowano"
            logger.info(f"Użytkownika {telegram_id} {action}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas ban/unban użytkownika: {e}", exc_info=True)
            return False
    
    async def activate_user(self, telegram_id: int, active: bool = True) -> bool:
        """
        Aktywuje/dezaktywuje użytkownika.
        
        Args:
            telegram_id: ID Telegram użytkownika
            active: True jeśli ma być aktywny, False jeśli nieaktywny
            
        Returns:
            bool: True jeśli operacja się udała
        """
        try:
            await self.execute_query(
                "UPDATE users SET is_active = $1, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = $2",
                active, telegram_id
            )
            action = "aktywowano" if active else "dezaktywowano"
            logger.info(f"Użytkownika {telegram_id} {action}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktywacji/dezaktywacji użytkownika: {e}", exc_info=True)
            return False
    
    # ===================
    # QUERY METHODS
    # ===================
    
    async def get_users_by_permission(self, permission_level: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera użytkowników o określonym poziomie uprawnień.
        
        Args:
            permission_level: Poziom uprawnień
            limit: Limit wyników
            offset: Offset
            
        Returns:
            List[Dict[str, Any]]: Lista użytkowników
        """
        return await self.fetch_all(
            """
            SELECT id, telegram_id, telegram_username, telegram_first_name, 
                   telegram_last_name, permission_level, is_active, is_banned,
                   created_at, last_activity
            FROM users 
            WHERE permission_level = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            permission_level, limit, offset
        )
    
    async def get_active_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera aktywnych użytkowników.
        
        Args:
            limit: Limit wyników
            offset: Offset
            
        Returns:
            List[Dict[str, Any]]: Lista aktywnych użytkowników
        """
        return await self.fetch_all(
            """
            SELECT id, telegram_id, telegram_username, telegram_first_name,
                   telegram_last_name, permission_level, last_activity
            FROM users 
            WHERE is_active = TRUE AND is_banned = FALSE
            ORDER BY last_activity DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
    
    async def get_recent_users(self, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera użytkowników aktywnych w ostatnich X dniach.
        
        Args:
            days: Liczba dni wstecz
            limit: Limit wyników
            
        Returns:
            List[Dict[str, Any]]: Lista ostatnio aktywnych użytkowników
        """
        return await self.fetch_all(
            """
            SELECT id, telegram_id, telegram_username, telegram_first_name,
                   telegram_last_name, permission_level, last_activity
            FROM users 
            WHERE last_activity > CURRENT_TIMESTAMP - INTERVAL '%s days'
                AND is_active = TRUE AND is_banned = FALSE
            ORDER BY last_activity DESC
            LIMIT $1
            """ % days,
            limit
        )
    
    async def search_telegram_users(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Wyszukuje użytkowników Telegram po nazwie/username.
        
        Args:
            search_term: Termin wyszukiwania
            
        Returns:
            List[Dict[str, Any]]: Lista znalezionych użytkowników
        """
        return await self.fetch_all(
            """
            SELECT id, telegram_id, telegram_username, telegram_first_name,
                   telegram_last_name, permission_level, is_active, is_banned,
                   created_at, last_activity
            FROM users 
            WHERE (telegram_username ILIKE $1 
                   OR telegram_first_name ILIKE $1 
                   OR telegram_last_name ILIKE $1
                   OR CONCAT(telegram_first_name, ' ', telegram_last_name) ILIKE $1)
            ORDER BY last_activity DESC
            """,
            f"%{search_term}%"
        )
    
    # ===================
    # STATISTICS METHODS
    # ===================
    
    async def get_user_statistics(self) -> Dict[str, Any]:
        """
        Pobiera statystyki użytkowników.
        
        Returns:
            Dict[str, Any]: Statystyki użytkowników
        """
        try:
            stats = await self.fetch_one(
                """
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(*) FILTER (WHERE is_active = TRUE) as active_users,
                    COUNT(*) FILTER (WHERE is_banned = TRUE) as banned_users,
                    COUNT(*) FILTER (WHERE telegram_id IS NOT NULL) as telegram_users,
                    COUNT(*) FILTER (WHERE permission_level = 'admin') as admin_users,
                    COUNT(*) FILTER (WHERE permission_level = 'trader') as trader_users,
                    COUNT(*) FILTER (WHERE last_activity > CURRENT_TIMESTAMP - INTERVAL '24 hours') as active_last_24h,
                    COUNT(*) FILTER (WHERE last_activity > CURRENT_TIMESTAMP - INTERVAL '7 days') as active_last_7d,
                    COUNT(*) FILTER (WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '30 days') as new_users_30d
                FROM users
                """
            )
            return dict(stats) if stats else {}
        except Exception as e:
            logger.error(f"Błąd podczas pobierania statystyk użytkowników: {e}")
            return {}
    
    # ===================
    # LOGGING METHODS  
    # ===================
    
    async def log_action(self, telegram_id: int, action: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """
        Loguje akcję użytkownika (opcjonalnie może być rozszerzone o osobną tabelę logów).
        
        Args:
            telegram_id: ID Telegram użytkownika
            action: Nazwa akcji
            details: Szczegóły akcji
            
        Returns:
            bool: True jeśli logowanie się udało
        """
        try:
            # Na razie aktualizuj tylko last_activity i stats
            stats_update = {
                "last_action": action,
                "last_action_time": datetime.now().isoformat(),
                "total_actions": 1
            }
            
            if details:
                stats_update["last_action_details"] = details
            
            await self.execute_query(
                """
                UPDATE users 
                SET last_activity = CURRENT_TIMESTAMP,
                    stats = COALESCE(stats, '{}'::jsonb) || $1::jsonb
                WHERE telegram_id = $2
                """,
                json.dumps(stats_update), telegram_id
            )
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas logowania akcji użytkownika: {e}")
            return False 