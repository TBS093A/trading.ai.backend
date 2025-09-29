"""
REST API Controller dla domeny synchronizacji systemu.

Ten kontroler implementuje endpointy REST dla:
- Pełnej synchronizacji systemu
- Synchronizacji poszczególnych komponentów (exchanges, analyses, LLM, transactions)
- Monitoringu stanu synchronizacji
- Health check komponentów

Bazuje na funkcjonalności z main_controller_sync.py

Autor: AI Assistant
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, Path
from pydantic import BaseModel, Field

# Import SyncController
from main_controller_sync import SyncController

logger = logging.getLogger(__name__)

# Konfiguracja routera
router = APIRouter()
PREFIX = "/sync"
TAGS = ["Synchronization"]

# Modele Pydantic dla request/response


class SyncResponse(BaseModel):
    """Standardowa odpowiedź synchronizacji."""
    success: bool
    message: str
    duration: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class SyncStatus(BaseModel):
    """Status operacji synchronizacji."""
    operation_id: str
    operation_type: str
    status: str  # "running", "completed", "error"
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[str] = None
    error: Optional[str] = None


class WorkflowStatus(BaseModel):
    """Status workflow synchronizacji."""
    exchanges_completed: bool
    fundamental_analysis_completed: bool
    technical_analysis_completed: bool
    llm_fundamental_completed: bool
    llm_technical_completed: bool
    llm_general_completed: bool
    transactions_wallets_pre_completed: bool
    transactions_completed: bool
    transactions_wallets_post_completed: bool


class HealthCheckResult(BaseModel):
    """Wynik health check komponentu."""
    healthy: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SystemHealth(BaseModel):
    """Ogólny stan zdrowia systemu."""
    overall_healthy: bool
    components: Dict[str, HealthCheckResult]
    timestamp: datetime = Field(default_factory=datetime.now)


class SyncParameters(BaseModel):
    """Parametry synchronizacji z limit/offset."""
    limit: int = Field(default=50, ge=1, le=1000, description="Limit rekordów do przetworzenia")
    offset: int = Field(default=0, ge=0, description="Offset od którego zacząć przetwarzanie")


# Singleton dla SyncController
sync_controller: Optional[SyncController] = None
running_operations: Dict[str, Dict[str, Any]] = {}


def get_sync_controller(test_mode: bool = False) -> SyncController:
    """
    Dependency do pobierania instancji SyncController.
    
    Args:
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        SyncController: Instancja kontrolera synchronizacji
    """
    global sync_controller
    
    if sync_controller is None:
        sync_controller = SyncController(test_mode=test_mode)
    
    return sync_controller


def generate_operation_id(operation_type: str) -> str:
    """Generuje unikalny ID operacji."""
    timestamp = int(datetime.now().timestamp())
    return f"{operation_type}_{timestamp}"


async def run_sync_operation_background(operation_id: str, operation_type: str, sync_func, *args, **kwargs):
    """
    Uruchamia operację synchronizacji w tle.
    
    Args:
        operation_id: ID operacji
        operation_type: Typ operacji
        sync_func: Funkcja synchronizacji do uruchomienia
        *args, **kwargs: Argumenty dla funkcji synchronizacji
    """
    try:
        logger.info(f"Rozpoczęcie operacji w tle: {operation_id}")
        
        # Rozpocznij operację
        running_operations[operation_id] = {
            "type": operation_type,
            "status": "running",
            "start_time": datetime.now()
        }
        
        # Uruchom operację synchronizacji
        result = await sync_func(*args, **kwargs)
        
        # Zaktualizuj status
        running_operations[operation_id]["status"] = "completed" if result else "error"
        running_operations[operation_id]["end_time"] = datetime.now()
        running_operations[operation_id]["result"] = result
        
        if not result:
            running_operations[operation_id]["error"] = "Synchronization failed"
        
        logger.info(f"Operacja {operation_id} zakończona: {'sukces' if result else 'błąd'}")
        
    except Exception as e:
        logger.error(f"Błąd w operacji {operation_id}: {e}")
        running_operations[operation_id]["status"] = "error"
        running_operations[operation_id]["end_time"] = datetime.now()
        running_operations[operation_id]["error"] = str(e)
    
    finally:
        # Usuń operację po 10 minutach
        await asyncio.sleep(600)
        running_operations.pop(operation_id, None)


# ===================
# ENDPOINTY GŁÓWNE
# ===================

@router.get("", response_model=Dict[str, Any])
async def sync_info():
    """Informacje o dostępnych endpointach synchronizacji."""
    return {
        "message": "Sync System REST API",
        "version": "1.0.0",
        "available_endpoints": {
            "full_sync": "POST /sync/all - Pełna synchronizacja systemu",
            "exchanges": "POST /sync/exchanges - Synchronizacja giełd",
            "technical_analysis": "POST /sync/analysis/technical - Synchronizacja analiz technicznych",
            "fundamental_analysis": "POST /sync/analysis/fundamental - Synchronizacja analiz fundamentalnych",
            "parallel_analysis": "POST /sync/analysis - Równoległa synchronizacja analiz (fundamentalne + techniczne)",
            "llm_technical": "POST /sync/llm/interpretation/technical - Interpretacja LLM analiz technicznych",
            "llm_fundamental": "POST /sync/llm/interpretation/fundamental - Interpretacja LLM analiz fundamentalnych",
            "llm_parallel": "POST /sync/llm/interpretation - Równoległa interpretacja LLM (fundamentalne + techniczne)",
            "llm_general": "POST /sync/llm/decision/general - Generalna decyzja LLM",
            "transactions_wallets": "POST /sync/transactions/wallets - Synchronizacja portfeli",
            "transactions": "POST /sync/transactions - Synchronizacja transakcji",
            "status": "GET /sync/status - Status operacji",
            "workflow": "GET /sync/workflow - Status workflow",
            "health": "GET /sync/health - Health check systemu"
        }
    }


@router.get("/status", response_model=List[SyncStatus])
async def get_sync_status():
    """Pobiera status wszystkich uruchomionych operacji synchronizacji."""
    statuses = []
    
    for operation_id, operation_data in running_operations.items():
        duration = None
        if operation_data.get("end_time"):
            duration = str(operation_data["end_time"] - operation_data["start_time"])
        
        statuses.append(SyncStatus(
            operation_id=operation_id,
            operation_type=operation_data["type"],
            status=operation_data["status"],
            start_time=operation_data["start_time"],
            end_time=operation_data.get("end_time"),
            duration=duration,
            error=operation_data.get("error")
        ))
    
    return statuses


@router.get("/status/{operation_id}", response_model=SyncStatus)
async def get_operation_status(operation_id: str = Path(..., description="ID operacji synchronizacji")):
    """Pobiera status konkretnej operacji synchronizacji."""
    if operation_id not in running_operations:
        raise HTTPException(status_code=404, detail="Operacja nie została znaleziona")
    
    operation_data = running_operations[operation_id]
    duration = None
    if operation_data.get("end_time"):
        duration = str(operation_data["end_time"] - operation_data["start_time"])
    
    return SyncStatus(
        operation_id=operation_id,
        operation_type=operation_data["type"],
        status=operation_data["status"],
        start_time=operation_data["start_time"],
        end_time=operation_data.get("end_time"),
        duration=duration,
        error=operation_data.get("error")
    )


@router.get("/workflow", response_model=WorkflowStatus)
async def get_workflow_status(sync_controller: SyncController = Depends(get_sync_controller)):
    """Pobiera status workflow synchronizacji."""
    return WorkflowStatus(**sync_controller.workflow_status)


# ===================
# SYNCHRONIZACJA PEŁNA
# ===================

@router.post("/all", response_model=SyncResponse)
async def sync_all(
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Uruchamia pełny workflow synchronizacji systemu."""
    operation_id = generate_operation_id("sync_all")
    
    # Uruchom w tle
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_all",
        sync_controller.run_full_sync_workflow
    )
    
    return SyncResponse(
        success=True,
        message=f"Pełna synchronizacja rozpoczęta (ID: {operation_id})",
        details={"operation_id": operation_id, "status_endpoint": f"/status/{operation_id}"}
    )


# ===================
# SYNCHRONIZACJA KOMPONENTÓW
# ===================

@router.post("/exchanges", response_model=SyncResponse)
async def sync_exchanges(
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja assetów z giełd."""
    operation_id = generate_operation_id("sync_exchanges")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_exchanges",
        sync_controller._run_exchanges_sync
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja giełd rozpoczęta (ID: {operation_id})",
        details={"operation_id": operation_id}
    )


@router.post("/analysis/technical", response_model=SyncResponse)
async def sync_technical_analysis(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja analiz technicznych."""
    operation_id = generate_operation_id("sync_technical_analysis")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_technical_analysis",
        sync_controller._run_technical_analysis_sync,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja analiz technicznych rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


@router.post("/analysis/fundamental", response_model=SyncResponse)
async def sync_fundamental_analysis(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja analiz fundamentalnych."""
    operation_id = generate_operation_id("sync_fundamental_analysis")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_fundamental_analysis",
        sync_controller._run_fundamental_analysis_sync,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja analiz fundamentalnych rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


@router.post("/analysis", response_model=SyncResponse)
async def sync_analysis_parallel(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Równoległa synchronizacja analiz (techniczna + fundamentalna równolegle)."""
    operation_id = generate_operation_id("sync_analysis_parallel")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_analysis_parallel",
        sync_controller._run_parallel_analysis,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Równoległa synchronizacja analiz rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


# ===================
# INTERPRETACJE LLM
# ===================

@router.post("/llm/interpretation/technical", response_model=SyncResponse)
async def sync_llm_technical_interpretation(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja interpretacji LLM analiz technicznych."""
    operation_id = generate_operation_id("sync_llm_technical")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_llm_technical",
        sync_controller._run_llm_technical_interpretation_sync,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja interpretacji LLM technicznych rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


@router.post("/llm/interpretation/fundamental", response_model=SyncResponse)
async def sync_llm_fundamental_interpretation(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja interpretacji LLM analiz fundamentalnych."""
    operation_id = generate_operation_id("sync_llm_fundamental")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_llm_fundamental",
        sync_controller._run_llm_fundamental_interpretation_sync,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja interpretacji LLM fundamentalnych rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


@router.post("/llm/interpretation", response_model=SyncResponse)
async def sync_llm_analysis_parallel(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Równoległa synchronizacja interpretacji LLM (fundamentalne + techniczne równolegle)."""
    operation_id = generate_operation_id("sync_llm_analysis_parallel")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_llm_analysis_parallel",
        sync_controller._run_parallel_llm_interpretations,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Równoległa synchronizacja interpretacji LLM rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


@router.post("/llm/decision/general", response_model=SyncResponse)
async def sync_llm_general_decision(
    params: SyncParameters,
    background_tasks: BackgroundTasks,
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja generalnych decyzji LLM."""
    operation_id = generate_operation_id("sync_llm_general")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_llm_general",
        sync_controller._run_llm_general_decision_sync,
        limit=params.limit,
        offset=params.offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja generalnych decyzji LLM rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": params.limit,
            "offset": params.offset
        }
    )


# ===================
# TRANSAKCJE
# ===================

@router.post("/transactions/wallets", response_model=SyncResponse)
async def sync_transactions_wallets(
    background_tasks: BackgroundTasks,
    phase: str = Query(default="pre", description="Faza synchronizacji portfeli (pre/post)"),
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja portfeli/walletów z giełd."""
    if phase not in ["pre", "post"]:
        raise HTTPException(status_code=400, detail="Parametr phase musi być 'pre' lub 'post'")
    
    operation_id = generate_operation_id(f"sync_transactions_wallets_{phase}")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        f"sync_transactions_wallets_{phase}",
        sync_controller._run_transactions_wallets_sync,
        phase=phase
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja portfeli ({phase}) rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "phase": phase
        }
    )


@router.post("/transactions", response_model=SyncResponse)
async def sync_transactions(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=500, ge=1, le=10000, description="Limit transakcji do przetworzenia"),
    offset: int = Query(default=0, ge=0, description="Offset transakcji"),
    sync_controller: SyncController = Depends(get_sync_controller)
):
    """Synchronizacja transakcji."""
    operation_id = generate_operation_id("sync_transactions")
    
    background_tasks.add_task(
        run_sync_operation_background,
        operation_id,
        "sync_transactions",
        sync_controller._run_transactions_sync,
        limit=limit,
        offset=offset
    )
    
    return SyncResponse(
        success=True,
        message=f"Synchronizacja transakcji rozpoczęta (ID: {operation_id})",
        details={
            "operation_id": operation_id,
            "limit": limit,
            "offset": offset
        }
    )


# ===================
# HEALTH & MONITORING
# ===================

@router.get("/health", response_model=SystemHealth)
async def health_check(sync_controller: SyncController = Depends(get_sync_controller)):
    """Health check systemu synchronizacji."""
    try:
        components = {}
        overall_healthy = True
        
        # Check SyncController
        try:
            if sync_controller:
                components["SyncController"] = HealthCheckResult(
                    healthy=True,
                    message="Dostępny",
                    details={
                        "cpu_count": sync_controller.cpu_count,
                        "max_workers": sync_controller.max_workers,
                        "workflow_status": sync_controller.workflow_status
                    }
                )
            else:
                components["SyncController"] = HealthCheckResult(
                    healthy=False,
                    message="Niedostępny",
                    error="SyncController is None"
                )
                overall_healthy = False
        except Exception as e:
            components["SyncController"] = HealthCheckResult(
                healthy=False,
                message="Błąd",
                error=str(e)
            )
            overall_healthy = False
        
        # Check Database
        try:
            if hasattr(sync_controller, 'db') and sync_controller.db:
                # Spróbuj zainicjalizować bazę
                await sync_controller._init_database()
                components["Database"] = HealthCheckResult(
                    healthy=True,
                    message="Połączenie OK"
                )
            else:
                components["Database"] = HealthCheckResult(
                    healthy=False,
                    message="Nie zainicjalizowana",
                    error="Database not initialized"
                )
                overall_healthy = False
        except Exception as e:
            components["Database"] = HealthCheckResult(
                healthy=False,
                message="Błąd połączenia",
                error=str(e)
            )
            overall_healthy = False
        
        # Check running operations
        components["Operations"] = HealthCheckResult(
            healthy=True,
            message=f"Aktywnych operacji: {len(running_operations)}",
            details={
                "running_count": len(running_operations),
                "operations": list(running_operations.keys())
            }
        )
        
        return SystemHealth(
            overall_healthy=overall_healthy,
            components=components
        )
        
    except Exception as e:
        logger.error(f"Błąd w health check: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd health check: {str(e)}")

