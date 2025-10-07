"""
REST API Controller dla domeny fundamental analysis (analiza fundamentalna).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania analizami fundamentalnymi (CRUD)
- Filtrowania analiz po asset, service, timestamp
- Wyszukiwania po zawartości JSON
- Zarządzania powiązaniami asset-analysis
- Pobierania analiz bez interpretacji LLM
- Statystyk analiz fundamentalnych

UWAGA: Ten kontroler obsługuje TYLKO analizę fundamentalną.
LLM interpretacje będą w osobnej domenie później.

Bazuje na funkcjonalności z fundamental_analysis_table.py

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
PREFIX = "/analysis/fundamental"
TAGS = ["Fundamental Analysis"]

# Modele Pydantic dla request/response


class FundamentalAnalysisResponse(BaseModel):
    """Odpowiedź z informacją o analizie fundamentalnej."""
    id: int
    timestamp: int
    content: Dict[str, Any]
    link: Optional[str] = None
    service: str
    created_at: Optional[datetime] = None
    assets: Optional[List[str]] = None
    quotes: Optional[List[str]] = None
    asset_ids: Optional[List[int]] = None


class FundamentalAnalysisCreate(BaseModel):
    """Model do tworzenia nowej analizy fundamentalnej."""
    asset_ids: List[int] = Field(..., min_items=1, description="Lista ID assetów")
    timestamp: int = Field(..., description="Timestamp analizy")
    content: Dict[str, Any] = Field(..., description="Obiekt JSON z danymi analizy")
    link: Optional[str] = Field(None, description="Link do źródła")
    service: str = Field(..., min_length=1, description="Nazwa serwisu źródłowego")

    class Config:
        json_schema_extra = {
            "example": {
                "asset_ids": [1, 2],
                "timestamp": 1609459200,
                "link": "https://example.com/news/123",
                "service": "CoinTelegraph",
                "content": {
                    "title": "Bitcoin hits new ATH",
                    "summary": "Bitcoin reached a new all-time high today",
                    "sentiment": "positive"
                }
            }
        }


class FundamentalAnalysisUpdate(BaseModel):
    """Model do aktualizacji analizy fundamentalnej."""
    timestamp: Optional[int] = Field(None, description="Timestamp analizy")
    content: Optional[Dict[str, Any]] = Field(None, description="Obiekt JSON z danymi")
    link: Optional[str] = Field(None, description="Link do źródła")
    service: Optional[str] = Field(None, min_length=1, description="Nazwa serwisu")


class AssetManagementRequest(BaseModel):
    """Request do zarządzania assetami w analizie."""
    asset_id: int = Field(..., ge=1, description="ID assetu")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class FundamentalAnalysisListResponse(BaseModel):
    """Lista analiz fundamentalnych z informacją o paginacji."""
    analyses: List[FundamentalAnalysisResponse]
    pagination: PaginationInfo


class FundamentalAnalysisStatsResponse(BaseModel):
    """Statystyki analiz fundamentalnych."""
    total_analyses: int
    analyses_by_service: Optional[Dict[str, int]] = None
    total_asset_connections: Optional[int] = None


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class AnalysisExistsResponse(BaseModel):
    """Odpowiedź sprawdzająca istnienie analizy."""
    exists: bool
    analysis_id: Optional[int] = None


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
async def fundamental_analysis_info():
    """Informacje o dostępnych endpointach analizy fundamentalnej."""
    return {
        "message": "Fundamental Analysis REST API",
        "version": "1.0.0",
        "description": "API for fundamental analysis (NOT LLM interpretations)",
        "available_endpoints": {
            "crud": {
                "list": "GET /analysis/fundamental/list - Lista wszystkich analiz",
                "get": "GET /analysis/fundamental/{id} - Szczegóły analizy"
            },
            "filtering": {
                "by_asset": "GET /analysis/fundamental/asset/{asset_id} - Analizy dla assetu",
                "by_service": "GET /analysis/fundamental/service/{service} - Analizy z serwisu",
                "by_timestamp": "GET /analysis/fundamental/timestamp/{timestamp} - Analizy z timestamp",
                "by_timestamp_range": "GET /analysis/fundamental/timestamp/range - Analizy z zakresu czasowego (+ opcjonalne asset_id, service)",
                "by_timestamp_range_asset": "GET /analysis/fundamental/timestamp/range/asset/{asset_id} - Analizy z zakresu dla assetu",
                "by_timestamp_service": "GET /analysis/fundamental/timestamp/{timestamp}/service/{service} - Analizy po timestamp i serwisie",
                "latest_by_asset": "GET /analysis/fundamental/asset/{asset_id}/latest - Najnowsza analiza dla assetu",
                "without_interpretation": "GET /analysis/fundamental/without-interpretation - Analizy bez interpretacji LLM"
            },
            "asset_management": {
                "get_assets": "GET /analysis/fundamental/{id}/assets - Lista assetów powiązanych z analizą",
                "add_asset": "POST /analysis/fundamental/{id}/assets - Dodaj asset do analizy",
                "remove_asset": "DELETE /analysis/fundamental/{id}/assets/{asset_id} - Usuń asset z analizy"
            },
            "search": {
                "by_json": "GET /analysis/fundamental/search/json/{pattern} - Wyszukiwanie w JSON",
                "by_content": "GET /analysis/fundamental/search/content/{content} - Wyszukiwanie w zawartości"
            },
            "validation": {
                "check_exists": "POST /analysis/fundamental/check-exists - Sprawdź czy analiza istnieje"
            },
            "stats": {
                "count": "GET /analysis/fundamental/count - Liczba wszystkich analiz",
                "count_by_asset": "GET /analysis/fundamental/count/asset/{asset_id} - Liczba analiz dla assetu",
                "stats": "GET /analysis/fundamental/stats - Statystyki analiz"
            }
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{analysis_id}

@router.get("/list", response_model=FundamentalAnalysisListResponse)
async def list_fundamental_analyses(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich analiz fundamentalnych z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz fundamentalnych
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing fundamental analyses: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list fundamental analyses: {str(e)}")


# ===================
# FILTERING - PRZED /{analysis_id}
# ===================

@router.get("/asset/{asset_id}", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz dla assetu
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.get_by_asset_id(asset_id=asset_id, limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analyses: {str(e)}")


@router.get("/asset/{asset_id}/latest", response_model=FundamentalAnalysisResponse)
async def get_latest_fundamental_analysis_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera najnowszą analizę fundamentalną dla assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        FundamentalAnalysisResponse: Najnowsza analiza
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analysis = await fa_table.get_latest_by_asset_id(asset_id)
        
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"No fundamental analysis found for asset {asset_id}"
            )
        
        return FundamentalAnalysisResponse(
            id=analysis['id'],
            timestamp=analysis['timestamp'],
            content=analysis['content'],
            link=analysis.get('link'),
            service=analysis['service'],
            created_at=analysis.get('created_at'),
            assets=analysis.get('assets'),
            quotes=analysis.get('quotes'),
            asset_ids=analysis.get('asset_ids')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting latest fundamental analysis for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest analysis: {str(e)}")


@router.get("/service/{service}", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_by_service(
    service: str = Path(..., description="Nazwa serwisu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne z określonego serwisu.
    
    Args:
        service: Nazwa serwisu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz z serwisu
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.get_by_service(service=service, limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses for service {service}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analyses: {str(e)}")


@router.get("/timestamp/{timestamp}", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_by_timestamp(
    timestamp: int = Path(..., description="Timestamp"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne dla konkretnego timestamp.
    
    Args:
        timestamp: Timestamp
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.get_by_timestamp(timestamp=timestamp, limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses for timestamp {timestamp}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analyses: {str(e)}")


@router.get("/timestamp/{timestamp}/service/{service}", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_by_timestamp_and_service(
    timestamp: int = Path(..., description="Timestamp"),
    service: str = Path(..., description="Nazwa serwisu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne dla timestamp i serwisu.
    
    Args:
        timestamp: Timestamp
        service: Nazwa serwisu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.get_by_timestamp_and_service(
            timestamp=timestamp,
            service=service,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses for timestamp {timestamp} and service {service}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analyses: {str(e)}")


@router.get("/timestamp/range", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_by_timestamp_range(
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    asset_id: Optional[int] = Query(None, ge=1, description="Opcjonalny filtr po asset_id"),
    service: Optional[str] = Query(None, description="Opcjonalny filtr po serwisie"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne z zakresu czasowego.
    
    Args:
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        asset_id: Opcjonalny filtr po asset_id
        service: Opcjonalny filtr po serwisie
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz z zakresu
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        # Wybierz odpowiednią metodę w zależności od parametrów
        if asset_id:
            analyses = await fa_table.get_by_timestamp_range_and_asset_id(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                asset_id=asset_id,
                limit=limit + 1,
                offset=offset
            )
        elif service:
            analyses = await fa_table.get_by_timestamp_range_and_service(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                service=service,
                limit=limit + 1,
                offset=offset
            )
        else:
            analyses = await fa_table.get_by_timestamp_range(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                limit=limit + 1,
                offset=offset
            )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses by timestamp range: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analyses: {str(e)}")


@router.get("/timestamp/range/asset/{asset_id}", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_by_timestamp_range_and_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne z zakresu czasowego dla konkretnego assetu.
    
    Dedykowany endpoint dla wygodnego filtrowania po zakresie czasowym i asset.
    
    Args:
        asset_id: ID assetu
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz z zakresu dla assetu
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.get_by_timestamp_range_and_asset_id(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses by timestamp range and asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analyses: {str(e)}")


@router.get("/without-interpretation", response_model=FundamentalAnalysisListResponse)
async def get_fundamental_analyses_without_interpretation(
    asset_id: Optional[int] = Query(None, ge=1, description="Opcjonalny filtr po asset_id"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy fundamentalne które nie mają jeszcze interpretacji LLM.
    
    Args:
        asset_id: Opcjonalny filtr po asset_id
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista analiz bez interpretacji
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        if asset_id:
            analyses = await fa_table.get_analyses_without_interpretation_by_asset_id(
                asset_id=asset_id,
                limit=limit + 1,
                offset=offset
            )
        else:
            analyses = await fa_table.get_analyses_without_interpretation(
                limit=limit + 1,
                offset=offset
            )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analyses without interpretation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analyses: {str(e)}")


# ===================
# SEARCH - PRZED /{analysis_id}
# ===================

@router.get("/search/json/{pattern}", response_model=FundamentalAnalysisListResponse)
async def search_fundamental_analyses_by_json(
    pattern: str = Path(..., min_length=1, description="Wzorzec do wyszukania w JSON"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje analizy fundamentalne po wzorcu w JSON (case-insensitive).
    
    Args:
        pattern: Wzorzec do wyszukania
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista znalezionych analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.search_by_json_pattern(
            pattern=pattern,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching fundamental analyses by JSON pattern '{pattern}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search analyses: {str(e)}")


@router.get("/search/content/{content}", response_model=FundamentalAnalysisListResponse)
async def search_fundamental_analyses_by_content(
    content: str = Path(..., min_length=1, description="Zawartość do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje analizy fundamentalne po zawartości (case-insensitive).
    
    Args:
        content: Zawartość do wyszukania
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisListResponse: Lista znalezionych analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analyses = await fa_table.search_by_content(
            content=content,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            FundamentalAnalysisResponse(
                id=a['id'],
                timestamp=a['timestamp'],
                content=a['content'],
                link=a.get('link'),
                service=a['service'],
                created_at=a.get('created_at'),
                assets=a.get('assets'),
                quotes=a.get('quotes'),
                asset_ids=a.get('asset_ids')
            )
            for a in page_analyses
        ]
        
        return FundamentalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching fundamental analyses by content '{content}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search analyses: {str(e)}")


# ===================
# VALIDATION - PRZED /{analysis_id}
# ===================

class CheckAnalysisExistsRequest(BaseModel):
    """Request do sprawdzania istnienia analizy."""
    asset_ids: List[int] = Field(..., min_items=1)
    timestamp: int
    service: str


@router.post("/check-exists", response_model=AnalysisExistsResponse)
async def check_analysis_exists(
    analysis_data: CheckAnalysisExistsRequest = Body(..., description="Dane analizy do sprawdzenia")
):
    """
    Sprawdza czy analiza o podanych parametrach już istnieje.
    
    Args:
        analysis_data: Dane analizy (asset_ids, timestamp, service)
        
    Returns:
        AnalysisExistsResponse: Informacja czy analiza istnieje
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        exists = await fa_table.check_analysis_exists(
            asset_ids=analysis_data.asset_ids,
            timestamp=analysis_data.timestamp,
            service=analysis_data.service
        )
        
        return AnalysisExistsResponse(exists=exists)
        
    except Exception as e:
        logger.error(f"Error checking analysis existence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check analysis existence: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{analysis_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_fundamental_analyses():
    """
    Zlicza wszystkie analizy fundamentalne.
    
    Returns:
        Dict z liczbą analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        count = await fa_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting fundamental analyses: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count analyses: {str(e)}")


@router.get("/count/asset/{asset_id}", response_model=Dict[str, int])
async def count_fundamental_analyses_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Zlicza analizy fundamentalne dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        Dict z liczbą analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        count = await fa_table.count_by_asset(asset_id)
        
        return {"count": count, "asset_id": asset_id}
        
    except Exception as e:
        logger.error(f"Error counting fundamental analyses for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count analyses: {str(e)}")


@router.get("/stats", response_model=FundamentalAnalysisStatsResponse)
async def get_fundamental_analysis_stats():
    """
    Pobiera statystyki analiz fundamentalnych.
    
    Returns:
        FundamentalAnalysisStatsResponse: Statystyki analiz
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        total_count = await fa_table.count_all()
        
        return FundamentalAnalysisStatsResponse(
            total_analyses=total_count
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental analysis stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ PO SPECYFICZNYCH
# ===================

@router.get("/{analysis_id}", response_model=FundamentalAnalysisResponse)
async def get_fundamental_analysis(
    analysis_id: int = Path(..., ge=1, description="ID analizy fundamentalnej")
):
    """
    Pobiera szczegóły konkretnej analizy fundamentalnej.
    
    Args:
        analysis_id: ID analizy
        
    Returns:
        FundamentalAnalysisResponse: Szczegóły analizy
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        analysis = await fa_table.get_by_id(analysis_id)
        
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental analysis with ID {analysis_id} not found"
            )
        
        return FundamentalAnalysisResponse(
            id=analysis['id'],
            timestamp=analysis['timestamp'],
            content=analysis['content'],
            link=analysis.get('link'),
            service=analysis['service'],
            created_at=analysis.get('created_at'),
            assets=analysis.get('assets'),
            quotes=analysis.get('quotes'),
            asset_ids=analysis.get('asset_ids')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting fundamental analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental analysis: {str(e)}")


@router.get("/{analysis_id}/assets", response_model=List[Dict[str, Any]])
async def get_analysis_assets(
    analysis_id: int = Path(..., ge=1, description="ID analizy")
):
    """
    Pobiera wszystkie assety powiązane z analizą fundamentalną.
    
    Args:
        analysis_id: ID analizy
        
    Returns:
        List[Dict]: Lista assetów
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        # Sprawdź czy analiza istnieje
        analysis = await fa_table.get_by_id(analysis_id)
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental analysis with ID {analysis_id} not found"
            )
        
        assets = await fa_table.get_analysis_assets(analysis_id)
        
        return assets
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assets for analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


@router.post("/{analysis_id}/assets", response_model=StandardResponse)
async def add_asset_to_analysis(
    analysis_id: int = Path(..., ge=1, description="ID analizy"),
    asset_data: AssetManagementRequest = Body(..., description="Dane assetu do dodania")
):
    """
    Dodaje asset do istniejącej analizy fundamentalnej.
    
    Args:
        analysis_id: ID analizy
        asset_data: Dane assetu (asset_id)
        
    Returns:
        StandardResponse: Potwierdzenie dodania
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        # Sprawdź czy analiza istnieje
        existing = await fa_table.get_by_id(analysis_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental analysis with ID {analysis_id} not found"
            )
        
        # Dodaj asset
        success = await fa_table.add_asset_to_analysis(analysis_id, asset_data.asset_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add asset to analysis")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_data.asset_id} added to analysis {analysis_id} successfully",
            data={"analysis_id": analysis_id, "asset_id": asset_data.asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding asset to analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add asset: {str(e)}")


@router.delete("/{analysis_id}/assets/{asset_id}", response_model=StandardResponse)
async def remove_asset_from_analysis(
    analysis_id: int = Path(..., ge=1, description="ID analizy"),
    asset_id: int = Path(..., ge=1, description="ID assetu do usunięcia")
):
    """
    Usuwa asset z analizy fundamentalnej.
    
    Args:
        analysis_id: ID analizy
        asset_id: ID assetu do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        fa_table = db.get_factory().get_fundamental_analysis_table()
        
        # Sprawdź czy analiza istnieje
        existing = await fa_table.get_by_id(analysis_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental analysis with ID {analysis_id} not found"
            )
        
        # Usuń asset
        success = await fa_table.remove_asset_from_analysis(analysis_id, asset_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove asset from analysis")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_id} removed from analysis {analysis_id} successfully",
            data={"analysis_id": analysis_id, "asset_id": asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing asset from analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove asset: {str(e)}")

