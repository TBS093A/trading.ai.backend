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
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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

# Konfiguracja CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # W produkcji należy ograniczyć do konkretnych domen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_rest_controllers() -> List[str]:
    """
    Wczytuje wszystkie kontrolery REST z katalogu src.
    
    Szuka plików controller_rest_*.py i importuje ich routery.
    
    Returns:
        List[str]: Lista załadowanych kontrolerów
    """
    loaded_controllers = []
    src_path = os.path.join(os.path.dirname(__file__), "src")
    
    if not os.path.exists(src_path):
        logger.warning(f"Katalog src nie istnieje: {src_path}")
        return loaded_controllers
    
    try:
        for filename in os.listdir(src_path):
            if filename.startswith("controller_rest_") and filename.endswith(".py"):
                module_name = filename[:-3]  # Usuń .py
                
                try:
                    # Importuj moduł
                    module = importlib.import_module(f"src.{module_name}")
                    
                    # Sprawdź czy ma router
                    if hasattr(module, 'router'):
                        # Dodaj router do aplikacji
                        router = getattr(module, 'router')
                        
                        # Pobierz prefix z modułu lub użyj domyślnego
                        prefix = getattr(module, 'PREFIX', f"/{module_name.replace('controller_rest_', '')}")
                        tags = getattr(module, 'TAGS', [module_name.replace('controller_rest_', '').replace('_', ' ').title()])
                        
                        app.include_router(router, prefix=prefix, tags=tags)
                        loaded_controllers.append(module_name)
                        logger.info(f"✅ Załadowano kontroler: {module_name} (prefix: {prefix})")
                    else:
                        logger.warning(f"⚠️ Moduł {module_name} nie ma routera")
                        
                except Exception as e:
                    logger.error(f"❌ Błąd podczas ładowania kontrolera {module_name}: {e}")
                    
    except Exception as e:
        logger.error(f"❌ Błąd podczas skanowania katalogu src: {e}")
    
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "telegram-pump-bot-api"
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


# Event handlers zostały przeniesione do lifespan context manager


# Handler dla błędów 404
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handler dla błędów 404."""
    return {
        "error": "Not Found",
        "message": f"Endpoint {request.url.path} nie został znaleziony",
        "available_docs": "/docs"
    }


# Handler dla błędów 500
@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handler dla błędów 500."""
    logger.error(f"Błąd serwera dla {request.url.path}: {exc}")
    return {
        "error": "Internal Server Error",
        "message": "Wystąpił błąd serwera. Sprawdź logi dla szczegółów."
    }


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
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("🛑 Serwer przerwany przez użytkownika")
    except Exception as e:
        logger.error(f"❌ Krytyczny błąd serwera: {e}")
    finally:
        logger.info("👋 Serwer REST API zakończony")
