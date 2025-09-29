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
from main_controller_sync import SyncController

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
        
        # Utwórz kontroler synchronizacji
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_sync', 'progress': 50}
        )
        
        # Uruchom synchronizację giełd (synchronicznie w taskg)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(sync_controller._run_exchanges_sync())
        finally:
            loop.close()
        
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


@celery.task(bind=True, name='sync_tasks.sync_all')
def sync_all_task(self, test_mode: bool = False) -> Dict[str, Any]:
    """
    Zadanie Celery dla pełnej synchronizacji systemu.
    
    Args:
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🚀 Starting sync_all task (ID: {self.request.id})")
        start_time = datetime.now()
        
        # Aktualizuj status zadania
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0}
        )
        
        # Utwórz kontroler synchronizacji
        sync_controller = SyncController(test_mode=test_mode)
        
        stages = [
            ('exchanges', 10),
            ('analysis', 30),
            ('llm_interpretations', 50),
            ('llm_general', 70),
            ('transactions_wallets_pre', 80),
            ('transactions', 90),
            ('transactions_wallets_post', 100)
        ]
        
        # Uruchom pełny workflow synchronizacji
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Aktualizuj progress przez workflow
            for stage, progress in stages:
                self.update_state(
                    state='PROGRESS',
                    meta={'stage': stage, 'progress': progress}
                )
                
            # Uruchom pełny workflow
            result = loop.run_until_complete(sync_controller.run_full_sync_workflow())
        finally:
            loop.close()
        
        # Oblicz czas wykonania
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_all task completed (ID: {self.request.id})")
        
        return {
            'success': True,
            'task_id': self.request.id,
            'duration': duration,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'workflow_status': sync_controller.workflow_status,
            'message': 'Full system synchronization completed successfully'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_all task failed (ID: {self.request.id}): {exc}")
        
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
            'message': f'Full synchronization failed: {exc}'
        }
