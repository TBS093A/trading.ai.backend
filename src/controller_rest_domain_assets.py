"""
REST API Controller dla domeny assetów.

Ten kontroler implementuje endpointy REST dla:
- Zarządzania assetami (CRUD)
- Wyszukiwania i filtrowania assetów
- Relacji asset-exchange
- Zaawansowanych zapytań dla analiz
- Statystyk assetów

Bazuje na funkcjonalności z controller_telegram_domain_assets.py

Autor: AI Assistant
"""

import logging
from datetime import timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/assets"
TAGS = ["Assets"]

# Modele Pydantic dla request/response


class AssetResponse(BaseModel):
    """Odpowiedź z informacją o assecie."""
    id: int
    asset: str
    quote: str


class AssetCreate(BaseModel):
    """Model do tworzenia nowego assetu."""
    asset: str = Field(..., min_length=1, max_length=50, description="Nazwa base asset")
    quote: str = Field(..., min_length=1, max_length=50, description="Nazwa quote currency")


class AssetUpdate(BaseModel):
    """Model do aktualizacji assetu."""
    asset: Optional[str] = Field(None, min_length=1, max_length=50, description="Nazwa base asset")
    quote: Optional[str] = Field(None, min_length=1, max_length=50, description="Nazwa quote currency")


class AssetExchangeResponse(BaseModel):
    """Odpowiedź z relacją asset-exchange."""
    id: int
    asset_id: int
    exchange_id: int
    asset: str
    quote: str
    exchange_name: str
    display_name: Optional[str] = None


class AssetWithExchangesResponse(BaseModel):
    """Asset wraz z listą giełd."""
    id: int
    asset: str
    quote: str
    exchanges: List[str]
    exchange_count: int


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class AssetListResponse(BaseModel):
    """Lista assetów z informacją o paginacji."""
    assets: List[AssetResponse]
    pagination: PaginationInfo


class StatsResponse(BaseModel):
    """Statystyki assetów."""
    total_assets: int
    total_exchanges: int
    total_relations: int
    assets_without_patterns: Optional[int] = None


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
async def assets_info():
    """Informacje o dostępnych endpointach assetów."""
    return {
        "message": "Assets REST API",
        "version": "1.0.0",
        "available_endpoints": {
            "list": "GET /assets/list - Lista wszystkich assetów z paginacją",
            "get": "GET /assets/{id} - Szczegóły assetu",
            "create": "POST /assets - Tworzenie nowego assetu",
            "update": "PUT /assets/{id} - Aktualizacja assetu",
            "delete": "DELETE /assets/{id} - Usunięcie assetu",
            "count": "GET /assets/count - Liczba wszystkich assetów",
            "search_asset": "GET /assets/search/asset/{name} - Wyszukiwanie po nazwie assetu",
            "search_quote": "GET /assets/search/quote/{quote} - Wyszukiwanie po quote",
            "exchanges": "GET /assets/{id}/exchanges - Giełdy dla assetu",
            "by_exchange": "GET /assets/exchange/{exchange_id} - Assety na giełdzie",
            "link": "POST /assets/{asset_id}/exchanges/{exchange_id} - Przypisz asset do giełdy",
            "unlink": "DELETE /assets/{asset_id}/exchanges/{exchange_id} - Usuń relację",
            "without_patterns": "GET /assets/without-harmonic-patterns - Assety bez analiz",
            "old_patterns": "GET /assets/with-old-harmonic-patterns - Assety ze starymi analizami",
            "recent_patterns": "GET /assets/with-recent-harmonic-patterns - Assety z nowymi analizami",
            "unprocessed_charts": "GET /assets/with-unprocessed-chart-images - Assety z nieprzetworzonymi obrazami",
            "stats": "GET /assets/stats - Statystyki assetów"
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

@router.get("/list", response_model=AssetListResponse)
async def list_assets(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników na stronę"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich assetów z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        AssetListResponse: Lista assetów z informacją o paginacji
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        # Pobierz assety z dodatkowym rekordem dla sprawdzenia następnej strony
        assets = await assets_table.get_all(limit=limit + 1, offset=offset)
        
        # Sprawdź czy są następne strony
        has_more = len(assets) > limit
        page_assets = assets[:limit]
        
        # Konwertuj na response model
        asset_responses = [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in page_assets
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return AssetListResponse(
            assets=asset_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error listing assets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list assets: {str(e)}")


@router.get("/count", response_model=Dict[str, int])
async def count_assets():
    """
    Zlicza wszystkie assety w bazie danych.
    
    Returns:
        Dict z liczbą assetów
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        count = await assets_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting assets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count assets: {str(e)}")


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera szczegóły konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        AssetResponse: Szczegóły assetu
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        asset = await assets_table.get_by_id(asset_id)
        
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset with ID {asset_id} not found")
        
        return AssetResponse(
            id=asset['id'],
            asset=asset['asset'],
            quote=asset['quote']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get asset: {str(e)}")


@router.post("", response_model=StandardResponse, status_code=201)
async def create_asset(
    asset_data: AssetCreate = Body(..., description="Dane nowego assetu")
):
    """
    Tworzy nowy asset.
    
    Args:
        asset_data: Dane assetu do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonego assetu
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        # Sprawdź czy asset już istnieje
        existing = await assets_table.get_by_asset_quote(asset_data.asset, asset_data.quote)
        if existing:
            raise HTTPException(
                status_code=409, 
                detail=f"Asset {asset_data.asset}/{asset_data.quote} already exists with ID {existing['id']}"
            )
        
        # Utwórz asset
        asset_id = await assets_table.create(asset_data.asset, asset_data.quote)
        
        if not asset_id:
            raise HTTPException(status_code=500, detail="Failed to create asset")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_data.asset}/{asset_data.quote} created successfully",
            data={"asset_id": asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating asset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create asset: {str(e)}")


@router.put("/{asset_id}", response_model=StandardResponse)
async def update_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu do aktualizacji"),
    asset_data: AssetUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejący asset.
    
    Args:
        asset_id: ID assetu do aktualizacji
        asset_data: Nowe dane assetu
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        # Sprawdź czy asset istnieje
        existing = await assets_table.get_by_id(asset_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Asset with ID {asset_id} not found")
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if asset_data.asset is not None:
            update_data['asset'] = asset_data.asset
        if asset_data.quote is not None:
            update_data['quote'] = asset_data.quote
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await assets_table.update(asset_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update asset")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_id} updated successfully",
            data={"asset_id": asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update asset: {str(e)}")


@router.delete("/{asset_id}", response_model=StandardResponse)
async def delete_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu do usunięcia")
):
    """
    Usuwa asset z bazy danych.
    
    UWAGA: To usunie również wszystkie powiązane relacje i dane analiz!
    
    Args:
        asset_id: ID assetu do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        # Sprawdź czy asset istnieje
        existing = await assets_table.get_by_id(asset_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Asset with ID {asset_id} not found")
        
        # Usuń asset
        success = await assets_table.delete(asset_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete asset")
        
        return StandardResponse(
            success=True,
            message=f"Asset {existing['asset']}/{existing['quote']} (ID: {asset_id}) deleted successfully",
            data={"asset_id": asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete asset: {str(e)}")


# ===================
# SEARCH OPERATIONS
# ===================

@router.get("/search/asset/{asset_name}", response_model=List[AssetResponse])
async def search_by_asset(
    asset_name: str = Path(..., min_length=1, description="Nazwa assetu do wyszukania")
):
    """
    Wyszukuje assety po nazwie base asset (case-insensitive, LIKE search).
    
    Args:
        asset_name: Nazwa lub część nazwy assetu
        
    Returns:
        List[AssetResponse]: Lista znalezionych assetów
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        assets = await assets_table.search_by_asset(asset_name)
        
        return [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in assets
        ]
        
    except Exception as e:
        logger.error(f"Error searching assets by name '{asset_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search assets: {str(e)}")


@router.get("/search/quote/{quote_name}", response_model=List[AssetResponse])
async def search_by_quote(
    quote_name: str = Path(..., min_length=1, description="Nazwa quote currency do wyszukania")
):
    """
    Wyszukuje assety po nazwie quote currency (case-insensitive, LIKE search).
    
    Args:
        quote_name: Nazwa lub część nazwy quote
        
    Returns:
        List[AssetResponse]: Lista znalezionych assetów
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        assets = await assets_table.search_by_quote(quote_name)
        
        return [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in assets
        ]
        
    except Exception as e:
        logger.error(f"Error searching assets by quote '{quote_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search assets: {str(e)}")


# ===================
# EXCHANGE RELATIONS
# ===================

@router.get("/{asset_id}/exchanges", response_model=List[AssetExchangeResponse])
async def get_asset_exchanges(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera listę wszystkich giełd dla danego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        List[AssetExchangeResponse]: Lista giełd dla assetu
    """
    try:
        db = await get_db()
        asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
        
        exchanges = await asset_exchanges_table.get_by_asset_id(asset_id)
        
        return [
            AssetExchangeResponse(
                id=e['id'],
                asset_id=e['asset_id'],
                exchange_id=e['exchange_id'],
                asset=e['asset'],
                quote=e['quote'],
                exchange_name=e['exchange_name'],
                display_name=e.get('display_name')
            )
            for e in exchanges
        ]
        
    except Exception as e:
        logger.error(f"Error getting exchanges for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get exchanges: {str(e)}")


@router.get("/exchange/{exchange_id}", response_model=AssetListResponse)
async def get_assets_by_exchange(
    exchange_id: int = Path(..., ge=1, description="ID giełdy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich assetów na danej giełdzie.
    
    Args:
        exchange_id: ID giełdy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        AssetListResponse: Lista assetów na giełdzie
    """
    try:
        db = await get_db()
        asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
        
        # Pobierz z dodatkowym rekordem dla sprawdzenia następnej strony
        assets = await asset_exchanges_table.get_by_exchange_id(
            exchange_id, 
            limit=limit + 1, 
            offset=offset
        )
        
        # Sprawdź czy są następne strony
        has_more = len(assets) > limit
        page_assets = assets[:limit]
        
        # Konwertuj na response model
        asset_responses = [
            AssetResponse(id=a['asset_id'], asset=a['asset'], quote=a['quote'])
            for a in page_assets
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return AssetListResponse(
            assets=asset_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error getting assets for exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


@router.post("/{asset_id}/exchanges/{exchange_id}", response_model=StandardResponse, status_code=201)
async def link_asset_to_exchange(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Tworzy relację między assetem a giełdą.
    
    Args:
        asset_id: ID assetu
        exchange_id: ID giełdy
        
    Returns:
        StandardResponse: Potwierdzenie utworzenia relacji
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        exchanges_table = db.get_factory().get_exchanges_table()
        asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
        
        # Sprawdź czy asset istnieje
        asset = await assets_table.get_by_id(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset with ID {asset_id} not found")
        
        # Sprawdź czy exchange istnieje
        exchange = await exchanges_table.get_by_id(exchange_id)
        if not exchange:
            raise HTTPException(status_code=404, detail=f"Exchange with ID {exchange_id} not found")
        
        # Sprawdź czy relacja już istnieje
        existing = await asset_exchanges_table.get_by_asset_and_exchange(asset_id, exchange_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Relation between asset {asset_id} and exchange {exchange_id} already exists"
            )
        
        # Utwórz relację
        relation_id = await asset_exchanges_table.create(asset_id, exchange_id)
        
        if not relation_id:
            raise HTTPException(status_code=500, detail="Failed to create relation")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset['asset']}/{asset['quote']} linked to exchange {exchange['name']}",
            data={"relation_id": relation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error linking asset {asset_id} to exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to link asset to exchange: {str(e)}")


@router.delete("/{asset_id}/exchanges/{exchange_id}", response_model=StandardResponse)
async def unlink_asset_from_exchange(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    exchange_id: int = Path(..., ge=1, description="ID giełdy")
):
    """
    Usuwa relację między assetem a giełdą.
    
    Args:
        asset_id: ID assetu
        exchange_id: ID giełdy
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia relacji
    """
    try:
        db = await get_db()
        asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
        
        # Sprawdź czy relacja istnieje
        existing = await asset_exchanges_table.get_by_asset_and_exchange(asset_id, exchange_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Relation between asset {asset_id} and exchange {exchange_id} not found"
            )
        
        # Usuń relację
        success = await asset_exchanges_table.delete_by_asset_and_exchange(asset_id, exchange_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete relation")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_id} unlinked from exchange {exchange_id}",
            data={"asset_id": asset_id, "exchange_id": exchange_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unlinking asset {asset_id} from exchange {exchange_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to unlink asset from exchange: {str(e)}")


# ===================
# ADVANCED QUERIES (PRZYDATNE DLA CLI)
# ===================

@router.get("/without-harmonic-patterns", response_model=AssetListResponse)
async def get_assets_without_harmonic_patterns(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera assety, które nie mają żadnych analiz technicznych harmonic patterns.
    Przydatne do identyfikacji assetów wymagających analizy.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        AssetListResponse: Lista assetów bez analiz
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        # Pobierz z dodatkowym rekordem
        assets = await assets_table.get_assets_without_harmonic_patterns(
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(assets) > limit
        page_assets = assets[:limit]
        
        asset_responses = [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in page_assets
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return AssetListResponse(
            assets=asset_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error getting assets without harmonic patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


@router.get("/with-old-harmonic-patterns", response_model=AssetListResponse)
async def get_assets_with_old_harmonic_patterns(
    days: int = Query(default=365, ge=1, le=3650, description="Liczba dni definiująca 'stare' analizy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera assety, które mają analizy techniczne starsze niż podana liczba dni,
    ale NIE mają młodszych analiz.
    Przydatne do identyfikacji assetów wymagających aktualizacji analiz.
    
    Args:
        days: Liczba dni definiująca 'stare' analizy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        AssetListResponse: Lista assetów ze starymi analizami
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        time_delta = timedelta(days=days)
        
        # Pobierz z dodatkowym rekordem
        assets = await assets_table.get_assets_with_old_harmonic_patterns(
            time_delta=time_delta,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(assets) > limit
        page_assets = assets[:limit]
        
        asset_responses = [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in page_assets
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return AssetListResponse(
            assets=asset_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error getting assets with old harmonic patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


@router.get("/with-recent-harmonic-patterns", response_model=AssetListResponse)
async def get_assets_with_recent_harmonic_patterns(
    days: int = Query(default=30, ge=1, le=3650, description="Liczba dni definiująca 'nowe' analizy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera assety, które mają analizy techniczne młodsze niż podana liczba dni.
    Przydatne do identyfikacji aktywnie analizowanych assetów.
    
    Args:
        days: Liczba dni definiująca 'nowe' analizy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        AssetListResponse: Lista assetów z nowymi analizami
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        time_delta = timedelta(days=days)
        
        # Pobierz z dodatkowym rekordem
        assets = await assets_table.get_assets_with_recent_harmonic_patterns(
            time_delta=time_delta,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(assets) > limit
        page_assets = assets[:limit]
        
        asset_responses = [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in page_assets
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return AssetListResponse(
            assets=asset_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error getting assets with recent harmonic patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


@router.get("/with-unprocessed-chart-images", response_model=AssetListResponse)
async def get_assets_with_unprocessed_chart_images(
    interval: str = Query(..., description="Interwał czasowy (np. '4h', '1d')"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera assety, które mają chart images nieprzypisane do żadnej analizy technicznej
    dla konkretnego interwału.
    Przydatne do identyfikacji assetów z obrazami wymagającymi interpretacji LLM.
    
    Args:
        interval: Interwał czasowy (np. '4h', '1d', '1w')
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        AssetListResponse: Lista assetów z nieprzetworzonymi obrazami
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        
        # Pobierz z dodatkowym rekordem
        assets = await assets_table.get_assets_with_unprocessed_chart_images_by_interval(
            interval=interval,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(assets) > limit
        page_assets = assets[:limit]
        
        asset_responses = [
            AssetResponse(id=a['id'], asset=a['asset'], quote=a['quote'])
            for a in page_assets
        ]
        
        pagination_info = PaginationInfo(
            limit=limit,
            offset=offset,
            has_more=has_more
        )
        
        return AssetListResponse(
            assets=asset_responses,
            pagination=pagination_info
        )
        
    except Exception as e:
        logger.error(f"Error getting assets with unprocessed chart images: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


# ===================
# STATISTICS
# ===================

@router.get("/stats", response_model=StatsResponse)
async def get_assets_stats():
    """
    Pobiera ogólne statystyki assetów i relacji.
    
    Returns:
        StatsResponse: Statystyki assetów
    """
    try:
        db = await get_db()
        assets_table = db.get_factory().get_assets_table()
        exchanges_table = db.get_factory().get_exchanges_table()
        asset_exchanges_table = db.get_factory().get_asset_exchanges_table()
        
        # Zlicz assety
        total_assets = await assets_table.count_all()
        
        # Zlicz giełdy
        all_exchanges = await exchanges_table.get_all(limit=10000)
        total_exchanges = len(all_exchanges)
        
        # Zlicz relacje
        all_relations = await asset_exchanges_table.get_all(limit=100000)
        total_relations = len(all_relations)
        
        # Zlicz assety bez analiz (opcjonalnie)
        try:
            assets_without = await assets_table.get_assets_without_harmonic_patterns(limit=100000)
            assets_without_patterns = len(assets_without)
        except Exception as e:
            logger.warning(f"Could not count assets without patterns: {e}")
            assets_without_patterns = None
        
        return StatsResponse(
            total_assets=total_assets,
            total_exchanges=total_exchanges,
            total_relations=total_relations,
            assets_without_patterns=assets_without_patterns
        )
        
    except Exception as e:
        logger.error(f"Error getting assets stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

