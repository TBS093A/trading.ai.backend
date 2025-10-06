"""
REST API Controller dla domeny technical analysis interpretation (interpretacje LLM analizy technicznej).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania interpretacjami LLM analizy technicznej (CRUD)
- Filtrowania interpretacji po asset, technical_analysis_id, timestamp
- Wyszukiwania po zawartości interpretacji
- Pobierania interpretacji z chart images
- Pobierania interpretacji bez interpretacji generalnej
- Statystyk interpretacji

UWAGA: Ten kontroler obsługuje TYLKO interpretacje LLM analizy technicznej.
Czysta analiza techniczna jest w osobnym kontrolerze.
Interpretacje generalne będą w osobnej domenie później.

Bazuje na funkcjonalności z technical_analysis_interpretation_table.py

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
PREFIX = "/llm/interpretation/technical"
TAGS = ["Technical Analysis LLM Interpretation"]

# Modele Pydantic dla request/response


class TechnicalAnalysisInterpretationResponse(BaseModel):
    """Odpowiedź z informacją o interpretacji LLM analizy technicznej."""
    id: int
    asset_id: int
    technical_analysis_id: int
    timestamp: str
    content: str
    created_at: Optional[datetime] = None
    asset: Optional[str] = None
    quote: Optional[str] = None
    x_point_timestamp: Optional[int] = None


class TechnicalAnalysisInterpretationWithImagesResponse(BaseModel):
    """Odpowiedź z interpretacją i chart images."""
    id: int
    asset_id: int
    technical_analysis_id: int
    timestamp: str
    content: str
    created_at: Optional[datetime] = None
    asset: Optional[str] = None
    quote: Optional[str] = None
    x_point_timestamp: Optional[int] = None
    chart_images: List[Dict[str, Any]] = []


class TechnicalAnalysisInterpretationCreate(BaseModel):
    """Model do tworzenia nowej interpretacji."""
    asset_id: int = Field(..., ge=1, description="ID assetu")
    technical_analysis_id: int = Field(..., ge=1, description="ID analizy technicznej")
    timestamp: str = Field(..., description="Timestamp interpretacji")
    content: str = Field(..., min_length=1, description="Treść interpretacji LLM")

    class Config:
        json_schema_extra = {
            "example": {
                "asset_id": 1,
                "technical_analysis_id": 42,
                "timestamp": "2024-01-15T10:30:00",
                "content": "Based on the harmonic pattern analysis, a bullish Gartley pattern has been identified..."
            }
        }


class TechnicalAnalysisInterpretationUpdate(BaseModel):
    """Model do aktualizacji interpretacji."""
    asset_id: Optional[int] = Field(None, ge=1, description="ID assetu")
    technical_analysis_id: Optional[int] = Field(None, ge=1, description="ID analizy technicznej")
    timestamp: Optional[str] = Field(None, description="Timestamp interpretacji")
    content: Optional[str] = Field(None, min_length=1, description="Treść interpretacji LLM")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class TechnicalAnalysisInterpretationListResponse(BaseModel):
    """Lista interpretacji z informacją o paginacji."""
    interpretations: List[TechnicalAnalysisInterpretationResponse]
    pagination: PaginationInfo


class TechnicalAnalysisInterpretationWithImagesListResponse(BaseModel):
    """Lista interpretacji z chart images z informacją o paginacji."""
    interpretations: List[TechnicalAnalysisInterpretationWithImagesResponse]
    pagination: PaginationInfo


class TechnicalAnalysisInterpretationStatsResponse(BaseModel):
    """Statystyki interpretacji."""
    total_interpretations: int
    interpretations_by_asset: Optional[Dict[str, int]] = None


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
async def technical_interpretation_info():
    """Informacje o dostępnych endpointach interpretacji LLM analizy technicznej."""
    return {
        "message": "Technical Analysis Interpretation (LLM) REST API",
        "version": "1.0.0",
        "description": "API for LLM interpretations of technical analysis (NOT raw technical analysis)",
        "available_endpoints": {
            "crud": {
                "list": "GET /llm/interpretation/technical/list - Lista wszystkich interpretacji",
                "get": "GET /llm/interpretation/technical/{id} - Szczegóły interpretacji",
                "create": "POST /llm/interpretation/technical - Tworzenie nowej interpretacji",
                "update": "PUT /llm/interpretation/technical/{id} - Aktualizacja interpretacji",
                "delete": "DELETE /llm/interpretation/technical/{id} - Usunięcie interpretacji"
            },
            "filtering": {
                "by_asset": "GET /llm/interpretation/technical/asset/{asset_id} - Interpretacje dla assetu",
                "latest_by_asset": "GET /llm/interpretation/technical/asset/{asset_id}/latest - Najnowsza interpretacja dla assetu",
                "by_technical_analysis": "GET /llm/interpretation/technical/analysis/{technical_analysis_id} - Interpretacje dla analizy technicznej",
                "by_timestamp_range": "GET /llm/interpretation/technical/timestamp/range - Interpretacje z zakresu czasowego",
                "by_timestamp_range_and_asset": "GET /llm/interpretation/technical/timestamp/range/asset/{asset_id} - Interpretacje z zakresu czasowego dla assetu",
                "without_general": "GET /llm/interpretation/technical/without-general/asset/{asset_id} - Interpretacje bez interpretacji generalnej"
            },
            "images": {
                "with_images": "GET /llm/interpretation/technical/{id}/images - Interpretacja z chart images",
                "all_with_images": "GET /llm/interpretation/technical/images - Wszystkie interpretacje z chart images",
                "intervals": "GET /llm/interpretation/technical/{id}/intervals - Interwały wzorców harmonicznych"
            },
            "search": {
                "by_content": "GET /llm/interpretation/technical/search/content/{content} - Wyszukiwanie w treści"
            },
            "stats": {
                "count": "GET /llm/interpretation/technical/count - Liczba wszystkich interpretacji",
                "count_by_asset": "GET /llm/interpretation/technical/count/asset/{asset_id} - Liczba interpretacji dla assetu",
                "stats": "GET /llm/interpretation/technical/stats - Statystyki interpretacji"
            }
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{interpretation_id}

@router.get("/list", response_model=TechnicalAnalysisInterpretationListResponse)
async def list_technical_interpretations(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich interpretacji LLM analizy technicznej z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisInterpretationListResponse: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing technical interpretations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list technical interpretations: {str(e)}")


# ===================
# FILTERING - PRZED /{interpretation_id}
# ===================

@router.get("/asset/{asset_id}", response_model=TechnicalAnalysisInterpretationListResponse)
async def get_technical_interpretations_by_asset(
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
        TechnicalAnalysisInterpretationListResponse: Lista interpretacji dla assetu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_asset_id(asset_id=asset_id, limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical interpretations for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical interpretations: {str(e)}")


@router.get("/asset/{asset_id}/latest", response_model=TechnicalAnalysisInterpretationResponse)
async def get_latest_technical_interpretation_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera najnowszą interpretację LLM dla assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        TechnicalAnalysisInterpretationResponse: Najnowsza interpretacja
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretation = await interp_table.get_latest_by_asset_id(asset_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"No technical interpretation found for asset {asset_id}"
            )
        
        return TechnicalAnalysisInterpretationResponse(
            id=interpretation['id'],
            asset_id=interpretation['asset_id'],
            technical_analysis_id=interpretation['technical_analysis_id'],
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            asset=interpretation.get('asset'),
            quote=interpretation.get('quote'),
            x_point_timestamp=interpretation.get('x_point_timestamp')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting latest technical interpretation for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest interpretation: {str(e)}")


@router.get("/analysis/{technical_analysis_id}", response_model=List[TechnicalAnalysisInterpretationResponse])
async def get_technical_interpretations_by_technical_analysis(
    technical_analysis_id: int = Path(..., ge=1, description="ID analizy technicznej")
):
    """
    Pobiera interpretacje LLM dla konkretnej analizy technicznej.
    
    Args:
        technical_analysis_id: ID analizy technicznej
        
    Returns:
        List[TechnicalAnalysisInterpretationResponse]: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_technical_analysis_id(technical_analysis_id)
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in interpretations
        ]
        
        return interpretation_responses
        
    except Exception as e:
        logger.error(f"Error getting technical interpretations for analysis {technical_analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical interpretations: {str(e)}")


@router.get("/timestamp/range", response_model=TechnicalAnalysisInterpretationListResponse)
async def get_technical_interpretations_by_timestamp_range(
    start_timestamp: str = Query(..., description="Timestamp początkowy"),
    end_timestamp: str = Query(..., description="Timestamp końcowy"),
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
        TechnicalAnalysisInterpretationListResponse: Lista interpretacji z zakresu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.get_by_timestamp_range(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical interpretations by timestamp range: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical interpretations: {str(e)}")


@router.get("/timestamp/range/asset/{asset_id}", response_model=TechnicalAnalysisInterpretationListResponse)
async def get_technical_interpretations_by_timestamp_range_and_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    start_timestamp: str = Query(..., description="Timestamp początkowy"),
    end_timestamp: str = Query(..., description="Timestamp końcowy"),
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
        TechnicalAnalysisInterpretationListResponse: Lista interpretacji z zakresu dla assetu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
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
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical interpretations by timestamp range for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical interpretations: {str(e)}")


@router.get("/without-general/asset/{asset_id}", response_model=TechnicalAnalysisInterpretationListResponse)
async def get_technical_interpretations_without_general(
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
        TechnicalAnalysisInterpretationListResponse: Lista interpretacji bez interpretacji generalnej
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.get_interpretations_without_general_interpretation_by_asset_id(
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical interpretations without general for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get interpretations: {str(e)}")


# ===================
# IMAGES - PRZED /{interpretation_id}
# ===================

@router.get("/images", response_model=TechnicalAnalysisInterpretationWithImagesListResponse)
async def get_all_technical_interpretations_with_images(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera wszystkie interpretacje LLM wraz z powiązanymi chart images.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisInterpretationWithImagesListResponse: Lista interpretacji z obrazami
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.get_all_with_chart_images(limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationWithImagesResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp'),
                chart_images=i.get('chart_images', [])
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationWithImagesListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical interpretations with images: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get interpretations with images: {str(e)}")


# ===================
# SEARCH - PRZED /{interpretation_id}
# ===================

@router.get("/search/content/{content}", response_model=TechnicalAnalysisInterpretationListResponse)
async def search_technical_interpretations_by_content(
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
        TechnicalAnalysisInterpretationListResponse: Lista znalezionych interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretations = await interp_table.search_by_content(
            content=content,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            TechnicalAnalysisInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_id=i['technical_analysis_id'],
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                x_point_timestamp=i.get('x_point_timestamp')
            )
            for i in page_interpretations
        ]
        
        return TechnicalAnalysisInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching technical interpretations by content '{content}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search interpretations: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{interpretation_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_technical_interpretations():
    """
    Zlicza wszystkie interpretacje LLM analizy technicznej.
    
    Returns:
        Dict z liczbą interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        count = await interp_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting technical interpretations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/count/asset/{asset_id}", response_model=Dict[str, int])
async def count_technical_interpretations_by_asset(
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
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        count = await interp_table.count_by_asset(asset_id)
        
        return {"count": count, "asset_id": asset_id}
        
    except Exception as e:
        logger.error(f"Error counting technical interpretations for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/stats", response_model=TechnicalAnalysisInterpretationStatsResponse)
async def get_technical_interpretation_stats():
    """
    Pobiera statystyki interpretacji LLM analizy technicznej.
    
    Returns:
        TechnicalAnalysisInterpretationStatsResponse: Statystyki interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        total_count = await interp_table.count_all()
        
        return TechnicalAnalysisInterpretationStatsResponse(
            total_interpretations=total_count
        )
        
    except Exception as e:
        logger.error(f"Error getting technical interpretation stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ PO SPECYFICZNYCH
# ===================

@router.get("/{interpretation_id}", response_model=TechnicalAnalysisInterpretationResponse)
async def get_technical_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera szczegóły konkretnej interpretacji LLM.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        TechnicalAnalysisInterpretationResponse: Szczegóły interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretation = await interp_table.get_by_id(interpretation_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Technical interpretation with ID {interpretation_id} not found"
            )
        
        return TechnicalAnalysisInterpretationResponse(
            id=interpretation['id'],
            asset_id=interpretation['asset_id'],
            technical_analysis_id=interpretation['technical_analysis_id'],
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            asset=interpretation.get('asset'),
            quote=interpretation.get('quote'),
            x_point_timestamp=interpretation.get('x_point_timestamp')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technical interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical interpretation: {str(e)}")


@router.get("/{interpretation_id}/images", response_model=TechnicalAnalysisInterpretationWithImagesResponse)
async def get_technical_interpretation_with_images(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera interpretację LLM wraz z powiązanymi chart images.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        TechnicalAnalysisInterpretationWithImagesResponse: Interpretacja z obrazami
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        interpretation = await interp_table.get_with_chart_images(interpretation_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Technical interpretation with ID {interpretation_id} not found"
            )
        
        return TechnicalAnalysisInterpretationWithImagesResponse(
            id=interpretation['id'],
            asset_id=interpretation['asset_id'],
            technical_analysis_id=interpretation['technical_analysis_id'],
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            asset=interpretation.get('asset'),
            quote=interpretation.get('quote'),
            x_point_timestamp=interpretation.get('x_point_timestamp'),
            chart_images=interpretation.get('chart_images', [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technical interpretation with images {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get interpretation with images: {str(e)}")


@router.get("/{interpretation_id}/intervals", response_model=List[str])
async def get_technical_interpretation_intervals(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera wszystkie interwały wzorców harmonicznych powiązanych z interpretacją.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        List[str]: Lista interwałów
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        interpretation = await interp_table.get_by_id(interpretation_id)
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"Technical interpretation with ID {interpretation_id} not found"
            )
        
        intervals = await interp_table.get_all_intervals_of_used_harmonic_patterns(interpretation_id)
        
        return intervals
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting intervals for interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get intervals: {str(e)}")


@router.post("", response_model=StandardResponse, status_code=201)
async def create_technical_interpretation(
    interpretation_data: TechnicalAnalysisInterpretationCreate = Body(..., description="Dane nowej interpretacji")
):
    """
    Tworzy nową interpretację LLM analizy technicznej.
    
    Args:
        interpretation_data: Dane interpretacji do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonej interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        # Utwórz interpretację
        interpretation_id = await interp_table.create(
            asset_id=interpretation_data.asset_id,
            technical_analysis_id=interpretation_data.technical_analysis_id,
            timestamp=interpretation_data.timestamp,
            content=interpretation_data.content
        )
        
        if not interpretation_id:
            raise HTTPException(status_code=500, detail="Failed to create technical interpretation")
        
        return StandardResponse(
            success=True,
            message="Technical interpretation created successfully",
            data={"interpretation_id": interpretation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating technical interpretation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create technical interpretation: {str(e)}")


@router.put("/{interpretation_id}", response_model=StandardResponse)
async def update_technical_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji do aktualizacji"),
    interpretation_data: TechnicalAnalysisInterpretationUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejącą interpretację LLM.
    
    Args:
        interpretation_id: ID interpretacji do aktualizacji
        interpretation_data: Nowe dane interpretacji
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        existing = await interp_table.get_by_id(interpretation_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Technical interpretation with ID {interpretation_id} not found"
            )
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if interpretation_data.asset_id is not None:
            update_data['asset_id'] = interpretation_data.asset_id
        if interpretation_data.technical_analysis_id is not None:
            update_data['technical_analysis_id'] = interpretation_data.technical_analysis_id
        if interpretation_data.timestamp is not None:
            update_data['timestamp'] = interpretation_data.timestamp
        if interpretation_data.content is not None:
            update_data['content'] = interpretation_data.content
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await interp_table.update(interpretation_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update technical interpretation")
        
        return StandardResponse(
            success=True,
            message=f"Technical interpretation {interpretation_id} updated successfully",
            data={"interpretation_id": interpretation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating technical interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update technical interpretation: {str(e)}")


@router.delete("/{interpretation_id}", response_model=StandardResponse)
async def delete_technical_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji do usunięcia")
):
    """
    Usuwa interpretację LLM z bazy danych.
    
    Args:
        interpretation_id: ID interpretacji do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_technical_analysis_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        existing = await interp_table.get_by_id(interpretation_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Technical interpretation with ID {interpretation_id} not found"
            )
        
        # Usuń interpretację
        success = await interp_table.delete(interpretation_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete technical interpretation")
        
        return StandardResponse(
            success=True,
            message=f"Technical interpretation (ID: {interpretation_id}) deleted successfully",
            data={"interpretation_id": interpretation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting technical interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete technical interpretation: {str(e)}")

