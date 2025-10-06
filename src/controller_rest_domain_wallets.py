"""
REST API Controller dla domeny wallets (exchange account state - wallety transakcyjne).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania walletami/stanami kont giełdowych (CRUD)
- Filtrowania walletów po giełdzie, walucie, typie konta (SPOT/FUTURES)
- Pobierania aktywnych walletów i walletów z saldem
- Zarządzania statusem walletów (enable/disable)
- Aktualizacji sald walletów
- Podsumowania portfeli i statystyk
- Operacji batch (tworzenie wielu walletów)

UWAGA: Ten kontroler obsługuje TYLKO wallety transakcyjne (exchange account state).
Zwykłe transakcje będą w osobnym kontrolerze.

Bazuje na funkcjonalności z exchange_account_state_table.py

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field
from datetime import datetime

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/wallets"
TAGS = ["Exchange Account State / Wallets"]

# Modele Pydantic dla request/response


class WalletResponse(BaseModel):
    """Odpowiedź z informacją o wallecie/stanie konta giełdowego."""
    id: int
    exchange_id: int
    type: str  # SPOT lub FUTURES
    is_enabled: bool
    currency: str
    amount: Decimal
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    exchange_name: Optional[str] = None
    exchange_display_name: Optional[str] = None


class WalletCreate(BaseModel):
    """Model do tworzenia nowego walletu."""
    exchange_id: int = Field(..., ge=1, description="ID giełdy")
    type: str = Field(..., pattern="^(SPOT|FUTURES)$", description="Typ konta: SPOT lub FUTURES")
    currency: str = Field(..., min_length=1, max_length=10, description="Waluta (np. BTC, ETH, USDT)")
    amount: Decimal = Field(default=0.0, ge=0, description="Początkowe saldo")
    is_enabled: bool = Field(default=True, description="Czy wallet jest aktywny")

    class Config:
        json_schema_extra = {
            "example": {
                "exchange_id": 1,
                "type": "SPOT",
                "currency": "USDT",
                "amount": 1000.0,
                "is_enabled": True
            }
        }


class WalletBatchCreate(BaseModel):
    """Model do tworzenia wielu walletów jednocześnie."""
    wallets: List[WalletCreate] = Field(..., min_items=1, max_items=100, description="Lista walletów do utworzenia")


class WalletUpdate(BaseModel):
    """Model do aktualizacji walletu."""
    exchange_id: Optional[int] = Field(None, ge=1, description="ID giełdy")
    type: Optional[str] = Field(None, pattern="^(SPOT|FUTURES)$", description="Typ konta")
    currency: Optional[str] = Field(None, min_length=1, max_length=10, description="Waluta")
    amount: Optional[Decimal] = Field(None, ge=0, description="Saldo")
    is_enabled: Optional[bool] = Field(None, description="Status aktywności")


class WalletAmountUpdate(BaseModel):
    """Model do aktualizacji tylko salda walletu."""
    amount: Decimal = Field(..., ge=0, description="Nowe saldo")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class WalletListResponse(BaseModel):
    """Lista walletów z informacją o paginacji."""
    wallets: List[WalletResponse]
    pagination: PaginationInfo


class PortfolioSummaryItem(BaseModel):
    """Element podsumowania portfela."""
    exchange_name: str
    account_type: str
    currency: str
    total_amount: Decimal
    accounts_count: int
    enabled_accounts: int
    last_updated: Optional[datetime] = None


class CurrencyBalanceResponse(BaseModel):
    """Łączne saldo dla waluty."""
    currency: str
    total_amount: Decimal
    accounts_count: int
    exchanges_count: int
    enabled_accounts: int


class WalletStatsResponse(BaseModel):
    """Statystyki walletów."""
    total_wallets: int
    enabled_wallets: int
    disabled_wallets: int
    wallets_with_balance: int
    unique_currencies: int
    unique_exchanges: int


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class BatchCreateResponse(BaseModel):
    """Odpowiedź dla batch create."""
    success: bool
    message: str
    created_count: int
    created_wallets: Dict[str, int]


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
async def wallets_info():
    """Informacje o dostępnych endpointach walletów transakcyjnych."""
    return {
        "message": "Exchange Account State / Wallets REST API",
        "version": "1.0.0",
        "description": "API for managing exchange account states (transaction wallets) including SPOT and FUTURES accounts",
        "available_endpoints": {
            "crud": {
                "list": "GET /wallets/list - Lista wszystkich walletów",
                "get": "GET /wallets/{id} - Szczegóły walletu",
                "get_specific": "GET /wallets/specific/{exchange_id}/{type}/{currency} - Konkretny wallet",
                "create": "POST /wallets - Tworzenie nowego walletu",
                "create_batch": "POST /wallets/batch - Tworzenie wielu walletów",
                "update": "PUT /wallets/{id} - Aktualizacja walletu",
                "update_amount": "PATCH /wallets/{id}/amount - Aktualizacja salda",
                "delete": "DELETE /wallets/{id} - Usunięcie walletu"
            },
            "filtering": {
                "by_exchange": "GET /wallets/exchange/{exchange_id} - Wallety dla giełdy",
                "by_exchange_and_type": "GET /wallets/exchange/{exchange_id}/type/{account_type} - Wallety dla giełdy i typu",
                "by_currency": "GET /wallets/currency/{currency} - Wallety dla waluty",
                "enabled": "GET /wallets/enabled - Aktywne wallety",
                "with_balance": "GET /wallets/with-balance - Wallety z saldem"
            },
            "portfolio": {
                "portfolio_summary": "GET /wallets/portfolio/{exchange_id} - Podsumowanie portfela dla giełdy",
                "balance_by_currency": "GET /wallets/balance/currency/{currency} - Łączne saldo dla waluty"
            },
            "management": {
                "enable": "POST /wallets/{id}/enable - Włączenie walletu",
                "disable": "POST /wallets/{id}/disable - Wyłączenie walletu",
                "toggle_status": "POST /wallets/{id}/toggle - Zmiana statusu"
            },
            "stats": {
                "count": "GET /wallets/count - Liczba wszystkich walletów",
                "count_by_exchange": "GET /wallets/count/exchange/{exchange_id} - Liczba walletów dla giełdy",
                "stats": "GET /wallets/stats - Statystyki walletów"
            }
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{wallet_id}

@router.get("/list", response_model=WalletListResponse)
async def list_wallets(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich walletów z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        WalletListResponse: Lista walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(wallets) > limit
        page_wallets = wallets[:limit]
        
        wallet_responses = [
            WalletResponse(
                id=w['id'],
                exchange_id=w['exchange_id'],
                type=w['type'],
                is_enabled=w['is_enabled'],
                currency=w['currency'],
                amount=Decimal(str(w['amount'])),
                created_at=w.get('created_at'),
                updated_at=w.get('updated_at'),
                exchange_name=w.get('exchange_name'),
                exchange_display_name=w.get('exchange_display_name')
            )
            for w in page_wallets
        ]
        
        return WalletListResponse(
            wallets=wallet_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing wallets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list wallets: {str(e)}")


# ===================
# FILTERING - PRZED /{wallet_id}
# ===================

@router.get("/exchange/{exchange_id}", response_model=WalletListResponse)
async def get_wallets_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera wallety dla konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        WalletListResponse: Lista walletów dla giełdy
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_by_exchange_id(exchange_id=exchange_id, limit=limit + 1, offset=offset)
        
        has_more = len(wallets) > limit
        page_wallets = wallets[:limit]
        
        wallet_responses = [
            WalletResponse(
                id=w['id'],
                exchange_id=w['exchange_id'],
                type=w['type'],
                is_enabled=w['is_enabled'],
                currency=w['currency'],
                amount=Decimal(str(w['amount'])),
                created_at=w.get('created_at'),
                updated_at=w.get('updated_at'),
                exchange_name=w.get('exchange_name'),
                exchange_display_name=w.get('exchange_display_name')
            )
            for w in page_wallets
        ]
        
        return WalletListResponse(
            wallets=wallet_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting wallets for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallets: {str(e)}")


@router.get("/exchange/{exchange_id}/type/{account_type}", response_model=WalletListResponse)
async def get_wallets_by_exchange_and_type(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    account_type: str = Path(..., pattern="^(SPOT|FUTURES)$", description="Typ konta"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera wallety dla giełdy i typu konta.
    
    Args:
        exchange_id: ID giełdy
        account_type: Typ konta (SPOT lub FUTURES)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        WalletListResponse: Lista walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_by_exchange_and_type(
            exchange_id=exchange_id,
            account_type=account_type,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(wallets) > limit
        page_wallets = wallets[:limit]
        
        wallet_responses = [
            WalletResponse(
                id=w['id'],
                exchange_id=w['exchange_id'],
                type=w['type'],
                is_enabled=w['is_enabled'],
                currency=w['currency'],
                amount=Decimal(str(w['amount'])),
                created_at=w.get('created_at'),
                updated_at=w.get('updated_at'),
                exchange_name=w.get('exchange_name'),
                exchange_display_name=w.get('exchange_display_name')
            )
            for w in page_wallets
        ]
        
        return WalletListResponse(
            wallets=wallet_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting wallets for exchange {exchange_id} and type {account_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallets: {str(e)}")


@router.get("/currency/{currency}", response_model=WalletListResponse)
async def get_wallets_by_currency(
    currency: str = Path(..., min_length=1, max_length=10, description="Waluta"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera wallety dla konkretnej waluty.
    
    Args:
        currency: Waluta (np. BTC, ETH, USDT)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        WalletListResponse: Lista walletów dla waluty
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_by_currency(currency=currency, limit=limit + 1, offset=offset)
        
        has_more = len(wallets) > limit
        page_wallets = wallets[:limit]
        
        wallet_responses = [
            WalletResponse(
                id=w['id'],
                exchange_id=w['exchange_id'],
                type=w['type'],
                is_enabled=w['is_enabled'],
                currency=w['currency'],
                amount=Decimal(str(w['amount'])),
                created_at=w.get('created_at'),
                updated_at=w.get('updated_at'),
                exchange_name=w.get('exchange_name'),
                exchange_display_name=w.get('exchange_display_name')
            )
            for w in page_wallets
        ]
        
        return WalletListResponse(
            wallets=wallet_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting wallets for currency {currency}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallets: {str(e)}")


@router.get("/enabled", response_model=WalletListResponse)
async def get_enabled_wallets(
    exchange_id: Optional[int] = Query(None, ge=1, description="Opcjonalny filtr po giełdzie"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera aktywne wallety (is_enabled = true).
    
    Args:
        exchange_id: Opcjonalny filtr po giełdzie
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        WalletListResponse: Lista aktywnych walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_enabled_accounts(
            exchange_id=exchange_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(wallets) > limit
        page_wallets = wallets[:limit]
        
        wallet_responses = [
            WalletResponse(
                id=w['id'],
                exchange_id=w['exchange_id'],
                type=w['type'],
                is_enabled=w['is_enabled'],
                currency=w['currency'],
                amount=Decimal(str(w['amount'])),
                created_at=w.get('created_at'),
                updated_at=w.get('updated_at'),
                exchange_name=w.get('exchange_name'),
                exchange_display_name=w.get('exchange_display_name')
            )
            for w in page_wallets
        ]
        
        return WalletListResponse(
            wallets=wallet_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting enabled wallets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get enabled wallets: {str(e)}")


@router.get("/with-balance", response_model=WalletListResponse)
async def get_wallets_with_balance(
    min_amount: float = Query(default=0.0, ge=0, description="Minimalne saldo"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera wallety z saldem większym niż podana wartość.
    
    Args:
        min_amount: Minimalne saldo
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        WalletListResponse: Lista walletów z saldem
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_accounts_with_balance(
            min_amount=min_amount,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(wallets) > limit
        page_wallets = wallets[:limit]
        
        wallet_responses = [
            WalletResponse(
                id=w['id'],
                exchange_id=w['exchange_id'],
                type=w['type'],
                is_enabled=w['is_enabled'],
                currency=w['currency'],
                amount=Decimal(str(w['amount'])),
                created_at=w.get('created_at'),
                updated_at=w.get('updated_at'),
                exchange_name=w.get('exchange_name'),
                exchange_display_name=w.get('exchange_display_name')
            )
            for w in page_wallets
        ]
        
        return WalletListResponse(
            wallets=wallet_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting wallets with balance: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallets: {str(e)}")


@router.get("/specific/{exchange_id}/{account_type}/{currency}", response_model=WalletResponse)
async def get_specific_wallet(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    account_type: str = Path(..., pattern="^(SPOT|FUTURES)$", description="Typ konta"),
    currency: str = Path(..., min_length=1, max_length=10, description="Waluta")
):
    """
    Pobiera konkretny wallet po exchange_id, typie i walucie.
    
    Args:
        exchange_id: ID giełdy
        account_type: Typ konta (SPOT lub FUTURES)
        currency: Waluta
        
    Returns:
        WalletResponse: Szczegóły walletu
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallet = await wallets_table.get_specific_account(
            exchange_id=exchange_id,
            account_type=account_type,
            currency=currency
        )
        
        if not wallet:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet not found for exchange {exchange_id}, type {account_type}, currency {currency}"
            )
        
        return WalletResponse(
            id=wallet['id'],
            exchange_id=wallet['exchange_id'],
            type=wallet['type'],
            is_enabled=wallet['is_enabled'],
            currency=wallet['currency'],
            amount=Decimal(str(wallet['amount'])),
            created_at=wallet.get('created_at'),
            updated_at=wallet.get('updated_at'),
            exchange_name=wallet.get('exchange_name'),
            exchange_display_name=wallet.get('exchange_display_name')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting specific wallet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallet: {str(e)}")


# ===================
# PORTFOLIO - PRZED /{wallet_id}
# ===================

@router.get("/portfolio/{exchange_id}", response_model=List[PortfolioSummaryItem])
async def get_portfolio_summary(
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Pobiera podsumowanie portfela dla giełdy (wszystkie waluty i typy kont).
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        List[PortfolioSummaryItem]: Podsumowanie portfela
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        summary = await wallets_table.get_portfolio_summary_by_exchange(exchange_id)
        
        summary_responses = [
            PortfolioSummaryItem(
                exchange_name=s['exchange_name'],
                account_type=s['account_type'],
                currency=s['currency'],
                total_amount=Decimal(str(s['total_amount'])),
                accounts_count=s['accounts_count'],
                enabled_accounts=s['enabled_accounts'],
                last_updated=s.get('last_updated')
            )
            for s in summary
        ]
        
        return summary_responses
        
    except Exception as e:
        logger.error(f"Error getting portfolio summary for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")


@router.get("/balance/currency/{currency}", response_model=CurrencyBalanceResponse)
async def get_balance_by_currency(
    currency: str = Path(..., min_length=1, max_length=10, description="Waluta")
):
    """
    Pobiera łączne saldo dla waluty na wszystkich giełdach i kontach.
    
    Args:
        currency: Waluta (np. BTC, ETH, USDT)
        
    Returns:
        CurrencyBalanceResponse: Łączne saldo dla waluty
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        balance = await wallets_table.get_total_balance_by_currency(currency)
        
        if not balance:
            raise HTTPException(
                status_code=404,
                detail=f"No balance found for currency {currency}"
            )
        
        return CurrencyBalanceResponse(
            currency=balance['currency'],
            total_amount=Decimal(str(balance['total_amount'])),
            accounts_count=balance['accounts_count'],
            exchanges_count=balance['exchanges_count'],
            enabled_accounts=balance['enabled_accounts']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting balance for currency {currency}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get balance: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{wallet_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_wallets():
    """
    Zlicza wszystkie wallety.
    
    Returns:
        Dict z liczbą walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Pobierz wszystkie i zlicz
        all_wallets = await wallets_table.get_all(limit=10000)
        count = len(all_wallets)
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting wallets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count wallets: {str(e)}")


@router.get("/count/exchange/{exchange_id}", response_model=Dict[str, int])
async def count_wallets_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Zlicza wallety dla konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        Dict z liczbą walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallets = await wallets_table.get_by_exchange_id(exchange_id, limit=10000)
        count = len(wallets)
        
        return {"count": count, "exchange_id": exchange_id}
        
    except Exception as e:
        logger.error(f"Error counting wallets for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count wallets: {str(e)}")


@router.get("/stats", response_model=WalletStatsResponse)
async def get_wallet_stats():
    """
    Pobiera statystyki walletów.
    
    Returns:
        WalletStatsResponse: Statystyki walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        all_wallets = await wallets_table.get_all(limit=10000)
        enabled_wallets = await wallets_table.get_enabled_accounts(limit=10000)
        wallets_with_balance = await wallets_table.get_accounts_with_balance(min_amount=0.0001, limit=10000)
        
        # Zlicz unikalne waluty i giełdy
        currencies = set()
        exchanges = set()
        for wallet in all_wallets:
            currencies.add(wallet['currency'])
            exchanges.add(wallet['exchange_id'])
        
        return WalletStatsResponse(
            total_wallets=len(all_wallets),
            enabled_wallets=len(enabled_wallets),
            disabled_wallets=len(all_wallets) - len(enabled_wallets),
            wallets_with_balance=len(wallets_with_balance),
            unique_currencies=len(currencies),
            unique_exchanges=len(exchanges)
        )
        
    except Exception as e:
        logger.error(f"Error getting wallet stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ PO SPECYFICZNYCH
# ===================

@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: int = Path(..., ge=1, description="ID walletu")
):
    """
    Pobiera szczegóły konkretnego walletu.
    
    Args:
        wallet_id: ID walletu
        
    Returns:
        WalletResponse: Szczegóły walletu
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallet = await wallets_table.get_by_id(wallet_id)
        
        if not wallet:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        return WalletResponse(
            id=wallet['id'],
            exchange_id=wallet['exchange_id'],
            type=wallet['type'],
            is_enabled=wallet['is_enabled'],
            currency=wallet['currency'],
            amount=Decimal(str(wallet['amount'])),
            created_at=wallet.get('created_at'),
            updated_at=wallet.get('updated_at'),
            exchange_name=wallet.get('exchange_name'),
            exchange_display_name=wallet.get('exchange_display_name')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get wallet: {str(e)}")


@router.post("", response_model=StandardResponse, status_code=201)
async def create_wallet(
    wallet_data: WalletCreate = Body(..., description="Dane nowego walletu")
):
    """
    Tworzy nowy wallet.
    
    Args:
        wallet_data: Dane walletu do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonego walletu
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        wallet_id = await wallets_table.create(
            exchange_id=wallet_data.exchange_id,
            type=wallet_data.type,
            currency=wallet_data.currency,
            amount=float(wallet_data.amount),
            is_enabled=wallet_data.is_enabled
        )
        
        if not wallet_id:
            raise HTTPException(status_code=500, detail="Failed to create wallet")
        
        return StandardResponse(
            success=True,
            message="Wallet created successfully",
            data={"wallet_id": wallet_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating wallet: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create wallet: {str(e)}")


@router.post("/batch", response_model=BatchCreateResponse, status_code=201)
async def create_wallets_batch(
    batch_data: WalletBatchCreate = Body(..., description="Lista walletów do utworzenia")
):
    """
    Tworzy wiele walletów jednocześnie.
    
    Args:
        batch_data: Lista walletów do utworzenia
        
    Returns:
        BatchCreateResponse: Odpowiedź z listą utworzonych walletów
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Przygotuj dane dla create_many
        wallets_to_create = [
            {
                "exchange_id": w.exchange_id,
                "type": w.type,
                "currency": w.currency,
                "amount": float(w.amount),
                "is_enabled": w.is_enabled
            }
            for w in batch_data.wallets
        ]
        
        created_wallets = await wallets_table.create_many(wallets_to_create)
        
        return BatchCreateResponse(
            success=True,
            message=f"Created {len(created_wallets)} wallets out of {len(batch_data.wallets)} requested",
            created_count=len(created_wallets),
            created_wallets=created_wallets
        )
        
    except Exception as e:
        logger.error(f"Error creating wallets batch: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create wallets: {str(e)}")


@router.put("/{wallet_id}", response_model=StandardResponse)
async def update_wallet(
    wallet_id: int = Path(..., ge=1, description="ID walletu do aktualizacji"),
    wallet_data: WalletUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejący wallet.
    
    Args:
        wallet_id: ID walletu do aktualizacji
        wallet_data: Nowe dane walletu
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Sprawdź czy wallet istnieje
        existing = await wallets_table.get_by_id(wallet_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if wallet_data.exchange_id is not None:
            update_data['exchange_id'] = wallet_data.exchange_id
        if wallet_data.type is not None:
            update_data['type'] = wallet_data.type
        if wallet_data.currency is not None:
            update_data['currency'] = wallet_data.currency
        if wallet_data.amount is not None:
            update_data['amount'] = float(wallet_data.amount)
        if wallet_data.is_enabled is not None:
            update_data['is_enabled'] = wallet_data.is_enabled
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        success = await wallets_table.update(wallet_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update wallet")
        
        return StandardResponse(
            success=True,
            message=f"Wallet {wallet_id} updated successfully",
            data={"wallet_id": wallet_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update wallet: {str(e)}")


@router.patch("/{wallet_id}/amount", response_model=StandardResponse)
async def update_wallet_amount(
    wallet_id: int = Path(..., ge=1, description="ID walletu"),
    amount_data: WalletAmountUpdate = Body(..., description="Nowe saldo")
):
    """
    Aktualizuje tylko saldo walletu.
    
    Args:
        wallet_id: ID walletu
        amount_data: Nowe saldo
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Sprawdź czy wallet istnieje
        existing = await wallets_table.get_by_id(wallet_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        success = await wallets_table.update_amount(wallet_id, float(amount_data.amount))
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update wallet amount")
        
        return StandardResponse(
            success=True,
            message=f"Wallet {wallet_id} amount updated successfully",
            data={"wallet_id": wallet_id, "new_amount": str(amount_data.amount)}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating wallet amount {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update wallet amount: {str(e)}")


@router.delete("/{wallet_id}", response_model=StandardResponse)
async def delete_wallet(
    wallet_id: int = Path(..., ge=1, description="ID walletu do usunięcia")
):
    """
    Usuwa wallet z bazy danych.
    
    Args:
        wallet_id: ID walletu do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Sprawdź czy wallet istnieje
        existing = await wallets_table.get_by_id(wallet_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        success = await wallets_table.delete(wallet_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete wallet")
        
        return StandardResponse(
            success=True,
            message=f"Wallet (ID: {wallet_id}) deleted successfully",
            data={"wallet_id": wallet_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete wallet: {str(e)}")


# ===================
# MANAGEMENT OPERATIONS
# ===================

@router.post("/{wallet_id}/enable", response_model=StandardResponse)
async def enable_wallet(
    wallet_id: int = Path(..., ge=1, description="ID walletu do włączenia")
):
    """
    Włącza wallet (is_enabled = true).
    
    Args:
        wallet_id: ID walletu
        
    Returns:
        StandardResponse: Potwierdzenie włączenia
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Sprawdź czy wallet istnieje
        existing = await wallets_table.get_by_id(wallet_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        if existing.get('is_enabled'):
            return StandardResponse(
                success=True,
                message=f"Wallet {wallet_id} is already enabled",
                data={"wallet_id": wallet_id, "is_enabled": True}
            )
        
        success = await wallets_table.update(wallet_id, is_enabled=True)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to enable wallet")
        
        return StandardResponse(
            success=True,
            message=f"Wallet {wallet_id} enabled successfully",
            data={"wallet_id": wallet_id, "is_enabled": True}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable wallet: {str(e)}")


@router.post("/{wallet_id}/disable", response_model=StandardResponse)
async def disable_wallet(
    wallet_id: int = Path(..., ge=1, description="ID walletu do wyłączenia")
):
    """
    Wyłącza wallet (is_enabled = false).
    
    Args:
        wallet_id: ID walletu
        
    Returns:
        StandardResponse: Potwierdzenie wyłączenia
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Sprawdź czy wallet istnieje
        existing = await wallets_table.get_by_id(wallet_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        if not existing.get('is_enabled'):
            return StandardResponse(
                success=True,
                message=f"Wallet {wallet_id} is already disabled",
                data={"wallet_id": wallet_id, "is_enabled": False}
            )
        
        success = await wallets_table.update(wallet_id, is_enabled=False)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disable wallet")
        
        return StandardResponse(
            success=True,
            message=f"Wallet {wallet_id} disabled successfully",
            data={"wallet_id": wallet_id, "is_enabled": False}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable wallet: {str(e)}")


@router.post("/{wallet_id}/toggle", response_model=StandardResponse)
async def toggle_wallet_status(
    wallet_id: int = Path(..., ge=1, description="ID walletu")
):
    """
    Zmienia status walletu na przeciwny (enabled <-> disabled).
    
    Args:
        wallet_id: ID walletu
        
    Returns:
        StandardResponse: Potwierdzenie zmiany statusu
    """
    try:
        db = await get_db()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        
        # Sprawdź czy wallet istnieje
        existing = await wallets_table.get_by_id(wallet_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Wallet with ID {wallet_id} not found"
            )
        
        success = await wallets_table.toggle_account_status(wallet_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to toggle wallet status")
        
        new_status = not existing.get('is_enabled')
        
        return StandardResponse(
            success=True,
            message=f"Wallet {wallet_id} status toggled successfully",
            data={"wallet_id": wallet_id, "is_enabled": new_status}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling wallet status {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to toggle wallet status: {str(e)}")

