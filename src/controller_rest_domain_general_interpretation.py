"""
REST API Controller dla domeny general interpretation (interpretacje generalne/decyzyjne LLM).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania interpretacjami generalnymi/decyzyjnymi LLM (CRUD)
- Filtrowania interpretacji po asset, technical/fundamental interpretation, investment strategy
- Pobierania kompletnych interpretacji ze wszystkimi powiązanymi danymi
- Pobierania interpretacji bez powiązanych transakcji
- Wyszukiwania po zawartości interpretacji
- Statystyk interpretacji

UWAGA: Ten kontroler obsługuje TYLKO interpretacje generalne/decyzyjne LLM.
Interpretacje techniczne i fundamentalne są w osobnych kontrolerach.

Bazuje na funkcjonalności z general_interpretation_table.py

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
PREFIX = "/llm/interpretation/general"
TAGS = ["General Interpretation"]

# Modele Pydantic dla request/response


class GeneralInterpretationResponse(BaseModel):
    """Odpowiedź z informacją o interpretacji generalnej/decyzyjnej LLM."""
    id: int
    asset_id: int
    technical_analysis_interpretation_id: Optional[int] = None
    fundamental_analysis_interpretation_id: Optional[int] = None
    investment_strategy_id: Optional[int] = None
    timestamp: str
    content: str
    created_at: Optional[datetime] = None
    asset: Optional[str] = None
    quote: Optional[str] = None
    investment_strategy_name: Optional[str] = None
    investment_strategy_description: Optional[str] = None


class GeneralInterpretationCompleteResponse(BaseModel):
    """Odpowiedź z kompletną interpretacją generalną wraz ze wszystkimi powiązanymi danymi."""
    id: int
    asset_id: int
    technical_analysis_interpretation_id: Optional[int] = None
    fundamental_analysis_interpretation_id: Optional[int] = None
    investment_strategy_id: Optional[int] = None
    timestamp: str
    content: str
    created_at: Optional[datetime] = None
    asset: Optional[str] = None
    quote: Optional[str] = None
    technical_interpretation_content: Optional[str] = None
    fundamental_interpretation_content: Optional[Dict[str, Any]] = None
    investment_strategy_name: Optional[str] = None
    investment_strategy_description: Optional[str] = None


class GeneralInterpretationCreate(BaseModel):
    """Model do tworzenia nowej interpretacji generalnej."""
    asset_id: int = Field(..., ge=1, description="ID assetu")
    timestamp: str = Field(..., description="Timestamp interpretacji")
    content: str = Field(..., min_length=1, description="Treść interpretacji generalnej LLM")
    technical_analysis_interpretation_id: Optional[int] = Field(None, ge=1, description="ID interpretacji technicznej")
    fundamental_analysis_interpretation_id: Optional[int] = Field(None, ge=1, description="ID interpretacji fundamentalnej")
    investment_strategy_id: Optional[int] = Field(None, ge=1, description="ID strategii inwestycyjnej")

    class Config:
        json_schema_extra = {
            "example": {
                "asset_id": 1,
                "timestamp": "2024-01-15T10:30:00",
                "content": "Based on comprehensive analysis combining technical and fundamental insights, the recommended action is BUY with a target price of $50 and stop loss at $40.",
                "technical_analysis_interpretation_id": 42,
                "fundamental_analysis_interpretation_id": 43,
                "investment_strategy_id": 1
            }
        }


class GeneralInterpretationUpdate(BaseModel):
    """Model do aktualizacji interpretacji generalnej."""
    asset_id: Optional[int] = Field(None, ge=1, description="ID assetu")
    technical_analysis_interpretation_id: Optional[int] = Field(None, ge=1, description="ID interpretacji technicznej")
    fundamental_analysis_interpretation_id: Optional[int] = Field(None, ge=1, description="ID interpretacji fundamentalnej")
    investment_strategy_id: Optional[int] = Field(None, ge=1, description="ID strategii inwestycyjnej")
    timestamp: Optional[str] = Field(None, description="Timestamp interpretacji")
    content: Optional[str] = Field(None, min_length=1, description="Treść interpretacji")


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class GeneralInterpretationListResponse(BaseModel):
    """Lista interpretacji z informacją o paginacji."""
    interpretations: List[GeneralInterpretationResponse]
    pagination: PaginationInfo


class GeneralInterpretationStatsResponse(BaseModel):
    """Statystyki interpretacji."""
    total_interpretations: int
    interpretations_by_asset: Optional[Dict[str, int]] = None
    interpretations_by_strategy: Optional[Dict[str, int]] = None


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
async def general_interpretation_info():
    """Informacje o dostępnych endpointach interpretacji generalnej/decyzyjnej LLM."""
    return {
        "message": "General Interpretation (LLM) REST API",
        "version": "1.0.0",
        "description": "API for general/decision-making LLM interpretations combining technical and fundamental analysis",
        "available_endpoints": {
            "crud": {
                "list": "GET /llm/interpretation/general/list - Lista wszystkich interpretacji",
                "get": "GET /llm/interpretation/general/{id} - Szczegóły interpretacji",
                "create": "POST /llm/interpretation/general - Tworzenie nowej interpretacji",
                "update": "PUT /llm/interpretation/general/{id} - Aktualizacja interpretacji",
                "delete": "DELETE /llm/interpretation/general/{id} - Usunięcie interpretacji"
            },
            "filtering": {
                "by_asset": "GET /llm/interpretation/general/asset/{asset_id} - Interpretacje dla assetu",
                "latest_by_asset": "GET /llm/interpretation/general/asset/{asset_id}/latest - Najnowsza interpretacja dla assetu",
                "complete_by_asset": "GET /llm/interpretation/general/asset/{asset_id}/complete - Kompletna interpretacja dla assetu",
                "by_technical_interpretation": "GET /llm/interpretation/general/technical/{technical_interpretation_id} - Interpretacje dla interpretacji technicznej",
                "by_fundamental_interpretation": "GET /llm/interpretation/general/fundamental/{fundamental_interpretation_id} - Interpretacje dla interpretacji fundamentalnej",
                "by_investment_strategy": "GET /llm/interpretation/general/strategy/{investment_strategy_id} - Interpretacje dla strategii inwestycyjnej",
                "by_timestamp_range": "GET /llm/interpretation/general/timestamp/range - Interpretacje z zakresu czasowego",
                "by_timestamp_range_and_asset": "GET /llm/interpretation/general/timestamp/range/asset/{asset_id} - Interpretacje z zakresu czasowego dla assetu",
                "without_transactions": "GET /llm/interpretation/general/without-transactions - Interpretacje bez transakcji"
            },
            "search": {
                "by_content": "GET /llm/interpretation/general/search/content/{content} - Wyszukiwanie w treści"
            },
            "stats": {
                "count": "GET /llm/interpretation/general/count - Liczba wszystkich interpretacji",
                "count_by_asset": "GET /llm/interpretation/general/count/asset/{asset_id} - Liczba interpretacji dla assetu",
                "count_by_strategy": "GET /llm/interpretation/general/count/strategy/{investment_strategy_id} - Liczba interpretacji dla strategii",
                "stats": "GET /llm/interpretation/general/stats - Statystyki interpretacji"
            }
        }
    }


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{interpretation_id}

@router.get("/list", response_model=GeneralInterpretationListResponse)
async def list_general_interpretations(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich interpretacji generalnych LLM z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing general interpretations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list general interpretations: {str(e)}")


# ===================
# FILTERING - PRZED /{interpretation_id}
# ===================

@router.get("/asset/{asset_id}", response_model=GeneralInterpretationListResponse)
async def get_general_interpretations_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje generalne LLM dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista interpretacji dla assetu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_by_asset_id(asset_id=asset_id, limit=limit + 1, offset=offset)
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting general interpretations for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretations: {str(e)}")


@router.get("/asset/{asset_id}/latest", response_model=GeneralInterpretationResponse)
async def get_latest_general_interpretation_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera najnowszą interpretację generalną LLM dla assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        GeneralInterpretationResponse: Najnowsza interpretacja
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretation = await interp_table.get_latest_by_asset_id(asset_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"No general interpretation found for asset {asset_id}"
            )
        
        return GeneralInterpretationResponse(
            id=interpretation['id'],
            asset_id=interpretation['asset_id'],
            technical_analysis_interpretation_id=interpretation.get('technical_analysis_interpretation_id'),
            fundamental_analysis_interpretation_id=interpretation.get('fundamental_analysis_interpretation_id'),
            investment_strategy_id=interpretation.get('investment_strategy_id'),
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            asset=interpretation.get('asset'),
            quote=interpretation.get('quote'),
            investment_strategy_name=interpretation.get('investment_strategy_name'),
            investment_strategy_description=interpretation.get('investment_strategy_description')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting latest general interpretation for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest interpretation: {str(e)}")


@router.get("/asset/{asset_id}/complete", response_model=GeneralInterpretationCompleteResponse)
async def get_complete_general_interpretation_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera kompletną interpretację generalną LLM ze wszystkimi powiązanymi danymi.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        GeneralInterpretationCompleteResponse: Kompletna interpretacja z powiązanymi danymi
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretation = await interp_table.get_complete_interpretation(asset_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"No complete general interpretation found for asset {asset_id}"
            )
        
        return GeneralInterpretationCompleteResponse(
            id=interpretation['id'],
            asset_id=interpretation['asset_id'],
            technical_analysis_interpretation_id=interpretation.get('technical_analysis_interpretation_id'),
            fundamental_analysis_interpretation_id=interpretation.get('fundamental_analysis_interpretation_id'),
            investment_strategy_id=interpretation.get('investment_strategy_id'),
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            asset=interpretation.get('asset'),
            quote=interpretation.get('quote'),
            technical_interpretation_content=interpretation.get('technical_interpretation_content'),
            fundamental_interpretation_content=interpretation.get('fundamental_interpretation_content'),
            investment_strategy_name=interpretation.get('investment_strategy_name'),
            investment_strategy_description=interpretation.get('investment_strategy_description')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting complete general interpretation for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get complete interpretation: {str(e)}")


@router.get("/technical/{technical_interpretation_id}", response_model=List[GeneralInterpretationResponse])
async def get_general_interpretations_by_technical_interpretation(
    technical_interpretation_id: int = Path(..., ge=1, description="ID interpretacji technicznej")
):
    """
    Pobiera interpretacje generalne LLM dla konkretnej interpretacji technicznej.
    
    Args:
        technical_interpretation_id: ID interpretacji technicznej
        
    Returns:
        List[GeneralInterpretationResponse]: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_by_technical_analysis_interpretation_id(technical_interpretation_id)
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in interpretations
        ]
        
        return interpretation_responses
        
    except Exception as e:
        logger.error(f"Error getting general interpretations for technical interpretation {technical_interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretations: {str(e)}")


@router.get("/fundamental/{fundamental_interpretation_id}", response_model=List[GeneralInterpretationResponse])
async def get_general_interpretations_by_fundamental_interpretation(
    fundamental_interpretation_id: int = Path(..., ge=1, description="ID interpretacji fundamentalnej")
):
    """
    Pobiera interpretacje generalne LLM dla konkretnej interpretacji fundamentalnej.
    
    Args:
        fundamental_interpretation_id: ID interpretacji fundamentalnej
        
    Returns:
        List[GeneralInterpretationResponse]: Lista interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_by_fundamental_analysis_interpretation_id(fundamental_interpretation_id)
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in interpretations
        ]
        
        return interpretation_responses
        
    except Exception as e:
        logger.error(f"Error getting general interpretations for fundamental interpretation {fundamental_interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretations: {str(e)}")


@router.get("/strategy/{investment_strategy_id}", response_model=GeneralInterpretationListResponse)
async def get_general_interpretations_by_investment_strategy(
    investment_strategy_id: int = Path(..., ge=1, description="ID strategii inwestycyjnej"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje generalne LLM dla konkretnej strategii inwestycyjnej.
    
    Args:
        investment_strategy_id: ID strategii inwestycyjnej
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista interpretacji dla strategii
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_by_investment_strategy_id(
            investment_strategy_id=investment_strategy_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting general interpretations for strategy {investment_strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretations: {str(e)}")


@router.get("/timestamp/range", response_model=GeneralInterpretationListResponse)
async def get_general_interpretations_by_timestamp_range(
    start_timestamp: str = Query(..., description="Timestamp początkowy"),
    end_timestamp: str = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje generalne LLM z zakresu czasowego.
    
    Args:
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista interpretacji z zakresu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_by_timestamp_range(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting general interpretations by timestamp range: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretations: {str(e)}")


@router.get("/timestamp/range/asset/{asset_id}", response_model=GeneralInterpretationListResponse)
async def get_general_interpretations_by_timestamp_range_and_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    start_timestamp: str = Query(..., description="Timestamp początkowy"),
    end_timestamp: str = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje generalne LLM z zakresu czasowego dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista interpretacji z zakresu dla assetu
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
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
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting general interpretations by timestamp range and asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretations: {str(e)}")


@router.get("/without-transactions", response_model=GeneralInterpretationListResponse)
async def get_general_interpretations_without_transactions(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera interpretacje generalne LLM które nie mają powiązanych transakcji.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista interpretacji bez transakcji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.get_all_general_interpretations_without_transactions(
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting general interpretations without transactions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get interpretations: {str(e)}")


# ===================
# SEARCH - PRZED /{interpretation_id}
# ===================

@router.get("/search/content/{content}", response_model=GeneralInterpretationListResponse)
async def search_general_interpretations_by_content(
    content: str = Path(..., min_length=1, description="Zawartość do wyszukania"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje interpretacje generalne LLM po zawartości (case-insensitive).
    
    Args:
        content: Zawartość do wyszukania
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        GeneralInterpretationListResponse: Lista znalezionych interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretations = await interp_table.search_by_content(
            content=content,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(interpretations) > limit
        page_interpretations = interpretations[:limit]
        
        interpretation_responses = [
            GeneralInterpretationResponse(
                id=i['id'],
                asset_id=i['asset_id'],
                technical_analysis_interpretation_id=i.get('technical_analysis_interpretation_id'),
                fundamental_analysis_interpretation_id=i.get('fundamental_analysis_interpretation_id'),
                investment_strategy_id=i.get('investment_strategy_id'),
                timestamp=i['timestamp'],
                content=i['content'],
                created_at=i.get('created_at'),
                asset=i.get('asset'),
                quote=i.get('quote'),
                investment_strategy_name=i.get('investment_strategy_name'),
                investment_strategy_description=i.get('investment_strategy_description')
            )
            for i in page_interpretations
        ]
        
        return GeneralInterpretationListResponse(
            interpretations=interpretation_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching general interpretations by content '{content}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search interpretations: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{interpretation_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_general_interpretations():
    """
    Zlicza wszystkie interpretacje generalne LLM.
    
    Returns:
        Dict z liczbą interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        count = await interp_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting general interpretations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/count/asset/{asset_id}", response_model=Dict[str, int])
async def count_general_interpretations_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Zlicza interpretacje generalne LLM dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        Dict z liczbą interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        count = await interp_table.count_by_asset(asset_id)
        
        return {"count": count, "asset_id": asset_id}
        
    except Exception as e:
        logger.error(f"Error counting general interpretations for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/count/strategy/{investment_strategy_id}", response_model=Dict[str, int])
async def count_general_interpretations_by_strategy(
    investment_strategy_id: int = Path(..., ge=1, description="ID strategii inwestycyjnej")
):
    """
    Zlicza interpretacje generalne LLM dla konkretnej strategii inwestycyjnej.
    
    Args:
        investment_strategy_id: ID strategii inwestycyjnej
        
    Returns:
        Dict z liczbą interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        count = await interp_table.count_by_investment_strategy_id(investment_strategy_id)
        
        return {"count": count, "investment_strategy_id": investment_strategy_id}
        
    except Exception as e:
        logger.error(f"Error counting general interpretations for strategy {investment_strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count interpretations: {str(e)}")


@router.get("/stats", response_model=GeneralInterpretationStatsResponse)
async def get_general_interpretation_stats():
    """
    Pobiera statystyki interpretacji generalnych LLM.
    
    Returns:
        GeneralInterpretationStatsResponse: Statystyki interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        total_count = await interp_table.count_all()
        
        return GeneralInterpretationStatsResponse(
            total_interpretations=total_count
        )
        
    except Exception as e:
        logger.error(f"Error getting general interpretation stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ PO SPECYFICZNYCH
# ===================

@router.get("/{interpretation_id}", response_model=GeneralInterpretationResponse)
async def get_general_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji")
):
    """
    Pobiera szczegóły konkretnej interpretacji generalnej LLM.
    
    Args:
        interpretation_id: ID interpretacji
        
    Returns:
        GeneralInterpretationResponse: Szczegóły interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        interpretation = await interp_table.get_by_id(interpretation_id)
        
        if not interpretation:
            raise HTTPException(
                status_code=404,
                detail=f"General interpretation with ID {interpretation_id} not found"
            )
        
        return GeneralInterpretationResponse(
            id=interpretation['id'],
            asset_id=interpretation['asset_id'],
            technical_analysis_interpretation_id=interpretation.get('technical_analysis_interpretation_id'),
            fundamental_analysis_interpretation_id=interpretation.get('fundamental_analysis_interpretation_id'),
            investment_strategy_id=interpretation.get('investment_strategy_id'),
            timestamp=interpretation['timestamp'],
            content=interpretation['content'],
            created_at=interpretation.get('created_at'),
            asset=interpretation.get('asset'),
            quote=interpretation.get('quote'),
            investment_strategy_name=interpretation.get('investment_strategy_name'),
            investment_strategy_description=interpretation.get('investment_strategy_description')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting general interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get general interpretation: {str(e)}")


@router.post("", response_model=StandardResponse, status_code=201)
async def create_general_interpretation(
    interpretation_data: GeneralInterpretationCreate = Body(..., description="Dane nowej interpretacji")
):
    """
    Tworzy nową interpretację generalną/decyzyjną LLM.
    
    Args:
        interpretation_data: Dane interpretacji do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonej interpretacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        # Utwórz interpretację
        interpretation_id = await interp_table.create(
            asset_id=interpretation_data.asset_id,
            timestamp=interpretation_data.timestamp,
            content=interpretation_data.content,
            technical_analysis_interpretation_id=interpretation_data.technical_analysis_interpretation_id,
            fundamental_analysis_interpretation_id=interpretation_data.fundamental_analysis_interpretation_id,
            investment_strategy_id=interpretation_data.investment_strategy_id
        )
        
        if not interpretation_id:
            raise HTTPException(status_code=500, detail="Failed to create general interpretation")
        
        return StandardResponse(
            success=True,
            message="General interpretation created successfully",
            data={"interpretation_id": interpretation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating general interpretation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create general interpretation: {str(e)}")


@router.put("/{interpretation_id}", response_model=StandardResponse)
async def update_general_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji do aktualizacji"),
    interpretation_data: GeneralInterpretationUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejącą interpretację generalną LLM.
    
    Args:
        interpretation_id: ID interpretacji do aktualizacji
        interpretation_data: Nowe dane interpretacji
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        existing = await interp_table.get_by_id(interpretation_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"General interpretation with ID {interpretation_id} not found"
            )
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if interpretation_data.asset_id is not None:
            update_data['asset_id'] = interpretation_data.asset_id
        if interpretation_data.technical_analysis_interpretation_id is not None:
            update_data['technical_analysis_interpretation_id'] = interpretation_data.technical_analysis_interpretation_id
        if interpretation_data.fundamental_analysis_interpretation_id is not None:
            update_data['fundamental_analysis_interpretation_id'] = interpretation_data.fundamental_analysis_interpretation_id
        if interpretation_data.investment_strategy_id is not None:
            update_data['investment_strategy_id'] = interpretation_data.investment_strategy_id
        if interpretation_data.timestamp is not None:
            update_data['timestamp'] = interpretation_data.timestamp
        if interpretation_data.content is not None:
            update_data['content'] = interpretation_data.content
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await interp_table.update(interpretation_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update general interpretation")
        
        return StandardResponse(
            success=True,
            message=f"General interpretation {interpretation_id} updated successfully",
            data={"interpretation_id": interpretation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating general interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update general interpretation: {str(e)}")


@router.delete("/{interpretation_id}", response_model=StandardResponse)
async def delete_general_interpretation(
    interpretation_id: int = Path(..., ge=1, description="ID interpretacji do usunięcia")
):
    """
    Usuwa interpretację generalną LLM z bazy danych.
    
    Args:
        interpretation_id: ID interpretacji do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        interp_table = db.get_factory().get_general_interpretation_table()
        
        # Sprawdź czy interpretacja istnieje
        existing = await interp_table.get_by_id(interpretation_id)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"General interpretation with ID {interpretation_id} not found"
            )
        
        # Usuń interpretację
        success = await interp_table.delete(interpretation_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete general interpretation")
        
        return StandardResponse(
            success=True,
            message=f"General interpretation (ID: {interpretation_id}) deleted successfully",
            data={"interpretation_id": interpretation_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting general interpretation {interpretation_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete general interpretation: {str(e)}")

