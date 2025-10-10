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
from typing import Dict, Any, Tuple, Optional, List
from datetime import datetime

from ..controller_rest_celery_worker import celery
from ..sync_llm_technical_analysis_interpretation import LlmTechnicalAnalysisInterpretation
from ..sync_llm_fundamental_analysis_interpretation import LlmFundamentalAnalysisInterpretation
from ..sync_llm_general_analysis_transaction_decision import LlmGeneralAnalysisTransactionDecision
from .utils import run_async_task_safely, wait_for_dependencies

logger = logging.getLogger(__name__)


@celery.task(bind=True, name='llm_tasks.sync_llm_technical_interpretation')
def sync_llm_technical_interpretation_task(
    self, 
    limit: int = 50, 
    offset: int = 0, 
    test_mode: bool = False,
    custom_dependencies: Optional[List[str]] = None
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
        
        # Czekaj na zakończenie sync_technical_analysis (lub custom dependencies)
        wait_for_dependencies(
            default_dependencies=['analysis_tasks.sync_technical_analysis'],
            custom_dependencies=custom_dependencies,
            task_label='sync_llm_technical_interpretation'
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        llm_technical_interpretation = LlmTechnicalAnalysisInterpretation(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_technical_interpretation', 'progress': 50}
        )
        
        # Uruchom interpretację LLM analiz technicznych
        result = run_async_task_safely(
            llm_technical_interpretation.sync,
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
    test_mode: bool = False,
    custom_dependencies: Optional[List[str]] = None
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
        
        # Czekaj na zakończenie sync_fundamental_analysis (lub custom dependencies)
        wait_for_dependencies(
            default_dependencies=['analysis_tasks.sync_fundamental_analysis'],
            custom_dependencies=custom_dependencies,
            task_label='sync_llm_fundamental_interpretation'
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        llm_fundamental_interpretation = LlmFundamentalAnalysisInterpretation(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_fundamental_interpretation', 'progress': 50}
        )
        
        # Uruchom interpretację LLM analiz fundamentalnych
        result = run_async_task_safely(
            llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations,
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
    Wywołuje obie interpretacje sekwencyjnie.
    
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
        
        # Uruchom interpretację LLM techniczną
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_technical_interpretation', 'progress': 25}
        )
        logger.info("🤖📈 Running LLM technical interpretation")
        llm_technical_interpretation = LlmTechnicalAnalysisInterpretation(test_mode=test_mode)
        technical_success = run_async_task_safely(
            llm_technical_interpretation.sync,
            limit=limit,
            offset=offset
        )
        
        # Uruchom interpretację LLM fundamentalną
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_fundamental_interpretation', 'progress': 75}
        )
        logger.info("🤖📊 Running LLM fundamental interpretation")
        llm_fundamental_interpretation = LlmFundamentalAnalysisInterpretation(test_mode=test_mode)
        fundamental_success = run_async_task_safely(
            llm_fundamental_interpretation.sync_crypto_fundamental_analysis_interpretations,
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
    test_mode: bool = False,
    custom_dependencies: Optional[List[str]] = None
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
        
        # Czekaj na zakończenie obu interpretacji LLM (lub custom dependencies)
        wait_for_dependencies(
            default_dependencies=[
                'llm_tasks.sync_llm_technical_interpretation',
                'llm_tasks.sync_llm_fundamental_interpretation'
            ],
            custom_dependencies=custom_dependencies,
            task_label='sync_llm_general_decision'
        )
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'initializing', 'progress': 0, 'limit': limit, 'offset': offset}
        )
        
        llm_general_decision = LlmGeneralAnalysisTransactionDecision(test_mode=test_mode)
        
        self.update_state(
            state='PROGRESS',
            meta={'stage': 'running_llm_general_decision', 'progress': 50}
        )
        
        # Uruchom generalne decyzje LLM
        result = run_async_task_safely(
            llm_general_decision.sync,
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
