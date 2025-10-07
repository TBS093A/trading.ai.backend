"""
REST API Controller dla domeny fundamental analysis interpretation (interpretacje LLM analizy fundamentalnej).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania interpretacjami LLM analizy fundamentalnej (CRUD)
- Filtrowania interpretacji po asset, fundamental_analysis_id, timestamp
- Zarządzania powiązaniami z assets i fundamental analyses
- Wyszukiwania po zawartości i wzorcach JSON
- Pobierania interpretacji bez interpretacji generalnej
- Statystyk interpretacji

UWAGA: Ten kontroler obsługuje TYLKO interpretacje LLM analizy fundamentalnej.
Czysta analiza fundamentalna jest w osobnym kontrolerze.
Interpretacje generalne będą w osobnej domenie później.

Bazuje na funkcjonalności z fundamental_analysis_interpretation_table.py

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
PREFIX = "/llm/interpretation/fundamental"
TAGS = ["Fundamental Analysis LLM Interpretation"]

# Modele Pydantic dla request/response


class FundamentalAnalysisInterpretationResponse(BaseModel):
    """Odpowiedź z informacją o interpretacji LLM analizy fundamentalnej."""
    id: int
    timestamp: int
    content: Dict[str, Any]
    created_at: Optional[datetime] = None
    assets: Optional[List[str]] = None
    quotes: Optional[List[str]] = None
    asset_ids: Optional[List[int]] = None
    fundamental_analysis_ids: Optional[List[int]] = None


class FundamentalAnalysisInterpretationCreate(BaseModel):
    """Model do tworzenia nowej interpretacji."""
    asset_ids: List[int] = Field(..., min_items=1, description="Lista ID assetów")
    fundamental_analysis_ids: List[int] = Field(..., min_items=1, description="Lista ID analiz fundamentalnych")
    timestamp: int = Field(..., description="Timestamp interpretacji")
    content: Dict[str, Any] = Field(..., description="Obiekt JSON z treścią interpretacji LLM")

    class Config:
        json_schema_extra = {
            "example": {
                "asset_ids": [1, 2],
                "fundamental_analysis_ids": [42, 43],
                "timestamp": 1705324800,
                "content": {
                    "summary": "Positive market sentiment...",
                    "key_points": ["Strong fundamentals", "Growing revenue"],
                    "recommendation": "BUY"
                }
            }
        }


class FundamentalAnalysisInterpretationUpdate(BaseModel):
    """Model do aktualizacji interpretacji."""
    timestamp: Optional[int] = Field(None, description="Timestamp interpretacji")
    content: Optional[Dict[str, Any]] = Field(None, description="Obiekt JSON z treścią interpretacji")


class AssetManagementRequest(BaseModel):
    """Request do zarządzania assetami w interpretacji."""
    asset_id: int = Field(..., ge=1, description="ID assetu")


class AnalysisManagementRequest(BaseModel):
    """Request do zarządzania analizami w interpretacji."""
    fundamental_analysis_id: int = Field(..., ge=1, description="ID analizy fundamentalnej")


class CheckInterpretationExistsRequest(BaseModel):
    """Request do sprawdzania istnienia interpretacji."""
    asset_ids: List[int] = Field(..., min_items=1)
    fundamental_analysis_ids: List[int] = Field(..., min_items=1)
    timestamp: int


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class FundamentalAnalysisInterpretationListResponse(BaseModel):
    """Lista interpretacji z informacją o paginacji."""
    interpretations: List[FundamentalAnalysisInterpretationResponse]
    pagination: PaginationInfo


class FundamentalAnalysisInterpretationStatsResponse(BaseModel):
    """Statystyki interpretacji."""
    total_interpretations: int
    interpretations_by_asset: Optional[Dict[str, int]] = None


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class InterpretationExistsResponse(BaseModel):
    """Odpowiedź sprawdzająca istnienie interpretacji."""
    exists: bool


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
async def fundamental_interpretation_info():
    """Informacje o dostępnych endpointach interpretacji LLM analizy fundamentalnej."""
    return {
        "message": "Fundamental Analysis Interpretation (LLM) REST API",
        "version": "1.0.0",
        "description": "API for LLM interpretations of fundamental analysis (NOT raw fundamental analysis)",
        "available_endpoints": {
            "crud": {
                "list": "GET /llm/interpretation/fundamental/list - Lista wszystkich interpretacji",
                "get": "GET /llm/interpretation/fundamental/{id} - Szczegóły interpretacji"
            },
            "filtering": {
                "by_asset": "GET /llm/interpretation/fundamental/asset/{asset_id} - Interpretacje dla assetu",
                "latest_by_asset": "GET /llm/interpretation/fundamental/asset/{asset_id}/latest - Najnowsza interpretacja dla assetu",
                "by_fundamental_analysis": "GET /llm/interpretation/fundamental/analysis/{fundamental_analysis_id} - Interpretacje dla analizy fundamentalnej",
                "by_timestamp": "GET /llm/interpretation/fundamental/timestamp/{timestamp} - Interpretacje z konkretnego timestamp",
                "by_timestamp_range": "GET /llm/interpretation/fundamental/timestamp/range - Interpretacje z zakresu czasowego",
                "by_timestamp_range_and_asset": "GET /llm/interpretation/fundamental/timestamp/range/asset/{asset_id} - Interpretacje z zakresu czasowego dla assetu",
                "without_general": "GET /llm/interpretation/fundamental/without-general/asset/{asset_id} - Interpretacje bez interpretacji generalnej"
            },
            "assets": {
                "get_assets": "GET /llm/interpretation/fundamental/{id}/assets - Pobierz assety interpretacji",
                "add_asset": "POST /llm/interpretation/fundamental/{id}/assets - Dodaj asset do interpretacji",
                "remove_asset": "DELETE /llm/interpretation/fundamental/{id}/assets/{asset_id} - Usuń asset z interpretacji"
            },
            "analyses": {
                "get_analyses": "GET /llm/interpretation/fundamental/{id}/analyses - Pobierz analizy interpretacji",
                "add_analysis": "POST /llm/interpretation/fundamental/{id}/analyses - Dodaj analizę do interpretacji",
                "remove_analysis": "DELETE /llm/interpretation/fundamental/{id}/analyses/{analysis_id} - Usuń analizę z interpretacji"
            },
            "search": {
                "by_content": "GET /llm/interpretation/fundamental/search/content/{content} - Wyszukiwanie w treści",
                "by_json_pattern": "GET /llm/interpretation/fundamental/search/json/{pattern} - Wyszukiwanie po wzorcu JSON"
            },
            "stats": {
                "count": "GET /llm/interpretation/fundamental/count - Liczba wszystkich interpretacji",
                "count_by_asset": "GET /llm/interpretation/fundamental/count/asset/{asset_id} - Liczba interpretacji dla assetu",
                "stats": "GET /llm/interpretation/fundamental/stats - Statystyki interpretacji",
                "check_exists": "POST /llm/interpretation/fundamental/check-exists - Sprawdź czy interpretacja istnieje"
            }
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{interpretation_id}

@router.get("/list", response_model=FundamentalAnalysisInterpretationListResponse)
async def list_fundamental_interpretations(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich interpretacji LLM analizy fundamentalnej z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing fundamental interpretations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list fundamental interpretations: {str(e)}")


# ===================
# FILTERING - PRZED /{interpretation_id}
# ===================

@router.get("/asset/{asset_id}", response_model=FundamentalAnalysisInterpretationListResponse)
async def get_fundamental_interpretations_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje LLM dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista interpretacji dla assetu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_asset_id(asset_id=asset_id, limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretations for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental interpretations: {str(e)}")


@router.get("/asset/{asset_id}/latest", response_model=FundamentalAnalysisInterpretationResponse)
async def get_latest_fundamental_interpretation_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera najnowszą interpretację LLM dla assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        FundamentalAnalysisInterpretationResponse: Najnowsza interpretacja
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretation = await interp_table.get_latest_by_asset_id(asset_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"No fundamental interpretation found for asset {asset_id}"
            )
        
        return FundamentalAnalysisInterpretationResponse(
            id=interpretation['id'],
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            assets=interpretation.get('assets'),
            quotes=interpretation.get('quotes'),
            asset_ids=interpretation.get('asset_ids'),
            fundamental_analysis_ids=interpretation.get('fundamental_analysis_ids')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting latest fundamental interpretation for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest interpretation: {str(e)}")


@router.get("/analysis/{fundamental_analysis_id}", response_model=List[FundamentalAnalysisInterpretationResponse])
async def get_fundamental_interpretations_by_fundamental_analysis(
    fundamental_analysis_id: int = Path(..., ge=1, description="ID analizy fundamentalnej")
):
    """
    Pobiera interpretacje LLM dla konkretnej analizy fundamentalnej.
    
    Args:
        fundamental_analysis_id: ID analizy fundamentalnej
        
    Returns:
        List[FundamentalAnalysisInterpretationResponse]: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_fundamental_analysis_id(fundamental_analysis_id)
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in interpretations
        ]
        
        return interpretation_responses
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretations for analysis {fundamental_analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental interpretations: {str(e)}")


@router.get("/timestamp/{timestamp}", response_model=FundamentalAnalysisInterpretationListResponse)
async def get_fundamental_interpretations_by_timestamp(
    timestamp: int = Path(..., description="Timestamp"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje LLM z konkretnego timestamp.
    
    Args:
        timestamp: Timestamp
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista interpretacji z timestamp
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_timestamp(
            timestamp=timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretations by timestamp {timestamp}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental interpretations: {str(e)}")


@router.get("/timestamp/range", response_model=FundamentalAnalysisInterpretationListResponse)
async def get_fundamental_interpretations_by_timestamp_range(
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje LLM z zakresu czasowego.
    
    Args:
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista interpretacji z zakresu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_timestamp_range(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretations by timestamp range: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental interpretations: {str(e)}")


@router.get("/timestamp/range/asset/{asset_id}", response_model=FundamentalAnalysisInterpretationListResponse)
async def get_fundamental_interpretations_by_timestamp_range_and_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje LLM z zakresu czasowego dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista interpretacji z zakresu dla assetu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_timestamp_range_and_asset_id(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretations by timestamp range for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental interpretations: {str(e)}")


@router.get("/without-general/asset/{asset_id}", response_model=FundamentalAnalysisInterpretationListResponse)
async def get_fundamental_interpretations_without_general(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje LLM które nie mają jeszcze interpretacji generalnej.
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista interpretacji bez interpretacji generalnej
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.get_interpretations_without_general_interpretation_by_asset_id(
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretations without general for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get interpretations: {str(e)}")


# ===================
# SEARCH - PRZED /{interpretation_id}
# ===================

@router.get("/search/content/{content}", response_model=FundamentalAnalysisInterpretationListResponse)
async def search_fundamental_interpretations_by_content(
    content: str = Path(..., min_length=1, description="Zawartość do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje interpretacje LLM po zawartości (case-insensitive).
    
    Args:
        content: Zawartość do wyszukania
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista znalezionych interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.search_by_content(
            content=content,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching fundamental interpretations by content '{content}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search interpretations: {str(e)}")


@router.get("/search/json/{pattern}", response_model=FundamentalAnalysisInterpretationListResponse)
async def search_fundamental_interpretations_by_json_pattern(
    pattern: str = Path(..., min_length=1, description="Wzorzec JSON do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje interpretacje LLM po wzorcu w JSON (case-insensitive).
    
    Args:
        pattern: Wzorzec JSON do wyszukania
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        FundamentalAnalysisInterpretationListResponse: Lista znalezionych interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretations = await interp_table.search_by_json_pattern(
            pattern=pattern,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            FundamentalAnalysisInterpretationResponse(
                id=i['id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                assets=i.get('assets'),
                quotes=i.get('quotes'),
                asset_ids=i.get('asset_ids'),
                fundamental_analysis_ids=i.get('fundamental_analysis_ids')
            )
            for i in page_interpretations
        ]
        
        return FundamentalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching fundamental interpretations by JSON pattern '{pattern}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search interpretations: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{interpretation_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_fundamental_interpretations():
    """
    Zlicza wszystkie interpretacje LLM analizy fundamentalnej.
    
    Returns:
        Dict z liczbą interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        count = await interp_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting fundamental interpretations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/count/asset/{asset_id}", response_model=Dict[str, int])
async def count_fundamental_interpretations_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Zlicza interpretacje LLM dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        Dict z liczbą interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        count = await interp_table.count_by_asset(asset_id)
        
        return {"count": count, "asset_id": asset_id}
        
    except Exception as e:
        logger.error(f"Error counting fundamental interpretations for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/stats", response_model=FundamentalAnalysisInterpretationStatsResponse)
async def get_fundamental_interpretation_stats():
    """
    Pobiera statystyki interpretacji LLM analizy fundamentalnej.
    
    Returns:
        FundamentalAnalysisInterpretationStatsResponse: Statystyki interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        total_count = await interp_table.count_all()
        
        return FundamentalAnalysisInterpretationStatsResponse(
            total_interpretations=total_count
        )
        
    except Exception as e:
        logger.error(f"Error getting fundamental interpretation stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/check-exists", response_model=InterpretationExistsResponse)
async def check_fundamental_interpretation_exists(
    interpretation_data: CheckInterpretationExistsRequest = Body(..., description="Dane interpretacji do sprawdzenia")
):
    """
    Sprawdza czy interpretacja o podanych parametrach już istnieje.
    
    Args:
        interpretation_data: Dane interpretacji do sprawdzenia
        
    Returns:
        InterpretationExistsResponse: Informacja czy interpretacja istnieje
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        exists = await interp_table.check_interpretation_exists(
            asset_ids=interpretation_data.asset_ids,
            fundamental_analysis_ids=interpretation_data.fundamental_analysis_ids,
            timestamp=interpretation_data.timestamp
        )
        
        return InterpretationExistsResponse(exists=exists)
        
    except Exception as e:
        logger.error(f"Error checking fundamental interpretation exists: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check interpretation: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ PO SPECYFICZNYCH
# ===================

@router.get("/{interpretation_id}", response_model=FundamentalAnalysisInterpretationResponse)
async def get_fundamental_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera szczegóły konkretnej interpretacji LLM.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        FundamentalAnalysisInterpretationResponse: Szczegóły interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        interpretation = await interp_table.get_by_id(interpretation_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        return FundamentalAnalysisInterpretationResponse(
            id=interpretation['id'],
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            assets=interpretation.get('assets'),
            quotes=interpretation.get('quotes'),
            asset_ids=interpretation.get('asset_ids'),
            fundamental_analysis_ids=interpretation.get('fundamental_analysis_ids')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting fundamental interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fundamental interpretation: {str(e)}")


@router.get("/{interpretation_id}/assets", response_model=List[Dict[str, Any]])
async def get_fundamental_interpretation_assets(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera wszystkie assety powiązane z interpretacją.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        List[Dict]: Lista assetów
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        assets = await interp_table.get_interpretation_assets(interpretation_id)
        
        return assets
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting assets for interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get assets: {str(e)}")


@router.get("/{interpretation_id}/analyses", response_model=List[Dict[str, Any]])
async def get_fundamental_interpretation_analyses(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera wszystkie analizy fundamentalne powiązane z interpretacją.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        List[Dict]: Lista analiz fundamentalnych
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        analyses = await interp_table.get_interpretation_analyses(interpretation_id)
        
        return analyses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analyses for interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analyses: {str(e)}")

@router.post("/{interpretation_id}/assets", response_model=StandardResponse)
async def add_asset_to_fundamental_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji"),
    asset_data: AssetManagementRequest = Body(..., description="Dane assetu do dodania")
):
    """
    Dodaje asset do interpretacji.
    
    Args:
        interpretation_id: ID interpretacji
        asset_data: Dane assetu do dodania
        
    Returns:
        StandardResponse: Potwierdzenie dodania
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        # Dodaj asset
        success = await interp_table.add_asset_to_interpretation(interpretation_id, asset_data.asset_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add asset to interpretation")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_data.asset_id} added to interpretation {interpretation_id}",
            data={"interpretation_id": interpretation_id, "asset_id": asset_data.asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding asset to interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add asset: {str(e)}")


@router.delete("/{interpretation_id}/assets/{asset_id}", response_model=StandardResponse)
async def remove_asset_from_fundamental_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji"),
    asset_id: int = Path(..., ge=1, description="ID assetu do usunięcia")
):
    """
    Usuwa asset z interpretacji.
    
    Args:
        interpretation_id: ID interpretacji
        asset_id: ID assetu do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        # Usuń asset
        success = await interp_table.remove_asset_from_interpretation(interpretation_id, asset_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove asset from interpretation")
        
        return StandardResponse(
            success=True,
            message=f"Asset {asset_id} removed from interpretation {interpretation_id}",
            data={"interpretation_id": interpretation_id, "asset_id": asset_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing asset from interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove asset: {str(e)}")


@router.post("/{interpretation_id}/analyses", response_model=StandardResponse)
async def add_analysis_to_fundamental_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji"),
    analysis_data: AnalysisManagementRequest = Body(..., description="Dane analizy do dodania")
):
    """
    Dodaje analizę fundamentalną do interpretacji.
    
    Args:
        interpretation_id: ID interpretacji
        analysis_data: Dane analizy do dodania
        
    Returns:
        StandardResponse: Potwierdzenie dodania
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        # Dodaj analizę
        success = await interp_table.add_analysis_to_interpretation(
            interpretation_id, 
            analysis_data.fundamental_analysis_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add analysis to interpretation")
        
        return StandardResponse(
            success=True,
            message=f"Analysis {analysis_data.fundamental_analysis_id} added to interpretation {interpretation_id}",
            data={
                "interpretation_id": interpretation_id, 
                "fundamental_analysis_id": analysis_data.fundamental_analysis_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding analysis to interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add analysis: {str(e)}")


@router.delete("/{interpretation_id}/analyses/{analysis_id}", response_model=StandardResponse)
async def remove_analysis_from_fundamental_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji"),
    analysis_id: int = Path(..., ge=1, description="ID analizy do usunięcia")
):
    """
    Usuwa analizę fundamentalną z interpretacji.
    
    Args:
        interpretation_id: ID interpretacji
        analysis_id: ID analizy do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_fundamental_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Fundamental interpretation with ID {interpretation_id} not found"
            )
        
        # Usuń analizę
        success = await interp_table.remove_analysis_from_interpretation(interpretation_id, analysis_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove analysis from interpretation")
        
        return StandardResponse(
            success=True,
            message=f"Analysis {analysis_id} removed from interpretation {interpretation_id}",
            data={"interpretation_id": interpretation_id, "fundamental_analysis_id": analysis_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing analysis from interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove analysis: {str(e)}")

