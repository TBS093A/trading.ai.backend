"""
REST API Controller dla domeny exchanges (giełd kryptowalutowych).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania giełdami (CRUD)
- Filtrowania aktywnych/nieaktywnych giełd
- Wyszukiwania giełd po nazwie
- Zarządzania statusem giełd (włączanie/wyłączanie)
- Statystyk giełd i ich relacji z assetami
- Pobierania danych klines z giełd

Bazuje na funkcjonalności z controller_telegram_domain_exchanges.py

Autor: AI Assistant
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Union
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field
from datetime import datetime

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

# Import API Facade dla exchange APIs
from .api.api_facade import ApiFacade

# Import Celery Task
from .celery_tasks.sync_tasks import sync_exchanges_task

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/exchanges"
TAGS = ["Exchanges"]

# Modele Pydantic dla request/response


class ExchangeResponse(BaseModel):
    """Odpowiedź z informacją o giełdzie."""
    id: int
    name: str
    display_name: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None


class ExchangeCreate(BaseModel):
    """Model do tworzenia nowej giełdy."""
    name: str = Field(..., min_length=1, max_length=100, description="Nazwa systemowa giełdy")
    display_name: Optional[str] = Field(None, max_length=200, description="Nazwa wyświetlana")
    is_active: bool = Field(default=True, description="Czy giełda jest aktywna")


class ExchangeUpdate(BaseModel):
    """Model do aktualizacji giełdy."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Nazwa systemowa giełdy")
    display_name: Optional[str] = Field(None, max_length=200, description="Nazwa wyświetlana")
    is_active: Optional[bool] = Field(None, description="Czy giełda jest aktywna")


class ExchangeStatusUpdate(BaseModel):
    """Model do aktualizacji statusu giełdy."""
    is_active: bool = Field(..., description="Nowy status aktywności giełdy")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class ExchangeListResponse(BaseModel):
    """Lista giełd z informacją o paginacji."""
    exchanges: List[ExchangeResponse]
    pagination: PaginationInfo


class ExchangeStatsResponse(BaseModel):
    """Statystyki giełd."""
    total_exchanges: int
    active_exchanges: int
    inactive_exchanges: int
    exchange_asset_relations: int
    active_percentage: Optional[float] = None


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class SyncExchangesRequest(BaseModel):
    """Request do uruchomienia synchronizacji giełd."""
    test_mode: bool = Field(default=False, description="Tryb testowy (bez zapisu do bazy)")
    custom_dependencies: Optional[List[str]] = Field(
        default=None, 
        description="Lista niestandardowych zależności Celery do oczekiwania przed uruchomieniem"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "test_mode": False,
                "custom_dependencies": None
            }
        }


class SyncTaskResponse(BaseModel):
    """Odpowiedź po uruchomieniu zadania synchronizacji."""
    success: bool
    message: str
    task_id: str
    status_endpoint: str
    details: Dict[str, Any]


class KlineData(BaseModel):
    """Pojedynczy rekord kline/candlestick."""
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    trades: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float


class KlinesResponse(BaseModel):
    """Odpowiedź z danymi klines dla assetu."""
    asset: str
    quote: str
    interval: str
    exchange: str
    klines: List[KlineData]


# Singleton dla DatabasePostgreSQL z blokadą dla bezpieczeństwa wątkowego
db_instance: Optional[DatabasePostgreSQL] = None
db_lock: asyncio.Lock = asyncio.Lock()

# Singleton dla ApiFacade
api_facade_instance: Optional[ApiFacade] = None


def get_api_facade() -> ApiFacade:
    """
    Pobiera singleton instancji ApiFacade.
    
    Returns:
        ApiFacade: Instancja ApiFacade
    """
    global api_facade_instance
    
    if api_facade_instance is None:
        api_facade_instance = ApiFacade()
    
    return api_facade_instance


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
            db_instance = new_instance
    
    return db_instance


# ===================
# ENDPOINTY GŁÓWNE
# ===================

@router.get("", response_model=Dict[str, Any])
async def exchanges_info():
    """Informacje o dostępnych endpointach giełd."""
    return {
        "message": "Exchanges REST API",
        "version": "1.0.0",
        "available_endpoints": {
            "list": "GET /exchanges/list - Lista wszystkich giełd z paginacją",
            "active": "GET /exchanges/active - Lista tylko aktywnych giełd",
            "get": "GET /exchanges/{id} - Szczegóły giełdy",
            "count": "GET /exchanges/count - Liczba wszystkich giełd",
            "count_active": "GET /exchanges/count/active - Liczba aktywnych giełd",
            "search": "GET /exchanges/search/{name} - Wyszukiwanie po nazwie",
            "enable": "POST /exchanges/{id}/enable - Włączenie giełdy",
            "disable": "POST /exchanges/{id}/disable - Wyłączenie giełdy",
            "stats": "GET /exchanges/stats - Statystyki giełd",
            "sync": "POST /exchanges/sync - Uruchom synchronizację giełd",
            "klines": "GET /exchanges/klines/{asset_id}/{interval} - Pobierz dane klines z Binance"
        }
    }


# ===================
# SYNC OPERATIONS
# ===================

@router.post("/sync", response_model=SyncTaskResponse)
async def trigger_sync_exchanges(
    request: SyncExchangesRequest = Body(
        default=SyncExchangesRequest(),
        description="Parametry synchronizacji giełd"
    )
):
    """
    Uruchamia zadanie Celery do synchronizacji assetów z giełd.
    
    Parametry:
        - **test_mode**: Tryb testowy bez zapisu do bazy (domyślnie False)
        - **custom_dependencies**: Lista niestandardowych zależności Celery 
          do oczekiwania przed uruchomieniem (domyślnie brak)
    
    Returns:
        SyncTaskResponse: Informacja o uruchomionym zadaniu z task_id do śledzenia statusu
    """
    try:
        # Uruchom zadanie Celery
        task = sync_exchanges_task.delay(
            test_mode=request.test_mode,
            custom_dependencies=request.custom_dependencies
        )
        
        logger.info(f"Started sync_exchanges task (ID: {task.id})")
        
        return SyncTaskResponse(
            success=True,
            message=f"Synchronizacja giełd rozpoczęta (Task ID: {task.id})",
            task_id=task.id,
            status_endpoint=f"/sync/status/{task.id}",
            details={
                "test_mode": request.test_mode,
                "custom_dependencies": request.custom_dependencies
            }
        )
        
    except Exception as e:
        logger.error(f"Error starting sync_exchanges task: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to start exchanges sync: {str(e)}"
        )


# ===================
# CRUD OPERATIONS
# ===================

@router.get("/list", response_model=ExchangeListResponse)
async def list_exchanges(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników na stronę"),
    offset: int = Query(default=0, ge=0, description="Offset wyników"),
    active_only: bool = Query(default=False, description="Tylko aktywne giełdy")
):
    """
    Pobiera listę giełd z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        active_only: Czy pokazywać tylko aktywne giełdy
        
    Returns:
        ExchangeListResponse: Lista giełd z informacją o paginacji
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        # Pobierz giełdy z dodatkowym rekordem dla sprawdzenia następnej strony
        if active_only:
            exchanges = await exchanges_table.get_active(limit=limit + 1, offset=offset)
        else:
            exchanges = await exchanges_table.get_all(limit=limit + 1, offset=offset)
        
        # Sprawdź czy są następne strony
        has_more = len(exchanges) > limit
        page_exchanges = exchanges[:limit]
        
        # Konwertuj na response model
        exchange_responses = [
            ExchangeResponse(
                id=e['id'],
                name=e['name'],
                display_name=e.get('display_name'),
                is_active=e.get('is_active', True),
                created_at=e.get('created_at')
            )
            for e in page_exchanges
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return ExchangeListResponse(
            exchanges=exchange_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error listing exchanges: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list exchanges: {str(e)}")


@router.get("/active", response_model=ExchangeListResponse)
async def list_active_exchanges(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę tylko aktywnych giełd.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        ExchangeListResponse: Lista aktywnych giełd
    """
    return await list_exchanges(limit=limit, offset=offset, active_only=True)


@router.get("/count", response_model=Dict[str, int])
async def count_exchanges():
    """
    Zlicza wszystkie giełdy w bazie danych.
    
    Returns:
        Dict z liczbą giełd
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        all_exchanges = await exchanges_table.get_all(limit=10000)
        count = len(all_exchanges)
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting exchanges: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count exchanges: {str(e)}")


@router.get("/count/active", response_model=Dict[str, int])
async def count_active_exchanges():
    """
    Zlicza tylko aktywne giełdy.
    
    Returns:
        Dict z liczbą aktywnych giełd
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        active_exchanges = await exchanges_table.get_active(limit=10000)
        count = len(active_exchanges)
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting active exchanges: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count active exchanges: {str(e)}")


# ===================
# SEARCH OPERATIONS
# ===================

@router.get("/search/{exchange_name}", response_model=List[ExchangeResponse])
async def search_exchanges(
    exchange_name: str = Path(..., min_length=1, description="Nazwa giełdy do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Maksymalna liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje giełdy po nazwie (case-insensitive, LIKE search).
    
    Args:
        exchange_name: Nazwa lub część nazwy giełdy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        List[ExchangeResponse]: Lista znalezionych giełd
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        exchanges = await exchanges_table.search_by_name(exchange_name, limit=limit, offset=offset)
        
        return [
            ExchangeResponse(
                id=e['id'],
                name=e['name'],
                display_name=e.get('display_name'),
                is_active=e.get('is_active', True),
                created_at=e.get('created_at')
            )
            for e in exchanges
        ]
        
    except Exception as e:
        logger.error(f"Error searching exchanges by name '{exchange_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search exchanges: {str(e)}")


# ===================
# KLINES DATA
# ===================

@router.get("/klines/{asset_id}/{interval}")
async def get_klines(
    asset_id: int = Path(..., ge=1),
    interval: str = Path(...),
    start_time: Optional[int] = Query(default=None),
    end_time: Optional[int] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000)
):
    """Pobiera klines dla assetu."""
    db = await get_db()
    assets_table = db.get_factory().get_assets_table()
    asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
    
    asset = await assets_table.get_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    asset_name = asset['asset']
    quote_name = asset['quote']
    
    # Sprawdź czy na Binance (BinanceAPI w bazie)
    asset_exchanges = await asset_exchanges_table.get_by_asset_id(asset_id)
    binance_found = any("BINANCE" in ex.get('exchange_name', '').upper() for ex in asset_exchanges)
    
    if not binance_found:
        raise HTTPException(status_code=404, detail="Asset not available on Binance")
    
    # Pobierz klines
    api_facade = get_api_facade()
    binance_api = api_facade.get_fabric().get_binance_api()
    
    klines_data = binance_api._get_klines(
        base_currency=asset_name,
        quote_currency=quote_name,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return {
        "asset": asset_name,
        "quote": quote_name,
        "interval": interval,
        "exchange": "BINANCE",
        "klines": klines_data
    }


# ===================
# STATUS MANAGEMENT
# ===================

@router.post("/{exchange_id}/enable", response_model=StandardResponse)
async def enable_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy do włączenia")
):
    """
    Włącza giełdę (ustawia is_active=True).
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        StandardResponse: Potwierdzenie włączenia
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        # Sprawdź czy giełda istnieje
        existing = await exchanges_table.get_by_id(exchange_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Exchange with ID {exchange_id} not found")
        
        # Sprawdź czy już włączona
        if existing.get('is_active'):
            return StandardResponse(
                success=True,
                message=f"Exchange '{existing['name']}' is already enabled",
                data={"exchange_id": exchange_id, "is_active": True}
            )
        
        # Włącz giełdę
        success = await exchanges_table.update(exchange_id, is_active=True)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to enable exchange")
        
        return StandardResponse(
            success=True,
            message=f"Exchange '{existing['name']}' enabled successfully",
            data={"exchange_id": exchange_id, "is_active": True}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable exchange: {str(e)}")


@router.post("/{exchange_id}/disable", response_model=StandardResponse)
async def disable_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy do wyłączenia")
):
    """
    Wyłącza giełdę (ustawia is_active=False).
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        StandardResponse: Potwierdzenie wyłączenia
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        # Sprawdź czy giełda istnieje
        existing = await exchanges_table.get_by_id(exchange_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Exchange with ID {exchange_id} not found")
        
        # Sprawdź czy już wyłączona
        if not existing.get('is_active'):
            return StandardResponse(
                success=True,
                message=f"Exchange '{existing['name']}' is already disabled",
                data={"exchange_id": exchange_id, "is_active": False}
            )
        
        # Wyłącz giełdę
        success = await exchanges_table.update(exchange_id, is_active=False)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disable exchange")
        
        return StandardResponse(
            success=True,
            message=f"Exchange '{existing['name']}' disabled successfully",
            data={"exchange_id": exchange_id, "is_active": False}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable exchange: {str(e)}")


# ===================
# STATISTICS
# ===================

@router.get("/stats", response_model=ExchangeStatsResponse)
async def get_exchange_stats():
    """
    Pobiera ogólne statystyki giełd i ich relacji z assetami.
    
    Returns:
        ExchangeStatsResponse: Statystyki giełd
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
        
        # Zlicz giełdy
        all_exchanges = await exchanges_table.get_all(limit=10000)
        total_exchanges = len(all_exchanges)
        
        # Zlicz aktywne giełdy
        active_exchanges = await exchanges_table.get_active(limit=10000)
        active_count = len(active_exchanges)
        
        # Nieaktywne
        inactive_count = total_exchanges - active_count
        
        # Zlicz relacje
        all_relations = await asset_exchanges_table.get_all(limit=100000)
        total_relations = len(all_relations)
        
        # Oblicz procent aktywnych
        active_percentage = None
        if total_exchanges > 0:
            active_percentage = round((active_count / total_exchanges) * 100, 2)
        
        return ExchangeStatsResponse(
            total_exchanges=total_exchanges,
            active_exchanges=active_count,
            inactive_exchanges=inactive_count,
            exchange_asset_relations=total_relations,
            active_percentage=active_percentage
        )
        
    except Exception as e:
        logger.error(f"Error getting exchange stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ NA KOŃCU
# ===================

@router.get("/{exchange_id}", response_model=ExchangeResponse)
async def get_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Pobiera szczegóły konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        ExchangeResponse: Szczegóły giełdy
    """
    try:
        db = await get_db()
        exchanges_table = db.get_factory().get_exchanges_table()
        
        exchange = await exchanges_table.get_by_id(exchange_id)
        
        if not exchange:
            raise HTTPException(status_code=404, detail=f"Exchange with ID {exchange_id} not found")
        
        return ExchangeResponse(
            id=exchange['id'],
            name=exchange['name'],
            display_name=exchange.get('display_name'),
            is_active=exchange.get('is_active', True),
            created_at=exchange.get('created_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get exchange: {str(e)}")

