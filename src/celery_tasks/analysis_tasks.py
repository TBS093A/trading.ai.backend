"""
Celery Tasks - Analysis

Zadania Celery dla analiz technicznych i fundamentalnych:
- Analiza techniczna
- Analiza fundamentalna
- Równoległa analiza (tech + fundamental)

Autor: AI Assistant
"""

import logging
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime

from ..controller_rest_celery_worker import celery
from ..sync_technical_analysis import TechnicalAnalysis
from ..sync_fundamental_analysis import FundamentalAnalysis
from .utils import run_async_task_safely, wait_for_dependencies

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='analysis_tasks.sync_technical_analysis')
def sync_technical_analysis_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False,
    custom_dependencies: Optional[List[str]] = None
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
        
        # Czekaj na zakończenie sync_exchanges (lub custom dependencies)
        wait_for_dependencies(
            default_dependencies=['sync_tasks.sync_exchanges'],
            custom_dependencies=custom_dependencies,
            task_label='sync_technical_analysis'
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        technical_analysis = TechnicalAnalysis(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_technical_analysis', 'progress': 50}
        )
        
        # Uruchom synchronizację analiz technicznych
        result = run_async_task_safely(
            technical_analysis.sync_technical_analysis,
            limit=limit,
            offset=offset
        )
        
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
    test_mode: bool = False,
    custom_dependencies: Optional[List[str]] = None
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
        
        # Czekaj na zakończenie sync_exchanges (lub custom dependencies)
        wait_for_dependencies(
            default_dependencies=['sync_tasks.sync_exchanges'],
            custom_dependencies=custom_dependencies,
            task_label='sync_fundamental_analysis'
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        fundamental_analysis = FundamentalAnalysis(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_fundamental_analysis', 'progress': 50}
        )
        
        # Uruchom synchronizację analiz fundamentalnych
        result = run_async_task_safely(
            fundamental_analysis.sync_news,
            limit=limit,
            offset=offset
        )
        
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
    Wywołuje obie analizy sekwencyjnie.
    
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
        
        # Uruchom analizę techniczną
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_technical_analysis', 'progress': 25}
        )
        logger.info("📈 Running technical analysis")
        technical_analysis = TechnicalAnalysis(test_mode=test_mode)
        technical_success = run_async_task_safely(
            technical_analysis.sync_technical_analysis,
            limit=limit,
            offset=offset
        )
        
        # Uruchom analizę fundamentalną
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_fundamental_analysis', 'progress': 75}
        )
        logger.info("📊 Running fundamental analysis")
        fundamental_analysis = FundamentalAnalysis(test_mode=test_mode)
        fundamental_success = run_async_task_safely(
            fundamental_analysis.sync_news,
            limit=limit,
            offset=offset
        )
        
        end_time = datetime.now()
        duration = str(end_time - start_time)
        
        overall_success = fundamental_success and technical_success
        
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

