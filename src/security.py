"""
Moduł bezpieczeństwa dla aplikacji FastAPI.

Zawiera:
- Middleware zabezpieczający (security headers)
- Rate limiting
- CSRF protection
- Input sanitization
- XSS prevention utilities
"""

import hashlib
import hmac
import html
import logging
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# =============================================================================
# CSRF Protection
# =============================================================================

class CSRFTokenManager:
    """
    Manager tokenów CSRF.
    
    Generuje i waliduje tokeny CSRF powiązane z sesjami użytkowników.
    """
    
    # Secret key dla HMAC - w produkcji powinien być z env vars
    _secret_key: Optional[str] = None
    
    # Token cache - mapowanie session_token -> csrf_token
    _token_cache: Dict[str, Tuple[str, float]] = {}
    
    # Czas życia tokenu CSRF w sekundach (1 godzina)
    TOKEN_LIFETIME = 3600
    
    @classmethod
    def set_secret_key(cls, secret: str):
        """Ustawia klucz tajny dla generowania tokenów."""
        cls._secret_key = secret
    
    @classmethod
    def _get_secret_key(cls) -> str:
        """Pobiera klucz tajny."""
        if cls._secret_key is None:
            # Generuj losowy klucz przy pierwszym użyciu
            cls._secret_key = secrets.token_hex(32)
            logger.warning("CSRF secret key wygenerowany automatycznie. Ustaw CSRF_SECRET_KEY w env vars dla produkcji.")
        return cls._secret_key
    
    @classmethod
    def generate_token(cls, session_token: Optional[str] = None) -> str:
        """
        Generuje nowy token CSRF.
        
        Args:
            session_token: Token sesji użytkownika (opcjonalny)
            
        Returns:
            str: Token CSRF
        """
        timestamp = str(int(time.time()))
        random_bytes = secrets.token_hex(16)
        
        # Utwórz dane do podpisu
        data = f"{timestamp}:{random_bytes}:{session_token or 'anonymous'}"
        
        # Wygeneruj podpis HMAC
        signature = hmac.new(
            cls._get_secret_key().encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Token = dane + podpis
        token = f"{timestamp}.{random_bytes}.{signature}"
        
        # Cache token
        if session_token:
            cls._token_cache[session_token] = (token, time.time())
            cls._cleanup_cache()
        
        return token
    
    @classmethod
    def validate_token(cls, csrf_token: str, session_token: Optional[str] = None) -> bool:
        """
        Waliduje token CSRF.
        
        Args:
            csrf_token: Token CSRF do walidacji
            session_token: Token sesji użytkownika (opcjonalny)
            
        Returns:
            bool: True jeśli token jest prawidłowy
        """
        if not csrf_token:
            return False
        
        try:
            parts = csrf_token.split('.')
            if len(parts) != 3:
                return False
            
            timestamp, random_bytes, signature = parts
            
            # Sprawdź czy token nie wygasł
            token_time = int(timestamp)
            if time.time() - token_time > cls.TOKEN_LIFETIME:
                logger.warning("CSRF token wygasł")
                return False
            
            # Weryfikuj podpis
            data = f"{timestamp}:{random_bytes}:{session_token or 'anonymous'}"
            expected_signature = hmac.new(
                cls._get_secret_key().encode(),
                data.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Nieprawidłowy podpis CSRF token")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas walidacji CSRF token: {e}")
            return False
    
    @classmethod
    def _cleanup_cache(cls):
        """Usuwa wygasłe tokeny z cache."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, created_at) in cls._token_cache.items()
            if current_time - created_at > cls.TOKEN_LIFETIME
        ]
        for key in expired_keys:
            del cls._token_cache[key]


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """
    Rate limiter oparty na sliding window.
    
    Ogranicza liczbę requestów per IP/endpoint w określonym oknie czasowym.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        block_duration_seconds: int = 300
    ):
        """
        Inicjalizuje rate limiter.
        
        Args:
            requests_per_minute: Maksymalna liczba requestów na minutę
            burst_size: Dozwolony burst powyżej limitu
            block_duration_seconds: Czas blokady po przekroczeniu limitu
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.block_duration = block_duration_seconds
        
        # Sliding window: {client_key: [timestamps]}
        self._request_history: Dict[str, List[float]] = defaultdict(list)
        
        # Blocked clients: {client_key: unblock_timestamp}
        self._blocked_clients: Dict[str, float] = {}
    
    def _get_client_key(self, request: Request, endpoint: Optional[str] = None) -> str:
        """Generuje klucz identyfikujący klienta."""
        ip = self._get_client_ip(request)
        if endpoint:
            return f"{ip}:{endpoint}"
        return ip
    
    def _get_client_ip(self, request: Request) -> str:
        """Pobiera IP klienta z uwzględnieniem proxy."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _cleanup_old_requests(self, client_key: str, window_seconds: int = 60):
        """Usuwa stare requesty z historii."""
        cutoff = time.time() - window_seconds
        self._request_history[client_key] = [
            ts for ts in self._request_history[client_key]
            if ts > cutoff
        ]
    
    def is_allowed(self, request: Request, endpoint: Optional[str] = None) -> Tuple[bool, Optional[int]]:
        """
        Sprawdza czy request jest dozwolony.
        
        Args:
            request: Request FastAPI
            endpoint: Opcjonalny endpoint do rate limitingu per-endpoint
            
        Returns:
            Tuple[bool, Optional[int]]: (is_allowed, retry_after_seconds)
        """
        client_key = self._get_client_key(request, endpoint)
        current_time = time.time()
        
        # Sprawdź czy klient jest zablokowany
        if client_key in self._blocked_clients:
            unblock_time = self._blocked_clients[client_key]
            if current_time < unblock_time:
                retry_after = int(unblock_time - current_time)
                return False, retry_after
            else:
                # Odblokuj klienta
                del self._blocked_clients[client_key]
        
        # Wyczyść starą historię
        self._cleanup_old_requests(client_key)
        
        # Sprawdź limit
        request_count = len(self._request_history[client_key])
        max_requests = self.requests_per_minute + self.burst_size
        
        if request_count >= max_requests:
            # Zablokuj klienta
            self._blocked_clients[client_key] = current_time + self.block_duration
            logger.warning(f"Rate limit przekroczony dla: {client_key}")
            return False, self.block_duration
        
        # Dodaj request do historii
        self._request_history[client_key].append(current_time)
        
        return True, None
    
    def get_remaining_requests(self, request: Request, endpoint: Optional[str] = None) -> int:
        """Zwraca liczbę pozostałych requestów."""
        client_key = self._get_client_key(request, endpoint)
        self._cleanup_old_requests(client_key)
        request_count = len(self._request_history[client_key])
        return max(0, self.requests_per_minute - request_count)


# Globalna instancja rate limitera
rate_limiter = RateLimiter(
    requests_per_minute=120,  # 2 requesty na sekundę
    burst_size=30,  # Pozwól na burst 30 requestów
    block_duration_seconds=300  # 5 minut blokady
)

# Rate limiter dla logowania (bardziej restrykcyjny)
login_rate_limiter = RateLimiter(
    requests_per_minute=10,  # 10 prób logowania na minutę
    burst_size=5,
    block_duration_seconds=900  # 15 minut blokady
)


# =============================================================================
# Input Sanitization
# =============================================================================

class InputSanitizer:
    """
    Klasa do sanityzacji danych wejściowych.
    
    Zapobiega XSS i innym atakom injection.
    """
    
    # Wzorce potencjalnie niebezpiecznych stringów
    DANGEROUS_PATTERNS = [
        r'<script\b[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers
        r'<\s*iframe',  # iframes
        r'<\s*object',  # object tags
        r'<\s*embed',  # embed tags
        r'expression\s*\(',  # CSS expressions
        r'vbscript:',  # VBScript protocol
        r'data:.*?base64',  # Data URLs with base64
    ]
    
    # Skompilowane wzorce
    _compiled_patterns = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in DANGEROUS_PATTERNS]
    
    @classmethod
    def sanitize_string(cls, value: str, max_length: Optional[int] = None) -> str:
        """
        Sanityzuje string wejściowy.
        
        Args:
            value: String do sanityzacji
            max_length: Opcjonalna maksymalna długość
            
        Returns:
            str: Zsanityzowany string
        """
        if not value:
            return value
        
        # Przytnij whitespace
        value = value.strip()
        
        # Ogranicz długość
        if max_length and len(value) > max_length:
            value = value[:max_length]
        
        # Escape HTML entities
        value = html.escape(value, quote=True)
        
        return value
    
    @classmethod
    def sanitize_html(cls, value: str, max_length: Optional[int] = None) -> str:
        """
        Usuwa potencjalnie niebezpieczne elementy HTML.
        
        Args:
            value: String HTML do sanityzacji
            max_length: Opcjonalna maksymalna długość
            
        Returns:
            str: Zsanityzowany string
        """
        if not value:
            return value
        
        # Usuń niebezpieczne wzorce
        for pattern in cls._compiled_patterns:
            value = pattern.sub('', value)
        
        # Podstawowa sanityzacja
        return cls.sanitize_string(value, max_length)
    
    @classmethod
    def is_safe_string(cls, value: str) -> bool:
        """
        Sprawdza czy string nie zawiera niebezpiecznych wzorców.
        
        Args:
            value: String do sprawdzenia
            
        Returns:
            bool: True jeśli string jest bezpieczny
        """
        if not value:
            return True
        
        for pattern in cls._compiled_patterns:
            if pattern.search(value):
                return False
        
        return True
    
    @classmethod
    def sanitize_filename(cls, filename: str, max_length: int = 255) -> str:
        """
        Sanityzuje nazwę pliku.
        
        Args:
            filename: Nazwa pliku do sanityzacji
            max_length: Maksymalna długość
            
        Returns:
            str: Zsanityzowana nazwa pliku
        """
        if not filename:
            return "unnamed"
        
        # Usuń ścieżkę
        filename = filename.split('/')[-1].split('\\')[-1]
        
        # Usuń niedozwolone znaki
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', filename)
        
        # Ogranicz długość
        if len(filename) > max_length:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            max_name_length = max_length - len(ext) - 1
            filename = f"{name[:max_name_length]}.{ext}" if ext else name[:max_length]
        
        return filename or "unnamed"
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], string_max_length: int = 10000) -> Dict[str, Any]:
        """
        Rekurencyjnie sanityzuje słownik.
        
        Args:
            data: Słownik do sanityzacji
            string_max_length: Maksymalna długość stringów
            
        Returns:
            Dict[str, Any]: Zsanityzowany słownik
        """
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            # Sanityzuj klucz
            safe_key = cls.sanitize_string(str(key), max_length=256)
            
            # Sanityzuj wartość rekurencyjnie
            if isinstance(value, str):
                sanitized[safe_key] = cls.sanitize_string(value, max_length=string_max_length)
            elif isinstance(value, dict):
                sanitized[safe_key] = cls.sanitize_dict(value, string_max_length)
            elif isinstance(value, list):
                sanitized[safe_key] = cls.sanitize_list(value, string_max_length)
            else:
                sanitized[safe_key] = value
        
        return sanitized
    
    @classmethod
    def sanitize_list(cls, data: List[Any], string_max_length: int = 10000) -> List[Any]:
        """
        Rekurencyjnie sanityzuje listę.
        
        Args:
            data: Lista do sanityzacji
            string_max_length: Maksymalna długość stringów
            
        Returns:
            List[Any]: Zsanityzowana lista
        """
        if not isinstance(data, list):
            return data
        
        sanitized = []
        for item in data:
            if isinstance(item, str):
                sanitized.append(cls.sanitize_string(item, max_length=string_max_length))
            elif isinstance(item, dict):
                sanitized.append(cls.sanitize_dict(item, string_max_length))
            elif isinstance(item, list):
                sanitized.append(cls.sanitize_list(item, string_max_length))
            else:
                sanitized.append(item)
        
        return sanitized


# =============================================================================
# Security Middleware
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware dodający nagłówki bezpieczeństwa do odpowiedzi.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Zapobiegaj MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Ochrona przed clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Włącz XSS filter w przeglądarkach
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy - basic restrictive policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'"
        )
        
        # Permissions Policy (dawniej Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=()"
        )
        
        # Cache Control dla wrażliwych danych
        if request.url.path.startswith("/user") or request.url.path.startswith("/auth"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware do rate limitingu.
    """
    
    # Endpointy wyłączone z rate limitingu
    EXCLUDED_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
        "/live",
        "/ready",
    ]
    
    # Endpointy z bardziej restrykcyjnym limitem
    STRICT_PATHS = ["/user/auth/login", "/user/auth/register"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Pomijaj wyłączone ścieżki
        if any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            return await call_next(request)
        
        # Wybierz odpowiedni rate limiter
        limiter = login_rate_limiter if any(path.startswith(strict) for strict in self.STRICT_PATHS) else rate_limiter
        
        # Sprawdź limit
        is_allowed, retry_after = limiter.is_allowed(request, endpoint=path)
        
        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {request.client.host if request.client else 'unknown'} on {path}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": "Zbyt wiele requestów. Spróbuj ponownie później.",
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Remaining": "0"
                }
            )
        
        # Wykonaj request
        response = await call_next(request)
        
        # Dodaj nagłówki rate limit
        remaining = limiter.get_remaining_requests(request, endpoint=path)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(limiter.requests_per_minute)
        
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware do walidacji tokenów CSRF.
    
    Waliduje token CSRF dla requestów modyfikujących stan (POST, PUT, DELETE, PATCH).
    """
    
    # Metody wymagające walidacji CSRF
    CSRF_METHODS = ["POST", "PUT", "DELETE", "PATCH"]
    
    # Ścieżki wyłączone z walidacji CSRF (np. login)
    EXCLUDED_PATHS = [
        "/user/auth/login",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
        "/info",
        "/health",
        "/live",
        "/ready",
    ]
    
    # Nagłówek z tokenem CSRF
    CSRF_HEADER = "X-CSRF-Token"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Pomijaj metody GET/HEAD/OPTIONS
        if request.method not in self.CSRF_METHODS:
            return await call_next(request)
        
        # Pomijaj wyłączone ścieżki
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            return await call_next(request)
        
        # Pobierz token CSRF z nagłówka
        csrf_token = request.headers.get(self.CSRF_HEADER)
        
        # Pobierz token sesji (jeśli jest)
        auth_header = request.headers.get("Authorization", "")
        session_token = None
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
        
        # Waliduj token CSRF
        if not CSRFTokenManager.validate_token(csrf_token, session_token):
            logger.warning(f"Invalid CSRF token for {request.method} {path}")
            return JSONResponse(
                status_code=403,
                content={
                    "error": "CSRF Validation Failed",
                    "message": "Nieprawidłowy lub brakujący token CSRF. Odśwież stronę i spróbuj ponownie."
                }
            )
        
        return await call_next(request)


class KubernetesProbeMiddleware(BaseHTTPMiddleware):
    """
    GET /live i GET /ready przed resztą stosu — kubelet nie wysyła JWT;
    unika też sytuacji, w której inna trasa lub zależność zwraca 401.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method != "GET":
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if path == "/live":
            from src.k8s_probes import live_body

            return JSONResponse(await live_body())
        if path == "/ready":
            from src.k8s_probes import ready_body

            status, body = await ready_body()
            return JSONResponse(body, status_code=status)
        return await call_next(request)


# =============================================================================
# Security Utilities
# =============================================================================

def validate_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    Sprawdza siłę hasła.
    
    Args:
        password: Hasło do sprawdzenia
        
    Returns:
        Tuple[bool, List[str]]: (is_valid, list_of_errors)
    """
    errors = []
    
    if len(password) < 8:
        errors.append("Hasło musi mieć minimum 8 znaków")
    
    if len(password) > 128:
        errors.append("Hasło może mieć maksymalnie 128 znaków")
    
    if not re.search(r'[a-z]', password):
        errors.append("Hasło musi zawierać małą literę")
    
    if not re.search(r'[A-Z]', password):
        errors.append("Hasło musi zawierać wielką literę")
    
    if not re.search(r'\d', password):
        errors.append("Hasło musi zawierać cyfrę")
    
    # Opcjonalne: wymagaj znaku specjalnego
    # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
    #     errors.append("Hasło musi zawierać znak specjalny")
    
    return len(errors) == 0, errors


def generate_secure_token(length: int = 32) -> str:
    """
    Generuje bezpieczny losowy token.
    
    Args:
        length: Długość tokenu w bajtach
        
    Returns:
        str: Token w formacie hex
    """
    return secrets.token_hex(length)


def constant_time_compare(a: str, b: str) -> bool:
    """
    Porównuje dwa stringi w stałym czasie (ochrona przed timing attacks).
    
    Args:
        a: Pierwszy string
        b: Drugi string
        
    Returns:
        bool: True jeśli stringi są identyczne
    """
    return hmac.compare_digest(a.encode(), b.encode())

