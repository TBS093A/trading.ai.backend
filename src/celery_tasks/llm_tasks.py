"""
Celery Tasks - LLM

Zadania Celery dla interpretacji LLM:
- Interpretacja LLM analiz technicznych
- Interpretacja LLM analiz fundamentalnych
- Równoległa interpretacja LLM
- Generalna decyzja LLM

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Tuple
from datetime import datetime

from ..controller_rest_celery_worker import celery
from main_controller_sync import SyncController
from .utils import run_async_task_safely

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='llm_tasks.sync_llm_technical_interpretation')
def sync_llm_technical_interpretation_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla interpretacji LLM analiz technicznych.
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🤖📈 Starting sync_llm_technical_interpretation task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_technical_interpretation', 'progress': 50}
        )
        
        # Uruchom interpretację LLM analiz technicznych
        result = run_async_task_safely(
            sync_controller._run_llm_technical_interpretation_sync,
            limit=limit,
            offset=offset
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_llm_technical_interpretation task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'LLM technical interpretation completed (processed {limit} records from offset {offset})'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_llm_technical_interpretation task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'LLM technical interpretation failed: {exc}'
        }


@celery.task(bind=True, name='llm_tasks.sync_llm_fundamental_interpretation')
def sync_llm_fundamental_interpretation_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla interpretacji LLM analiz fundamentalnych.
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🤖📊 Starting sync_llm_fundamental_interpretation task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_fundamental_interpretation', 'progress': 50}
        )
        
        # Uruchom interpretację LLM analiz fundamentalnych
        result = run_async_task_safely(
            sync_controller._run_llm_fundamental_interpretation_sync,
            limit=limit,
            offset=offset
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_llm_fundamental_interpretation task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'LLM fundamental interpretation completed (processed {limit} records from offset {offset})'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_llm_fundamental_interpretation task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'LLM fundamental interpretation failed: {exc}'
        }


@celery.task(bind=True, name='llm_tasks.sync_llm_analysis_parallel')
def sync_llm_analysis_parallel_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla równoległej interpretacji LLM (techniczna + fundamentalna).
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🤖📈📊 Starting sync_llm_analysis_parallel task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_parallel_interpretations', 'progress': 50}
        )
        
        # Uruchom równoległą interpretację LLM
        fundamental_success, technical_success = run_async_task_safely(
            sync_controller._run_parallel_llm_interpretations,
            limit=limit,
            offset=offset
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        overall_success = fundamental_success or technical_success
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_llm_analysis_parallel task completed (ID: {self.request.id})")
        
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
            'message': f'LLM parallel interpretation completed - Fundamental: {"✅" if fundamental_success else "❌"}, Technical: {"✅" if technical_success else "❌"}'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_llm_analysis_parallel task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'LLM parallel interpretation failed: {exc}'
        }


@celery.task(bind=True, name='llm_tasks.sync_llm_general_decision')
def sync_llm_general_decision_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Zadanie Celery dla generalnych decyzji LLM.
    
    Args:
        limit: Limit rekordów do przetworzenia
        offset: Offset od którego zacząć
        test_mode: Czy uruchamiać w trybie testowym
        
    Returns:
        Dict[str, Any]: Wynik synchronizacji
    """
    try:
        logger.info(f"🎯 Starting sync_llm_general_decision task (ID: {self.request.id})")
        start_time = datetime.now()
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        sync_controller = SyncController(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_general_decision', 'progress': 50}
        )
        
        # Uruchom generalne decyzje LLM
        result = run_async_task_safely(
            sync_controller._run_llm_general_decision_sync,
            limit=limit,
            offset=offset
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        self.update_state(
            state='SUCCESS',
            meta={'stage': 'completed', 'progress': 100}
        )
        
        logger.info(f"✅ sync_llm_general_decision task completed (ID: {self.request.id})")
        
        return {
            'success': result,
            'task_id': self.request.id,
            'duration': duration,
            'limit': limit,
            'offset': offset,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'message': f'LLM general decision completed (processed {limit} records from offset {offset})'
        }
        
    except Exception as exc:
        logger.error(f"❌ sync_llm_general_decision task failed (ID: {self.request.id}): {exc}")
        
        self.update_state(
            state='FAILURE',
            meta={'stage': 'error', 'error': str(exc)}
        )
        
        return {
            'success': False,
            'task_id': self.request.id,
            'error': str(exc),
            'message': f'LLM general decision failed: {exc}'
        }
