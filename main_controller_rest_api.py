#!/usr/bin/env python3
"""
Main FastAPI REST API Controller

Główny kontroler REST API oparty na FastAPI.
Automatycznie wczytuje endpointy z plików controller_rest_*.py z katalogu src.

Autor: AI Assistant
"""

import os
import logging
import importlib
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

# Import auth
from src.auth import require_auth, require_admin, AuthUser, get_current_user, get_app_database

# Import security
from src.security import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    CSRFMiddleware,
    CSRFTokenManager,
    InputSanitizer,
)

# Import config
from src.config import config

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rest_api.log')
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager dla event handlers startup/shutdown."""
    # Startup
    logger.info("🚀 Uruchamianie Telegram Pump Bot REST API")
    
    # Wczytaj kontrolery REST
    loaded_controllers = load_rest_controllers()
    app.state.loaded_controllers = loaded_controllers

    logger.info(f"📊 Załadowano {len(loaded_controllers)} kontrolerów: {', '.join(loaded_controllers)}")
    logger.info("✅ REST API gotowe do obsługi żądań")
    
    yield
    
    # Shutdown
    logger.info("🛑 Zamykanie Telegram Pump Bot REST API")


# Tworzenie aplikacji FastAPI
app = FastAPI(
    title="Telegram Pump Bot REST API",
    description="REST API dla bota analizy kryptowalut z funkcjami synchronizacji i zarządzania",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# =============================================================================
# Catch-all dla nieobsłużonych wyjątków
# =============================================================================
# WAŻNE: rejestrowane PRZED CORSMiddleware, żeby w stosie Starlette wylądować
# WEWNĄTRZ niego (Starlette owija middleware w kolejności odwrotnej do
# add_middleware). Wyjątek, który przeleci przez cały stos nieobsłużony,
# trafia do ServerErrorMiddleware — a ten siedzi POZA CORSMiddleware, więc
# odpowiedź 500 nigdy nie dostaje nagłówka Access-Control-Allow-Origin i
# przeglądarka pokazuje mylący błąd CORS zamiast prawdziwego 500
# (@app.exception_handler(500)/Exception ma dokładnie ten sam problem —
# Starlette kieruje go też do ServerErrorMiddleware). Łapiąc tutaj, response
# wraca normalnie przez CORSMiddleware i dostaje właściwe nagłówki.
@app.middleware("http")
async def catch_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Nieobsłużony wyjątek dla {request.url.path}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": "Wystąpił błąd serwera. Sprawdź logi dla szczegółów."
            }
        )


# =============================================================================
# Konfiguracja CORS
# =============================================================================
# Pobierz dozwolone originy z konfiguracji
cors_allowed_origins = config.get_cors_allowed_origins()
logger.info(f"🔒 CORS - Środowisko: {config.environment}")
logger.info(f"🔒 CORS - Dozwolone originy: {cors_allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    # Lista dozwolonych originów (development: localhost:3000, production: 00x097.com)
    allow_origins=cors_allowed_origins,
    # Pozwól na credentials (cookies, Authorization header)
    allow_credentials=True,
    # Dozwolone metody HTTP
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    # Dozwolone nagłówki w requestach
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-CSRF-Token",
        "X-Requested-With",
        "Accept",
        "Origin",
    ],
    # Nagłówki odpowiedzi widoczne dla klienta
    expose_headers=[
        "X-RateLimit-Remaining",
        "X-RateLimit-Limit",
        "Retry-After",
        "X-Request-ID",
    ],
    # Cache preflight response na 1 godzinę (3600 sekund)
    max_age=3600,
)

# Security Middlewares (kolejność ma znaczenie - wykonują się od dołu do góry)
# 1. Security Headers - dodaje nagłówki bezpieczeństwa
app.add_middleware(SecurityHeadersMiddleware)

# 2. Rate Limiting - ogranicza liczbę requestów
app.add_middleware(RateLimitMiddleware)

# 3. CSRF Protection - waliduje tokeny CSRF dla modyfikujących requestów
# UWAGA: Tymczasowo wyłączone dla łatwiejszego developmentu
# W produkcji należy odkomentować:
# app.add_middleware(CSRFMiddleware)

# =============================================================================
# Prometheus Metrics
# =============================================================================
Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_group_untemplated=True,
    excluded_handlers=["/metrics", "/live", "/ready"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def load_rest_controllers() -> List[str]:
    """
    Wczytuje wszystkie kontrolery REST z katalogu src.
    
    Szuka plików controller_rest_*.py i importuje ich routery.
    
    Returns:
        List[str]: Lista załadowanych kontrolerów
    """
    loaded_controllers = []
    src_path = os.path.join(os.path.dirname(__file__), "src")
    
    logger.info(f"🔍 Szukam kontrolerów REST w: {src_path}")
    
    if not os.path.exists(src_path):
        logger.warning(f"Katalog src nie istnieje: {src_path}")
        return loaded_controllers
    
    try:
        files = os.listdir(src_path)
        logger.info(f"📁 Znalezione pliki w src: {[f for f in files if f.endswith('.py')]}")
        
        for filename in files:
            if filename.startswith("controller_rest_") and filename.endswith(".py"):
                module_name = filename[:-3]  # Usuń .py
                logger.info(f"🔄 Próba załadowania modułu: {module_name}")
                
                try:
                    # Importuj moduł
                    module = importlib.import_module(f"src.{module_name}")
                    logger.info(f"✅ Zaimportowano moduł: {module_name}")
                    
                    # Sprawdź atrybuty modułu
                    module_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
                    logger.info(f"📋 Atrybuty modułu {module_name}: {module_attrs}")
                    
                    # Sprawdź czy ma router
                    if hasattr(module, 'router'):
                        # Dodaj router do aplikacji
                        router = getattr(module, 'router')
                        
                        # Pobierz prefix z modułu lub użyj domyślnego
                        prefix = getattr(module, 'PREFIX', f"/{module_name.replace('controller_rest_', '').replace('_', '-')}")
                        tags = getattr(module, 'TAGS', [module_name.replace('controller_rest_', '').replace('_', ' ').title()])
                        
                        logger.info(f"🚀 Dodawanie routera z prefixem: {prefix}, tags: {tags}")
                        app.include_router(router, prefix=prefix, tags=tags)
                        loaded_controllers.append(module_name)
                        logger.info(f"✅ Załadowano kontroler: {module_name} (prefix: {prefix}, tags: {tags})")
                    else:
                        logger.warning(f"⚠️ Moduł {module_name} nie ma routera")
                        
                except Exception as e:
                    logger.error(f"❌ Błąd podczas ładowania kontrolera {module_name}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
    except Exception as e:
        logger.error(f"❌ Błąd podczas skanowania katalogu src: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    logger.info(f"📊 Załadowano kontrolerów: {len(loaded_controllers)}")
    return loaded_controllers


# Podstawowe endpointy aplikacji
@app.get("/")
async def root():
    """Endpoint główny - informacje o API."""
    return {
        "message": "Telegram Pump Bot REST API",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/live", tags=["Kubernetes"])
async def live():
    """Liveness probe (K8s) — proces odpowiada, bez zależności zewnętrznych."""
    return {"status": "ok"}


@app.get("/ready", tags=["Kubernetes"])
async def ready():
    """Readiness probe (K8s) — sprawdzenie PostgreSQL."""
    db = await get_app_database()
    result = await db.test_connection()
    if result.get("test_passed"):
        return {"status": "ready", "database": result.get("connection", "OK")}
    return JSONResponse(
        {"status": "not_ready", "database": result.get("connection", "FAILED"), "error": result.get("error")},
        status_code=503,
    )


@app.get("/health")
async def health_check(current_user: AuthUser = Depends(require_admin)):
    """
    Health check endpoint.
    
    Wymaga uprawnień administratora.
    """
    return {
        "status": "healthy",
        "service": "telegram-pump-bot-api",
        "user": current_user.username
    }


@app.get("/info")
async def api_info():
    """Informacje o dostępnych endpointach i kontrolerach."""
    routes_info = []
    
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes_info.append({
                "path": route.path,
                "methods": list(route.methods)
            })
    
    return {
        "total_routes": len(routes_info),
        "routes": routes_info,
        "loaded_controllers": getattr(app.state, 'loaded_controllers', [])
    }


# =============================================================================
# Security Endpoints
# =============================================================================

@app.get("/csrf-token")
async def get_csrf_token(
    request: Request,
    current_user: Optional[AuthUser] = Depends(get_current_user)
):
    """
    Pobiera token CSRF dla aktualnej sesji.
    
    Token powinien być wysyłany w nagłówku X-CSRF-Token przy każdym
    requeście modyfikującym (POST, PUT, DELETE, PATCH).
    
    Returns:
        dict: Token CSRF
    """
    session_token = None
    
    # Pobierz token sesji jeśli użytkownik jest zalogowany
    if current_user:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]
    
    csrf_token = CSRFTokenManager.generate_token(session_token)
    
    return {
        "csrf_token": csrf_token,
        "expires_in": CSRFTokenManager.TOKEN_LIFETIME,
        "header_name": "X-CSRF-Token"
    }


# Event handlers zostały przeniesione do lifespan context manager


# Handler dla błędów 404
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handler dla błędów 404."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"Endpoint {request.url.path} nie został znaleziony",
            "available_docs": "/docs"
        }
    )


# Handler dla błędów 500
@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handler dla błędów 500."""
    from fastapi.responses import JSONResponse
    logger.error(f"Błąd serwera dla {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "Wystąpił błąd serwera. Sprawdź logi dla szczegółów."
        }
    )


if __name__ == "__main__":
    """Punkt startowy aplikacji REST API."""
    import uvicorn
    
    logger.info("🎉 URUCHAMIANIE REST API SERVER")
    
    try:
        # Uruchom serwer uvicorn
        uvicorn.run(
            "main_controller_rest_api:app",
            host="0.0.0.0",
            port=9090,
            reload=True,
            # Brak endpointów WebSocket; pyharmonics -> alpaca-trade-api wymusza websockets<11,
            # z którym nowy uvicorn (ws="auto") crashuje przy imporcie ServerProtocol
            ws="none",
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("🛑 Serwer przerwany przez użytkownika")
    except Exception as e:
        logger.error(f"❌ Krytyczny błąd serwera: {e}")
    finally:
        logger.info("👋 Serwer REST API zakończony")
