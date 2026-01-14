"""
Tabela sesji użytkowników.

Przechowuje tokeny sesji użytkowników z czasem wygaśnięcia.
Pozwala na weryfikację czy użytkownik jest wciąż zalogowany.
"""

from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
import secrets
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)


class UserSessionsTable(AbstractTable):
    """Klasa do zarządzania tabelą UserSessions."""
    
    # Domyślny czas wygaśnięcia sesji (24 godziny)
    DEFAULT_EXPIRY_HOURS = 24
    
    def create_table(self) -> str:
        """Tworzy tabelę user_sessions z odpowiednią strukturą."""
        return """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token);
        CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
        """
    
    @staticmethod
    def generate_token() -> str:
        """
        Generuje bezpieczny token sesji.
        
        Returns:
            str: 64-znakowy token w formacie hex
        """
        return secrets.token_hex(32)
    
    @staticmethod
    def parse_expiry_period(period_str: str) -> timedelta:
        """
        Parsuje string okresu wygaśnięcia do timedelta.
        
        Format: <number><unit> gdzie unit to:
        - s: sekundy
        - m: minuty
        - h: godziny
        - d: dni
        - w: tygodnie
        
        Przykłady: "15h", "7d", "30m", "2w"
        
        Args:
            period_str: String okresu wygaśnięcia
            
        Returns:
            timedelta: Okres wygaśnięcia
            
        Raises:
            ValueError: Jeśli format jest nieprawidłowy
        """
        if not period_str:
            return timedelta(hours=UserSessionsTable.DEFAULT_EXPIRY_HOURS)
        
        pattern = r'^(\d+)([smhdw])$'
        match = re.match(pattern, period_str.lower().strip())
        
        if not match:
            raise ValueError(
                f"Nieprawidłowy format okresu wygaśnięcia: '{period_str}'. "
                f"Oczekiwany format: <number><unit> np. 15h, 7d, 30m"
            )
        
        value = int(match.group(1))
        unit = match.group(2)
        
        unit_mapping = {
            's': timedelta(seconds=value),
            'm': timedelta(minutes=value),
            'h': timedelta(hours=value),
            'd': timedelta(days=value),
            'w': timedelta(weeks=value)
        }
        
        return unit_mapping[unit]
    
    async def create(
        self,
        user_id: int,
        expiry_period: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Tworzy nową sesję dla użytkownika.
        
        Args:
            user_id: ID użytkownika
            expiry_period: Okres wygaśnięcia (np. "15h", "7d")
            ip_address: Adres IP klienta
            user_agent: User-Agent klienta
            
        Returns:
            Optional[Dict[str, Any]]: Dane sesji z tokenem lub None w przypadku błędu
        """
        try:
            token = self.generate_token()
            
            # Oblicz czas wygaśnięcia
            if expiry_period:
                expiry_delta = self.parse_expiry_period(expiry_period)
            else:
                expiry_delta = timedelta(hours=self.DEFAULT_EXPIRY_HOURS)
            
            expires_at = datetime.now() + expiry_delta
            
            session_id = await self.fetch_val(
                """
                INSERT INTO user_sessions (user_id, token, expires_at, ip_address, user_agent) 
                VALUES ($1, $2, $3, $4, $5) 
                RETURNING id
                """,
                user_id, token, expires_at, ip_address, user_agent
            )
            
            logger.info(f"Utworzono sesję dla użytkownika ID: {user_id}, wygasa: {expires_at}")
            
            return {
                'id': session_id,
                'user_id': user_id,
                'token': token,
                'expires_at': expires_at,
                'created_at': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia sesji: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera sesję po ID."""
        return await self.fetch_one(
            """
            SELECT id, user_id, token, expires_at, created_at, last_activity, ip_address, user_agent 
            FROM user_sessions 
            WHERE id = $1
            """,
            record_id
        )
    
    async def get_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera sesję po tokenie.
        
        Args:
            token: Token sesji
            
        Returns:
            Optional[Dict[str, Any]]: Dane sesji lub None jeśli nie znaleziono
        """
        return await self.fetch_one(
            """
            SELECT id, user_id, token, expires_at, created_at, last_activity, ip_address, user_agent 
            FROM user_sessions 
            WHERE token = $1
            """,
            token
        )
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Waliduje token sesji i zwraca dane sesji jeśli jest aktywna.
        
        Sprawdza czy:
        - Token istnieje w bazie
        - Sesja nie wygasła
        
        Args:
            token: Token sesji do walidacji
            
        Returns:
            Optional[Dict[str, Any]]: Dane sesji z danymi użytkownika lub None jeśli nieaktywna
        """
        try:
            # Pobierz sesję z danymi użytkownika
            result = await self.fetch_one(
                """
                SELECT 
                    s.id as session_id,
                    s.user_id,
                    s.token,
                    s.expires_at,
                    s.created_at,
                    s.last_activity,
                    u.username,
                    u.role,
                    u.is_active as user_is_active
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = $1
                """,
                token
            )
            
            if not result:
                logger.debug(f"Token sesji nie znaleziony")
                return None
            
            # Sprawdź czy użytkownik jest aktywny
            if not result.get('user_is_active', False):
                logger.warning(f"Użytkownik {result['username']} jest zablokowany")
                return None
            
            # Sprawdź czy sesja nie wygasła
            expires_at = result['expires_at']
            if isinstance(expires_at, datetime) and expires_at < datetime.now():
                logger.debug(f"Sesja wygasła: {expires_at}")
                # Opcjonalnie: usuń wygasłą sesję
                await self.delete(result['session_id'])
                return None
            
            # Aktualizuj last_activity
            await self.update_activity(result['session_id'])
            
            return result
            
        except Exception as e:
            logger.error(f"Błąd podczas walidacji tokena: {e}", exc_info=True)
            return None
    
    async def update_activity(self, session_id: int) -> bool:
        """
        Aktualizuje czas ostatniej aktywności sesji.
        
        Args:
            session_id: ID sesji
            
        Returns:
            bool: True jeśli aktualizacja się powiodła
        """
        try:
            await self.execute_query(
                "UPDATE user_sessions SET last_activity = CURRENT_TIMESTAMP WHERE id = $1",
                session_id
            )
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji aktywności sesji: {e}")
            return False
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje sesję o podanym ID."""
        try:
            update_fields = []
            params = []
            param_counter = 1
            
            if 'expires_at' in kwargs:
                update_fields.append(f"expires_at = ${param_counter}")
                params.append(kwargs['expires_at'])
                param_counter += 1
            
            if 'ip_address' in kwargs:
                update_fields.append(f"ip_address = ${param_counter}")
                params.append(kwargs['ip_address'])
                param_counter += 1
            
            if 'user_agent' in kwargs:
                update_fields.append(f"user_agent = ${param_counter}")
                params.append(kwargs['user_agent'])
                param_counter += 1
            
            if not update_fields:
                return False
            
            params.append(record_id)
            query = f"UPDATE user_sessions SET {', '.join(update_fields)} WHERE id = ${param_counter}"
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano sesję z ID: {record_id}")
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji sesji: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa sesję o podanym ID."""
        try:
            await self.execute_query("DELETE FROM user_sessions WHERE id = $1", record_id)
            logger.info(f"Usunięto sesję z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania sesji: {e}", exc_info=True)
            return False
    
    async def delete_by_token(self, token: str) -> bool:
        """Usuwa sesję po tokenie (logout)."""
        try:
            await self.execute_query("DELETE FROM user_sessions WHERE token = $1", token)
            logger.info(f"Usunięto sesję po tokenie")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania sesji: {e}", exc_info=True)
            return False
    
    async def delete_user_sessions(self, user_id: int) -> int:
        """
        Usuwa wszystkie sesje użytkownika.
        
        Args:
            user_id: ID użytkownika
            
        Returns:
            int: Liczba usuniętych sesji
        """
        try:
            result = await self.fetch_val(
                "WITH deleted AS (DELETE FROM user_sessions WHERE user_id = $1 RETURNING *) SELECT COUNT(*) FROM deleted",
                user_id
            )
            count = result or 0
            logger.info(f"Usunięto {count} sesji użytkownika ID: {user_id}")
            return count
        except Exception as e:
            logger.error(f"Błąd podczas usuwania sesji użytkownika: {e}", exc_info=True)
            return 0
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie sesje z limitem i offsetem."""
        return await self.fetch_all(
            """
            SELECT id, user_id, token, expires_at, created_at, last_activity, ip_address, user_agent 
            FROM user_sessions 
            ORDER BY created_at DESC 
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
    
    async def get_user_sessions(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie sesje użytkownika."""
        return await self.fetch_all(
            """
            SELECT id, user_id, token, expires_at, created_at, last_activity, ip_address, user_agent 
            FROM user_sessions 
            WHERE user_id = $1
            ORDER BY created_at DESC 
            LIMIT $2 OFFSET $3
            """,
            user_id, limit, offset
        )
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Usuwa wszystkie wygasłe sesje.
        
        Returns:
            int: Liczba usuniętych sesji
        """
        try:
            result = await self.fetch_val(
                """
                WITH deleted AS (
                    DELETE FROM user_sessions 
                    WHERE expires_at < CURRENT_TIMESTAMP 
                    RETURNING *
                ) 
                SELECT COUNT(*) FROM deleted
                """
            )
            count = result or 0
            if count > 0:
                logger.info(f"Usunięto {count} wygasłych sesji")
            return count
        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia wygasłych sesji: {e}", exc_info=True)
            return 0
    
    async def count_active_sessions(self) -> int:
        """Zwraca liczbę aktywnych (niewygasłych) sesji."""
        result = await self.fetch_val(
            "SELECT COUNT(*) FROM user_sessions WHERE expires_at > CURRENT_TIMESTAMP"
        )
        return result or 0
    
    async def count_user_active_sessions(self, user_id: int) -> int:
        """Zwraca liczbę aktywnych sesji użytkownika."""
        result = await self.fetch_val(
            "SELECT COUNT(*) FROM user_sessions WHERE user_id = $1 AND expires_at > CURRENT_TIMESTAMP",
            user_id
        )
        return result or 0

