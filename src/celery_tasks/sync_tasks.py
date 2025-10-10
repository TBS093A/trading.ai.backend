"""
Celery Tasks - Basic Synchronization

Zadania Celery dla podstawowych operacji synchronizacji:
- Synchronizacja giełd
- Pełna synchronizacja systemu

Autor: AI Assistant
"""

import logging
from typing import Dict, Any
from datetime import datetime

from ..controller_rest_celery_worker import celery
from ..sync_exchanges import Exchanges
from .utils import run_async_task_safely, wait_for_dependencies

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='sync_tasks.sync_exchanges')
def sync_exchanges_task(self, test_mode: bool = False) -> Dict[str, Any]:
    """
    Zadanie Celery dla synchronizacji assetów z giełd.
    
    Args:
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🔄 Starting sync_exchanges task (ID: {self.request.id})")
        start_time = datetime.now()
        
        # Aktualizuj status zadania
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0}
        )
        
        # Utwórz instancję klasy Exchanges
        exchanges = Exchanges(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_sync', 'progress': 50}
        )
        
        # Uruchom synchronizację giełd
        result = run_async_task_safely(
            exchanges.sync_assets
        )
        
        # Oblicz czas wykonania
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_exchanges task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': 'Exchanges synchronization completed successfully' if result else 'Exchanges synchronization failed'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_exchanges task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={
                'stage': 'error',
                'error': str(exc),
                'traceback': str(exc.__traceback__)
            }
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Exchanges synchronization failed: {exc}'
        }
