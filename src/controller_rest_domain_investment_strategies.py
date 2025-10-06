"""
REST API Controller dla domeny investment strategies (strategie inwestycyjne).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania strategiami inwestycyjnymi (CRUD)
- Włączania/wyłączania strategii
- Filtrowania strategii po statusie (enabled/disabled)
- Wyszukiwania strategii po nazwie i opisie
- Statystyk strategii

UWAGA: Ten kontroler NIE obsługuje strategii kupna i sprzedaży (trading strategies).
Te są w osobnej domenie controller_rest_domain_trading_strategies.py.

Bazuje na funkcjonalności z controller_telegram_domain_strategies.py

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field
from datetime import datetime

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/strategies/investment"
TAGS = ["Investment Strategies"]

# Modele Pydantic dla request/response


class InvestmentStrategyResponse(BaseModel):
    """Odpowiedź z informacją o strategii inwestycyjnej."""
    id: int
    name: str
    description: str
    enabled: bool
    created_at: Optional[datetime] = None


class InvestmentStrategyCreate(BaseModel):
    """Model do tworzenia nowej strategii inwestycyjnej."""
    name: str = Field(..., min_length=1, max_length=100, description="Nazwa strategii")
    description: str = Field(..., min_length=1, description="Opis strategii")
    enabled: bool = Field(default=True, description="Czy strategia jest włączona")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Conservative Growth",
                "description": "Strategy focused on stable long-term growth with minimal risk",
                "enabled": True
            }
        }


class InvestmentStrategyUpdate(BaseModel):
    """Model do aktualizacji strategii inwestycyjnej."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Nazwa strategii")
    description: Optional[str] = Field(None, min_length=1, description="Opis strategii")
    enabled: Optional[bool] = Field(None, description="Czy strategia jest włączona")


class InvestmentStrategyStatusUpdate(BaseModel):
    """Model do aktualizacji statusu strategii."""
    enabled: bool = Field(..., description="Nowy status strategii")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class InvestmentStrategiesListResponse(BaseModel):
    """Lista strategii inwestycyjnych z informacją o paginacji."""
    strategies: List[InvestmentStrategyResponse]
    pagination: PaginationInfo


class InvestmentStrategyStatsResponse(BaseModel):
    """Statystyki strategii inwestycyjnych."""
    total_strategies: int
    enabled_strategies: int
    disabled_strategies: int
    enabled_percentage: Optional[float] = None


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# Singleton dla DatabasePostgreSQL
db_instance: Optional[DatabasePostgreSQL] = None


async def get_db() -> DatabasePostgreSQL:
    """
    Dependency do pobierania instancji DatabasePostgreSQL.
    
    Returns:
        DatabasePostgreSQL: Instancja bazy danych PostgreSQL
    """
    global db_instance
    
    if db_instance is None:
        db_facade = DatabaseFacade()
        db_instance = db_facade.get_database_postgresql()
        await db_instance.init_db()
    
    return db_instance


# ===================
# ENDPOINTY GŁÓWNE
# ===================

@router.get("", response_model=Dict[str, Any])
async def investment_strategies_info():
    """Informacje o dostępnych endpointach strategii inwestycyjnych."""
    return {
        "message": "Investment Strategies REST API",
        "version": "1.0.0",
        "description": "API for investment strategies management (NOT trading buy/sell strategies)",
        "available_endpoints": {
            "list": "GET /strategies/investment - Lista wszystkich strategii",
            "enabled": "GET /strategies/investment/enabled - Lista włączonych strategii",
            "disabled": "GET /strategies/investment/disabled - Lista wyłączonych strategii",
            "get": "GET /strategies/investment/{id} - Szczegóły strategii",
            "create": "POST /strategies/investment - Tworzenie nowej strategii",
            "update": "PUT /strategies/investment/{id} - Aktualizacja strategii",
            "update_status": "PATCH /strategies/investment/{id}/status - Zmiana statusu strategii",
            "delete": "DELETE /strategies/investment/{id} - Usunięcie strategii",
            "enable": "POST /strategies/investment/{id}/enable - Włączenie strategii",
            "disable": "POST /strategies/investment/{id}/disable - Wyłączenie strategii",
            "search_name": "GET /strategies/investment/search/name/{pattern} - Wyszukiwanie po nazwie",
            "search_description": "GET /strategies/investment/search/description/{pattern} - Wyszukiwanie po opisie",
            "count": "GET /strategies/investment/count - Liczba wszystkich strategii",
            "count_enabled": "GET /strategies/investment/count/enabled - Liczba włączonych strategii",
            "stats": "GET /strategies/investment/stats - Statystyki strategii"
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{strategy_id}
# aby FastAPI nie próbowało parsować "count", "enabled" etc. jako integer

@router.get("/list", response_model=InvestmentStrategiesListResponse)
async def list_investment_strategies(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników"),
    enabled_only: bool = Query(default=False, description="Tylko włączone strategie")
):
    """
    Pobiera listę strategii inwestycyjnych z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        enabled_only: Czy pokazywać tylko włączone strategie
        
    Returns:
        InvestmentStrategiesListResponse: Lista strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Pobierz strategie z dodatkowym rekordem
        if enabled_only:
            strategies = await strategies_table.get_all_enabled_strategies(limit=limit + 1, offset=offset)
        else:
            strategies = await strategies_table.get_all(limit=limit + 1, offset=offset)
        
        # Sprawdź czy są następne strony
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        # Konwertuj na response model
        strategy_responses = [
            InvestmentStrategyResponse(
                id=s['id'],
                name=s['name'],
                description=s['description'],
                enabled=s['enabled'],
                created_at=s.get('created_at')
            )
            for s in page_strategies
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return InvestmentStrategiesListResponse(
            strategies=strategy_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error listing investment strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list investment strategies: {str(e)}")


@router.get("/enabled", response_model=InvestmentStrategiesListResponse)
async def list_enabled_investment_strategies(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę tylko włączonych strategii inwestycyjnych.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        InvestmentStrategiesListResponse: Lista włączonych strategii
    """
    return await list_investment_strategies(limit=limit, offset=offset, enabled_only=True)


@router.get("/disabled", response_model=InvestmentStrategiesListResponse)
async def list_disabled_investment_strategies(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę tylko wyłączonych strategii inwestycyjnych.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        InvestmentStrategiesListResponse: Lista wyłączonych strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Pobierz wszystkie i przefiltruj disabled
        all_strategies = await strategies_table.get_all(limit=10000)
        disabled_strategies = [s for s in all_strategies if not s['enabled']]
        
        # Zastosuj paginację
        start = offset
        end = offset + limit + 1
        page_strategies = disabled_strategies[start:end]
        
        has_more = len(page_strategies) > limit
        page_strategies = page_strategies[:limit]
        
        strategy_responses = [
            InvestmentStrategyResponse(
                id=s['id'],
                name=s['name'],
                description=s['description'],
                enabled=s['enabled'],
                created_at=s.get('created_at')
            )
            for s in page_strategies
        ]
        
        return InvestmentStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing disabled investment strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list disabled strategies: {str(e)}")


# ===================
# SEARCH OPERATIONS - PRZED /{strategy_id}
# ===================

@router.get("/search/name/{name_pattern}", response_model=InvestmentStrategiesListResponse)
async def search_investment_strategies_by_name(
    name_pattern: str = Path(..., min_length=1, description="Wzorzec nazwy do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje strategie inwestycyjne po wzorcu nazwy (case-insensitive, LIKE search).
    
    Args:
        name_pattern: Wzorzec nazwy lub część nazwy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        InvestmentStrategiesListResponse: Lista znalezionych strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        strategies = await strategies_table.search_by_name(
            name_pattern=name_pattern,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            InvestmentStrategyResponse(
                id=s['id'],
                name=s['name'],
                description=s['description'],
                enabled=s['enabled'],
                created_at=s.get('created_at')
            )
            for s in page_strategies
        ]
        
        return InvestmentStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching investment strategies by name '{name_pattern}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search strategies: {str(e)}")


@router.get("/search/description/{description_pattern}", response_model=InvestmentStrategiesListResponse)
async def search_investment_strategies_by_description(
    description_pattern: str = Path(..., min_length=1, description="Wzorzec opisu do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje strategie inwestycyjne po wzorcu opisu (case-insensitive, LIKE search).
    
    Args:
        description_pattern: Wzorzec opisu lub część opisu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        InvestmentStrategiesListResponse: Lista znalezionych strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        strategies = await strategies_table.search_by_description(
            description_pattern=description_pattern,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            InvestmentStrategyResponse(
                id=s['id'],
                name=s['name'],
                description=s['description'],
                enabled=s['enabled'],
                created_at=s.get('created_at')
            )
            for s in page_strategies
        ]
        
        return InvestmentStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching investment strategies by description '{description_pattern}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search strategies: {str(e)}")


# ===================
# COUNT OPERATIONS - PRZED /{strategy_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_investment_strategies():
    """
    Zlicza wszystkie strategie inwestycyjne.
    
    Returns:
        Dict z liczbą strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        count = await strategies_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting investment strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count strategies: {str(e)}")


@router.get("/count/enabled", response_model=Dict[str, int])
async def count_enabled_investment_strategies():
    """
    Zlicza tylko włączone strategie inwestycyjne.
    
    Returns:
        Dict z liczbą włączonych strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        count = await strategies_table.count_enabled()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting enabled investment strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count enabled strategies: {str(e)}")


# ===================
# STATISTICS - PRZED /{strategy_id}
# ===================

@router.get("/stats", response_model=InvestmentStrategyStatsResponse)
async def get_investment_strategies_stats():
    """
    Pobiera statystyki strategii inwestycyjnych.
    
    Returns:
        InvestmentStrategyStatsResponse: Statystyki strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Zlicz wszystkie i włączone
        total_count = await strategies_table.count_all()
        enabled_count = await strategies_table.count_enabled()
        disabled_count = total_count - enabled_count
        
        # Oblicz procent włączonych
        enabled_percentage = None
        if total_count > 0:
            enabled_percentage = round((enabled_count / total_count) * 100, 2)
        
        return InvestmentStrategyStatsResponse(
            total_strategies=total_count,
            enabled_strategies=enabled_count,
            disabled_strategies=disabled_count,
            enabled_percentage=enabled_percentage
        )
        
    except Exception as e:
        logger.error(f"Error getting investment strategies stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ NA KOŃCU
# ===================

@router.get("/{strategy_id}", response_model=InvestmentStrategyResponse)
async def get_investment_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii inwestycyjnej")
):
    """
    Pobiera szczegóły konkretnej strategii inwestycyjnej.
    
    Args:
        strategy_id: ID strategii
        
    Returns:
        InvestmentStrategyResponse: Szczegóły strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        strategy = await strategies_table.get_by_id(strategy_id)
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Investment strategy with ID {strategy_id} not found")
        
        return InvestmentStrategyResponse(
            id=strategy['id'],
            name=strategy['name'],
            description=strategy['description'],
            enabled=strategy['enabled'],
            created_at=strategy.get('created_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting investment strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get investment strategy: {str(e)}")


@router.post("", response_model=StandardResponse, status_code=201)
async def create_investment_strategy(
    strategy_data: InvestmentStrategyCreate = Body(..., description="Dane nowej strategii")
):
    """
    Tworzy nową strategię inwestycyjną.
    
    Args:
        strategy_data: Dane strategii do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonej strategii
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Sprawdź czy strategia o tej nazwie już istnieje
        existing = await strategies_table.get_by_name(strategy_data.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Investment strategy with name '{strategy_data.name}' already exists with ID {existing['id']}"
            )
        
        # Utwórz strategię
        strategy_id = await strategies_table.create(
            name=strategy_data.name,
            description=strategy_data.description,
            enabled=strategy_data.enabled
        )
        
        if not strategy_id:
            raise HTTPException(status_code=500, detail="Failed to create investment strategy")
        
        return StandardResponse(
            success=True,
            message=f"Investment strategy '{strategy_data.name}' created successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating investment strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create investment strategy: {str(e)}")


@router.put("/{strategy_id}", response_model=StandardResponse)
async def update_investment_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do aktualizacji"),
    strategy_data: InvestmentStrategyUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejącą strategię inwestycyjną.
    
    Args:
        strategy_id: ID strategii do aktualizacji
        strategy_data: Nowe dane strategii
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Investment strategy with ID {strategy_id} not found")
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if strategy_data.name is not None:
            # Sprawdź czy nowa nazwa nie koliduje z inną strategią
            name_check = await strategies_table.get_by_name(strategy_data.name)
            if name_check and name_check['id'] != strategy_id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Investment strategy with name '{strategy_data.name}' already exists"
                )
            update_data['name'] = strategy_data.name
        
        if strategy_data.description is not None:
            update_data['description'] = strategy_data.description
        
        if strategy_data.enabled is not None:
            update_data['enabled'] = strategy_data.enabled
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await strategies_table.update(strategy_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update investment strategy")
        
        return StandardResponse(
            success=True,
            message=f"Investment strategy {strategy_id} updated successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating investment strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update investment strategy: {str(e)}")


@router.patch("/{strategy_id}/status", response_model=StandardResponse)
async def update_investment_strategy_status(
    strategy_id: int = Path(..., ge=1, description="ID strategii"),
    status_data: InvestmentStrategyStatusUpdate = Body(..., description="Nowy status")
):
    """
    Aktualizuje tylko status strategii (enabled/disabled).
    
    Args:
        strategy_id: ID strategii
        status_data: Nowy status
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Investment strategy with ID {strategy_id} not found")
        
        # Aktualizuj status
        success = await strategies_table.update(strategy_id, enabled=status_data.enabled)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update strategy status")
        
        status_text = "enabled" if status_data.enabled else "disabled"
        
        return StandardResponse(
            success=True,
            message=f"Investment strategy '{existing['name']}' {status_text} successfully",
            data={"strategy_id": strategy_id, "enabled": status_data.enabled}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating investment strategy status {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update strategy status: {str(e)}")


@router.delete("/{strategy_id}", response_model=StandardResponse)
async def delete_investment_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do usunięcia")
):
    """
    Usuwa strategię inwestycyjną z bazy danych.
    
    Args:
        strategy_id: ID strategii do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Investment strategy with ID {strategy_id} not found")
        
        # Usuń strategię
        success = await strategies_table.delete(strategy_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete investment strategy")
        
        return StandardResponse(
            success=True,
            message=f"Investment strategy '{existing['name']}' (ID: {strategy_id}) deleted successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting investment strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete investment strategy: {str(e)}")


# ===================
# STATUS MANAGEMENT
# ===================

@router.post("/{strategy_id}/enable", response_model=StandardResponse)
async def enable_investment_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do włączenia")
):
    """
    Włącza strategię inwestycyjną (ustawia enabled=True).
    
    Args:
        strategy_id: ID strategii
        
    Returns:
        StandardResponse: Potwierdzenie włączenia
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Investment strategy with ID {strategy_id} not found")
        
        # Sprawdź czy już włączona
        if existing['enabled']:
            return StandardResponse(
                success=True,
                message=f"Investment strategy '{existing['name']}' is already enabled",
                data={"strategy_id": strategy_id, "enabled": True}
            )
        
        # Włącz strategię
        success = await strategies_table.enable_strategy(strategy_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to enable investment strategy")
        
        return StandardResponse(
            success=True,
            message=f"Investment strategy '{existing['name']}' enabled successfully",
            data={"strategy_id": strategy_id, "enabled": True}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling investment strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable investment strategy: {str(e)}")


@router.post("/{strategy_id}/disable", response_model=StandardResponse)
async def disable_investment_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do wyłączenia")
):
    """
    Wyłącza strategię inwestycyjną (ustawia enabled=False).
    
    Args:
        strategy_id: ID strategii
        
    Returns:
        StandardResponse: Potwierdzenie wyłączenia
    """
    try:
        db = await get_db()
        strategies_table = db.get_factory().get_investment_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Investment strategy with ID {strategy_id} not found")
        
        # Sprawdź czy już wyłączona
        if not existing['enabled']:
            return StandardResponse(
                success=True,
                message=f"Investment strategy '{existing['name']}' is already disabled",
                data={"strategy_id": strategy_id, "enabled": False}
            )
        
        # Wyłącz strategię
        success = await strategies_table.disable_strategy(strategy_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disable investment strategy")
        
        return StandardResponse(
            success=True,
            message=f"Investment strategy '{existing['name']}' disabled successfully",
            data={"strategy_id": strategy_id, "enabled": False}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling investment strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable investment strategy: {str(e)}")



