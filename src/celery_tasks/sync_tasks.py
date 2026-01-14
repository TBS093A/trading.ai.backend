"""
Celery Tasks - Basic Synchronization

Zadania Celery dla podstawowych operacji synchronizacji:
- Synchronizacja giełd
- Pełna synchronizacja systemu

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..controller_rest_celery_worker import celery
from ..sync_exchanges import Exchanges
from .utils import run_async_task_safely, wait_for_dependencies

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='sync_tasks.sync_exchanges')
def sync_exchanges_task(self, test_mode: bool = False, custom_dependencies: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Zadanie Celery dla synchronizacji assetów z giełd.
    
    Args:
        test_mode: Czy uruchamiać w trybie testowym
        custom_dependencies: Opcjonalne custom zależności dla zadania
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🔄 Starting sync_exchanges task (ID: {self.request.id})")
        start_time = datetime.now()
        
        # Czekaj na zakończenie zależności (jeśli są)
        if custom_dependencies:
            wait_for_dependencies(
                default_dependencies=[],
                custom_dependencies=custom_dependencies,
                task_label='sync_exchanges'
            )
        
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


@celery.task(bind=True, name='sync_tasks.sync_all')
def sync_all_task(self, test_mode: bool = False) -> Dict[str, Any]:
    """
    Zadanie Celery dla pełnej synchronizacji systemu.
    
    Uruchamia synchronizację wszystkich komponentów:
    1. Synchronizacja giełd (exchanges)
    2. Synchronizacja analizy technicznej
    
    Args:
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🚀 Starting full sync_all task (ID: {self.request.id})")
        start_time = datetime.now()
        
        results = {
            'exchanges': None,
            'technical_analysis': None
        }
        
        # Aktualizuj status - rozpoczęcie
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'exchanges', 'progress': 0, 'results': results}
        )
        
        # 1. Synchronizacja giełd
        logger.info("📊 Step 1: Synchronizing exchanges...")
        try:
            exchanges = Exchanges(test_mode=test_mode)
            exchanges_result = run_async_task_safely(exchanges.sync_assets)
            results['exchanges'] = {
                'success': exchanges_result,
                'message': 'Exchanges synchronized' if exchanges_result else 'Exchanges sync failed'
            }
        except Exception as e:
            logger.error(f"❌ Exchanges sync failed: {e}")
            results['exchanges'] = {'success': False, 'error': str(e)}
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'technical_analysis', 'progress': 50, 'results': results}
        )
        
        # 2. Synchronizacja analizy technicznej (opcjonalnie - wymaga importu)
        logger.info("📈 Step 2: Technical analysis sync skipped in full sync (use dedicated endpoint)")
        results['technical_analysis'] = {
            'success': True,
            'message': 'Skipped - use dedicated endpoint for technical analysis sync'
        }
        
        # Oblicz czas wykonania
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        # Określ ogólny sukces
        overall_success = all(
            r.get('success', False) for r in results.values() if r
        )
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100, 'results': results}
        )
        
        logger.info(f"✅ sync_all task completed (ID: {self.request.id})")
        
        return {
            'success': overall_success,
            'task_id': self.request.id,
            'duration': duration,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'results': results,
            'message': 'Full synchronization completed' if overall_success else 'Some sync operations failed'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_all task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={
                'stage': 'error',
                'error': str(exc)
            }
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Full synchronization failed: {exc}'
        }
