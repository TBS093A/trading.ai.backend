"""
Celery Tasks - Transactions

Zadania Celery dla transakcji i portfeli:
- Synchronizacja portfeli/walletów
- Synchronizacja transakcji

Autor: AI Assistant
"""

import logging
from typing import Dict, Any
from datetime import datetime

from ..controller_rest_celery_worker import celery
from main_controller_sync import SyncController
from .utils import run_async_task_safely

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='transaction_tasks.sync_transactions_wallets')
def sync_transactions_wallets_task(
    self, 
    phase: str = "pre", 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla synchronizacji portfeli/walletów z giełd.
    
    Args:
        phase: Faza synchronizacji ("pre" lub "post")
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        phase_label = "PRZED TRANSAKCJAMI" if phase == "pre" else "PO TRANSAKCJACH"
        logger.info(f"💼 Starting sync_transactions_wallets task {phase_label} (ID: {self.request.id})")
        start_time = datetime.now()
        
        # Walidacja fazy
        if phase not in ["pre", "post"]:
            raise ValueError(f"Invalid phase '{phase}'. Must be 'pre' or 'post'")
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'phase': phase}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': f'running_wallets_sync_{phase}', 'progress': 50}
        )
        
        # Uruchom synchronizację portfeli
        result = run_async_task_safely(
            sync_controller._run_transactions_wallets_sync,
            phase=phase
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_transactions_wallets task {phase_label} completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'phase': phase,
            'phase_label': phase_label,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'Wallets synchronization {phase_label} completed successfully' if result else f'Wallets synchronization {phase_label} failed'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_transactions_wallets task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Wallets synchronization failed: {exc}'
        }


@celery.task(bind=True, name='transaction_tasks.sync_transactions')
def sync_transactions_task(
    self, 
    limit: int = 500, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla synchronizacji transakcji.
    
    Args:
        limit: Limit transakcji do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"💰 Starting sync_transactions task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_transactions_sync', 'progress': 50}
        )
        
        # Uruchom synchronizację transakcji
        result = run_async_task_safely(
            sync_controller._run_transactions_sync,
            limit=limit,
            offset=offset
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_transactions task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'Transactions synchronization completed (processed up to {limit} transactions from offset {offset})'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_transactions task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Transactions synchronization failed: {exc}'
        }
