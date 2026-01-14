"""
Moduł autentykacji dla FastAPI.

Zawiera dependency do weryfikacji tokenów sesji oraz sprawdzania uprawnień.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Security scheme dla Bearer token
security = HTTPBearer(auto_error=False)

# Singleton dla bazy danych w auth module
_db_instance = None
_db_lock = asyncio.Lock()


async def _get_db():
    """Pobiera singleton instancji bazy danych."""
    global _db_instance
    
    if _db_instance is not None:
        return _db_instance
    
    async with _db_lock:
        if _db_instance is None:
            from .db.database_facade import DatabaseFacade
            db_facade = DatabaseFacade()
            _db_instance = db_facade.get_database_postgresql()
            await _db_instance.init_db()
    
    return _db_instance


class AuthUser:
    """Klasa reprezentująca zalogowanego użytkownika."""
    
    def __init__(self, session_data: Dict[str, Any]):
        self.session_id: int = session_data.get('session_id')
        self.user_id: int = session_data.get('user_id')
        self.username: str = session_data.get('username')
        self.role: str = session_data.get('role')
        self.token: str = session_data.get('token')
        self.expires_at = session_data.get('expires_at')
        self._raw_data = session_data
    
    @property
    def id(self) -> int:
        """Alias dla user_id - dla wygody."""
        return self.user_id
    
    @property
    def is_admin(self) -> bool:
        """Sprawdza czy użytkownik jest administratorem."""
        return self.role == 'administrator'
    
    def __repr__(self) -> str:
        return f"AuthUser(id={self.user_id}, username='{self.username}', role='{self.role}')"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthUser]:
    """
    Dependency do pobierania aktualnie zalogowanego użytkownika.
    
    Waliduje token Bearer i zwraca AuthUser jeśli token jest prawidłowy.
    
    Args:
        request: Request FastAPI
        credentials: Credentials z nagłówka Authorization
        
    Returns:
        Optional[AuthUser]: Zalogowany użytkownik lub None
    """
    if credentials is None:
        return None
    
    token = credentials.credentials
    
    try:
        db = await _get_db()
        sessions_table = db.get_factory().get_user_sessions_table()
        session_data = await sessions_table.validate_token(token)
        
        if session_data is None:
            return None
        
        return AuthUser(session_data)
        
    except Exception as e:
        logger.error(f"Błąd podczas walidacji tokenu: {e}")
        return None


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthUser:
    """
    Dependency wymagająca autentykacji.
    
    Rzuca HTTPException 401 jeśli użytkownik nie jest zalogowany.
    
    Args:
        request: Request FastAPI
        credentials: Credentials z nagłówka Authorization
        
    Returns:
        AuthUser: Zalogowany użytkownik
        
    Raises:
        HTTPException: 401 jeśli brak autoryzacji
    """
    user = await get_current_user(request, credentials)
    
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Nie jesteś zalogowany. Podaj prawidłowy token w nagłówku Authorization.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user


async def require_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthUser:
    """
    Dependency wymagająca uprawnień administratora.
    
    Rzuca HTTPException 401 jeśli użytkownik nie jest zalogowany,
    lub HTTPException 403 jeśli użytkownik nie jest administratorem.
    
    Args:
        request: Request FastAPI
        credentials: Credentials z nagłówka Authorization
        
    Returns:
        AuthUser: Zalogowany administrator
        
    Raises:
        HTTPException: 401 jeśli brak autoryzacji, 403 jeśli brak uprawnień
    """
    user = await require_auth(request, credentials)
    
    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail=f"Brak uprawnień. Ta operacja wymaga roli administratora. Twoja rola: {user.role}"
        )
    
    return user


def get_client_ip(request: Request) -> Optional[str]:
    """
    Pobiera adres IP klienta z requestu.
    
    Uwzględnia nagłówki proxy (X-Forwarded-For, X-Real-IP).
    
    Args:
        request: Request FastAPI
        
    Returns:
        Optional[str]: Adres IP klienta
    """
    # Sprawdź nagłówki proxy
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Weź pierwszy IP z listy (oryginalny klient)
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Pobierz IP z połączenia
    if request.client:
        return request.client.host
    
    return None


def get_user_agent(request: Request) -> Optional[str]:
    """
    Pobiera User-Agent z requestu.
    
    Args:
        request: Request FastAPI
        
    Returns:
        Optional[str]: User-Agent
    """
    return request.headers.get("User-Agent")

