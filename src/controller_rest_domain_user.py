"""
REST API Controller dla domeny użytkowników i autentykacji.

Ten kontroler implementuje endpointy REST dla:
- Logowania użytkowników (auth/login)
- Wylogowywania (auth/logout)
- Weryfikacji sesji (auth/verify)
- Zarządzania użytkownikami (CRUD) - tylko dla administratorów
- Pobierania profilu zalogowanego użytkownika

Autor: AI Assistant
"""

import asyncio
import logging
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Path, Body, Request, Depends, UploadFile, File
from pydantic import BaseModel, Field

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL
from .db.postgresql.tables.users_table import UsersTable

# Import Auth
from .auth import (
    AuthUser,
    require_auth,
    require_admin,
    get_client_ip,
    get_user_agent
)

# Import Config
from .config import config

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/user"
TAGS = ["User & Authentication"]

# Singleton dla DatabasePostgreSQL z blokadą dla bezpieczeństwa wątkowego
db_instance: Optional[DatabasePostgreSQL] = None
db_lock: asyncio.Lock = asyncio.Lock()


async def get_db() -> DatabasePostgreSQL:
    """
    Dependency do pobierania instancji DatabasePostgreSQL.
    Używa blokady aby uniknąć race condition podczas inicjalizacji.
    
    Returns:
        DatabasePostgreSQL: Instancja bazy danych PostgreSQL
    """
    global db_instance
    
    if db_instance is not None:
        return db_instance
    
    async with db_lock:
        # Double-check po uzyskaniu blokady
        if db_instance is None:
            db_facade = DatabaseFacade()
            new_instance = db_facade.get_database_postgresql()
            await new_instance.init_db()
            
            # Inicjalizuj administratora systemowego
            await _initialize_admin_user(new_instance)
            
            db_instance = new_instance
    
    return db_instance


async def _initialize_admin_user(db: DatabasePostgreSQL) -> None:
    """
    Inicjalizuje użytkownika administracyjnego na podstawie zmiennych środowiskowych.
    
    Administrator jest tworzony z ID = 0 jeśli:
    - Nie istnieje jeszcze administrator o ID 0
    - LUB zmienna ADMIN_CREATE_FORCE=true
    
    Args:
        db: Instancja bazy danych
    """
    auth_config = config.auth_config
    admin_username = auth_config['admin_username']
    admin_password = auth_config['admin_password']
    admin_create_force = auth_config['admin_create_force']
    
    if not admin_password:
        logger.warning(
            "⚠️ ADMIN_PASSWORD nie jest ustawiony! "
            "Administrator systemowy nie zostanie utworzony automatycznie."
        )
        return
    
    users_table = db.get_factory().get_users_table()
    admin_id = UsersTable.ADMIN_USER_ID  # 0
    
    # Sprawdź czy administrator już istnieje
    admin_exists = await users_table.admin_exists(admin_id)
    
    if admin_exists and not admin_create_force:
        logger.info(f"ℹ️ Administrator systemowy (ID: {admin_id}) już istnieje. Pomijam tworzenie.")
        return
    
    if admin_exists and admin_create_force:
        logger.warning(f"⚠️ ADMIN_CREATE_FORCE=true - nadpisuję administratora systemowego (ID: {admin_id})")
        # Usuń istniejącego administratora
        await users_table.delete(admin_id)
    
    # Utwórz administratora
    try:
        created_id = await users_table.create_with_id(
            user_id=admin_id,
            username=admin_username,
            password=admin_password,
            role=UsersTable.ROLE_ADMINISTRATOR,
            is_active=True
        )
        
        if created_id is not None:
            logger.info(f"✅ Utworzono administratora systemowego: {admin_username} (ID: {admin_id})")
        else:
            logger.error(f"❌ Nie udało się utworzyć administratora systemowego")
            
    except Exception as e:
        logger.error(f"❌ Błąd podczas tworzenia administratora systemowego: {e}")


# ===================
# MODELE PYDANTIC
# ===================

class LoginRequest(BaseModel):
    """Request do logowania."""
    username: str = Field(..., min_length=1, max_length=100, description="Nazwa użytkownika")
    password: str = Field(..., min_length=1, description="Hasło")


class LoginResponse(BaseModel):
    """Odpowiedź po zalogowaniu."""
    success: bool
    message: str
    token: Optional[str] = None
    expires_at: Optional[datetime] = None
    user: Optional[Dict[str, Any]] = None


class LogoutResponse(BaseModel):
    """Odpowiedź po wylogowaniu."""
    success: bool
    message: str


class VerifyResponse(BaseModel):
    """Odpowiedź weryfikacji sesji."""
    valid: bool
    message: str
    user: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class UserResponse(BaseModel):
    """Odpowiedź z danymi użytkownika."""
    id: int
    username: str
    role: str
    is_active: bool
    has_avatar: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserCreateRequest(BaseModel):
    """Request do tworzenia użytkownika."""
    username: str = Field(..., min_length=3, max_length=100, description="Nazwa użytkownika")
    password: str = Field(..., min_length=8, description="Hasło (min. 8 znaków)")
    role: str = Field(default="user", description="Rola użytkownika (user lub administrator)")
    is_active: bool = Field(default=True, description="Czy użytkownik jest aktywny")


class UserUpdateRequest(BaseModel):
    """Request do aktualizacji użytkownika."""
    username: Optional[str] = Field(None, min_length=3, max_length=100, description="Nowa nazwa użytkownika")
    password: Optional[str] = Field(None, min_length=8, description="Nowe hasło")
    role: Optional[str] = Field(None, description="Nowa rola")
    is_active: Optional[bool] = Field(None, description="Nowy status aktywności")


class PasswordChangeRequest(BaseModel):
    """Request do zmiany hasła."""
    current_password: str = Field(..., description="Aktualne hasło")
    new_password: str = Field(..., min_length=8, description="Nowe hasło (min. 8 znaków)")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class UserListResponse(BaseModel):
    """Lista użytkowników z paginacją."""
    users: List[UserResponse]
    pagination: PaginationInfo


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# ===================
# HELPER FUNCTIONS
# ===================

def user_to_response(user: Dict[str, Any]) -> UserResponse:
    """Konwertuje dane użytkownika z bazy na response model."""
    return UserResponse(
        id=user['id'],
        username=user['username'],
        role=user['role'],
        is_active=user.get('is_active', True),
        has_avatar=user.get('avatar') is not None,
        created_at=user.get('created_at'),
        updated_at=user.get('updated_at')
    )


# ===================
# ENDPOINTY GŁÓWNE
# ===================

@router.get("", response_model=Dict[str, Any])
async def user_info():
    """Informacje o dostępnych endpointach użytkownika."""
    return {
        "message": "User & Authentication REST API",
        "version": "1.0.0",
        "available_endpoints": {
            "auth": {
                "login": "POST /user/auth/login - Logowanie użytkownika",
                "logout": "POST /user/auth/logout - Wylogowanie użytkownika",
                "verify": "GET /user/auth/verify - Weryfikacja sesji"
            },
            "profile": {
                "me": "GET /user/me - Profil zalogowanego użytkownika",
                "change_password": "POST /user/me/password - Zmiana hasła",
                "avatar": "GET /user/me/avatar - Pobierz avatar",
                "upload_avatar": "POST /user/me/avatar - Wgraj avatar"
            },
            "admin": {
                "list": "GET /user/list - Lista użytkowników (admin)",
                "create": "POST /user/create - Utwórz użytkownika (admin)",
                "get": "GET /user/{id} - Szczegóły użytkownika (admin)",
                "update": "PUT /user/{id} - Aktualizuj użytkownika (admin)",
                "delete": "DELETE /user/{id} - Usuń użytkownika (admin)"
            }
        }
    }


# ===================
# AUTENTYKACJA
# ===================

@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest = Body(...)
):
    """
    Logowanie użytkownika.
    
    Endpoint autentykacji - nie wymaga wcześniejszego zalogowania.
    
    Args:
        login_data: Dane logowania (username, password)
        
    Returns:
        LoginResponse: Token sesji i dane użytkownika
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        sessions_table = db.get_factory().get_user_sessions_table()
        
        # Autentykuj użytkownika
        user = await users_table.authenticate(login_data.username, login_data.password)
        
        if not user:
            logger.warning(f"Nieudane logowanie dla: {login_data.username}")
            raise HTTPException(
                status_code=401,
                detail="Nieprawidłowa nazwa użytkownika lub hasło"
            )
        
        # Pobierz okres wygaśnięcia sesji z konfiguracji
        expiry_period = config.session_expiry_period
        
        # Utwórz sesję
        session = await sessions_table.create(
            user_id=user['id'],
            expiry_period=expiry_period,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request)
        )
        
        if not session:
            raise HTTPException(
                status_code=500,
                detail="Nie udało się utworzyć sesji"
            )
        
        logger.info(f"Użytkownik zalogowany: {user['username']} (ID: {user['id']})")
        
        return LoginResponse(
            success=True,
            message="Zalogowano pomyślnie",
            token=session['token'],
            expires_at=session['expires_at'],
            user={
                'id': user['id'],
                'username': user['username'],
                'role': user['role']
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas logowania: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(current_user: AuthUser = Depends(require_auth)):
    """
    Wylogowanie użytkownika.
    
    Usuwa bieżącą sesję użytkownika.
    
    Returns:
        LogoutResponse: Potwierdzenie wylogowania
    """
    try:
        db = await get_db()
        sessions_table = db.get_factory().get_user_sessions_table()
        
        # Usuń sesję
        await sessions_table.delete_by_token(current_user.token)
        
        logger.info(f"Użytkownik wylogowany: {current_user.username}")
        
        return LogoutResponse(
            success=True,
            message="Wylogowano pomyślnie"
        )
        
    except Exception as e:
        logger.error(f"Błąd podczas wylogowania: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify_session(current_user: AuthUser = Depends(require_auth)):
    """
    Weryfikacja sesji użytkownika.
    
    Sprawdza czy token jest prawidłowy i sesja aktywna.
    
    Returns:
        VerifyResponse: Status sesji i dane użytkownika
    """
    return VerifyResponse(
        valid=True,
        message="Sesja aktywna",
        user={
            'id': current_user.user_id,
            'username': current_user.username,
            'role': current_user.role
        },
        expires_at=current_user.expires_at
    )


# ===================
# PROFIL UŻYTKOWNIKA
# ===================

@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: AuthUser = Depends(require_auth)):
    """
    Pobiera profil zalogowanego użytkownika.
    
    Returns:
        UserResponse: Dane profilu użytkownika
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        user = await users_table.get_by_id(current_user.user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
        
        return user_to_response(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania profilu: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/me/password", response_model=StandardResponse)
async def change_password(
    password_data: PasswordChangeRequest = Body(...),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Zmiana hasła zalogowanego użytkownika.
    
    Args:
        password_data: Aktualne i nowe hasło
        
    Returns:
        StandardResponse: Potwierdzenie zmiany hasła
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        # Pobierz użytkownika z hashem hasła
        user = await users_table.get_by_id(current_user.user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
        
        # Weryfikuj aktualne hasło
        if not users_table.verify_password(password_data.current_password, user['password_hash']):
            raise HTTPException(status_code=401, detail="Nieprawidłowe aktualne hasło")
        
        # Aktualizuj hasło
        success = await users_table.update(current_user.user_id, password=password_data.new_password)
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się zmienić hasła")
        
        logger.info(f"Użytkownik {current_user.username} zmienił hasło")
        
        return StandardResponse(
            success=True,
            message="Hasło zostało zmienione"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas zmiany hasła: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/me/avatar")
async def get_my_avatar(current_user: AuthUser = Depends(require_auth)):
    """
    Pobiera avatar zalogowanego użytkownika.
    
    Returns:
        Obraz avatara w formacie base64 lub informacja o braku avatara
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        user = await users_table.get_by_id(current_user.user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
        
        avatar = user.get('avatar')
        
        if not avatar:
            return {
                "has_avatar": False,
                "message": "Użytkownik nie ma ustawionego avatara"
            }
        
        # Zwróć avatar jako base64
        avatar_base64 = base64.b64encode(avatar).decode('utf-8')
        
        return {
            "has_avatar": True,
            "avatar_base64": avatar_base64
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania avatara: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/me/avatar", response_model=StandardResponse)
async def upload_my_avatar(
    avatar: UploadFile = File(..., description="Plik obrazka avatara"),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Wgrywa avatar dla zalogowanego użytkownika.
    
    Args:
        avatar: Plik obrazka (max 5MB)
        
    Returns:
        StandardResponse: Potwierdzenie wgrania avatara
    """
    try:
        # Sprawdź typ pliku
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if avatar.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy typ pliku. Dozwolone: {', '.join(allowed_types)}"
            )
        
        # Odczytaj zawartość pliku
        avatar_bytes = await avatar.read()
        
        # Sprawdź rozmiar (max 5MB)
        max_size = 5 * 1024 * 1024  # 5MB
        if len(avatar_bytes) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Plik zbyt duży. Maksymalny rozmiar: 5MB"
            )
        
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        # Aktualizuj avatar
        success = await users_table.update(current_user.user_id, avatar=avatar_bytes)
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się zapisać avatara")
        
        logger.info(f"Użytkownik {current_user.username} wgrał avatar ({len(avatar_bytes)} bytes)")
        
        return StandardResponse(
            success=True,
            message="Avatar został zapisany",
            data={"size_bytes": len(avatar_bytes)}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas wgrywania avatara: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/me/avatar", response_model=StandardResponse)
async def delete_my_avatar(current_user: AuthUser = Depends(require_auth)):
    """
    Usuwa avatar zalogowanego użytkownika.
    
    Returns:
        StandardResponse: Potwierdzenie usunięcia avatara
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        # Ustaw avatar na None
        success = await users_table.update(current_user.user_id, avatar=None)
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się usunąć avatara")
        
        logger.info(f"Użytkownik {current_user.username} usunął avatar")
        
        return StandardResponse(
            success=True,
            message="Avatar został usunięty"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas usuwania avatara: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


# ===================
# ZARZĄDZANIE UŻYTKOWNIKAMI (ADMIN)
# ===================

@router.get("/list", response_model=UserListResponse)
async def list_users(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników na stronę"),
    offset: int = Query(default=0, ge=0, description="Offset wyników"),
    current_user: AuthUser = Depends(require_admin)
):
    """
    Lista wszystkich użytkowników (tylko dla administratorów).
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        UserListResponse: Lista użytkowników z paginacją
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        # Pobierz użytkowników z dodatkowym rekordem dla sprawdzenia następnej strony
        users = await users_table.get_all(limit=limit + 1, offset=offset)
        
        # Sprawdź czy są następne strony
        has_more = len(users) > limit
        page_users = users[:limit]
        
        # Konwertuj na response model
        user_responses = [user_to_response(u) for u in page_users]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return UserListResponse(
            users=user_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Błąd podczas pobierania listy użytkowników: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/create", response_model=UserResponse)
async def create_user(
    user_data: UserCreateRequest = Body(...),
    current_user: AuthUser = Depends(require_admin)
):
    """
    Tworzy nowego użytkownika (tylko dla administratorów).
    
    Args:
        user_data: Dane nowego użytkownika
        
    Returns:
        UserResponse: Dane utworzonego użytkownika
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        # Sprawdź czy nazwa użytkownika jest dostępna
        existing = await users_table.get_by_username(user_data.username)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Nazwa użytkownika '{user_data.username}' jest już zajęta"
            )
        
        # Waliduj rolę
        if user_data.role not in UsersTable.VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowa rola. Dozwolone: {UsersTable.VALID_ROLES}"
            )
        
        # Utwórz użytkownika
        user_id = await users_table.create(
            username=user_data.username,
            password=user_data.password,
            role=user_data.role,
            is_active=user_data.is_active
        )
        
        if not user_id:
            raise HTTPException(status_code=500, detail="Nie udało się utworzyć użytkownika")
        
        # Pobierz utworzonego użytkownika
        user = await users_table.get_by_id(user_id)
        
        logger.info(f"Administrator {current_user.username} utworzył użytkownika: {user_data.username}")
        
        return user_to_response(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas tworzenia użytkownika: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int = Path(..., ge=0, description="ID użytkownika"),
    current_user: AuthUser = Depends(require_admin)
):
    """
    Pobiera szczegóły użytkownika (tylko dla administratorów).
    
    Args:
        user_id: ID użytkownika
        
    Returns:
        UserResponse: Dane użytkownika
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        user = await users_table.get_by_id(user_id)
        
        if not user:
            raise HTTPException(status_code=404, detail=f"Użytkownik o ID {user_id} nie istnieje")
        
        return user_to_response(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania użytkownika: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int = Path(..., ge=0, description="ID użytkownika"),
    user_data: UserUpdateRequest = Body(...),
    current_user: AuthUser = Depends(require_admin)
):
    """
    Aktualizuje użytkownika (tylko dla administratorów).
    
    Args:
        user_id: ID użytkownika
        user_data: Dane do aktualizacji
        
    Returns:
        UserResponse: Zaktualizowane dane użytkownika
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        
        # Sprawdź czy użytkownik istnieje
        existing = await users_table.get_by_id(user_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Użytkownik o ID {user_id} nie istnieje")
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        
        if user_data.username is not None:
            # Sprawdź czy nowa nazwa nie jest zajęta
            name_check = await users_table.get_by_username(user_data.username)
            if name_check and name_check['id'] != user_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Nazwa użytkownika '{user_data.username}' jest już zajęta"
                )
            update_data['username'] = user_data.username
        
        if user_data.password is not None:
            update_data['password'] = user_data.password
        
        if user_data.role is not None:
            if user_data.role not in UsersTable.VALID_ROLES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Nieprawidłowa rola. Dozwolone: {UsersTable.VALID_ROLES}"
                )
            update_data['role'] = user_data.role
        
        if user_data.is_active is not None:
            update_data['is_active'] = user_data.is_active
        
        if not update_data:
            raise HTTPException(status_code=400, detail="Brak danych do aktualizacji")
        
        # Aktualizuj użytkownika
        success = await users_table.update(user_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się zaktualizować użytkownika")
        
        # Pobierz zaktualizowanego użytkownika
        user = await users_table.get_by_id(user_id)
        
        logger.info(f"Administrator {current_user.username} zaktualizował użytkownika ID: {user_id}")
        
        return user_to_response(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas aktualizacji użytkownika: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/{user_id}", response_model=StandardResponse)
async def delete_user(
    user_id: int = Path(..., ge=0, description="ID użytkownika"),
    current_user: AuthUser = Depends(require_admin)
):
    """
    Usuwa użytkownika (tylko dla administratorów).
    
    Uwaga: Nie można usunąć własnego konta ani administratora systemowego (ID=0).
    
    Args:
        user_id: ID użytkownika
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        users_table = db.get_factory().get_users_table()
        sessions_table = db.get_factory().get_user_sessions_table()
        
        # Nie pozwól usunąć administratora systemowego
        if user_id == UsersTable.ADMIN_USER_ID:
            raise HTTPException(
                status_code=403,
                detail="Nie można usunąć administratora systemowego (ID=0)"
            )
        
        # Nie pozwól usunąć własnego konta
        if user_id == current_user.user_id:
            raise HTTPException(
                status_code=403,
                detail="Nie można usunąć własnego konta"
            )
        
        # Sprawdź czy użytkownik istnieje
        existing = await users_table.get_by_id(user_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Użytkownik o ID {user_id} nie istnieje")
        
        username = existing['username']
        
        # Usuń wszystkie sesje użytkownika
        deleted_sessions = await sessions_table.delete_user_sessions(user_id)
        
        # Usuń użytkownika
        success = await users_table.delete(user_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się usunąć użytkownika")
        
        logger.info(f"Administrator {current_user.username} usunął użytkownika: {username} (ID: {user_id})")
        
        return StandardResponse(
            success=True,
            message=f"Użytkownik '{username}' został usunięty",
            data={
                "deleted_user_id": user_id,
                "deleted_sessions_count": deleted_sessions
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas usuwania użytkownika: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


# ===================
# SESJE UŻYTKOWNIKÓW (ADMIN)
# ===================

@router.get("/sessions/active", response_model=Dict[str, Any])
async def get_active_sessions(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(require_admin)
):
    """
    Pobiera listę aktywnych sesji (tylko dla administratorów).
    
    Returns:
        Lista aktywnych sesji z informacjami o użytkownikach
    """
    try:
        db = await get_db()
        sessions_table = db.get_factory().get_user_sessions_table()
        
        sessions = await sessions_table.get_all(limit=limit, offset=offset)
        active_count = await sessions_table.count_active_sessions()
        
        return {
            "active_sessions": active_count,
            "sessions": [
                {
                    "id": s['id'],
                    "user_id": s['user_id'],
                    "created_at": s['created_at'],
                    "expires_at": s['expires_at'],
                    "last_activity": s['last_activity'],
                    "ip_address": s['ip_address']
                }
                for s in sessions
            ],
            "pagination": {
                "limit": limit,
                "offset": offset
            }
        }
        
    except Exception as e:
        logger.error(f"Błąd podczas pobierania sesji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.post("/sessions/cleanup", response_model=StandardResponse)
async def cleanup_expired_sessions(current_user: AuthUser = Depends(require_admin)):
    """
    Czyści wygasłe sesje (tylko dla administratorów).
    
    Returns:
        StandardResponse: Liczba usuniętych sesji
    """
    try:
        db = await get_db()
        sessions_table = db.get_factory().get_user_sessions_table()
        
        deleted_count = await sessions_table.cleanup_expired_sessions()
        
        logger.info(f"Administrator {current_user.username} wyczyścił {deleted_count} wygasłych sesji")
        
        return StandardResponse(
            success=True,
            message=f"Usunięto {deleted_count} wygasłych sesji",
            data={"deleted_count": deleted_count}
        )
        
    except Exception as e:
        logger.error(f"Błąd podczas czyszczenia sesji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


# ===================
# SAVED ANALYSES
# ===================

class SavedAnalysisCreate(BaseModel):
    """Model do tworzenia zapisanej analizy."""
    name: str = Field(..., min_length=1, max_length=255, description="Nazwa zapisanej analizy")
    description: Optional[str] = Field(None, max_length=1000, description="Opcjonalny opis")
    asset_id: int = Field(..., description="ID assetu")
    asset_name: Optional[str] = Field(None, description="Nazwa assetu")
    quote_name: Optional[str] = Field(None, description="Waluta kwotowana")
    exchange_id: Optional[int] = Field(None, description="ID giełdy")
    exchange_name: Optional[str] = Field(None, description="Nazwa giełdy")
    interval: str = Field(..., description="Interwał wykresu (np. '1h', '4h', '1d')")
    chart_visible_range: Optional[Dict[str, Any]] = Field(None, description="Widoczny zakres wykresu")
    selected_pattern_id: Optional[int] = Field(None, description="ID wybranego patternu")
    expanded_pattern_id: Optional[int] = Field(None, description="ID rozwiniętego patternu")
    pattern_display_options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Opcje wyświetlania patternów")
    shared_pattern_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Dane patternów dla cross-interval sharing")
    global_pattern_display: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Globalne ustawienia wyświetlania patternów")
    indicators: Optional[Dict[str, bool]] = Field(default_factory=dict, description="Widoczność indykatorów")
    unselected_alpha: Optional[float] = Field(default=0.15, ge=0, le=1, description="Alpha dla niewybranych patternów")
    auto_center_on_select: Optional[bool] = Field(default=True, description="Auto-center przy wyborze patternu")
    harmonic_pattern_ids: Optional[List[int]] = Field(default_factory=list, description="Lista ID patternów harmonicznych")
    thumbnail: Optional[str] = Field(None, description="Miniaturka jako base64")


class SavedAnalysisUpdate(BaseModel):
    """Model do aktualizacji zapisanej analizy."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    chart_visible_range: Optional[Dict[str, Any]] = None
    selected_pattern_id: Optional[int] = None
    expanded_pattern_id: Optional[int] = None
    pattern_display_options: Optional[Dict[str, Any]] = None
    shared_pattern_data: Optional[Dict[str, Any]] = None
    global_pattern_display: Optional[Dict[str, Any]] = None
    indicators: Optional[Dict[str, bool]] = None
    unselected_alpha: Optional[float] = Field(None, ge=0, le=1)
    auto_center_on_select: Optional[bool] = None
    harmonic_pattern_ids: Optional[List[int]] = None
    thumbnail: Optional[str] = None


class SavedAnalysisListItem(BaseModel):
    """Model dla elementu listy zapisanych analiz."""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    asset_id: int
    asset_name: Optional[str]
    quote_name: Optional[str]
    exchange_id: Optional[int]
    exchange_name: Optional[str]
    interval: str
    created_at: datetime
    updated_at: datetime


class SavedAnalysisFull(BaseModel):
    """Model dla pełnych danych zapisanej analizy."""
    id: int
    user_id: int
    name: str
    description: Optional[str]
    asset_id: int
    asset_name: Optional[str]
    quote_name: Optional[str]
    exchange_id: Optional[int]
    exchange_name: Optional[str]
    interval: str
    chart_visible_range: Optional[Dict[str, Any]]
    selected_pattern_id: Optional[int]
    expanded_pattern_id: Optional[int]
    pattern_display_options: Dict[str, Any]
    shared_pattern_data: Dict[str, Any]
    global_pattern_display: Dict[str, Any]
    indicators: Dict[str, bool]
    unselected_alpha: float
    auto_center_on_select: bool
    harmonic_pattern_ids: List[int]
    thumbnail: Optional[str]
    created_at: datetime
    updated_at: datetime


@router.post("/saved-analyses", response_model=StandardResponse)
async def create_saved_analysis(
    analysis_data: SavedAnalysisCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Tworzy nową zapisaną analizę dla zalogowanego użytkownika.
    
    Dostępne dla wszystkich zalogowanych użytkowników (user i administrator).
    
    Args:
        analysis_data: Dane analizy do zapisania
        
    Returns:
        StandardResponse: ID utworzonej analizy
    """
    try:
        db = await get_db()
        saved_analyses_table = db.get_factory().get_saved_analyses_table()
        
        analysis_id = await saved_analyses_table.create(
            user_id=current_user.id,
            name=analysis_data.name,
            description=analysis_data.description,
            asset_id=analysis_data.asset_id,
            asset_name=analysis_data.asset_name,
            quote_name=analysis_data.quote_name,
            exchange_id=analysis_data.exchange_id,
            exchange_name=analysis_data.exchange_name,
            interval=analysis_data.interval,
            chart_visible_range=analysis_data.chart_visible_range,
            selected_pattern_id=analysis_data.selected_pattern_id,
            expanded_pattern_id=analysis_data.expanded_pattern_id,
            pattern_display_options=analysis_data.pattern_display_options,
            shared_pattern_data=analysis_data.shared_pattern_data,
            global_pattern_display=analysis_data.global_pattern_display,
            indicators=analysis_data.indicators,
            unselected_alpha=analysis_data.unselected_alpha,
            auto_center_on_select=analysis_data.auto_center_on_select,
            harmonic_pattern_ids=analysis_data.harmonic_pattern_ids,
            thumbnail=analysis_data.thumbnail
        )
        
        if analysis_id is None:
            raise HTTPException(status_code=500, detail="Nie udało się utworzyć zapisanej analizy")
        
        logger.info(f"Użytkownik {current_user.username} utworzył zapisaną analizę: {analysis_data.name} (ID: {analysis_id})")
        
        return StandardResponse(
            success=True,
            message=f"Utworzono zapisaną analizę '{analysis_data.name}'",
            data={
                "analysis_id": analysis_id,
                "name": analysis_data.name,
                "asset_id": analysis_data.asset_id,
                "interval": analysis_data.interval
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas tworzenia zapisanej analizy: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/saved-analyses")
async def get_my_saved_analyses(
    limit: int = Query(default=50, ge=1, le=1000, description="Limit wyników"),
    offset: int = Query(default=0, ge=0, description="Offset dla paginacji"),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Pobiera listę zapisanych analiz zalogowanego użytkownika.
    
    Zwraca skróconą wersję danych (bez szczegółów wykresu) dla szybkiego wyświetlenia listy.
    
    Returns:
        Lista zapisanych analiz z podstawowymi informacjami
    """
    try:
        db = await get_db()
        saved_analyses_table = db.get_factory().get_saved_analyses_table()
        
        analyses = await saved_analyses_table.get_by_user(
            user_id=current_user.id,
            limit=limit,
            offset=offset
        )
        
        total_count = await saved_analyses_table.count_by_user(current_user.id)
        
        # Konwertuj datetime na ISO string dla serializacji JSON
        serialized_analyses = []
        for analysis in analyses:
            serialized = dict(analysis)
            if 'created_at' in serialized and serialized['created_at']:
                serialized['created_at'] = serialized['created_at'].isoformat()
            if 'updated_at' in serialized and serialized['updated_at']:
                serialized['updated_at'] = serialized['updated_at'].isoformat()
            serialized_analyses.append(serialized)
        
        return {
            "analyses": serialized_analyses,
            "total_count": total_count,
            "pagination": {
                "limit": limit,
                "offset": offset
            }
        }
        
    except Exception as e:
        logger.error(f"Błąd podczas pobierania zapisanych analiz: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.get("/saved-analyses/{analysis_id}")
async def get_saved_analysis(
    analysis_id: int = Path(..., description="ID zapisanej analizy"),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Pobiera pełne dane zapisanej analizy po ID.
    
    Użytkownik może pobierać tylko swoje analizy.
    
    Args:
        analysis_id: ID analizy do pobrania
        
    Returns:
        Pełne dane zapisanej analizy
    """
    try:
        db = await get_db()
        saved_analyses_table = db.get_factory().get_saved_analyses_table()
        
        analysis = await saved_analyses_table.get_by_user_full(
            user_id=current_user.id,
            analysis_id=analysis_id
        )
        
        if analysis is None:
            raise HTTPException(status_code=404, detail=f"Zapisana analiza o ID {analysis_id} nie istnieje")
        
        # Konwertuj datetime na ISO string dla serializacji JSON
        serialized = dict(analysis)
        if 'created_at' in serialized and serialized['created_at']:
            serialized['created_at'] = serialized['created_at'].isoformat()
        if 'updated_at' in serialized and serialized['updated_at']:
            serialized['updated_at'] = serialized['updated_at'].isoformat()
        
        return {
            "analysis": serialized
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas pobierania zapisanej analizy: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.put("/saved-analyses/{analysis_id}", response_model=StandardResponse)
async def update_saved_analysis(
    analysis_id: int = Path(..., description="ID zapisanej analizy"),
    update_data: SavedAnalysisUpdate = Body(...),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Aktualizuje zapisaną analizę.
    
    Użytkownik może aktualizować tylko swoje analizy.
    
    Args:
        analysis_id: ID analizy do aktualizacji
        update_data: Dane do aktualizacji
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        saved_analyses_table = db.get_factory().get_saved_analyses_table()
        
        # Sprawdź czy analiza należy do użytkownika
        existing = await saved_analyses_table.get_by_user_full(
            user_id=current_user.id,
            analysis_id=analysis_id
        )
        
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Zapisana analiza o ID {analysis_id} nie istnieje")
        
        # Przygotuj dane do aktualizacji (tylko niepuste pola)
        update_dict = {}
        for field, value in update_data.model_dump().items():
            if value is not None:
                update_dict[field] = value
        
        if not update_dict:
            return StandardResponse(
                success=True,
                message="Brak danych do aktualizacji",
                data={"analysis_id": analysis_id}
            )
        
        success = await saved_analyses_table.update(analysis_id, **update_dict)
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się zaktualizować analizy")
        
        logger.info(f"Użytkownik {current_user.username} zaktualizował analizę ID: {analysis_id}")
        
        return StandardResponse(
            success=True,
            message=f"Zaktualizowano zapisaną analizę",
            data={
                "analysis_id": analysis_id,
                "updated_fields": list(update_dict.keys())
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas aktualizacji zapisanej analizy: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")


@router.delete("/saved-analyses/{analysis_id}", response_model=StandardResponse)
async def delete_saved_analysis(
    analysis_id: int = Path(..., description="ID zapisanej analizy"),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Usuwa zapisaną analizę.
    
    Użytkownik może usuwać tylko swoje analizy.
    
    Args:
        analysis_id: ID analizy do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        saved_analyses_table = db.get_factory().get_saved_analyses_table()
        
        # Pobierz analizę przed usunięciem (dla logowania)
        existing = await saved_analyses_table.get_by_user_full(
            user_id=current_user.id,
            analysis_id=analysis_id
        )
        
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Zapisana analiza o ID {analysis_id} nie istnieje")
        
        analysis_name = existing.get('name', 'Unknown')
        
        success = await saved_analyses_table.delete_by_user(
            record_id=analysis_id,
            user_id=current_user.id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Nie udało się usunąć analizy")
        
        logger.info(f"Użytkownik {current_user.username} usunął analizę: {analysis_name} (ID: {analysis_id})")
        
        return StandardResponse(
            success=True,
            message=f"Usunięto zapisaną analizę '{analysis_name}'",
            data={"deleted_analysis_id": analysis_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas usuwania zapisanej analizy: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd serwera: {str(e)}")

