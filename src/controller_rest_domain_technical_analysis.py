"""
REST API Controller dla domeny technical analysis (analiza techniczna - wzorce harmoniczne).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania analizami technicznymi wzorców harmonicznych (CRUD)
- Filtrowania analiz po asset, interval, timestamp
- Wyszukiwania po punktach czasowych (X, A, B, C, D)
- Pobierania kompletnych i niekompletnych wzorców
- Pobierania analiz z obrazami wykresów
- Statystyk analiz technicznych

UWAGA: Ten kontroler obsługuje TYLKO analizę techniczną wzorców harmonicznych.
LLM interpretacje będą w osobnej domenie później.

Bazuje na funkcjonalności z technical_analysis_harmonic_patterns_table.py

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, Path, Body
from pydantic import BaseModel, Field

# Import Database
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL

# Import Celery Task
from .celery_tasks.analysis_tasks import sync_technical_analysis_task

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/analysis/technical"
TAGS = ["Technical Analysis"]

# Modele Pydantic dla request/response


class TechnicalAnalysisResponse(BaseModel):
    """Odpowiedź z informacją o analizie technicznej."""
    id: int
    asset_id: int
    asset: Optional[str] = None
    quote: Optional[str] = None
    interval: Optional[str] = None
    x_point_timestamp: Optional[int] = None
    a_point_timestamp: Optional[int] = None
    b_point_timestamp: Optional[int] = None
    c_point_timestamp: Optional[int] = None
    d_point_timestamp: Optional[int] = None
    ta_object_json: Dict[str, Any]


class TechnicalAnalysisWithImagesResponse(BaseModel):
    """Odpowiedź z analizą techniczną i obrazami wykresów."""
    id: int
    asset_id: int
    asset: Optional[str] = None
    quote: Optional[str] = None
    interval: Optional[str] = None
    x_point_timestamp: Optional[int] = None
    a_point_timestamp: Optional[int] = None
    b_point_timestamp: Optional[int] = None
    c_point_timestamp: Optional[int] = None
    d_point_timestamp: Optional[int] = None
    ta_object_json: Dict[str, Any]
    chart_images: List[Dict[str, Any]] = []


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class TechnicalAnalysisListResponse(BaseModel):
    """Lista analiz technicznych z informacją o paginacji."""
    analyses: List[TechnicalAnalysisResponse]
    pagination: PaginationInfo


class TechnicalAnalysisWithImagesListResponse(BaseModel):
    """Lista analiz technicznych z obrazami z informacją o paginacji."""
    analyses: List[TechnicalAnalysisWithImagesResponse]
    pagination: PaginationInfo


class TechnicalAnalysisStatsResponse(BaseModel):
    """Statystyki analiz technicznych."""
    total_analyses: int
    analyses_by_asset: Optional[Dict[str, int]] = None
    complete_patterns: Optional[int] = None
    incomplete_patterns: Optional[int] = None


class PatternExistsResponse(BaseModel):
    """Odpowiedź sprawdzająca istnienie wzorca."""
    exists: bool
    pattern_id: Optional[int] = None


class SyncTechnicalAnalysisRequest(BaseModel):
    """Request do uruchomienia synchronizacji analiz technicznych."""
    limit: int = Field(default=50, ge=1, le=1000, description="Limit rekordów do przetworzenia")
    offset: int = Field(default=0, ge=0, description="Offset od którego zacząć przetwarzanie")
    test_mode: bool = Field(default=False, description="Tryb testowy (bez zapisu do bazy)")
    custom_dependencies: Optional[List[str]] = Field(
        default=None, 
        description="Lista niestandardowych zależności Celery (domyślnie: sync_tasks.sync_exchanges)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "limit": 50,
                "offset": 0,
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
async def technical_analysis_info():
    """Informacje o dostępnych endpointach analizy technicznej."""
    return {
        "message": "Technical Analysis REST API",
        "version": "1.0.0",
        "description": "API for technical analysis of harmonic patterns (NOT LLM interpretations)",
        "available_endpoints": {
            "crud": {
                "list": "GET /analysis/technical/list - Lista wszystkich analiz",
                "get": "GET /analysis/technical/{id} - Szczegóły analizy"
            },
            "filtering": {
                "by_asset": "GET /analysis/technical/asset/{asset_id} - Analizy dla assetu",
                "by_asset_interval": "GET /analysis/technical/asset/{asset_id}/interval/{interval} - Analizy dla assetu i interwału",
                "latest_by_asset": "GET /analysis/technical/asset/{asset_id}/latest - Najnowsza analiza dla assetu",
                "by_timestamp_range": "GET /analysis/technical/timestamp/range - Analizy z zakresu czasowego (+ opcjonalne asset_id, interval)",
                "by_timestamp_range_asset": "GET /analysis/technical/timestamp/range/asset/{asset_id} - Analizy z zakresu dla assetu",
                "by_timestamp_range_asset_interval": "GET /analysis/technical/timestamp/range/asset/{asset_id}/interval/{interval} - Analizy z zakresu dla assetu i interwału",
                "complete_patterns": "GET /analysis/technical/patterns/complete/{asset_id} - Kompletne wzorce",
                "incomplete_patterns": "GET /analysis/technical/patterns/incomplete/{asset_id} - Niekompletne wzorce"
            },
            "points": {
                "by_point": "GET /analysis/technical/point/{point_type}/{timestamp} - Analizy po punkcie",
                "by_point_range": "GET /analysis/technical/point/{point_type}/range - Analizy z zakresu punktu",
                "check_exists": "POST /analysis/technical/check-exists - Sprawdź czy wzorzec istnieje",
                "by_points": "POST /analysis/technical/find-by-points - Znajdź wzorzec po punktach"
            },
            "images": {
                "with_images": "GET /analysis/technical/{id}/images - Analiza z obrazami",
                "all_with_images": "GET /analysis/technical/images - Wszystkie analizy z obrazami"
            },
            "search": {
                "by_json": "GET /analysis/technical/search/json/{pattern} - Wyszukiwanie w JSON"
            },
            "stats": {
                "count": "GET /analysis/technical/count - Liczba wszystkich analiz",
                "count_by_asset": "GET /analysis/technical/count/asset/{asset_id} - Liczba analiz dla assetu",
                "stats": "GET /analysis/technical/stats - Statystyki analiz"
            },
            "sync": {
                "trigger": "POST /analysis/technical/sync - Uruchom synchronizację analiz technicznych"
            }
        }
    }


# ===================
# SYNC OPERATIONS
# ===================

@router.post("/sync", response_model=SyncTaskResponse)
async def trigger_sync_technical_analysis(
    request: SyncTechnicalAnalysisRequest = Body(
        default=SyncTechnicalAnalysisRequest(),
        description="Parametry synchronizacji analiz technicznych"
    )
):
    """
    Uruchamia zadanie Celery do synchronizacji analiz technicznych.
    
    Parametry:
        - **limit**: Maksymalna liczba rekordów do przetworzenia (1-1000, domyślnie 50)
        - **offset**: Offset od którego zacząć przetwarzanie (domyślnie 0)
        - **test_mode**: Tryb testowy bez zapisu do bazy (domyślnie False)
        - **custom_dependencies**: Lista niestandardowych zależności Celery 
          (domyślnie czeka na sync_tasks.sync_exchanges)
    
    Returns:
        SyncTaskResponse: Informacja o uruchomionym zadaniu z task_id do śledzenia statusu
    """
    try:
        # Uruchom zadanie Celery
        task = sync_technical_analysis_task.delay(
            limit=request.limit,
            offset=request.offset,
            test_mode=request.test_mode,
            custom_dependencies=request.custom_dependencies
        )
        
        logger.info(f"Started sync_technical_analysis task (ID: {task.id})")
        
        return SyncTaskResponse(
            success=True,
            message=f"Synchronizacja analiz technicznych rozpoczęta (Task ID: {task.id})",
            task_id=task.id,
            status_endpoint=f"/sync/status/{task.id}",
            details={
                "limit": request.limit,
                "offset": request.offset,
                "test_mode": request.test_mode,
                "custom_dependencies": request.custom_dependencies
            }
        )
        
    except Exception as e:
        logger.error(f"Error starting sync_technical_analysis task: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to start technical analysis sync: {str(e)}"
        )


# ===================
# CRUD OPERATIONS
# ===================

# UWAGA: Specyficzne ścieżki MUSZĄ być przed parametryzowaną /{analysis_id}

@router.get("/list", response_model=TechnicalAnalysisListResponse)
async def list_technical_analyses(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich analiz technicznych z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz technicznych
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing technical analyses: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list technical analyses: {str(e)}")


# ===================
# FILTERING - PRZED /{analysis_id}
# ===================

@router.get("/asset/{asset_id}", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz dla assetu
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_by_asset_id(asset_id=asset_id, limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analyses for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


@router.get("/asset/{asset_id}/interval/{interval}", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_asset_and_interval(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    interval: str = Path(..., description="Interwał czasowy (np. 1h, 4h, 1d)"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne dla assetu i interwału.
    
    Args:
        asset_id: ID assetu
        interval: Interwał czasowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_by_asset_id_and_interval(
            asset_id=asset_id,
            interval=interval,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analyses for asset {asset_id} and interval {interval}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


@router.get("/asset/{asset_id}/latest", response_model=TechnicalAnalysisResponse)
async def get_latest_technical_analysis_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Pobiera najnowszą analizę techniczną dla assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        TechnicalAnalysisResponse: Najnowsza analiza
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analysis = await ta_table.get_latest_by_asset_id(asset_id)
        
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"No technical analysis found for asset {asset_id}"
            )
        
        return TechnicalAnalysisResponse(
            id=analysis['id'],
            asset_id=analysis['asset_id'],
            asset=analysis.get('asset'),
            quote=analysis.get('quote'),
            interval=analysis.get('interval'),
            x_point_timestamp=analysis.get('x_point_timestamp'),
            a_point_timestamp=analysis.get('a_point_timestamp'),
            b_point_timestamp=analysis.get('b_point_timestamp'),
            c_point_timestamp=analysis.get('c_point_timestamp'),
            d_point_timestamp=analysis.get('d_point_timestamp'),
            ta_object_json=analysis['ta_object_json']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting latest technical analysis for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest analysis: {str(e)}")


@router.get("/timestamp/range", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_timestamp_range(
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    asset_id: Optional[int] = Query(None, ge=1, description="Opcjonalny filtr po asset_id"),
    interval: Optional[str] = Query(None, description="Opcjonalny filtr po interwale"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne z zakresu czasowego (używa x_point_timestamp).
    
    Args:
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        asset_id: Opcjonalny filtr po asset_id
        interval: Opcjonalny filtr po interwale
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz z zakresu
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        # Wybierz odpowiednią metodę w zależności od parametrów
        if asset_id and interval:
            analyses = await ta_table.get_by_timestamp_range_and_asset_id_and_interval(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                asset_id=asset_id,
                interval=interval,
                limit=limit + 1,
                offset=offset
            )
        elif asset_id:
            analyses = await ta_table.get_by_timestamp_range_and_asset_id(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                asset_id=asset_id,
                limit=limit + 1,
                offset=offset
            )
        else:
            analyses = await ta_table.get_by_timestamp_range(
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                limit=limit + 1,
                offset=offset
            )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analyses by timestamp range: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


@router.get("/timestamp/range/asset/{asset_id}", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_timestamp_range_and_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne z zakresu czasowego dla konkretnego assetu.
    
    Dedykowany endpoint dla wygodnego filtrowania po zakresie czasowym i asset.
    
    Args:
        asset_id: ID assetu
        start_timestamp: Timestamp początkowy (x_point_timestamp)
        end_timestamp: Timestamp końcowy (x_point_timestamp)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz z zakresu dla assetu
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_by_timestamp_range_and_asset_id(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analyses by timestamp range and asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


@router.get("/timestamp/range/asset/{asset_id}/interval/{interval}", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_timestamp_range_asset_and_interval(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    interval: str = Path(..., description="Interwał czasowy (np. 1h, 4h, 1d)"),
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne z zakresu czasowego dla assetu i interwału.
    
    Dedykowany endpoint dla wygodnego filtrowania po zakresie czasowym, asset i interwale.
    Rozszerzona wersja asset/{asset_id}/interval/{interval} z filtrowaniem po czasie.
    
    Args:
        asset_id: ID assetu
        interval: Interwał czasowy
        start_timestamp: Timestamp początkowy (x_point_timestamp)
        end_timestamp: Timestamp końcowy (x_point_timestamp)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz z zakresu dla assetu i interwału
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_by_timestamp_range_and_asset_id_and_interval(
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            asset_id=asset_id,
            interval=interval,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analyses by timestamp range, asset {asset_id} and interval {interval}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


@router.get("/patterns/complete/{asset_id}", response_model=TechnicalAnalysisListResponse)
async def get_complete_patterns(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera kompletne wzorce harmoniczne (wszystkie punkty X, A, B, C, D wypełnione).
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista kompletnych wzorców
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_complete_patterns(
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting complete patterns for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get complete patterns: {str(e)}")


@router.get("/patterns/incomplete/{asset_id}", response_model=TechnicalAnalysisListResponse)
async def get_incomplete_patterns(
    asset_id: int = Path(..., ge=1, description="ID assetu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera niekompletne wzorce harmoniczne (przynajmniej jeden punkt jest NULL).
    
    Args:
        asset_id: ID assetu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista niekompletnych wzorców
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_incomplete_patterns(
            asset_id=asset_id,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting incomplete patterns for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get incomplete patterns: {str(e)}")


# ===================
# POINT OPERATIONS - PRZED /{analysis_id}
# ===================

@router.get("/point/{point_type}/{timestamp}", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_point(
    point_type: str = Path(..., pattern="^(x|a|b|c|d)$", description="Typ punktu: x, a, b, c, d"),
    timestamp: int = Path(..., description="Timestamp punktu"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne według konkretnego punktu czasowego.
    
    Args:
        point_type: Typ punktu (x, a, b, c, d)
        timestamp: Timestamp punktu
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_by_point_timestamp(
            point_type=point_type,
            timestamp=timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting technical analyses by point {point_type}/{timestamp}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


@router.get("/point/{point_type}/range", response_model=TechnicalAnalysisListResponse)
async def get_technical_analyses_by_point_range(
    point_type: str = Path(..., pattern="^(x|a|b|c|d)$", description="Typ punktu: x, a, b, c, d"),
    start_timestamp: int = Query(..., description="Timestamp początkowy"),
    end_timestamp: int = Query(..., description="Timestamp końcowy"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera analizy techniczne według zakresu czasowego konkretnego punktu.
    
    Args:
        point_type: Typ punktu (x, a, b, c, d)
        start_timestamp: Timestamp początkowy
        end_timestamp: Timestamp końcowy
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_by_point_timestamp_range(
            point_type=point_type,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting technical analyses by point range {point_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analyses: {str(e)}")


class CheckPatternExistsRequest(BaseModel):
    """Request do sprawdzania istnienia wzorca."""
    asset_id: int = Field(..., ge=1)
    x_point_timestamp: int
    a_point_timestamp: int
    b_point_timestamp: int
    c_point_timestamp: int
    d_point_timestamp: int


@router.post("/check-exists", response_model=PatternExistsResponse)
async def check_pattern_exists(
    pattern_data: CheckPatternExistsRequest = Body(..., description="Dane wzorca do sprawdzenia")
):
    """
    Sprawdza czy wzorzec o podanych timestampach już istnieje dla danego assetu.
    
    Args:
        pattern_data: Dane wzorca (asset_id i timestampy punktów)
        
    Returns:
        PatternExistsResponse: Informacja czy wzorzec istnieje
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        exists = await ta_table.check_pattern_exists(
            asset_id=pattern_data.asset_id,
            x_point_timestamp=pattern_data.x_point_timestamp,
            a_point_timestamp=pattern_data.a_point_timestamp,
            b_point_timestamp=pattern_data.b_point_timestamp,
            c_point_timestamp=pattern_data.c_point_timestamp,
            d_point_timestamp=pattern_data.d_point_timestamp
        )
        
        pattern_id = None
        if exists:
            # Pobierz ID wzorca
            pattern = await ta_table.get_by_point_timestamps(
                asset_id=pattern_data.asset_id,
                x_point_timestamp=pattern_data.x_point_timestamp,
                a_point_timestamp=pattern_data.a_point_timestamp,
                b_point_timestamp=pattern_data.b_point_timestamp,
                c_point_timestamp=pattern_data.c_point_timestamp,
                d_point_timestamp=pattern_data.d_point_timestamp
            )
            if pattern:
                pattern_id = pattern['id']
        
        return PatternExistsResponse(exists=exists, pattern_id=pattern_id)
        
    except Exception as e:
        logger.error(f"Error checking pattern existence: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check pattern existence: {str(e)}")


@router.post("/find-by-points", response_model=TechnicalAnalysisResponse)
async def find_technical_analysis_by_points(
    pattern_data: CheckPatternExistsRequest = Body(..., description="Dane wzorca do wyszukania")
):
    """
    Znajduje wzorzec o podanych timestampach dla danego assetu.
    
    Args:
        pattern_data: Dane wzorca (asset_id i timestampy punktów)
        
    Returns:
        TechnicalAnalysisResponse: Znaleziony wzorzec
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        pattern = await ta_table.get_by_point_timestamps(
            asset_id=pattern_data.asset_id,
            x_point_timestamp=pattern_data.x_point_timestamp,
            a_point_timestamp=pattern_data.a_point_timestamp,
            b_point_timestamp=pattern_data.b_point_timestamp,
            c_point_timestamp=pattern_data.c_point_timestamp,
            d_point_timestamp=pattern_data.d_point_timestamp
        )
        
        if not pattern:
            raise HTTPException(
                status_code=404,
                detail="Pattern with given timestamps not found"
            )
        
        return TechnicalAnalysisResponse(
            id=pattern['id'],
            asset_id=pattern['asset_id'],
            asset=pattern.get('asset'),
            quote=pattern.get('quote'),
            interval=pattern.get('interval'),
            x_point_timestamp=pattern.get('x_point_timestamp'),
            a_point_timestamp=pattern.get('a_point_timestamp'),
            b_point_timestamp=pattern.get('b_point_timestamp'),
            c_point_timestamp=pattern.get('c_point_timestamp'),
            d_point_timestamp=pattern.get('d_point_timestamp'),
            ta_object_json=pattern['ta_object_json']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding technical analysis by points: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to find pattern: {str(e)}")


# ===================
# IMAGES - PRZED /{analysis_id}
# ===================

@router.get("/images", response_model=TechnicalAnalysisWithImagesListResponse)
async def get_all_technical_analyses_with_images(
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera wszystkie analizy techniczne wraz z powiązanymi obrazami wykresów.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisWithImagesListResponse: Lista analiz z obrazami
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.get_all_with_chart_images(limit=limit + 1, offset=offset)
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisWithImagesResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json'],
                chart_images=a.get('chart_images', [])
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisWithImagesListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analyses with images: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analyses with images: {str(e)}")


# ===================
# SEARCH - PRZED /{analysis_id}
# ===================

@router.get("/search/json/{pattern}", response_model=TechnicalAnalysisListResponse)
async def search_technical_analyses_by_json(
    pattern: str = Path(..., min_length=1, description="Wzorzec do wyszukania w JSON"),
    limit: int = Query(default=50, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Wyszukuje analizy techniczne po wzorcu w JSON (case-insensitive).
    
    Args:
        pattern: Wzorzec do wyszukania
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        TechnicalAnalysisListResponse: Lista znalezionych analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analyses = await ta_table.search_by_json_pattern(
            pattern=pattern,
            limit=limit + 1,
            offset=offset
        )
        
        has_more = len(analyses) > limit
        page_analyses = analyses[:limit]
        
        analysis_responses = [
            TechnicalAnalysisResponse(
                id=a['id'],
                asset_id=a['asset_id'],
                asset=a.get('asset'),
                quote=a.get('quote'),
                interval=a.get('interval'),
                x_point_timestamp=a.get('x_point_timestamp'),
                a_point_timestamp=a.get('a_point_timestamp'),
                b_point_timestamp=a.get('b_point_timestamp'),
                c_point_timestamp=a.get('c_point_timestamp'),
                d_point_timestamp=a.get('d_point_timestamp'),
                ta_object_json=a['ta_object_json']
            )
            for a in page_analyses
        ]
        
        return TechnicalAnalysisListResponse(
            analyses=analysis_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error searching technical analyses by JSON pattern '{pattern}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search analyses: {str(e)}")


# ===================
# COUNT & STATS - PRZED /{analysis_id}
# ===================

@router.get("/count", response_model=Dict[str, int])
async def count_technical_analyses():
    """
    Zlicza wszystkie analizy techniczne.
    
    Returns:
        Dict z liczbą analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        count = await ta_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting technical analyses: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count analyses: {str(e)}")


@router.get("/count/asset/{asset_id}", response_model=Dict[str, int])
async def count_technical_analyses_by_asset(
    asset_id: int = Path(..., ge=1, description="ID assetu")
):
    """
    Zlicza analizy techniczne dla konkretnego assetu.
    
    Args:
        asset_id: ID assetu
        
    Returns:
        Dict z liczbą analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        count = await ta_table.count_by_asset(asset_id)
        
        return {"count": count, "asset_id": asset_id}
        
    except Exception as e:
        logger.error(f"Error counting technical analyses for asset {asset_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count analyses: {str(e)}")


@router.get("/stats", response_model=TechnicalAnalysisStatsResponse)
async def get_technical_analysis_stats():
    """
    Pobiera statystyki analiz technicznych.
    
    Returns:
        TechnicalAnalysisStatsResponse: Statystyki analiz
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        total_count = await ta_table.count_all()
        
        return TechnicalAnalysisStatsResponse(
            total_analyses=total_count
        )
        
    except Exception as e:
        logger.error(f"Error getting technical analysis stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# ===================
# PARAMETRYZOWANA ŚCIEŻKA - MUSI BYĆ NA KOŃCU
# ===================

@router.get("/{analysis_id}", response_model=TechnicalAnalysisResponse)
async def get_technical_analysis(
    analysis_id: int = Path(..., ge=1, description="ID analizy technicznej")
):
    """
    Pobiera szczegóły konkretnej analizy technicznej.
    
    Args:
        analysis_id: ID analizy
        
    Returns:
        TechnicalAnalysisResponse: Szczegóły analizy
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analysis = await ta_table.get_by_id(analysis_id)
        
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"Technical analysis with ID {analysis_id} not found"
            )
        
        return TechnicalAnalysisResponse(
            id=analysis['id'],
            asset_id=analysis['asset_id'],
            asset=analysis.get('asset'),
            quote=analysis.get('quote'),
            interval=analysis.get('interval'),
            x_point_timestamp=analysis.get('x_point_timestamp'),
            a_point_timestamp=analysis.get('a_point_timestamp'),
            b_point_timestamp=analysis.get('b_point_timestamp'),
            c_point_timestamp=analysis.get('c_point_timestamp'),
            d_point_timestamp=analysis.get('d_point_timestamp'),
            ta_object_json=analysis['ta_object_json']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technical analysis {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get technical analysis: {str(e)}")


@router.get("/{analysis_id}/images", response_model=TechnicalAnalysisWithImagesResponse)
async def get_technical_analysis_with_images(
    analysis_id: int = Path(..., ge=1, description="ID analizy technicznej")
):
    """
    Pobiera analizę techniczną wraz z powiązanymi obrazami wykresów.
    
    Args:
        analysis_id: ID analizy
        
    Returns:
        TechnicalAnalysisWithImagesResponse: Analiza z obrazami
    """
    try:
        db = await get_db()
        ta_table = db.get_factory().get_technical_analysis_harmonic_patterns_table()
        
        analysis = await ta_table.get_with_chart_images(analysis_id)
        
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"Technical analysis with ID {analysis_id} not found"
            )
        
        return TechnicalAnalysisWithImagesResponse(
            id=analysis['id'],
            asset_id=analysis['asset_id'],
            asset=analysis.get('asset'),
            quote=analysis.get('quote'),
            interval=analysis.get('interval'),
            x_point_timestamp=analysis.get('x_point_timestamp'),
            a_point_timestamp=analysis.get('a_point_timestamp'),
            b_point_timestamp=analysis.get('b_point_timestamp'),
            c_point_timestamp=analysis.get('c_point_timestamp'),
            d_point_timestamp=analysis.get('d_point_timestamp'),
            ta_object_json=analysis['ta_object_json'],
            chart_images=analysis.get('chart_images', [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technical analysis with images {analysis_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analysis with images: {str(e)}")