"""
REST API Controller dla domeny trading strategies (strategie kupna i sprzedaży).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania strategiami kupna (buy strategies)
- Zarządzania strategiami sprzedaży (sell strategies)
- Filtrowania strategii po typie (MARKET/LIMIT)
- Filtrowania strategii po metodzie (percent/absolute)
- Filtrowania strategii po giełdach
- Obliczania rzeczywistych kwot kupna/sprzedaży
- Statystyk strategii

UWAGA: Ten kontroler NIE obsługuje strategii inwestycyjnych (investment strategies).
Te będą w osobnej domenie.

Bazuje na funkcjonalności z controller_telegram_domain_strategies.py

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/strategies/trading"
TAGS = ["Trading Strategies"]

# Modele Pydantic dla request/response


class BuyStrategyResponse(BaseModel):
    """Odpowiedź z informacją o strategii kupna."""
    id: int
    exchange_account_state_id: int
    is_percent: bool
    type: str  # MARKET lub LIMIT
    movement_amount: Decimal
    exchange_id: Optional[int] = None
    exchange_name: Optional[str] = None
    account_type: Optional[str] = None
    currency: Optional[str] = None
    account_amount: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SellStrategyResponse(BaseModel):
    """Odpowiedź z informacją o strategii sprzedaży."""
    id: int
    exchange_account_state_id: int
    is_percent: bool
    type: str  # MARKET lub LIMIT
    movement_amount: Decimal
    exchange_id: Optional[int] = None
    exchange_name: Optional[str] = None
    account_type: Optional[str] = None
    currency: Optional[str] = None
    account_amount: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StrategyCreate(BaseModel):
    """Model do tworzenia nowej strategii."""
    exchange_account_state_id: int = Field(..., ge=1, description="ID stanu konta giełdowego")
    is_percent: bool = Field(..., description="Czy kwota jest procentem")
    type: str = Field(..., pattern="^(MARKET|LIMIT)$", description="Typ zlecenia: MARKET lub LIMIT")
    movement_amount: Decimal = Field(..., gt=0, description="Kwota ruchu (procent lub wartość bezwzględna)")

    class Config:
        json_schema_extra = {
            "example": {
                "exchange_account_state_id": 1,
                "is_percent": True,
                "type": "MARKET",
                "movement_amount": 10.5
            }
        }


class StrategyUpdate(BaseModel):
    """Model do aktualizacji strategii."""
    exchange_account_state_id: Optional[int] = Field(None, ge=1, description="ID stanu konta giełdowego")
    is_percent: Optional[bool] = Field(None, description="Czy kwota jest procentem")
    type: Optional[str] = Field(None, pattern="^(MARKET|LIMIT)$", description="Typ zlecenia")
    movement_amount: Optional[Decimal] = Field(None, gt=0, description="Kwota ruchu")


class CalculatedAmountResponse(BaseModel):
    """Odpowiedź z obliczoną kwotą."""
    strategy_id: int
    calculated_amount: float
    is_percent: bool
    movement_amount: Decimal
    account_amount: Optional[Decimal] = None


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class BuyStrategiesListResponse(BaseModel):
    """Lista strategii kupna z informacją o paginacji."""
    strategies: List[BuyStrategyResponse]
    pagination: PaginationInfo


class SellStrategiesListResponse(BaseModel):
    """Lista strategii sprzedaży z informacją o paginacji."""
    strategies: List[SellStrategyResponse]
    pagination: PaginationInfo


class StrategyStatsResponse(BaseModel):
    """Statystyki strategii."""
    total_buy_strategies: int
    total_sell_strategies: int
    buy_market_strategies: int
    buy_limit_strategies: int
    sell_market_strategies: int
    sell_limit_strategies: int
    buy_percent_strategies: int
    buy_absolute_strategies: int
    sell_percent_strategies: int
    sell_absolute_strategies: int


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
async def trading_strategies_info():
    """Informacje o dostępnych endpointach strategii tradingowych."""
    return {
        "message": "Trading Strategies REST API",
        "version": "1.0.0",
        "description": "API for buy and sell trading strategies (NOT investment strategies)",
        "available_endpoints": {
            "buy_strategies": {
                "list": "GET /strategies/trading/buy - Lista strategii kupna",
                "get": "GET /strategies/trading/buy/{id} - Szczegóły strategii kupna",
                "create": "POST /strategies/trading/buy - Tworzenie strategii kupna",
                "update": "PUT /strategies/trading/buy/{id} - Aktualizacja strategii kupna",
                "delete": "DELETE /strategies/trading/buy/{id} - Usunięcie strategii kupna",
                "by_type": "GET /strategies/trading/buy/type/{type} - Filtrowanie po typie (MARKET/LIMIT)",
                "by_exchange": "GET /strategies/trading/buy/exchange/{exchange_id} - Strategie dla giełdy",
                "percent": "GET /strategies/trading/buy/percent - Strategie procentowe",
                "absolute": "GET /strategies/trading/buy/absolute - Strategie z kwotą bezwzględną",
                "calculate": "GET /strategies/trading/buy/{id}/calculate - Oblicz rzeczywistą kwotę",
            },
            "sell_strategies": {
                "list": "GET /strategies/trading/sell - Lista strategii sprzedaży",
                "get": "GET /strategies/trading/sell/{id} - Szczegóły strategii sprzedaży",
                "create": "POST /strategies/trading/sell - Tworzenie strategii sprzedaży",
                "update": "PUT /strategies/trading/sell/{id} - Aktualizacja strategii sprzedaży",
                "delete": "DELETE /strategies/trading/sell/{id} - Usunięcie strategii sprzedaży",
                "by_type": "GET /strategies/trading/sell/type/{type} - Filtrowanie po typie (MARKET/LIMIT)",
                "by_exchange": "GET /strategies/trading/sell/exchange/{exchange_id} - Strategie dla giełdy",
                "percent": "GET /strategies/trading/sell/percent - Strategie procentowe",
                "absolute": "GET /strategies/trading/sell/absolute - Strategie z kwotą bezwzględną",
                "calculate": "GET /strategies/trading/sell/{id}/calculate - Oblicz rzeczywistą kwotę",
            },
            "stats": "GET /strategies/trading/stats - Statystyki strategii"
        }
    }


# ===================
# BUY STRATEGIES - CRUD
# ===================

@router.get("/buy", response_model=BuyStrategiesListResponse)
async def list_buy_strategies(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich strategii kupna z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        BuyStrategiesListResponse: Lista strategii kupna
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        # Pobierz strategie z dodatkowym rekordem
        strategies = await buy_strategies_table.get_all(limit=limit + 1, offset=offset)
        
        # Sprawdź czy są następne strony
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        # Konwertuj na response model
        strategy_responses = [
            BuyStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return BuyStrategiesListResponse(
            strategies=strategy_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error listing buy strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list buy strategies: {str(e)}")


@router.get("/buy/{strategy_id}", response_model=BuyStrategyResponse)
async def get_buy_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii kupna")
):
    """
    Pobiera szczegóły konkretnej strategii kupna.
    
    Args:
        strategy_id: ID strategii
        
    Returns:
        BuyStrategyResponse: Szczegóły strategii kupna
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        strategy = await buy_strategies_table.get_by_id(strategy_id)
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Buy strategy with ID {strategy_id} not found")
        
        return BuyStrategyResponse(
            id=strategy['id'],
            exchange_account_state_id=strategy['exchange_account_state_id'],
            is_percent=strategy['is_percent'],
            type=strategy['type'],
            movement_amount=strategy['movement_amount'],
            exchange_id=strategy.get('exchange_id'),
            exchange_name=strategy.get('exchange_name'),
            account_type=strategy.get('account_type'),
            currency=strategy.get('currency'),
            account_amount=strategy.get('account_amount'),
            created_at=strategy.get('created_at'),
            updated_at=strategy.get('updated_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting buy strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get buy strategy: {str(e)}")


@router.post("/buy", response_model=StandardResponse, status_code=201)
async def create_buy_strategy(
    strategy_data: StrategyCreate = Body(..., description="Dane nowej strategii kupna")
):
    """
    Tworzy nową strategię kupna.
    
    Args:
        strategy_data: Dane strategii do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonej strategii
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        # Walidacja dla procentów
        if strategy_data.is_percent and strategy_data.movement_amount > 100:
            raise HTTPException(
                status_code=400,
                detail="For is_percent=True, movement_amount should not exceed 100%"
            )
        
        # Sprawdź czy strategia dla tego account_state już istnieje (relacja 1:1)
        existing = await buy_strategies_table.get_by_exchange_account_state_id(
            strategy_data.exchange_account_state_id
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Buy strategy for account_state_id {strategy_data.exchange_account_state_id} already exists with ID {existing['id']}"
            )
        
        # Utwórz strategię
        strategy_id = await buy_strategies_table.create(
            exchange_account_state_id=strategy_data.exchange_account_state_id,
            is_percent=strategy_data.is_percent,
            type=strategy_data.type,
            movement_amount=float(strategy_data.movement_amount)
        )
        
        if not strategy_id:
            raise HTTPException(status_code=500, detail="Failed to create buy strategy")
        
        return StandardResponse(
            success=True,
            message=f"Buy strategy created successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating buy strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create buy strategy: {str(e)}")


@router.put("/buy/{strategy_id}", response_model=StandardResponse)
async def update_buy_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do aktualizacji"),
    strategy_data: StrategyUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejącą strategię kupna.
    
    Args:
        strategy_id: ID strategii do aktualizacji
        strategy_data: Nowe dane strategii
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await buy_strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Buy strategy with ID {strategy_id} not found")
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if strategy_data.exchange_account_state_id is not None:
            update_data['exchange_account_state_id'] = strategy_data.exchange_account_state_id
        if strategy_data.is_percent is not None:
            update_data['is_percent'] = strategy_data.is_percent
        if strategy_data.type is not None:
            update_data['type'] = strategy_data.type
        if strategy_data.movement_amount is not None:
            update_data['movement_amount'] = float(strategy_data.movement_amount)
            
            # Walidacja dla procentów
            is_percent_new = strategy_data.is_percent if strategy_data.is_percent is not None else existing['is_percent']
            if is_percent_new and strategy_data.movement_amount > 100:
                raise HTTPException(
                    status_code=400,
                    detail="For is_percent=True, movement_amount should not exceed 100%"
                )
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await buy_strategies_table.update(strategy_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update buy strategy")
        
        return StandardResponse(
            success=True,
            message=f"Buy strategy {strategy_id} updated successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating buy strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update buy strategy: {str(e)}")


@router.delete("/buy/{strategy_id}", response_model=StandardResponse)
async def delete_buy_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do usunięcia")
):
    """
    Usuwa strategię kupna z bazy danych.
    
    Args:
        strategy_id: ID strategii do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await buy_strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Buy strategy with ID {strategy_id} not found")
        
        # Usuń strategię
        success = await buy_strategies_table.delete(strategy_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete buy strategy")
        
        return StandardResponse(
            success=True,
            message=f"Buy strategy (ID: {strategy_id}) deleted successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting buy strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete buy strategy: {str(e)}")


# ===================
# BUY STRATEGIES - FILTERING
# ===================

@router.get("/buy/type/{strategy_type}", response_model=BuyStrategiesListResponse)
async def get_buy_strategies_by_type(
    strategy_type: str = Path(..., pattern="^(MARKET|LIMIT)$", description="Typ strategii"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie kupna filtrowane po typie (MARKET lub LIMIT).
    
    Args:
        strategy_type: Typ strategii (MARKET lub LIMIT)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        BuyStrategiesListResponse: Lista strategii kupna
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        strategies = await buy_strategies_table.get_by_strategy_type(
            strategy_type=strategy_type,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            BuyStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return BuyStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting buy strategies by type {strategy_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get buy strategies: {str(e)}")


@router.get("/buy/exchange/{exchange_id}", response_model=BuyStrategiesListResponse)
async def get_buy_strategies_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie kupna dla konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        BuyStrategiesListResponse: Lista strategii kupna dla giełdy
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        strategies = await buy_strategies_table.get_by_exchange_id(
            exchange_id=exchange_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            BuyStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return BuyStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting buy strategies for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get buy strategies: {str(e)}")


@router.get("/buy/percent", response_model=BuyStrategiesListResponse)
async def get_buy_strategies_percent(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie kupna bazujące na procentach.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        BuyStrategiesListResponse: Lista strategii procentowych
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        strategies = await buy_strategies_table.get_percent_based_strategies(
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            BuyStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return BuyStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting percent-based buy strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get buy strategies: {str(e)}")


@router.get("/buy/absolute", response_model=BuyStrategiesListResponse)
async def get_buy_strategies_absolute(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie kupna bazujące na kwotach bezwzględnych.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        BuyStrategiesListResponse: Lista strategii z kwotami bezwzględnymi
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        strategies = await buy_strategies_table.get_absolute_amount_strategies(
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            BuyStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return BuyStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting absolute-amount buy strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get buy strategies: {str(e)}")


@router.get("/buy/{strategy_id}/calculate", response_model=CalculatedAmountResponse)
async def calculate_buy_amount(
    strategy_id: int = Path(..., ge=1, description="ID strategii kupna")
):
    """
    Oblicza rzeczywistą kwotę do zakupu na podstawie strategii.
    
    Dla strategii procentowych: kwota = (saldo_konta * procent) / 100
    Dla strategii bezwzględnych: kwota = movement_amount
    
    Args:
        strategy_id: ID strategii kupna
        
    Returns:
        CalculatedAmountResponse: Obliczona kwota zakupu
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        
        # Oblicz kwotę
        calculated_amount = await buy_strategies_table.calculate_buy_amount(strategy_id)
        
        if calculated_amount is None:
            raise HTTPException(status_code=404, detail=f"Buy strategy with ID {strategy_id} not found")
        
        # Pobierz szczegóły strategii
        strategy = await buy_strategies_table.get_by_id(strategy_id)
        
        return CalculatedAmountResponse(
            strategy_id=strategy_id,
            calculated_amount=calculated_amount,
            is_percent=strategy['is_percent'],
            movement_amount=strategy['movement_amount'],
            account_amount=strategy.get('account_amount')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating buy amount for strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate buy amount: {str(e)}")


# ===================
# SELL STRATEGIES - CRUD
# ===================

@router.get("/sell", response_model=SellStrategiesListResponse)
async def list_sell_strategies(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich strategii sprzedaży z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        SellStrategiesListResponse: Lista strategii sprzedaży
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        strategies = await sell_strategies_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            SellStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return SellStrategiesListResponse(
            strategies=strategy_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error listing sell strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sell strategies: {str(e)}")


@router.get("/sell/{strategy_id}", response_model=SellStrategyResponse)
async def get_sell_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii sprzedaży")
):
    """
    Pobiera szczegóły konkretnej strategii sprzedaży.
    
    Args:
        strategy_id: ID strategii
        
    Returns:
        SellStrategyResponse: Szczegóły strategii sprzedaży
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        strategy = await sell_strategies_table.get_by_id(strategy_id)
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Sell strategy with ID {strategy_id} not found")
        
        return SellStrategyResponse(
            id=strategy['id'],
            exchange_account_state_id=strategy['exchange_account_state_id'],
            is_percent=strategy['is_percent'],
            type=strategy['type'],
            movement_amount=strategy['movement_amount'],
            exchange_id=strategy.get('exchange_id'),
            exchange_name=strategy.get('exchange_name'),
            account_type=strategy.get('account_type'),
            currency=strategy.get('currency'),
            account_amount=strategy.get('account_amount'),
            created_at=strategy.get('created_at'),
            updated_at=strategy.get('updated_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sell strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sell strategy: {str(e)}")


@router.post("/sell", response_model=StandardResponse, status_code=201)
async def create_sell_strategy(
    strategy_data: StrategyCreate = Body(..., description="Dane nowej strategii sprzedaży")
):
    """
    Tworzy nową strategię sprzedaży.
    
    Args:
        strategy_data: Dane strategii do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonej strategii
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # Walidacja dla procentów
        if strategy_data.is_percent and strategy_data.movement_amount > 100:
            raise HTTPException(
                status_code=400,
                detail="For is_percent=True, movement_amount should not exceed 100%"
            )
        
        # Sprawdź czy strategia dla tego account_state już istnieje (relacja 1:1)
        existing = await sell_strategies_table.get_by_exchange_account_state_id(
            strategy_data.exchange_account_state_id
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Sell strategy for account_state_id {strategy_data.exchange_account_state_id} already exists with ID {existing['id']}"
            )
        
        # Utwórz strategię
        strategy_id = await sell_strategies_table.create(
            exchange_account_state_id=strategy_data.exchange_account_state_id,
            is_percent=strategy_data.is_percent,
            type=strategy_data.type,
            movement_amount=float(strategy_data.movement_amount)
        )
        
        if not strategy_id:
            raise HTTPException(status_code=500, detail="Failed to create sell strategy")
        
        return StandardResponse(
            success=True,
            message=f"Sell strategy created successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating sell strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create sell strategy: {str(e)}")


@router.put("/sell/{strategy_id}", response_model=StandardResponse)
async def update_sell_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do aktualizacji"),
    strategy_data: StrategyUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejącą strategię sprzedaży.
    
    Args:
        strategy_id: ID strategii do aktualizacji
        strategy_data: Nowe dane strategii
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await sell_strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Sell strategy with ID {strategy_id} not found")
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if strategy_data.exchange_account_state_id is not None:
            update_data['exchange_account_state_id'] = strategy_data.exchange_account_state_id
        if strategy_data.is_percent is not None:
            update_data['is_percent'] = strategy_data.is_percent
        if strategy_data.type is not None:
            update_data['type'] = strategy_data.type
        if strategy_data.movement_amount is not None:
            update_data['movement_amount'] = float(strategy_data.movement_amount)
            
            # Walidacja dla procentów
            is_percent_new = strategy_data.is_percent if strategy_data.is_percent is not None else existing['is_percent']
            if is_percent_new and strategy_data.movement_amount > 100:
                raise HTTPException(
                    status_code=400,
                    detail="For is_percent=True, movement_amount should not exceed 100%"
                )
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await sell_strategies_table.update(strategy_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update sell strategy")
        
        return StandardResponse(
            success=True,
            message=f"Sell strategy {strategy_id} updated successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating sell strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update sell strategy: {str(e)}")


@router.delete("/sell/{strategy_id}", response_model=StandardResponse)
async def delete_sell_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii do usunięcia")
):
    """
    Usuwa strategię sprzedaży z bazy danych.
    
    Args:
        strategy_id: ID strategii do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # Sprawdź czy strategia istnieje
        existing = await sell_strategies_table.get_by_id(strategy_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Sell strategy with ID {strategy_id} not found")
        
        # Usuń strategię
        success = await sell_strategies_table.delete(strategy_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete sell strategy")
        
        return StandardResponse(
            success=True,
            message=f"Sell strategy (ID: {strategy_id}) deleted successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting sell strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete sell strategy: {str(e)}")


# ===================
# SELL STRATEGIES - FILTERING
# ===================

@router.get("/sell/type/{strategy_type}", response_model=SellStrategiesListResponse)
async def get_sell_strategies_by_type(
    strategy_type: str = Path(..., pattern="^(MARKET|LIMIT)$", description="Typ strategii"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie sprzedaży filtrowane po typie (MARKET lub LIMIT).
    
    Args:
        strategy_type: Typ strategii (MARKET lub LIMIT)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        SellStrategiesListResponse: Lista strategii sprzedaży
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        strategies = await sell_strategies_table.get_by_strategy_type(
            strategy_type=strategy_type,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            SellStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return SellStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting sell strategies by type {strategy_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sell strategies: {str(e)}")


@router.get("/sell/exchange/{exchange_id}", response_model=SellStrategiesListResponse)
async def get_sell_strategies_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie sprzedaży dla konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        SellStrategiesListResponse: Lista strategii sprzedaży dla giełdy
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        strategies = await sell_strategies_table.get_by_exchange_id(
            exchange_id=exchange_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            SellStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return SellStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting sell strategies for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sell strategies: {str(e)}")


@router.get("/sell/percent", response_model=SellStrategiesListResponse)
async def get_sell_strategies_percent(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie sprzedaży bazujące na procentach.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        SellStrategiesListResponse: Lista strategii procentowych
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        strategies = await sell_strategies_table.get_percent_based_strategies(
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            SellStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return SellStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting percent-based sell strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sell strategies: {str(e)}")


@router.get("/sell/absolute", response_model=SellStrategiesListResponse)
async def get_sell_strategies_absolute(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera strategie sprzedaży bazujące na kwotach bezwzględnych.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        SellStrategiesListResponse: Lista strategii z kwotami bezwzględnymi
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        strategies = await sell_strategies_table.get_absolute_amount_strategies(
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(strategies) > limit
        page_strategies = strategies[:limit]
        
        strategy_responses = [
            SellStrategyResponse(
                id=s['id'],
                exchange_account_state_id=s['exchange_account_state_id'],
                is_percent=s['is_percent'],
                type=s['type'],
                movement_amount=s['movement_amount'],
                exchange_id=s.get('exchange_id'),
                exchange_name=s.get('exchange_name'),
                account_type=s.get('account_type'),
                currency=s.get('currency'),
                account_amount=s.get('account_amount'),
                created_at=s.get('created_at'),
                updated_at=s.get('updated_at')
            )
            for s in page_strategies
        ]
        
        return SellStrategiesListResponse(
            strategies=strategy_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting absolute-amount sell strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sell strategies: {str(e)}")


@router.get("/sell/{strategy_id}/calculate", response_model=CalculatedAmountResponse)
async def calculate_sell_amount(
    strategy_id: int = Path(..., ge=1, description="ID strategii sprzedaży")
):
    """
    Oblicza rzeczywistą kwotę do sprzedaży na podstawie strategii.
    
    Dla strategii procentowych: kwota = (saldo_konta * procent) / 100
    Dla strategii bezwzględnych: kwota = movement_amount
    
    Args:
        strategy_id: ID strategii sprzedaży
        
    Returns:
        CalculatedAmountResponse: Obliczona kwota sprzedaży
    """
    try:
        db = await get_db()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # Oblicz kwotę
        calculated_amount = await sell_strategies_table.calculate_sell_amount(strategy_id)
        
        if calculated_amount is None:
            raise HTTPException(status_code=404, detail=f"Sell strategy with ID {strategy_id} not found")
        
        # Pobierz szczegóły strategii
        strategy = await sell_strategies_table.get_by_id(strategy_id)
        
        return CalculatedAmountResponse(
            strategy_id=strategy_id,
            calculated_amount=calculated_amount,
            is_percent=strategy['is_percent'],
            movement_amount=strategy['movement_amount'],
            account_amount=strategy.get('account_amount')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating sell amount for strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to calculate sell amount: {str(e)}")


# ===================
# STATISTICS
# ===================

@router.get("/stats", response_model=StrategyStatsResponse)
async def get_trading_strategies_stats():
    """
    Pobiera statystyki strategii kupna i sprzedaży.
    
    Returns:
        StrategyStatsResponse: Statystyki strategii
    """
    try:
        db = await get_db()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # Zlicz wszystkie strategie
        all_buy = await buy_strategies_table.get_all(limit=10000)
        all_sell = await sell_strategies_table.get_all(limit=10000)
        
        # Zlicz według typu
        buy_market = await buy_strategies_table.get_by_strategy_type("MARKET", limit=10000)
        buy_limit = await buy_strategies_table.get_by_strategy_type("LIMIT", limit=10000)
        sell_market = await sell_strategies_table.get_by_strategy_type("MARKET", limit=10000)
        sell_limit = await sell_strategies_table.get_by_strategy_type("LIMIT", limit=10000)
        
        # Zlicz według metody (procent vs absolute)
        buy_percent = await buy_strategies_table.get_percent_based_strategies(limit=10000)
        sell_percent = await sell_strategies_table.get_percent_based_strategies(limit=10000)
        
        return StrategyStatsResponse(
            total_buy_strategies=len(all_buy),
            total_sell_strategies=len(all_sell),
            buy_market_strategies=len(buy_market),
            buy_limit_strategies=len(buy_limit),
            sell_market_strategies=len(sell_market),
            sell_limit_strategies=len(sell_limit),
            buy_percent_strategies=len(buy_percent),
            buy_absolute_strategies=len(all_buy) - len(buy_percent),
            sell_percent_strategies=len(sell_percent),
            sell_absolute_strategies=len(all_sell) - len(sell_percent)
        )
        
    except Exception as e:
        logger.error(f"Error getting trading strategies stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

