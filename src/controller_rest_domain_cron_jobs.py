"""
REST API Controller dla domeny cron jobs (zadania cron do synchronizacji systemu).

Ten kontroler implementuje endpointy REST dla:
- Zarządzania zadaniami cron (CRUD)
- Włączania/wyłączania zadań cron
- Filtrowania zadań po procesach, statusie (enabled/disabled)
- Pobierania listy dostępnych procesów systemowych
- Statystyk zadań cron

UWAGA: SystemSyncJob (procesy) są stałe i dodawane przy inicjalizacji bazy.
CronSystemSyncJob to zadania cron przypisane do konkretnych procesów.

Bazuje na funkcjonalności z cron_system_sync_job_table.py i system_sync_job_table.py

Autor: AI Assistant
"""

import logging
import asyncio
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
PREFIX = "/system/cron"
TAGS = ["Cron Jobs"]

# Modele Pydantic dla request/response


class CronJobResponse(BaseModel):
    """Odpowiedź z informacją o zadaniu cron."""
    id: int
    name: str
    system_sync_job_id: int
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    week: Optional[int] = None
    day_of_week: Optional[str] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    second: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    timezone: str
    jitter: int
    enabled: bool
    process_name: Optional[str] = None
    created_at: Optional[datetime] = None


class CronJobCreate(BaseModel):
    """Model do tworzenia nowego zadania cron."""
    name: str = Field(..., min_length=1, description="Nazwa zadania cron")
    system_sync_job_id: int = Field(..., ge=1, description="ID procesu synchronizacji")
    year: Optional[int] = Field(None, description="Rok wykonania (4-cyfrowy)")
    month: Optional[int] = Field(None, ge=1, le=12, description="Miesiąc (1-12)")
    day: Optional[int] = Field(None, ge=1, le=31, description="Dzień (1-31)")
    week: Optional[int] = Field(None, description="Numer tygodnia")
    day_of_week: Optional[str] = Field(None, description="Dzień tygodnia (0-6 lub mon-sun)")
    hour: Optional[int] = Field(None, ge=0, le=23, description="Godzina (0-23)")
    minute: Optional[int] = Field(None, ge=0, le=59, description="Minuta (0-59)")
    second: Optional[int] = Field(None, ge=0, le=59, description="Sekunda (0-59)")
    start_date: Optional[str] = Field(None, description="Data rozpoczęcia (ISO 8601)")
    end_date: Optional[str] = Field(None, description="Data zakończenia (ISO 8601)")
    timezone: str = Field(default="UTC", description="Strefa czasowa")
    jitter: int = Field(default=0, ge=0, description="Jitter w sekundach")
    enabled: bool = Field(default=True, description="Czy zadanie jest włączone")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Daily Exchange Sync",
                "system_sync_job_id": 1,
                "hour": 2,
                "minute": 0,
                "timezone": "UTC",
                "enabled": True
            }
        }


class CronJobUpdate(BaseModel):
    """Model do aktualizacji zadania cron."""
    name: Optional[str] = Field(None, min_length=1, description="Nazwa zadania cron")
    system_sync_job_id: Optional[int] = Field(None, ge=1, description="ID procesu synchronizacji")
    year: Optional[int] = Field(None, description="Rok wykonania")
    month: Optional[int] = Field(None, ge=1, le=12, description="Miesiąc")
    day: Optional[int] = Field(None, ge=1, le=31, description="Dzień")
    week: Optional[int] = Field(None, description="Numer tygodnia")
    day_of_week: Optional[str] = Field(None, description="Dzień tygodnia")
    hour: Optional[int] = Field(None, ge=0, le=23, description="Godzina")
    minute: Optional[int] = Field(None, ge=0, le=59, description="Minuta")
    second: Optional[int] = Field(None, ge=0, le=59, description="Sekunda")
    start_date: Optional[str] = Field(None, description="Data rozpoczęcia")
    end_date: Optional[str] = Field(None, description="Data zakończenia")
    timezone: Optional[str] = Field(None, description="Strefa czasowa")
    jitter: Optional[int] = Field(None, ge=0, description="Jitter w sekundach")
    enabled: Optional[bool] = Field(None, description="Czy zadanie jest włączone")


class SystemSyncJobResponse(BaseModel):
    """Odpowiedź z informacją o procesie synchronizacji."""
    id: int
    process: str
    created_at: Optional[datetime] = None


class PaginationInfo(BaseModel):
    """Informacje o paginacji."""
    total: Optional[int] = None
    limit: int
    offset: int
    has_more: bool


class CronJobListResponse(BaseModel):
    """Lista zadań cron z informacją o paginacji."""
    cron_jobs: List[CronJobResponse]
    pagination: PaginationInfo


class SystemSyncJobListResponse(BaseModel):
    """Lista procesów synchronizacji z informacją o paginacji."""
    processes: List[SystemSyncJobResponse]
    pagination: PaginationInfo


class CronJobStatsResponse(BaseModel):
    """Statystyki zadań cron."""
    total_jobs: int
    enabled_jobs: int
    disabled_jobs: int
    jobs_by_process: Optional[Dict[str, int]] = None


class StandardResponse(BaseModel):
    """Standardowa odpowiedź."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# Singleton dla DatabasePostgreSQL z blokadą dla bezpieczeństwa wątkowego
db_instance: Optional[DatabasePostgreSQL] = None
db_lock: asyncio.Lock = asyncio.Lock()


async def get_db() -> DatabasePostgreSQL:
    """
    Dependency do pobierania instancji DatabasePostgreSQL.
    Używa blokady aby uniknąć race condition podczas inicjalizacji.
    
    Returns:
        DatabasePostgreSQL: Instancja bazy danych PostgreSQL
    """
    global db_instance
    
    if db_instance is not None:
        return db_instance
    
    async with db_lock:
        # Double-check po uzyskaniu blokady
        if db_instance is None:
            db_facade = DatabaseFacade()
            new_instance = db_facade.get_database_postgresql()
            await new_instance.init_db()
            db_instance = new_instance
    
    return db_instance


# ===================
# ENDPOINTY GŁÓWNE
# ===================

@router.get("", response_model=Dict[str, Any])
async def cron_jobs_info():
    """Informacje o dostępnych endpointach zarządzania zadaniami cron."""
    return {
        "message": "Cron Jobs REST API",
        "version": "1.0.0",
        "description": "API for managing system synchronization cron jobs",
        "available_endpoints": {
            "cron_jobs": {
                "list": "GET /system/cron/jobs - Lista wszystkich zadań cron",
                "list_enabled": "GET /system/cron/jobs/enabled - Lista włączonych zadań",
                "get": "GET /system/cron/jobs/{id} - Szczegóły zadania cron",
                "get_by_name": "GET /system/cron/jobs/name/{name} - Zadanie po nazwie",
                "create": "POST /system/cron/jobs - Tworzenie nowego zadania cron",
                "update": "PUT /system/cron/jobs/{id} - Aktualizacja zadania cron",
                "delete": "DELETE /system/cron/jobs/{id} - Usunięcie zadania cron",
                "enable": "POST /system/cron/jobs/{id}/enable - Włączenie zadania",
                "disable": "POST /system/cron/jobs/{id}/disable - Wyłączenie zadania",
                "by_process": "GET /system/cron/jobs/process/{process_id} - Zadania dla procesu"
            },
            "processes": {
                "list": "GET /system/cron/processes - Lista dostępnych procesów",
                "get": "GET /system/cron/processes/{id} - Szczegóły procesu"
            },
            "stats": {
                "count": "GET /system/cron/stats/count - Liczba wszystkich zadań",
                "count_enabled": "GET /system/cron/stats/count-enabled - Liczba włączonych zadań",
                "stats": "GET /system/cron/stats - Statystyki zadań cron"
            }
        }
    }


# ===================
# CRON JOBS - CRUD
# ===================

@router.get("/jobs", response_model=CronJobListResponse)
async def list_cron_jobs(
    limit: int = Query(default=100, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich zadań cron z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        CronJobListResponse: Lista zadań cron
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        cron_jobs = await cron_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(cron_jobs) > limit
        page_cron_jobs = cron_jobs[:limit]
        
        cron_job_responses = [
            CronJobResponse(
                id=job['id'],
                name=job['name'],
                system_sync_job_id=job['system_sync_job_id'],
                year=job.get('year'),
                month=job.get('month'),
                day=job.get('day'),
                week=job.get('week'),
                day_of_week=job.get('day_of_week'),
                hour=job.get('hour'),
                minute=job.get('minute'),
                second=job.get('second'),
                start_date=job.get('start_date'),
                end_date=job.get('end_date'),
                timezone=job.get('timezone', 'UTC'),
                jitter=job.get('jitter', 0),
                enabled=job.get('enabled', True),
                process_name=job.get('process_name'),
                created_at=job.get('created_at')
            )
            for job in page_cron_jobs
        ]
        
        return CronJobListResponse(
            cron_jobs=cron_job_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing cron jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list cron jobs: {str(e)}")


@router.get("/jobs/enabled", response_model=CronJobListResponse)
async def list_enabled_cron_jobs(
    limit: int = Query(default=100, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę włączonych zadań cron z paginacją.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        CronJobListResponse: Lista włączonych zadań cron
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        cron_jobs = await cron_table.get_all_enabled(limit=limit + 1, offset=offset)
        
        has_more = len(cron_jobs) > limit
        page_cron_jobs = cron_jobs[:limit]
        
        cron_job_responses = [
            CronJobResponse(
                id=job['id'],
                name=job['name'],
                system_sync_job_id=job['system_sync_job_id'],
                year=job.get('year'),
                month=job.get('month'),
                day=job.get('day'),
                week=job.get('week'),
                day_of_week=job.get('day_of_week'),
                hour=job.get('hour'),
                minute=job.get('minute'),
                second=job.get('second'),
                start_date=job.get('start_date'),
                end_date=job.get('end_date'),
                timezone=job.get('timezone', 'UTC'),
                jitter=job.get('jitter', 0),
                enabled=job.get('enabled', True),
                process_name=job.get('process_name'),
                created_at=job.get('created_at')
            )
            for job in page_cron_jobs
        ]
        
        return CronJobListResponse(
            cron_jobs=cron_job_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing enabled cron jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list enabled cron jobs: {str(e)}")


@router.get("/jobs/{job_id}", response_model=CronJobResponse)
async def get_cron_job(
    job_id: int = Path(..., ge=1, description="ID zadania cron")
):
    """
    Pobiera szczegóły konkretnego zadania cron.
    
    Args:
        job_id: ID zadania cron
        
    Returns:
        CronJobResponse: Szczegóły zadania cron
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        job = await cron_table.get_by_id(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Cron job with ID {job_id} not found")
        
        return CronJobResponse(
            id=job['id'],
            name=job['name'],
            system_sync_job_id=job['system_sync_job_id'],
            year=job.get('year'),
            month=job.get('month'),
            day=job.get('day'),
            week=job.get('week'),
            day_of_week=job.get('day_of_week'),
            hour=job.get('hour'),
            minute=job.get('minute'),
            second=job.get('second'),
            start_date=job.get('start_date'),
            end_date=job.get('end_date'),
            timezone=job.get('timezone', 'UTC'),
            jitter=job.get('jitter', 0),
            enabled=job.get('enabled', True),
            process_name=job.get('process_name'),
            created_at=job.get('created_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cron job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cron job: {str(e)}")


@router.get("/jobs/name/{name}", response_model=CronJobResponse)
async def get_cron_job_by_name(
    name: str = Path(..., description="Nazwa zadania cron")
):
    """
    Pobiera zadanie cron po nazwie.
    
    Args:
        name: Nazwa zadania cron
        
    Returns:
        CronJobResponse: Szczegóły zadania cron
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        job = await cron_table.get_by_name(name)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Cron job with name '{name}' not found")
        
        return CronJobResponse(
            id=job['id'],
            name=job['name'],
            system_sync_job_id=job['system_sync_job_id'],
            year=job.get('year'),
            month=job.get('month'),
            day=job.get('day'),
            week=job.get('week'),
            day_of_week=job.get('day_of_week'),
            hour=job.get('hour'),
            minute=job.get('minute'),
            second=job.get('second'),
            start_date=job.get('start_date'),
            end_date=job.get('end_date'),
            timezone=job.get('timezone', 'UTC'),
            jitter=job.get('jitter', 0),
            enabled=job.get('enabled', True),
            process_name=job.get('process_name'),
            created_at=job.get('created_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cron job by name '{name}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cron job: {str(e)}")


@router.post("/jobs", response_model=StandardResponse, status_code=201)
async def create_cron_job(
    job_data: CronJobCreate = Body(..., description="Dane nowego zadania cron")
):
    """
    Tworzy nowe zadanie cron.
    
    Args:
        job_data: Dane zadania cron do utworzenia
        
    Returns:
        StandardResponse: Odpowiedź z ID utworzonego zadania
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        # Sprawdź czy proces o podanym ID istnieje
        process_table = db.get_factory().get_system_sync_job_table()
        process = await process_table.get_by_id(job_data.system_sync_job_id)
        if not process:
            raise HTTPException(
                status_code=404,
                detail=f"System sync job with ID {job_data.system_sync_job_id} not found"
            )
        
        # Sprawdź czy zadanie o tej nazwie już istnieje
        existing = await cron_table.get_by_name(job_data.name)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Cron job with name '{job_data.name}' already exists with ID {existing['id']}"
            )
        
        # Utwórz zadanie cron
        job_id = await cron_table.create(
            name=job_data.name,
            system_sync_job_id=job_data.system_sync_job_id,
            year=job_data.year,
            month=job_data.month,
            day=job_data.day,
            week=job_data.week,
            day_of_week=job_data.day_of_week,
            hour=job_data.hour,
            minute=job_data.minute,
            second=job_data.second,
            start_date=job_data.start_date,
            end_date=job_data.end_date,
            timezone=job_data.timezone,
            jitter=job_data.jitter,
            enabled=job_data.enabled
        )
        
        if not job_id:
            raise HTTPException(status_code=500, detail="Failed to create cron job")
        
        return StandardResponse(
            success=True,
            message=f"Cron job '{job_data.name}' created successfully",
            data={"job_id": job_id, "process": process['process']}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating cron job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create cron job: {str(e)}")


@router.put("/jobs/{job_id}", response_model=StandardResponse)
async def update_cron_job(
    job_id: int = Path(..., ge=1, description="ID zadania do aktualizacji"),
    job_data: CronJobUpdate = Body(..., description="Dane do aktualizacji")
):
    """
    Aktualizuje istniejące zadanie cron.
    
    Args:
        job_id: ID zadania do aktualizacji
        job_data: Nowe dane zadania cron
        
    Returns:
        StandardResponse: Potwierdzenie aktualizacji
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        # Sprawdź czy zadanie istnieje
        existing = await cron_table.get_by_id(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Cron job with ID {job_id} not found")
        
        # Przygotuj dane do aktualizacji
        update_data = {}
        if job_data.name is not None:
            # Sprawdź czy nowa nazwa nie jest zajęta przez inny cron job
            name_check = await cron_table.get_by_name(job_data.name)
            if name_check and name_check['id'] != job_id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Cron job with name '{job_data.name}' already exists"
                )
            update_data['name'] = job_data.name
            
        if job_data.system_sync_job_id is not None:
            # Sprawdź czy proces istnieje
            process_table = db.get_factory().get_system_sync_job_table()
            process = await process_table.get_by_id(job_data.system_sync_job_id)
            if not process:
                raise HTTPException(
                    status_code=404,
                    detail=f"System sync job with ID {job_data.system_sync_job_id} not found"
                )
            update_data['system_sync_job_id'] = job_data.system_sync_job_id
            
        # Dodaj pozostałe pola jeśli są podane
        for field in ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 
                      'minute', 'second', 'start_date', 'end_date', 'timezone', 
                      'jitter', 'enabled']:
            value = getattr(job_data, field, None)
            if value is not None:
                update_data[field] = value
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No data provided for update")
        
        # Wykonaj aktualizację
        success = await cron_table.update(job_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update cron job")
        
        return StandardResponse(
            success=True,
            message=f"Cron job (ID: {job_id}) updated successfully",
            data={"job_id": job_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating cron job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update cron job: {str(e)}")


@router.delete("/jobs/{job_id}", response_model=StandardResponse)
async def delete_cron_job(
    job_id: int = Path(..., ge=1, description="ID zadania do usunięcia")
):
    """
    Usuwa zadanie cron z bazy danych.
    
    Args:
        job_id: ID zadania do usunięcia
        
    Returns:
        StandardResponse: Potwierdzenie usunięcia
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        # Sprawdź czy zadanie istnieje
        existing = await cron_table.get_by_id(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Cron job with ID {job_id} not found")
        
        # Usuń zadanie
        success = await cron_table.delete(job_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete cron job")
        
        return StandardResponse(
            success=True,
            message=f"Cron job '{existing['name']}' (ID: {job_id}) deleted successfully",
            data={"job_id": job_id, "name": existing['name']}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting cron job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete cron job: {str(e)}")


# ===================
# CRON JOBS - OPERATIONS
# ===================

@router.post("/jobs/{job_id}/enable", response_model=StandardResponse)
async def enable_cron_job(
    job_id: int = Path(..., ge=1, description="ID zadania do włączenia")
):
    """
    Włącza zadanie cron.
    
    Args:
        job_id: ID zadania do włączenia
        
    Returns:
        StandardResponse: Potwierdzenie włączenia
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        # Sprawdź czy zadanie istnieje
        existing = await cron_table.get_by_id(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Cron job with ID {job_id} not found")
        
        # Sprawdź czy już jest włączone
        if existing.get('enabled', False):
            return StandardResponse(
                success=True,
                message=f"Cron job '{existing['name']}' is already enabled",
                data={"job_id": job_id, "enabled": True}
            )
        
        # Włącz zadanie
        success = await cron_table.enable_job(job_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to enable cron job")
        
        return StandardResponse(
            success=True,
            message=f"Cron job '{existing['name']}' (ID: {job_id}) enabled successfully",
            data={"job_id": job_id, "enabled": True}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling cron job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable cron job: {str(e)}")


@router.post("/jobs/{job_id}/disable", response_model=StandardResponse)
async def disable_cron_job(
    job_id: int = Path(..., ge=1, description="ID zadania do wyłączenia")
):
    """
    Wyłącza zadanie cron.
    
    Args:
        job_id: ID zadania do wyłączenia
        
    Returns:
        StandardResponse: Potwierdzenie wyłączenia
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        # Sprawdź czy zadanie istnieje
        existing = await cron_table.get_by_id(job_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Cron job with ID {job_id} not found")
        
        # Sprawdź czy już jest wyłączone
        if not existing.get('enabled', False):
            return StandardResponse(
                success=True,
                message=f"Cron job '{existing['name']}' is already disabled",
                data={"job_id": job_id, "enabled": False}
            )
        
        # Wyłącz zadanie
        success = await cron_table.disable_job(job_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disable cron job")
        
        return StandardResponse(
            success=True,
            message=f"Cron job '{existing['name']}' (ID: {job_id}) disabled successfully",
            data={"job_id": job_id, "enabled": False}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling cron job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable cron job: {str(e)}")


# ===================
# CRON JOBS - FILTERING
# ===================

@router.get("/jobs/process/{process_id}", response_model=CronJobListResponse)
async def get_cron_jobs_by_process(
    process_id: int = Path(..., ge=1, description="ID procesu synchronizacji"),
    limit: int = Query(default=100, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera zadania cron dla konkretnego procesu synchronizacji.
    
    Args:
        process_id: ID procesu synchronizacji (system_sync_job_id)
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        CronJobListResponse: Lista zadań cron dla procesu
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        # Sprawdź czy proces istnieje
        process_table = db.get_factory().get_system_sync_job_table()
        process = await process_table.get_by_id(process_id)
        if not process:
            raise HTTPException(
                status_code=404,
                detail=f"System sync job with ID {process_id} not found"
            )
        
        # Pobierz zadania cron dla tego procesu
        # get_by_process zwraca listę bez paginacji, więc musimy to obsłużyć ręcznie
        all_jobs = await cron_table.get_by_process(process['process'])
        
        # Zastosuj paginację
        total = len(all_jobs)
        page_jobs = all_jobs[offset:offset + limit]
        has_more = (offset + limit) < total
        
        cron_job_responses = [
            CronJobResponse(
                id=job['id'],
                name=job['name'],
                system_sync_job_id=job['system_sync_job_id'],
                year=job.get('year'),
                month=job.get('month'),
                day=job.get('day'),
                week=job.get('week'),
                day_of_week=job.get('day_of_week'),
                hour=job.get('hour'),
                minute=job.get('minute'),
                second=job.get('second'),
                start_date=job.get('start_date'),
                end_date=job.get('end_date'),
                timezone=job.get('timezone', 'UTC'),
                jitter=job.get('jitter', 0),
                enabled=job.get('enabled', True),
                process_name=job.get('process_name'),
                created_at=job.get('created_at')
            )
            for job in page_jobs
        ]
        
        return CronJobListResponse(
            cron_jobs=cron_job_responses,
            pagination=PaginationInfo(
                total=total,
                limit=limit,
                offset=offset,
                has_more=has_more
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting cron jobs for process {process_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cron jobs: {str(e)}")


# ===================
# SYSTEM SYNC JOBS (PROCESSES) - READ ONLY
# ===================

@router.get("/processes", response_model=SystemSyncJobListResponse)
async def list_system_sync_processes(
    limit: int = Query(default=100, ge=1, le=1000, description="Liczba wyników"),
    offset: int = Query(default=0, ge=0, description="Offset wyników")
):
    """
    Pobiera listę wszystkich dostępnych procesów synchronizacji.
    
    UWAGA: Procesy są stałe i tworzone przy inicjalizacji bazy danych.
    Ten endpoint służy tylko do odczytu listy dostępnych procesów.
    
    Args:
        limit: Maksymalna liczba wyników
        offset: Przesunięcie wyników
        
    Returns:
        SystemSyncJobListResponse: Lista procesów synchronizacji
    """
    try:
        db = await get_db()
        process_table = db.get_factory().get_system_sync_job_table()
        
        processes = await process_table.get_all(limit=limit + 1, offset=offset)
        
        has_more = len(processes) > limit
        page_processes = processes[:limit]
        
        process_responses = [
            SystemSyncJobResponse(
                id=proc['id'],
                process=proc['process'],
                created_at=proc.get('created_at')
            )
            for proc in page_processes
        ]
        
        return SystemSyncJobListResponse(
            processes=process_responses,
            pagination=PaginationInfo(limit=limit, offset=offset, has_more=has_more)
        )
        
    except Exception as e:
        logger.error(f"Error listing system sync processes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list processes: {str(e)}")


@router.get("/processes/{process_id}", response_model=SystemSyncJobResponse)
async def get_system_sync_process(
    process_id: int = Path(..., ge=1, description="ID procesu synchronizacji")
):
    """
    Pobiera szczegóły konkretnego procesu synchronizacji.
    
    Args:
        process_id: ID procesu
        
    Returns:
        SystemSyncJobResponse: Szczegóły procesu
    """
    try:
        db = await get_db()
        process_table = db.get_factory().get_system_sync_job_table()
        
        process = await process_table.get_by_id(process_id)
        
        if not process:
            raise HTTPException(
                status_code=404,
                detail=f"System sync job with ID {process_id} not found"
            )
        
        return SystemSyncJobResponse(
            id=process['id'],
            process=process['process'],
            created_at=process.get('created_at')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system sync process {process_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get process: {str(e)}")


# ===================
# STATISTICS
# ===================

@router.get("/stats/count", response_model=Dict[str, int])
async def count_cron_jobs():
    """
    Zlicza wszystkie zadania cron.
    
    Returns:
        Dict z liczbą zadań
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        count = await cron_table.count_all()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting cron jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count cron jobs: {str(e)}")


@router.get("/stats/count-enabled", response_model=Dict[str, int])
async def count_enabled_cron_jobs():
    """
    Zlicza włączone zadania cron.
    
    Returns:
        Dict z liczbą włączonych zadań
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        count = await cron_table.count_enabled()
        
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error counting enabled cron jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to count enabled cron jobs: {str(e)}")


@router.get("/stats", response_model=CronJobStatsResponse)
async def get_cron_job_stats():
    """
    Pobiera statystyki zadań cron.
    
    Returns:
        CronJobStatsResponse: Statystyki zadań cron
    """
    try:
        db = await get_db()
        cron_table = db.get_factory().get_cron_system_sync_job_table()
        
        total_count = await cron_table.count_all()
        enabled_count = await cron_table.count_enabled()
        disabled_count = total_count - enabled_count
        
        # Pobierz wszystkie zadania i policz według procesów
        all_jobs = await cron_table.get_all(limit=1000)
        jobs_by_process: Dict[str, int] = {}
        for job in all_jobs:
            process_name = job.get('process_name', 'Unknown')
            jobs_by_process[process_name] = jobs_by_process.get(process_name, 0) + 1
        
        return CronJobStatsResponse(
            total_jobs=total_count,
            enabled_jobs=enabled_count,
            disabled_jobs=disabled_count,
            jobs_by_process=jobs_by_process if jobs_by_process else None
        )
        
    except Exception as e:
        logger.error(f"Error getting cron job stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

