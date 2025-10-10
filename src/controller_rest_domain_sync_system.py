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
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from pydantic import BaseModel, Field

# Import SyncController
from main_controller_sync import SyncController

# Import Celery tasks
from .celery_tasks.sync_tasks import sync_exchanges_task, sync_all_task
from .celery_tasks.analysis_tasks import (
    sync_technical_analysis_task,
    sync_fundamental_analysis_task, 
    sync_analysis_parallel_task
)
from .celery_tasks.llm_tasks import (
    sync_llm_technical_interpretation_task,
    sync_llm_fundamental_interpretation_task,
    sync_llm_analysis_parallel_task,
    sync_llm_general_decision_task
)
from .celery_tasks.transaction_tasks import (
    sync_transactions_wallets_task,
    sync_transactions_task
)
from .controller_rest_celery_worker import get_task_status, get_celery_app

# Import Health Checkers dla Celery
from .health_checkers import (
    BrokerHealthCheckerFactory,
    ResultBackendHealthCheckerFactory
)
from .config import config

# Import API Facade dla storage health checks
from .api.api_facade import ApiFacade

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
    """
    Status workflow synchronizacji (DEPRECATED).
    
    Ten model jest przestarzały - workflow jest teraz zarządzany przez Celery tasks.
    Endpoint /workflow zwraca aktywne zadania Celery zamiast tego modelu.
    """
    exchanges_completed: bool = False
    fundamental_analysis_completed: bool = False
    technical_analysis_completed: bool = False
    llm_fundamental_completed: bool = False
    llm_technical_completed: bool = False
    llm_general_completed: bool = False
    transactions_wallets_pre_completed: bool = False
    transactions_completed: bool = False
    transactions_wallets_post_completed: bool = False


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

# Globalne śledzenie aktywnych operacji
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
            "workflow": "GET /sync/workflow - Status workflow (Celery tasks)",
            "health": "GET /sync/health - Health check systemu"
        }
    }


@router.get("/status", response_model=List[Dict[str, Any]])
async def get_sync_status():
    """Pobiera status wszystkich zadań Celery."""
    try:
        celery_app = get_celery_app()
        inspect = celery_app.control.inspect()
        
        # Pobierz aktywne zadania
        active_tasks = inspect.active() or {}
        scheduled_tasks = inspect.scheduled() or {}
        
        all_statuses = []
        
        # Przetwórz aktywne zadania
        for worker, tasks in active_tasks.items():
            for task in tasks:
                all_statuses.append({
                    'task_id': task['id'],
                    'task_name': task['name'],
                    'status': 'RUNNING',
                    'worker': worker,
                    'args': task.get('args', []),
                    'kwargs': task.get('kwargs', {}),
                })
        
        # Przetwórz zaplanowane zadania
        for worker, tasks in scheduled_tasks.items():
            for task in tasks:
                all_statuses.append({
                    'task_id': task['request']['id'],
                    'task_name': task['request']['task'],
                    'status': 'PENDING',
                    'worker': worker,
                    'eta': task.get('eta'),
                })
        
        return all_statuses
        
    except Exception as e:
        logger.error(f"Error getting Celery status: {e}")
        return []


@router.get("/status/{task_id}", response_model=Dict[str, Any])
async def get_operation_status(task_id: str = Path(..., description="ID zadania Celery")):
    """Pobiera status konkretnego zadania Celery."""
    try:
        status = get_task_status(task_id)
        if status.get('status') == 'ERROR' and 'error' in status:
            raise HTTPException(status_code=404, detail="Task not found")
        return status
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Task not found: {str(e)}")


@router.delete("/status/{task_id}", response_model=SyncResponse)
async def cancel_operation(task_id: str = Path(..., description="ID zadania Celery do anulowania")):
    """
    Anuluje wykonanie zadania Celery.
    
    Endpoint umożliwia anulowanie długotrwałych operacji synchronizacji
    na podstawie ID zadania pobranego z get_sync_status.
    """
    try:
        celery_app = get_celery_app()
        
        # Sprawdź czy zadanie istnieje
        task_status = get_task_status(task_id)
        current_status = task_status.get('status', 'UNKNOWN')
        
        # Sprawdź czy zadanie można anulować
        if current_status in ['SUCCESS', 'FAILURE', 'REVOKED']:
            return SyncResponse(
                success=False,
                message=f"Nie można anulować zadania - status: {current_status}",
                details={
                    "task_id": task_id,
                    "current_status": current_status,
                    "reason": "Task already completed or revoked"
                }
            )
        
        # Anuluj zadanie z terminate=True (zatrzyma wykonywanie)
        celery_app.control.revoke(
            task_id, 
            terminate=True,  # Natychmiast zatrzymaj wykonywanie
            signal='SIGTERM'  # Używaj SIGTERM zamiast SIGKILL dla graceful shutdown
        )
        
        # Dodatkowe anulowanie przez AsyncResult
        from celery.result import AsyncResult
        result = AsyncResult(task_id, app=celery_app)
        result.revoke(terminate=True)
        
        logger.info(f"🚫 Anulowano zadanie Celery: {task_id}")
        
        # Usuń zadanie z globalnego running_operations jeśli istnieje
        if task_id in running_operations:
            running_operations[task_id]["status"] = "cancelled"
            running_operations[task_id]["end_time"] = datetime.now()
            logger.info(f"🗑️ Usunięto zadanie z running_operations: {task_id}")
        
        return SyncResponse(
            success=True,
            message=f"Zadanie zostało anulowane: {task_id}",
            details={
                "task_id": task_id,
                "previous_status": current_status,
                "action": "revoked_with_terminate",
                "cancelled_at": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Błąd podczas anulowania zadania {task_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Nie udało się anulować zadania: {str(e)}"
        )


@router.get("/workflow", response_model=Dict[str, Any])
async def get_workflow_status():
    """
    Pobiera status workflow synchronizacji z Celery.
    
    Workflow jest teraz zarządzany przez zadania Celery z wewnętrznymi zależnościami.
    Ten endpoint zwraca aktywne zadania Celery zamiast wewnętrznego statusu.
    """
    try:
        celery_app = get_celery_app()
        inspect = celery_app.control.inspect()
        
        # Pobierz aktywne i zaplanowane zadania
        active_tasks = inspect.active() or {}
        scheduled_tasks = inspect.scheduled() or {}
        reserved_tasks = inspect.reserved() or {}
        
        # Grupuj zadania według typu
        workflow_status = {
            "exchanges": [],
            "technical_analysis": [],
            "fundamental_analysis": [],
            "llm_technical_interpretation": [],
            "llm_fundamental_interpretation": [],
            "llm_general_decision": [],
            "transactions_wallets": [],
            "transactions": []
        }
        
        # Przetwórz aktywne zadania
        for worker, tasks in active_tasks.items():
            for task in tasks:
                task_name = task['name'].split('.')[-1]  # Pobierz ostatnią część nazwy
                for key in workflow_status.keys():
                    if key in task_name:
                        workflow_status[key].append({
                            'task_id': task['id'],
                            'status': 'RUNNING',
                            'worker': worker
                        })
        
        # Przetwórz zaplanowane zadania
        for worker, tasks in scheduled_tasks.items():
            for task in tasks:
                task_name = task['request']['name'].split('.')[-1]
                for key in workflow_status.keys():
                    if key in task_name:
                        workflow_status[key].append({
                            'task_id': task['request']['id'],
                            'status': 'SCHEDULED',
                            'worker': worker,
                            'eta': task.get('eta')
                        })
        
        # Przetwórz zarezerwowane zadania
        for worker, tasks in reserved_tasks.items():
            for task in tasks:
                task_name = task['name'].split('.')[-1]
                for key in workflow_status.keys():
                    if key in task_name:
                        workflow_status[key].append({
                            'task_id': task['id'],
                            'status': 'RESERVED',
                            'worker': worker
                        })
        
        return {
            "message": "Workflow status from Celery tasks",
            "note": "Dependencies are managed internally by tasks",
            "workflow": workflow_status,
            "summary": {
                key: len(tasks) for key, tasks in workflow_status.items()
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting workflow status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


# ===================
# SYNCHRONIZACJA PEŁNA
# ===================

@router.post("/all", response_model=SyncResponse)
async def sync_all(test_mode: bool = Query(default=False, description="Tryb testowy")):
    """Uruchamia pełny workflow synchronizacji systemu."""
    try:
        # Uruchom zadanie Celery
        task = sync_all_task.delay(test_mode=test_mode)
        
        return SyncResponse(
            success=True,
            message=f"Pełna synchronizacja rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_all task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start synchronization: {str(e)}")


# ===================
# SYNCHRONIZACJA KOMPONENTÓW
# ===================

@router.post("/exchanges", response_model=SyncResponse)
async def sync_exchanges(test_mode: bool = Query(default=False, description="Tryb testowy")):
    """Synchronizacja assetów z giełd."""
    try:
        # Uruchom zadanie Celery
        task = sync_exchanges_task.delay(test_mode=test_mode)
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja giełd rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_exchanges task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start exchanges sync: {str(e)}")


@router.post("/analysis/technical", response_model=SyncResponse)
async def sync_technical_analysis(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja analiz technicznych."""
    try:
        # Uruchom zadanie Celery
        task = sync_technical_analysis_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja analiz technicznych rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_technical_analysis task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start technical analysis sync: {str(e)}")


@router.post("/analysis/fundamental", response_model=SyncResponse)
async def sync_fundamental_analysis(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja analiz fundamentalnych."""
    try:
        # Uruchom zadanie Celery
        task = sync_fundamental_analysis_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja analiz fundamentalnych rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_fundamental_analysis task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start fundamental analysis sync: {str(e)}")


@router.post("/analysis", response_model=SyncResponse)
async def sync_analysis_parallel(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Równoległa synchronizacja analiz (techniczna + fundamentalna równolegle)."""
    try:
        # Uruchom zadanie Celery
        task = sync_analysis_parallel_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Równoległa synchronizacja analiz rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_analysis_parallel task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start parallel analysis sync: {str(e)}")


# ===================
# INTERPRETACJE LLM
# ===================

@router.post("/llm/interpretation/technical", response_model=SyncResponse)
async def sync_llm_technical_interpretation(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja interpretacji LLM analiz technicznych."""
    try:
        # Uruchom zadanie Celery
        task = sync_llm_technical_interpretation_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja interpretacji LLM technicznych rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_llm_technical_interpretation task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start LLM technical interpretation: {str(e)}")


@router.post("/llm/interpretation/fundamental", response_model=SyncResponse)
async def sync_llm_fundamental_interpretation(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja interpretacji LLM analiz fundamentalnych."""
    try:
        # Uruchom zadanie Celery
        task = sync_llm_fundamental_interpretation_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja interpretacji LLM fundamentalnych rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_llm_fundamental_interpretation task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start LLM fundamental interpretation: {str(e)}")


@router.post("/llm/interpretation", response_model=SyncResponse)
async def sync_llm_analysis_parallel(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Równoległa synchronizacja interpretacji LLM (fundamentalne + techniczne równolegle)."""
    try:
        # Uruchom zadanie Celery
        task = sync_llm_analysis_parallel_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Równoległa synchronizacja interpretacji LLM rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_llm_analysis_parallel task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start LLM parallel interpretation: {str(e)}")


@router.post("/llm/decision/general", response_model=SyncResponse)
async def sync_llm_general_decision(
    params: SyncParameters,
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja generalnych decyzji LLM."""
    try:
        # Uruchom zadanie Celery
        task = sync_llm_general_decision_task.delay(
            limit=params.limit,
            offset=params.offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja generalnych decyzji LLM rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": params.limit,
                "offset": params.offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_llm_general_decision task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start LLM general decision: {str(e)}")


# ===================
# TRANSAKCJE
# ===================

@router.post("/transactions/wallets", response_model=SyncResponse)
async def sync_transactions_wallets(
    phase: str = Query(default="pre", description="Faza synchronizacji portfeli (pre/post)"),
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja portfeli/walletów z giełd."""
    if phase not in ["pre", "post"]:
        raise HTTPException(status_code=400, detail="Parametr phase musi być 'pre' lub 'post'")
    
    try:
        # Uruchom zadanie Celery
        task = sync_transactions_wallets_task.delay(
            phase=phase,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja portfeli ({phase}) rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "phase": phase,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_transactions_wallets task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start wallets sync: {str(e)}")


@router.post("/transactions", response_model=SyncResponse)
async def sync_transactions(
    limit: int = Query(default=500, ge=1, le=10000, description="Limit transakcji do przetworzenia"),
    offset: int = Query(default=0, ge=0, description="Offset transakcji"),
    test_mode: bool = Query(default=False, description="Tryb testowy")
):
    """Synchronizacja transakcji."""
    try:
        # Uruchom zadanie Celery
        task = sync_transactions_task.delay(
            limit=limit,
            offset=offset,
            test_mode=test_mode
        )
        
        return SyncResponse(
            success=True,
            message=f"Synchronizacja transakcji rozpoczęta (Task ID: {task.id})",
            details={
                "task_id": task.id,
                "status_endpoint": f"/sync/status/{task.id}",
                "limit": limit,
                "offset": offset,
                "test_mode": test_mode
            }
        )
    except Exception as e:
        logger.error(f"Error starting sync_transactions task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start transactions sync: {str(e)}")


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
                # Pobierz informacje o workerach Celery
                celery_app = get_celery_app()
                inspect = celery_app.control.inspect()
                stats = inspect.stats() or {}
                active = inspect.active() or {}
                
                total_workers = len(stats)
                active_tasks = sum(len(tasks) for tasks in active.values())
                
                components["SyncController"] = HealthCheckResult(
                    healthy=True,
                    message="Dostępny",
                    details={
                        "type": "Celery-based dispatcher",
                        "celery_workers": total_workers,
                        "active_tasks": active_tasks,
                        "test_mode": sync_controller.test_mode
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
                # Użyj nowej metody test_connection()
                test_result = await sync_controller.db.test_connection()
                if test_result.get('test_passed', False):
                    components["Database"] = HealthCheckResult(
                        healthy=True,
                        message="Połączenie OK",
                        details={
                            "connection": test_result.get('connection'),
                            "tables_count": test_result.get('tables_count', 0),
                            "database_version": test_result.get('database_version', 'Unknown')[:50] + '...' if len(test_result.get('database_version', '')) > 50 else test_result.get('database_version', 'Unknown')
                        }
                    )
                else:
                    components["Database"] = HealthCheckResult(
                        healthy=False,
                        message="Test połączenia nieudany",
                        error=test_result.get('error', 'Unknown error')
                    )
                    overall_healthy = False
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
        
        # Check Celery Broker
        try:
            broker_url = config.celery_broker_url
            if broker_url:
                broker_checker = BrokerHealthCheckerFactory.create_checker(broker_url)
                broker_result = await broker_checker.check_health()
                
                components["CeleryBroker"] = HealthCheckResult(
                    healthy=broker_result.get("healthy", False),
                    message=broker_result.get("message", "Unknown"),
                    details=broker_result.get("details"),
                    error=broker_result.get("error")
                )
                
                if not broker_result.get("healthy", False):
                    overall_healthy = False
            else:
                components["CeleryBroker"] = HealthCheckResult(
                    healthy=False,
                    message="Nie skonfigurowany",
                    error="CELERY_BROKER_URL nie jest ustawiony"
                )
                overall_healthy = False
        except Exception as e:
            components["CeleryBroker"] = HealthCheckResult(
                healthy=False,
                message="Błąd sprawdzania brokera",
                error=str(e)
            )
            overall_healthy = False
        
        # Check Celery Result Backend  
        try:
            backend_url = config.celery_result_backend
            if backend_url:
                backend_checker = ResultBackendHealthCheckerFactory.create_checker(backend_url)
                backend_result = await backend_checker.check_health()
                
                components["CeleryResultBackend"] = HealthCheckResult(
                    healthy=backend_result.get("healthy", False),
                    message=backend_result.get("message", "Unknown"),
                    details=backend_result.get("details"),
                    error=backend_result.get("error")
                )
                
                if not backend_result.get("healthy", False):
                    overall_healthy = False
            else:
                components["CeleryResultBackend"] = HealthCheckResult(
                    healthy=False,
                    message="Nie skonfigurowany",
                    error="CELERY_RESULT_BACKEND nie jest ustawiony"
                )
                overall_healthy = False
        except Exception as e:
            components["CeleryResultBackend"] = HealthCheckResult(
                healthy=False,
                message="Błąd sprawdzania result backend",
                error=str(e)
            )
            overall_healthy = False

        # Check Storage APIs
        try:
            api_facade = ApiFacade()
            storage_apis = api_facade.get_fabric().get_storage_apis()
            
            storage_results = {}
            for storage_api in storage_apis:
                storage_name = f"{storage_api.STORAGE}Storage"
                try:
                    storage_result = await storage_api.health_check()
                    storage_results[storage_name] = storage_result
                    
                    components[storage_name] = HealthCheckResult(
                        healthy=storage_result.get("healthy", False),
                        message=storage_result.get("message", "Unknown"),
                        details=storage_result.get("details"),
                        error=storage_result.get("error")
                    )
                    
                    if not storage_result.get("healthy", False):
                        overall_healthy = False
                        
                except Exception as e:
                    logger.error(f"Błąd podczas sprawdzania {storage_name}: {e}")
                    components[storage_name] = HealthCheckResult(
                        healthy=False,
                        message=f"Błąd sprawdzania {storage_name}",
                        error=str(e)
                    )
                    overall_healthy = False
            
            logger.info(f"Sprawdzono {len(storage_apis)} storage APIs: {list(storage_results.keys())}")
            
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji sprawdzania storage: {e}")
            components["StorageAPIs"] = HealthCheckResult(
                healthy=False,
                message="Błąd inicjalizacji sprawdzania storage",
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

