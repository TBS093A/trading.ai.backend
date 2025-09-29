"""
Celery Tasks - Analysis

Zadania Celery dla analiz technicznych i fundamentalnych:
- Analiza techniczna
- Analiza fundamentalna
- Równoległa analiza (tech + fundamental)

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Tuple
from datetime import datetime

from ..controller_rest_celery_worker import celery
from main_controller_sync import SyncController

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='analysis_tasks.sync_technical_analysis')
def sync_technical_analysis_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla synchronizacji analiz technicznych.
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"📈 Starting sync_technical_analysis task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_technical_analysis', 'progress': 50}
        )
        
        # Uruchom synchronizację analiz technicznych
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                sync_controller._run_technical_analysis_sync(limit=limit, offset=offset)
            )
        finally:
            loop.close()
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_technical_analysis task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'Technical analysis sync completed (processed {limit} records from offset {offset})'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_technical_analysis task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Technical analysis sync failed: {exc}'
        }


@celery.task(bind=True, name='analysis_tasks.sync_fundamental_analysis')
def sync_fundamental_analysis_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla synchronizacji analiz fundamentalnych.
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"📊 Starting sync_fundamental_analysis task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_fundamental_analysis', 'progress': 50}
        )
        
        # Uruchom synchronizację analiz fundamentalnych
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                sync_controller._run_fundamental_analysis_sync(limit=limit, offset=offset)
            )
        finally:
            loop.close()
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_fundamental_analysis task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'Fundamental analysis sync completed (processed {limit} records from offset {offset})'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_fundamental_analysis task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Fundamental analysis sync failed: {exc}'
        }


@celery.task(bind=True, name='analysis_tasks.sync_analysis_parallel')
def sync_analysis_parallel_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla równoległej synchronizacji analiz (techniczna + fundamentalna).
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"📈📊 Starting sync_analysis_parallel task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_parallel_analysis', 'progress': 50}
        )
        
        # Uruchom równoległą synchronizację analiz
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            fundamental_success, technical_success = loop.run_until_complete(
                sync_controller._run_parallel_analysis(limit=limit, offset=offset)
            )
        finally:
            loop.close()
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        overall_success = fundamental_success or technical_success
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_analysis_parallel task completed (ID: {self.request.id})")
        
        return {
            'success': overall_success,
            'fundamental_success': fundamental_success,
            'technical_success': technical_success,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'Parallel analysis sync completed - Fundamental: {"✅" if fundamental_success else "❌"}, Technical: {"✅" if technical_success else "❌"}'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_analysis_parallel task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'Parallel analysis sync failed: {exc}'
        }
