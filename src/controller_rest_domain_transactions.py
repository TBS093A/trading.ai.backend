"""
REST API Controller dla domeny transactions (exchange transactions - transakcje giełdowe).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania transakcjami giełdowymi (CRUD)
- Filtrowania transakcji po asset, giełdzie, typie (BUY/SELL), interpretacji
- Filtrowania po dacie, zakresie czasowym, portfelu, strategii
- Pobierania transakcji bez interpretacji
- Portfolio summary (podsumowania portfela)
- Batch creation (tworzenie wielu transakcji)
- Statystyk i agregacji danych transakcyjnych

UWAGA: Ten kontroler obsługuje transakcje giełdowe (exchange transactions).
Integruje logikę tworzenia transakcji z API exchanges z mapowaniem na bazę danych.

Bazuje na funkcjonalności z exchange_transactions_table.py i controller_telegram_domain_transactions.py

Autor: AI Assistant
"""

import logging
import json
from typing import Dict, Any, Optional, List
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field
from datetime import datetime

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

# Import API Facade for exchange integration
from .api import ApiFacade

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/transactions"
TAGS = ["Exchange Transactions"]

# Modele Pydantic dla request/response


class TransactionResponse(BaseModel):
    """Odpowiedź z informacją o transakcji giełdowej."""
    id: int
    exchange_id: int
    asset_id: int
    exchange_account_state_id: int
    general_interpretation_id: Optional[int] = None
    buy_strategy_id: Optional[int] = None
    sell_strategy_id: Optional[int] = None
    type: str  # BUY lub SELL
    quote_amount: Decimal
    asset_amount: Decimal
    created_at: int
    # Powiązane dane
    exchange_name: Optional[str] = None
    exchange_display_name: Optional[str] = None
    asset: Optional[str] = None
    quote: Optional[str] = None
    currency: Optional[str] = None
    account_amount: Optional[Decimal] = None
    account_type: Optional[str] = None
    buy_strategy_type: Optional[str] = None
    buy_movement_amount: Optional[Decimal] = None
    buy_is_percent: Optional[bool] = None
    sell_strategy_type: Optional[str] = None
    sell_movement_amount: Optional[Decimal] = None
    sell_is_percent: Optional[bool] = None
    interpretation_title: Optional[str] = None
    interpretation_content: Optional[str] = None


class TransactionCreate(BaseModel):
    """
    Model do tworzenia nowej transakcji poprzez wykonanie jej na giełdzie.
    
    Dwa podejścia:
    1. Z strategią - podaj buy_strategy_id (dla BUY) lub sell_strategy_id (dla SELL).
       Kwoty są obliczane automatycznie na podstawie strategii.
    2. Bez strategii (manual) - podaj asset_amount i quote_amount bezpośrednio.
       Używane dla ręcznych transakcji (nie przez cronjob).
    """
    exchange_id: int = Field(..., ge=1, description="ID giełdy")
    asset_id: int = Field(..., ge=1, description="ID assetu")
    exchange_account_state_id: int = Field(..., ge=1, description="ID stanu konta (wallet)")
    type: str = Field(..., pattern="^(BUY|SELL)$", description="Typ transakcji (BUY/SELL)")
    
    # Podejście 1: Z strategią (dla automatycznych transakcji)
    buy_strategy_id: Optional[int] = Field(None, ge=1, description="ID strategii kupna (dla transakcji automatycznych BUY)")
    sell_strategy_id: Optional[int] = Field(None, ge=1, description="ID strategii sprzedaży (dla transakcji automatycznych SELL)")
    
    # Podejście 2: Bez strategii (dla ręcznych transakcji)
    asset_amount: Optional[Decimal] = Field(None, gt=0, description="Ilość assetu (dla transakcji ręcznych)")
    quote_amount: Optional[Decimal] = Field(None, gt=0, description="Ilość quote (dla transakcji ręcznych)")
    
    general_interpretation_id: Optional[int] = Field(None, ge=1, description="ID interpretacji generalnej (opcjonalne)")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "description": "Transakcja z strategią (automatyczna)",
                    "value": {
                        "exchange_id": 1,
                        "asset_id": 1,
                        "exchange_account_state_id": 1,
                        "type": "BUY",
                        "buy_strategy_id": 1,
                        "general_interpretation_id": 1
                    }
                },
                {
                    "description": "Transakcja bez strategii (ręczna)",
                    "value": {
                        "exchange_id": 1,
                        "asset_id": 1,
                        "exchange_account_state_id": 1,
                        "type": "BUY",
                        "quote_amount": 100.0,
                        "asset_amount": 0.005
                    }
                }
            ]
        }


class TransactionUpdate(BaseModel):
    """Model do aktualizacji transakcji."""
    exchange_id: Optional[int] = Field(None, ge=1, description="ID giełdy")
    asset_id: Optional[int] = Field(None, ge=1, description="ID assetu")
    exchange_account_state_id: Optional[int] = Field(None, ge=1, description="ID stanu konta")
    general_interpretation_id: Optional[int] = Field(None, ge=1, description="ID interpretacji generalnej")
    buy_strategy_id: Optional[int] = Field(None, ge=1, description="ID strategii kupna")
    sell_strategy_id: Optional[int] = Field(None, ge=1, description="ID strategii sprzedaży")
    type: Optional[str] = Field(None, pattern="^(BUY|SELL)$", description="Typ transakcji")
    quote_amount: Optional[Decimal] = Field(None, gt=0, description="Kwota quote")
    asset_amount: Optional[Decimal] = Field(None, gt=0, description="Kwota assetu")


class PortfolioSummaryResponse(BaseModel):
    """Odpowiedź z podsumowaniem portfela dla assetu."""
    asset_id: int
    asset: str
    quote: str
    total_bought: Decimal
    total_sold: Decimal
    net_position: Decimal
    avg_buy_price: Optional[Decimal] = None
    avg_sell_price: Optional[Decimal] = None


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class TransactionListResponse(BaseModel):
    """Lista transakcji z informacją o paginacji."""
    transactions: List[TransactionResponse]
    pagination: PaginationInfo


class TransactionStatsResponse(BaseModel):
    """Statystyki transakcji."""
    total_transactions: int
    buy_transactions: int
    sell_transactions: int
    pending_interpretation: int
    total_volume_quote: Decimal
    total_volume_asset: Decimal
    unique_assets: int
    unique_exchanges: int


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class TransactionCreateResponse(BaseModel):
    """Odpowiedź dla utworzenia transakcji."""
    success: bool
    message: str
    transaction_id: Optional[int] = None
    exchange_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TransactionBatchCreate(BaseModel):
    """Model do tworzenia wielu transakcji jednocześnie."""
    transactions: List[TransactionCreate] = Field(..., min_items=1, max_items=50, description="Lista transakcji do wykonania")


class BatchTransactionResult(BaseModel):
    """Wynik pojedynczej transakcji w batch."""
    index: int
    success: bool
    transaction_id: Optional[int] = None
    message: str
    error: Optional[str] = None


class BatchCreateResponse(BaseModel):
    """Odpowiedź dla batch create."""
    total_requested: int
    successful: int
    failed: int
    results: List[BatchTransactionResult]


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
# HELPER FUNCTIONS
# ===================

def _calculate_transaction_amount(strategy: Dict[str, Any], account_state: Dict[str, Any]) -> float:
    """
    Oblicza kwotę przeznaczoną na transakcję na podstawie strategii i stanu konta.
    
    Args:
        strategy: Strategia kupna/sprzedaży
        account_state: Stan konta
        
    Returns:
        Kwota do wykorzystania w transakcji
    """
    try:
        movement_amount = strategy['movement_amount']
        account_amount = account_state['amount']
        is_percent = strategy['is_percent']
        
        if is_percent:
            # Oblicz kwotę na podstawie procentu
            calculated_amount = (account_amount * movement_amount) / 100
        else:
            # Użyj kwoty bezwzględnej
            calculated_amount = movement_amount
        
        # Jeśli obliczona kwota przekracza stan konta, użyj całego stanu konta
        if calculated_amount > account_amount:
            logger.info(f"Obliczona kwota ({calculated_amount}) przekracza stan konta ({account_amount}). Używam całego stanu konta.")
            return float(account_amount)
        
        return float(calculated_amount)
        
    except Exception as e:
        logger.error(f"Błąd podczas obliczania kwoty transakcji: {e}")
        return 0.0


def _get_exchange_api(exchange_name: str):
    """
    Pobiera API giełdy na podstawie nazwy.
    
    Args:
        exchange_name: Nazwa giełdy
        
    Returns:
        Obiekt API giełdy lub None jeśli nie znaleziono
    """
    try:
        api_facade = ApiFacade()
        exchanges = api_facade.get_fabric().get_exchanges_apis()
        
        for exchange in exchanges:
            exchange_api_name = getattr(exchange, 'EXCHANGE_NAME', exchange.__class__.__name__)
            if exchange_api_name == exchange_name:
                return exchange
        
        logger.warning(f"Nie znaleziono API dla giełdy: {exchange_name}")
        return None
        
    except Exception as e:
        logger.error(f"Błąd podczas pobierania API giełdy {exchange_name}: {e}")
        return None


async def _execute_transaction_on_exchange(exchange, transaction_side: str, strategy: Optional[Dict[str, Any]], 
                                         asset: Dict[str, Any], transaction_amount: float, 
                                         account_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Wykonuje transakcję na giełdzie.
    
    Args:
        exchange: Obiekt giełdy
        transaction_side: BUY lub SELL
        strategy: Strategia transakcyjna (None dla transakcji ręcznych)
        asset: Informacje o assecie
        transaction_amount: Kwota do wykorzystania
        account_state: Stan konta dla obliczania procentów
        
    Returns:
        Wynik transakcji lub None w przypadku błędu
    """
    try:
        asset_name = asset['asset']
        quote_name = asset['quote']
        
        # Jeśli nie ma strategii, użyj domyślnie MARKET
        strategy_type = strategy['type'] if strategy else 'MARKET'
        
        logger.info(f"Wykonuję transakcję {transaction_side} {strategy_type} dla {asset_name}/{quote_name} z kwotą {transaction_amount}")
        
        if strategy_type == 'MARKET':
            # Użyj market order
            if transaction_side == 'BUY':
                # Dla kupna market - używamy currency_size (quote)
                result = exchange.market_buy(
                    coin=asset_name,
                    currency_size=transaction_amount,
                    used_currency=quote_name
                )
            else:
                # Dla sprzedaży market - używamy coin_size (asset)
                result = exchange.market_sell(
                    coin=asset_name,
                    coin_size=transaction_amount,
                    used_currency=quote_name
                )
        else:
            # Użyj limit order (domyślne metody buy/sell)
            if transaction_side == 'BUY':
                result = exchange.buy(
                    coin=asset_name,
                    currency_size_to_buy=transaction_amount,
                    used_currency=quote_name
                )
            else:
                # Dla sprzedaży limit - oblicz wartość procentową na podstawie strategii
                if strategy and strategy['is_percent']:
                    # Jeśli strategia ma is_percent=true, użyj tej wartości procentowej
                    coin_percent_to_sell = strategy['movement_amount']
                else:
                    # Jeśli strategia ma wartość bezwzględną, oblicz procent z stanu konta
                    account_amount = account_state['amount']
                    if account_amount > 0:
                        coin_percent_to_sell = (transaction_amount / account_amount) * 100
                    else:
                        coin_percent_to_sell = 0.0
                
                logger.info(f"Sprzedaż LIMIT: używam {coin_percent_to_sell}% z konta")
                
                result = exchange.sell(
                    coin=asset_name,
                    coin_percent_size_to_sell=coin_percent_to_sell,
                    used_currency=quote_name
                )
        
        logger.info(f"Transakcja wykonana pomyślnie: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Błąd podczas wykonywania transakcji: {e}")
        return None


# ===================
# ENDPOINTY GŁÓWNE
# ===================

@router.get("", response_model=Dict[str, Any])
async def transactions_info():
    """Informacje o dostępnych endpointach transakcji giełdowych."""
    return {
        "message": "Exchange Transactions REST API",
        "version": "1.0.0",
        "description": "API for managing exchange transactions (BUY/SELL operations)",
        "transaction_modes": {
            "strategy_based": {
                "description": "Transakcje automatyczne oparte na strategiach buy/sell",
                "usage": "Podaj buy_strategy_id (dla BUY) lub sell_strategy_id (dla SELL)",
                "amounts": "Kwoty obliczane automatycznie na podstawie strategii i stanu portfela",
                "use_case": "Cronjob - transakcje automatyczne"
            },
            "manual": {
                "description": "Transakcje ręczne z określonymi kwotami",
                "usage": "Podaj asset_amount i quote_amount bezpośrednio",
                "amounts": "Kwoty podawane wprost przez użytkownika",
                "use_case": "Transakcje manualne - bez przypisywania strategii"
            }
        },
        "available_endpoints": {
            "crud": {
                "list": "GET /transactions/list - Lista wszystkich transakcji",
                "get": "GET /transactions/{id} - Szczegóły transakcji",
                "create": "POST /transactions - Wykonanie transakcji (z strategią lub manual z kwotami)",
                "create_batch": "POST /transactions/batch - Wykonanie wielu transakcji (batch)"
            },
            "filtering": {
                "by_asset": "GET /transactions/asset/{asset_id} - Transakcje dla assetu",
                "by_exchange": "GET /transactions/exchange/{exchange_id} - Transakcje dla giełdy",
                "by_type": "GET /transactions/type/{type} - Transakcje BUY lub SELL",
                "by_interpretation": "GET /transactions/interpretation/{interpretation_id} - Transakcje z interpretacją",
                "by_wallet": "GET /transactions/wallet/{wallet_id} - Transakcje dla portfela",
                "by_buy_strategy": "GET /transactions/strategy/buy/{strategy_id} - Transakcje ze strategią kupna",
                "by_sell_strategy": "GET /transactions/strategy/sell/{strategy_id} - Transakcje ze strategią sprzedaży",
                "by_date_range": "GET /transactions/date/range - Transakcje z zakresu czasowego",
                "by_date_range_asset": "GET /transactions/date/range/asset/{asset_id} - Transakcje z zakresu czasowego dla assetu",
                "without_interpretation": "GET /transactions/without-interpretation - Transakcje bez interpretacji"
            },
            "portfolio": {
                "summary_by_asset": "GET /transactions/portfolio/asset/{asset_id} - Podsumowanie portfela dla assetu",
                "summary_by_exchange": "GET /transactions/portfolio/exchange/{exchange_id} - Podsumowanie dla giełdy"
            },
            "stats": {
                "count": "GET /transactions/count - Liczba wszystkich transakcji",
                "count_by_asset": "GET /transactions/count/asset/{asset_id} - Liczba transakcji dla assetu",
                "count_by_exchange": "GET /transactions/count/exchange/{exchange_id} - Liczba transakcji dla giełdy",
                "stats": "GET /transactions/stats - Statystyki transakcji"
            }
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{transaction_id}

@router.get("/list", response_model=TransactionListResponse)
async def list_transactions(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich transakcji z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing transactions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list transactions: {str(e)}")


# ===================
# FILTERING - PRZED /{transaction_id}
# ===================

@router.get("/asset/{asset_id}", response_model=TransactionListResponse)
async def get_transactions_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji dla assetu
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_asset_id(asset_id=asset_id, limit=limit + 1, offset=offset)
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/exchange/{exchange_id}", response_model=TransactionListResponse)
async def get_transactions_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje dla konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji dla giełdy
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_exchange_id(exchange_id=exchange_id, limit=limit + 1, offset=offset)
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/type/{transaction_type}", response_model=TransactionListResponse)
async def get_transactions_by_type(
    transaction_type: str = Path(..., pattern="^(BUY|SELL)$", description="Typ transakcji"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje konkretnego typu (BUY lub SELL).
    
    Args:
        transaction_type: Typ transakcji (BUY lub SELL)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_type(transaction_type=transaction_type, limit=limit + 1, offset=offset)
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions by type {transaction_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/interpretation/{interpretation_id}", response_model=TransactionListResponse)
async def get_transactions_by_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje powiązane z konkretną interpretacją.
    
    Args:
        interpretation_id: ID interpretacji generalnej
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji z interpretacją
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_interpretation_id(
            interpretation_id=interpretation_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions for interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/wallet/{wallet_id}", response_model=TransactionListResponse)
async def get_transactions_by_wallet(
    wallet_id: int = Path(..., ge=1, description="ID portfela (exchange account state)"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje dla konkretnego portfela.
    
    Args:
        wallet_id: ID portfela (exchange_account_state)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji dla portfela
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_exchange_account_state_id(
            exchange_account_state_id=wallet_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions for wallet {wallet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/strategy/buy/{strategy_id}", response_model=TransactionListResponse)
async def get_transactions_by_buy_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii kupna"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje wykorzystujące określoną strategię kupna.
    
    Args:
        strategy_id: ID strategii kupna
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji ze strategią
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_buy_strategy_id(
            buy_strategy_id=strategy_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions for buy strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/strategy/sell/{strategy_id}", response_model=TransactionListResponse)
async def get_transactions_by_sell_strategy(
    strategy_id: int = Path(..., ge=1, description="ID strategii sprzedaży"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje wykorzystujące określoną strategię sprzedaży.
    
    Args:
        strategy_id: ID strategii sprzedaży
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji ze strategią
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_sell_strategy_id(
            sell_strategy_id=strategy_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions for sell strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/date/range", response_model=TransactionListResponse)
async def get_transactions_by_date_range(
    start_timestamp: int = Query(..., description="Timestamp początkowy (ms)"),
    end_timestamp: int = Query(..., description="Timestamp końcowy (ms)"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje z określonego zakresu czasowego.
    
    Args:
        start_timestamp: Timestamp początkowy w milisekundach
        end_timestamp: Timestamp końcowy w milisekundach
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji z zakresu
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_date_range(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions by date range: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/date/range/asset/{asset_id}", response_model=TransactionListResponse)
async def get_transactions_by_date_range_and_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    start_timestamp: int = Query(..., description="Timestamp początkowy (ms)"),
    end_timestamp: int = Query(..., description="Timestamp końcowy (ms)"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje z zakresu czasowego dla konkretnego assetu.
    
    Dedykowany endpoint dla wygodnego filtrowania po zakresie czasowym i asset.
    
    Args:
        asset_id: ID assetu
        start_timestamp: Timestamp początkowy w milisekundach
        end_timestamp: Timestamp końcowy w milisekundach
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji z zakresu dla assetu
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_timestamp_range_and_asset_id(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=t.get('interpretation_title'),
                interpretation_content=t.get('interpretation_content')
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions by date range and asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


@router.get("/without-interpretation", response_model=TransactionListResponse)
async def get_transactions_without_interpretation(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera transakcje które nie mają przypisanej interpretacji.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TransactionListResponse: Lista transakcji bez interpretacji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_transactions_without_interpretation(limit=limit + 1, offset=offset)
        
        has_more = len(transactions) > limit
        page_transactions = transactions[:limit]
        
        transaction_responses = [
            TransactionResponse(
                id=t['id'],
                exchange_id=t['exchange_id'],
                asset_id=t['asset_id'],
                exchange_account_state_id=t['exchange_account_state_id'],
                general_interpretation_id=t.get('general_interpretation_id'),
                buy_strategy_id=t.get('buy_strategy_id'),
                sell_strategy_id=t.get('sell_strategy_id'),
                type=t['type'],
                quote_amount=Decimal(str(t['quote_amount'])),
                asset_amount=Decimal(str(t['asset_amount'])),
                created_at=t['created_at'],
                exchange_name=t.get('exchange_name'),
                exchange_display_name=t.get('exchange_display_name'),
                asset=t.get('asset'),
                quote=t.get('quote'),
                currency=t.get('currency'),
                account_amount=Decimal(str(t['account_amount'])) if t.get('account_amount') is not None else None,
                account_type=t.get('account_type'),
                buy_strategy_type=t.get('buy_strategy_type'),
                buy_movement_amount=Decimal(str(t['buy_movement_amount'])) if t.get('buy_movement_amount') is not None else None,
                buy_is_percent=t.get('buy_is_percent'),
                sell_strategy_type=t.get('sell_strategy_type'),
                sell_movement_amount=Decimal(str(t['sell_movement_amount'])) if t.get('sell_movement_amount') is not None else None,
                sell_is_percent=t.get('sell_is_percent'),
                interpretation_title=None,
                interpretation_content=None
            )
            for t in page_transactions
        ]
        
        return TransactionListResponse(
            transactions=transaction_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting transactions without interpretation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transactions: {str(e)}")


# ===================
# PORTFOLIO - PRZED /{transaction_id}
# ===================

@router.get("/portfolio/asset/{asset_id}", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera podsumowanie portfela dla assetu (łączne kupno/sprzedaż, pozycja netto).
    
    Args:
        asset_id: ID assetu
        
    Returns:
        PortfolioSummaryResponse: Podsumowanie portfela
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        summary = await transactions_table.get_portfolio_summary_by_asset(asset_id)
        
        if not summary:
            raise HTTPException(
                status_code=404,
                detail=f"No portfolio data found for asset {asset_id}"
            )
        
        return PortfolioSummaryResponse(
            asset_id=summary['asset_id'],
            asset=summary['asset'],
            quote=summary['quote'],
            total_bought=Decimal(str(summary['total_bought'])),
            total_sold=Decimal(str(summary['total_sold'])),
            net_position=Decimal(str(summary['net_position'])),
            avg_buy_price=Decimal(str(summary['avg_buy_price'])) if summary.get('avg_buy_price') is not None else None,
            avg_sell_price=Decimal(str(summary['avg_sell_price'])) if summary.get('avg_sell_price') is not None else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio summary for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")


@router.get("/portfolio/exchange/{exchange_id}", response_model=List[PortfolioSummaryResponse])
async def get_portfolio_summary_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Pobiera podsumowanie portfela dla giełdy (wszystkie assety z pozycją netto).
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        List[PortfolioSummaryResponse]: Lista podsumowań dla każdego assetu
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        summary_list = await transactions_table.get_portfolio_summary_by_exchange(exchange_id)
        
        summary_responses = [
            PortfolioSummaryResponse(
                asset_id=s['asset_id'],
                asset=s['asset'],
                quote=s['quote'],
                total_bought=Decimal(str(s['total_bought'])),
                total_sold=Decimal(str(s['total_sold'])),
                net_position=Decimal(str(s['net_position'])),
                avg_buy_price=Decimal(str(s['avg_buy_price'])) if s.get('avg_buy_price') is not None else None,
                avg_sell_price=Decimal(str(s['avg_sell_price'])) if s.get('avg_sell_price') is not None else None
            )
            for s in summary_list
        ]
        
        return summary_responses
        
    except Exception as e:
        logger.error(f"Error getting portfolio summary for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{transaction_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_transactions():
    """
    Zlicza wszystkie transakcje.
    
    Returns:
        Dict z liczbą transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        all_transactions = await transactions_table.get_all(limit=100000)
        count = len(all_transactions)
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting transactions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count transactions: {str(e)}")


@router.get("/count/asset/{asset_id}", response_model=Dict[str, int])
async def count_transactions_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Zlicza transakcje dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        Dict z liczbą transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_asset_id(asset_id, limit=100000)
        count = len(transactions)
        
        return {"count": count, "asset_id": asset_id}
        
    except Exception as e:
        logger.error(f"Error counting transactions for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count transactions: {str(e)}")


@router.get("/count/exchange/{exchange_id}", response_model=Dict[str, int])
async def count_transactions_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Zlicza transakcje dla konkretnej giełdy.
    
    Args:
        exchange_id: ID giełdy
        
    Returns:
        Dict z liczbą transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transactions = await transactions_table.get_by_exchange_id(exchange_id, limit=100000)
        count = len(transactions)
        
        return {"count": count, "exchange_id": exchange_id}
        
    except Exception as e:
        logger.error(f"Error counting transactions for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count transactions: {str(e)}")


@router.get("/stats", response_model=TransactionStatsResponse)
async def get_transaction_stats():
    """
    Pobiera statystyki transakcji.
    
    Returns:
        TransactionStatsResponse: Statystyki transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        all_transactions = await transactions_table.get_all(limit=100000)
        buy_transactions = await transactions_table.get_by_type("BUY", limit=100000)
        sell_transactions = await transactions_table.get_by_type("SELL", limit=100000)
        pending_transactions = await transactions_table.get_transactions_without_interpretation(limit=100000)
        
        # Oblicz volume
        total_quote_volume = sum(float(t['quote_amount']) for t in all_transactions)
        total_asset_volume = sum(float(t['asset_amount']) for t in all_transactions)
        
        # Zlicz unikalne assety i giełdy
        unique_assets = set(t['asset_id'] for t in all_transactions)
        unique_exchanges = set(t['exchange_id'] for t in all_transactions)
        
        return TransactionStatsResponse(
            total_transactions=len(all_transactions),
            buy_transactions=len(buy_transactions),
            sell_transactions=len(sell_transactions),
            pending_interpretation=len(pending_transactions),
            total_volume_quote=Decimal(str(total_quote_volume)),
            total_volume_asset=Decimal(str(total_asset_volume)),
            unique_assets=len(unique_assets),
            unique_exchanges=len(unique_exchanges)
        )
        
    except Exception as e:
        logger.error(f"Error getting transaction stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ PO SPECYFICZNYCH
# ===================

@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int = Path(..., ge=1, description="ID transakcji")
):
    """
    Pobiera szczegóły konkretnej transakcji.
    
    Args:
        transaction_id: ID transakcji
        
    Returns:
        TransactionResponse: Szczegóły transakcji
    """
    try:
        db = await get_db()
        transactions_table = db.get_factory().get_exchange_transactions_table()
        
        transaction = await transactions_table.get_by_id(transaction_id)
        
        if not transaction:
            raise HTTPException(
                status_code=404,
                detail=f"Transaction with ID {transaction_id} not found"
            )
        
        return TransactionResponse(
            id=transaction['id'],
            exchange_id=transaction['exchange_id'],
            asset_id=transaction['asset_id'],
            exchange_account_state_id=transaction['exchange_account_state_id'],
            general_interpretation_id=transaction.get('general_interpretation_id'),
            buy_strategy_id=transaction.get('buy_strategy_id'),
            sell_strategy_id=transaction.get('sell_strategy_id'),
            type=transaction['type'],
            quote_amount=Decimal(str(transaction['quote_amount'])),
            asset_amount=Decimal(str(transaction['asset_amount'])),
            created_at=transaction['created_at'],
            exchange_name=transaction.get('exchange_name'),
            exchange_display_name=transaction.get('exchange_display_name'),
            asset=transaction.get('asset'),
            quote=transaction.get('quote'),
            currency=transaction.get('currency'),
            account_amount=Decimal(str(transaction['account_amount'])) if transaction.get('account_amount') is not None else None,
            account_type=transaction.get('account_type'),
            buy_strategy_type=transaction.get('buy_strategy_type'),
            buy_movement_amount=Decimal(str(transaction['buy_movement_amount'])) if transaction.get('buy_movement_amount') is not None else None,
            buy_is_percent=transaction.get('buy_is_percent'),
            sell_strategy_type=transaction.get('sell_strategy_type'),
            sell_movement_amount=Decimal(str(transaction['sell_movement_amount'])) if transaction.get('sell_movement_amount') is not None else None,
            sell_is_percent=transaction.get('sell_is_percent'),
            interpretation_title=transaction.get('interpretation_title'),
            interpretation_content=transaction.get('interpretation_content')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transaction {transaction_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get transaction: {str(e)}")


@router.post("", response_model=TransactionCreateResponse, status_code=201)
async def create_transaction(
    transaction_data: TransactionCreate = Body(..., description="Dane transakcji do wykonania na giełdzie")
):
    """
    Wykonuje transakcję na giełdzie i zapisuje ją w bazie danych.
    
    Dwa tryby działania:
    
    1. **Z strategią (automatyczna)**: Podaj buy_strategy_id (dla BUY) lub sell_strategy_id (dla SELL).
       - Kwoty są obliczane automatycznie na podstawie strategii i stanu portfela
       - Używane przez cronjob dla transakcji automatycznych
       
    2. **Bez strategii (ręczna)**: Podaj asset_amount i quote_amount bezpośrednio.
       - Kwoty są podane wprost przez użytkownika
       - Używane dla transakcji manualnych
       - Strategie buy/sell nie są przypisywane w bazie
    
    UWAGA: Ten endpoint faktycznie wykonuje transakcję na giełdzie!
    Używaj ostrożnie w środowisku produkcyjnym.
    
    Args:
        transaction_data: Dane transakcji do wykonania
        
    Returns:
        TransactionCreateResponse: Wynik wykonania transakcji
    """
    try:
        db = await get_db()
        
        # Pobierz potrzebne tabele
        transactions_table = db.get_factory().get_exchange_transactions_table()
        exchanges_table = db.get_factory().get_exchanges_table()
        assets_table = db.get_factory().get_assets_table()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # KROK 1: Walidacja - sprawdź czy istnieją wszystkie wymagane encje
        exchange = await exchanges_table.get_by_id(transaction_data.exchange_id)
        if not exchange:
            return TransactionCreateResponse(
                success=False,
                message=f"Exchange with ID {transaction_data.exchange_id} not found",
                error="EXCHANGE_NOT_FOUND"
            )
        
        asset = await assets_table.get_by_id(transaction_data.asset_id)
        if not asset:
            return TransactionCreateResponse(
                success=False,
                message=f"Asset with ID {transaction_data.asset_id} not found",
                error="ASSET_NOT_FOUND"
            )
        
        wallet = await wallets_table.get_by_id(transaction_data.exchange_account_state_id)
        if not wallet:
            return TransactionCreateResponse(
                success=False,
                message=f"Wallet with ID {transaction_data.exchange_account_state_id} not found",
                error="WALLET_NOT_FOUND"
            )
        
        # Sprawdź czy wallet należy do giełdy
        if wallet['exchange_id'] != transaction_data.exchange_id:
            return TransactionCreateResponse(
                success=False,
                message=f"Wallet {transaction_data.exchange_account_state_id} does not belong to exchange {transaction_data.exchange_id}",
                error="WALLET_EXCHANGE_MISMATCH"
            )
        
        # Sprawdź czy wallet jest włączony
        if not wallet.get('is_enabled', False):
            return TransactionCreateResponse(
                success=False,
                message=f"Wallet {transaction_data.exchange_account_state_id} is disabled",
                error="WALLET_DISABLED"
            )
        
        # Sprawdź czy wallet ma wystarczające środki
        if wallet['amount'] <= 0:
            return TransactionCreateResponse(
                success=False,
                message=f"Wallet {transaction_data.exchange_account_state_id} has insufficient funds",
                error="INSUFFICIENT_FUNDS"
            )
        
        # KROK 2: Określ tryb transakcji (z strategią czy bez)
        # Sprawdź czy mamy strategię czy kwoty ręczne
        has_strategy = (transaction_data.type == "BUY" and transaction_data.buy_strategy_id) or \
                       (transaction_data.type == "SELL" and transaction_data.sell_strategy_id)
        has_manual_amounts = transaction_data.asset_amount is not None and transaction_data.quote_amount is not None
        
        # Walidacja: musi być albo strategia albo kwoty ręczne (nie oba, nie żadne)
        if not has_strategy and not has_manual_amounts:
            return TransactionCreateResponse(
                success=False,
                message=f"Either strategy_id or both asset_amount and quote_amount must be provided for {transaction_data.type} transaction",
                error="MISSING_STRATEGY_OR_AMOUNTS"
            )
        
        if has_strategy and has_manual_amounts:
            return TransactionCreateResponse(
                success=False,
                message="Cannot provide both strategy_id and manual amounts. Choose one approach.",
                error="CONFLICTING_PARAMETERS"
            )
        
        # KROK 3a: Pobierz strategię (jeśli używamy trybu ze strategią)
        strategy = None
        transaction_amount = None
        
        if has_strategy:
            if transaction_data.type == "BUY":
                strategy = await buy_strategies_table.get_by_id(transaction_data.buy_strategy_id)
                if not strategy:
                    return TransactionCreateResponse(
                        success=False,
                        message=f"Buy strategy with ID {transaction_data.buy_strategy_id} not found",
                        error="BUY_STRATEGY_NOT_FOUND"
                    )
            else:  # SELL
                strategy = await sell_strategies_table.get_by_id(transaction_data.sell_strategy_id)
                if not strategy:
                    return TransactionCreateResponse(
                        success=False,
                        message=f"Sell strategy with ID {transaction_data.sell_strategy_id} not found",
                        error="SELL_STRATEGY_NOT_FOUND"
                    )
            
            # Oblicz kwotę transakcji na podstawie strategii
            transaction_amount = _calculate_transaction_amount(strategy, wallet)
            if transaction_amount <= 0:
                return TransactionCreateResponse(
                    success=False,
                    message="Calculated transaction amount is zero or negative",
                    error="INVALID_TRANSACTION_AMOUNT"
                )
            
            logger.info(f"Strategy-based transaction: calculated amount = {transaction_amount} for {transaction_data.type}")
        
        # KROK 3b: Użyj kwot ręcznych (jeśli używamy trybu manualnego)
        else:  # has_manual_amounts
            # Dla transakcji BUY używamy quote_amount, dla SELL używamy asset_amount
            if transaction_data.type == "BUY":
                transaction_amount = float(transaction_data.quote_amount)
            else:  # SELL
                transaction_amount = float(transaction_data.asset_amount)
            
            logger.info(f"Manual transaction: using amount = {transaction_amount} for {transaction_data.type}")
        
        # KROK 4: Pobierz API giełdy
        exchange_name = exchange.get('name')
        exchange_api = _get_exchange_api(exchange_name)
        if not exchange_api:
            return TransactionCreateResponse(
                success=False,
                message=f"Exchange API not found for {exchange_name}",
                error="EXCHANGE_API_NOT_FOUND"
            )
        
        # KROK 5: Wykonaj transakcję na giełdzie
        asset_dict = {'asset': asset['asset'], 'quote': asset['quote']}
        exchange_result = await _execute_transaction_on_exchange(
            exchange_api, 
            transaction_data.type, 
            strategy,  # None dla transakcji manualnych
            asset_dict, 
            transaction_amount, 
            wallet
        )
        
        if not exchange_result:
            return TransactionCreateResponse(
                success=False,
                message="Failed to execute transaction on exchange",
                error="EXCHANGE_EXECUTION_FAILED"
            )
        
        # KROK 6: Zapisz transakcję w bazie danych
        # Wyciągnij kwoty z wyniku transakcji lub użyj ręcznych kwot
        if has_manual_amounts:
            # Dla transakcji manualnych używamy podanych kwot
            quote_amount = float(transaction_data.quote_amount)
            asset_amount = float(transaction_data.asset_amount)
            logger.info(f"Using manual amounts: quote={quote_amount}, asset={asset_amount}")
        else:
            # Dla transakcji ze strategią wyciągamy z wyniku giełdy
            if transaction_data.type == 'BUY':
                quote_amount = transaction_amount
                asset_amount = exchange_result.get('bought_asset_size', 0.0)
            else:  # SELL
                asset_amount = transaction_amount
                quote_amount = exchange_result.get('sold_asset_price', 0.0)
            logger.info(f"Using exchange result amounts: quote={quote_amount}, asset={asset_amount}")
        
        transaction_id = await transactions_table.create(
            exchange_id=transaction_data.exchange_id,
            asset_id=transaction_data.asset_id,
            exchange_account_state_id=transaction_data.exchange_account_state_id,
            type=transaction_data.type,
            quote_amount=quote_amount,
            asset_amount=asset_amount,
            general_interpretation_id=transaction_data.general_interpretation_id,
            buy_strategy_id=transaction_data.buy_strategy_id if has_strategy and transaction_data.type == 'BUY' else None,
            sell_strategy_id=transaction_data.sell_strategy_id if has_strategy and transaction_data.type == 'SELL' else None
        )
        
        if not transaction_id:
            logger.error("Failed to save transaction to database after successful exchange execution")
            return TransactionCreateResponse(
                success=False,
                message="Transaction executed on exchange but failed to save to database",
                error="DATABASE_SAVE_FAILED",
                exchange_result=exchange_result
            )
        
        transaction_mode = "strategy-based" if has_strategy else "manual"
        logger.info(f"Successfully executed and saved {transaction_mode} transaction {transaction_id}")
        
        return TransactionCreateResponse(
            success=True,
            message=f"Transaction ({transaction_mode}) executed successfully on {exchange_name} and saved to database",
            transaction_id=transaction_id,
            exchange_result=exchange_result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing transaction: {e}")
        return TransactionCreateResponse(
            success=False,
            message=f"Error executing transaction: {str(e)}",
            error="UNEXPECTED_ERROR"
        )


@router.post("/batch", response_model=BatchCreateResponse, status_code=201)
async def create_transactions_batch(
    batch_data: TransactionBatchCreate = Body(..., description="Lista transakcji do wykonania na giełdach")
):
    """
    Wykonuje wiele transakcji na giełdach i zapisuje je w bazie danych.
    
    Każda transakcja jest przetwarzana niezależnie w jednym z dwóch trybów:
    
    1. **Z strategią (automatyczna)**: Podaj strategy_id - kwoty obliczane automatycznie
    2. **Bez strategii (ręczna)**: Podaj asset_amount i quote_amount bezpośrednio
    
    Dla każdej transakcji:
    - Walidacja powiązań (giełda, asset, portfel, opcjonalnie strategia)
    - Obliczenie kwoty na podstawie strategii LUB użycie kwot ręcznych
    - Wykonanie na giełdzie przez API
    - Zapis wyniku w bazie
    
    Jeśli jedna transakcja się nie powiedzie, pozostałe są kontynuowane.
    
    UWAGA: Ten endpoint faktycznie wykonuje transakcje na giełdach!
    Używaj ostrożnie w środowisku produkcyjnym.
    
    Args:
        batch_data: Lista transakcji do wykonania
        
    Returns:
        BatchCreateResponse: Wyniki wszystkich transakcji
    """
    results = []
    successful = 0
    failed = 0
    
    try:
        db = await get_db()
        
        # Pobierz potrzebne tabele (raz dla całego batcha)
        transactions_table = db.get_factory().get_exchange_transactions_table()
        exchanges_table = db.get_factory().get_exchanges_table()
        assets_table = db.get_factory().get_assets_table()
        wallets_table = db.get_factory().get_exchange_account_state_table()
        buy_strategies_table = db.get_factory().get_exchange_account_state_buy_strategies_table()
        sell_strategies_table = db.get_factory().get_exchange_account_state_sell_strategies_table()
        
        # Przetwarzaj każdą transakcję
        for idx, transaction_data in enumerate(batch_data.transactions):
            try:
                logger.info(f"Processing batch transaction {idx + 1}/{len(batch_data.transactions)}")
                
                # KROK 1: Walidacja
                exchange = await exchanges_table.get_by_id(transaction_data.exchange_id)
                if not exchange:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Exchange with ID {transaction_data.exchange_id} not found",
                        error="EXCHANGE_NOT_FOUND"
                    ))
                    failed += 1
                    continue
                
                asset = await assets_table.get_by_id(transaction_data.asset_id)
                if not asset:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Asset with ID {transaction_data.asset_id} not found",
                        error="ASSET_NOT_FOUND"
                    ))
                    failed += 1
                    continue
                
                wallet = await wallets_table.get_by_id(transaction_data.exchange_account_state_id)
                if not wallet:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Wallet with ID {transaction_data.exchange_account_state_id} not found",
                        error="WALLET_NOT_FOUND"
                    ))
                    failed += 1
                    continue
                
                # Walidacja wallet-exchange
                if wallet['exchange_id'] != transaction_data.exchange_id:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Wallet {transaction_data.exchange_account_state_id} does not belong to exchange {transaction_data.exchange_id}",
                        error="WALLET_EXCHANGE_MISMATCH"
                    ))
                    failed += 1
                    continue
                
                # Sprawdź czy wallet jest włączony
                if not wallet.get('is_enabled', False):
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Wallet {transaction_data.exchange_account_state_id} is disabled",
                        error="WALLET_DISABLED"
                    ))
                    failed += 1
                    continue
                
                # Sprawdź środki
                if wallet['amount'] <= 0:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Wallet {transaction_data.exchange_account_state_id} has insufficient funds",
                        error="INSUFFICIENT_FUNDS"
                    ))
                    failed += 1
                    continue
                
                # KROK 2: Określ tryb transakcji (z strategią czy bez)
                has_strategy = (transaction_data.type == "BUY" and transaction_data.buy_strategy_id) or \
                               (transaction_data.type == "SELL" and transaction_data.sell_strategy_id)
                has_manual_amounts = transaction_data.asset_amount is not None and transaction_data.quote_amount is not None
                
                # Walidacja: musi być albo strategia albo kwoty ręczne
                if not has_strategy and not has_manual_amounts:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Either strategy_id or both asset_amount and quote_amount must be provided",
                        error="MISSING_STRATEGY_OR_AMOUNTS"
                    ))
                    failed += 1
                    continue
                
                if has_strategy and has_manual_amounts:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message="Cannot provide both strategy_id and manual amounts",
                        error="CONFLICTING_PARAMETERS"
                    ))
                    failed += 1
                    continue
                
                # KROK 3a: Pobierz strategię (jeśli używamy trybu ze strategią)
                strategy = None
                transaction_amount = None
                
                if has_strategy:
                    if transaction_data.type == "BUY":
                        strategy = await buy_strategies_table.get_by_id(transaction_data.buy_strategy_id)
                        if not strategy:
                            results.append(BatchTransactionResult(
                                index=idx,
                                success=False,
                                message=f"Buy strategy with ID {transaction_data.buy_strategy_id} not found",
                                error="BUY_STRATEGY_NOT_FOUND"
                            ))
                            failed += 1
                            continue
                    else:  # SELL
                        strategy = await sell_strategies_table.get_by_id(transaction_data.sell_strategy_id)
                        if not strategy:
                            results.append(BatchTransactionResult(
                                index=idx,
                                success=False,
                                message=f"Sell strategy with ID {transaction_data.sell_strategy_id} not found",
                                error="SELL_STRATEGY_NOT_FOUND"
                            ))
                            failed += 1
                            continue
                    
                    # Oblicz kwotę transakcji na podstawie strategii
                    transaction_amount = _calculate_transaction_amount(strategy, wallet)
                    if transaction_amount <= 0:
                        results.append(BatchTransactionResult(
                            index=idx,
                            success=False,
                            message="Calculated transaction amount is zero or negative",
                            error="INVALID_TRANSACTION_AMOUNT"
                        ))
                        failed += 1
                        continue
                
                # KROK 3b: Użyj kwot ręcznych (jeśli używamy trybu manualnego)
                else:  # has_manual_amounts
                    if transaction_data.type == "BUY":
                        transaction_amount = float(transaction_data.quote_amount)
                    else:  # SELL
                        transaction_amount = float(transaction_data.asset_amount)
                
                # KROK 4: Pobierz API giełdy
                exchange_name = exchange.get('name')
                exchange_api = _get_exchange_api(exchange_name)
                if not exchange_api:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message=f"Exchange API not found for {exchange_name}",
                        error="EXCHANGE_API_NOT_FOUND"
                    ))
                    failed += 1
                    continue
                
                # KROK 5: Wykonaj transakcję na giełdzie
                asset_dict = {'asset': asset['asset'], 'quote': asset['quote']}
                exchange_result = await _execute_transaction_on_exchange(
                    exchange_api,
                    transaction_data.type,
                    strategy,
                    asset_dict,
                    transaction_amount,
                    wallet
                )
                
                if not exchange_result:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message="Failed to execute transaction on exchange",
                        error="EXCHANGE_EXECUTION_FAILED"
                    ))
                    failed += 1
                    continue
                
                # KROK 6: Zapisz w bazie
                # Wyciągnij kwoty z wyniku transakcji lub użyj ręcznych kwot
                if has_manual_amounts:
                    # Dla transakcji manualnych używamy podanych kwot
                    quote_amount = float(transaction_data.quote_amount)
                    asset_amount = float(transaction_data.asset_amount)
                else:
                    # Dla transakcji ze strategią wyciągamy z wyniku giełdy
                    if transaction_data.type == 'BUY':
                        quote_amount = transaction_amount
                        asset_amount = exchange_result.get('bought_asset_size', 0.0)
                    else:  # SELL
                        asset_amount = transaction_amount
                        quote_amount = exchange_result.get('sold_asset_price', 0.0)
                
                transaction_id = await transactions_table.create(
                    exchange_id=transaction_data.exchange_id,
                    asset_id=transaction_data.asset_id,
                    exchange_account_state_id=transaction_data.exchange_account_state_id,
                    type=transaction_data.type,
                    quote_amount=quote_amount,
                    asset_amount=asset_amount,
                    general_interpretation_id=transaction_data.general_interpretation_id,
                    buy_strategy_id=transaction_data.buy_strategy_id if has_strategy and transaction_data.type == 'BUY' else None,
                    sell_strategy_id=transaction_data.sell_strategy_id if has_strategy and transaction_data.type == 'SELL' else None
                )
                
                if transaction_id:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=True,
                        transaction_id=transaction_id,
                        message=f"Transaction executed successfully on {exchange_name}"
                    ))
                    successful += 1
                    logger.info(f"Batch transaction {idx + 1} completed: ID {transaction_id}")
                else:
                    results.append(BatchTransactionResult(
                        index=idx,
                        success=False,
                        message="Transaction executed on exchange but failed to save to database",
                        error="DATABASE_SAVE_FAILED"
                    ))
                    failed += 1
                
            except Exception as e:
                logger.error(f"Error processing batch transaction {idx}: {e}")
                results.append(BatchTransactionResult(
                    index=idx,
                    success=False,
                    message=f"Unexpected error: {str(e)}",
                    error="UNEXPECTED_ERROR"
                ))
                failed += 1
        
        logger.info(f"Batch processing complete: {successful} successful, {failed} failed")
        
        return BatchCreateResponse(
            total_requested=len(batch_data.transactions),
            successful=successful,
            failed=failed,
            results=results
        )
        
    except Exception as e:
        logger.error(f"Critical error in batch processing: {e}")
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")
