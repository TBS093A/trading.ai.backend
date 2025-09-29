"""
Celery Worker Configuration for REST API

Konfiguracja workera Celery do obsługi asynchronicznych zadań synchronizacji.
Używa RabbitMQ jako brokera wiadomości.

Autor: AI Assistant
"""

import logging
from celery import Celery
from typing import Dict, Any
from .config import config

logger = logging.getLogger(__name__)

# Konfiguracja Celery
def create_celery_app() -> Celery:
    """
    Tworzy i konfiguruje instancję aplikacji Celery.
    
    Returns:
        Celery: Skonfigurowana aplikacja Celery
    """
    
    # Pobierz konfigurację Celery z config.py
    celery_config = config.celery_config
    broker_url = celery_config['broker_url']
    result_backend = celery_config['result_backend']
    
    # Tworzenie aplikacji Celery
    celery_app = Celery(
        'telegram_pump_bot_worker',
        broker=broker_url,
        backend=result_backend,
        include=[
            'src.celery_tasks.sync_tasks',
            'src.celery_tasks.analysis_tasks', 
            'src.celery_tasks.llm_tasks',
            'src.celery_tasks.transaction_tasks'
        ]
    )
    
    # Konfiguracja Celery
    celery_app.conf.update(
        # Serialization
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Europe/Warsaw',
        enable_utc=True,
        
        # Task routing
        task_routes={
            'src.celery_tasks.sync_tasks.*': {'queue': 'sync_queue'},
            'src.celery_tasks.analysis_tasks.*': {'queue': 'analysis_queue'},
            'src.celery_tasks.llm_tasks.*': {'queue': 'llm_queue'},
            'src.celery_tasks.transaction_tasks.*': {'queue': 'transaction_queue'},
        },
        
        # Worker configuration
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_max_tasks_per_child=100,
        
        # Task execution
        task_soft_time_limit=1800,  # 30 minut soft limit
        task_time_limit=3600,       # 60 minut hard limit
        task_track_started=True,
        task_reject_on_worker_lost=True,
        
        # Results
        result_expires=3600,  # 1 godzina
        result_persistent=True,
        
        # Monitoring
        worker_send_task_events=True,
        task_send_sent_event=True,
        
        # Error handling
        task_annotations={
            '*': {
                'rate_limit': '10/s',
                'retry_policy': {
                    'max_retries': 3,
                    'interval_start': 0,
                    'interval_step': 0.2,
                    'interval_max': 0.2,
                }
            }
        }
    )
    
    logger.info(f"🔧 Celery configured with broker: {broker_url}")
    logger.info(f"📊 Result backend: {result_backend}")
    
    return celery_app


# Instancja Celery do importowania
celery = create_celery_app()


def get_celery_app() -> Celery:
    """
    Zwraca instancję aplikacji Celery.
    
    Returns:
        Celery: Aplikacja Celery
    """
    return celery


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Pobiera status zadania Celery.
    
    Args:
        task_id: ID zadania
        
    Returns:
        Dict[str, Any]: Status zadania
    """
    try:
        result = celery.AsyncResult(task_id)
        
        return {
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
            'traceback': result.traceback if result.failed() else None,
            'info': result.info,
            'ready': result.ready(),
            'successful': result.successful(),
            'failed': result.failed()
        }
    except Exception as e:
        logger.error(f"Error getting task status for {task_id}: {e}")
        return {
            'task_id': task_id,
            'status': 'ERROR',
            'error': str(e)
        }


def revoke_task(task_id: str, terminate: bool = False) -> bool:
    """
    Anuluje zadanie Celery.
    
    Args:
        task_id: ID zadania do anulowania
        terminate: Czy zakończyć siłą proces
        
    Returns:
        bool: True jeśli udało się anulować
    """
    try:
        celery.control.revoke(task_id, terminate=terminate)
        logger.info(f"Task {task_id} revoked (terminate={terminate})")
        return True
    except Exception as e:
        logger.error(f"Error revoking task {task_id}: {e}")
        return False


def get_active_tasks() -> Dict[str, Any]:
    """
    Pobiera listę aktywnych zadań.
    
    Returns:
        Dict[str, Any]: Słownik aktywnych zadań
    """
    try:
        inspect = celery.control.inspect()
        active_tasks = inspect.active()
        
        if active_tasks is None:
            return {}
        
        return active_tasks
    except Exception as e:
        logger.error(f"Error getting active tasks: {e}")
        return {}


def get_worker_stats() -> Dict[str, Any]:
    """
    Pobiera statystyki workerów.
    
    Returns:
        Dict[str, Any]: Statystyki workerów
    """
    try:
        inspect = celery.control.inspect()
        stats = inspect.stats()
        
        if stats is None:
            return {}
        
        return stats
    except Exception as e:
        logger.error(f"Error getting worker stats: {e}")
        return {}


if __name__ == '__main__':
    """Uruchomienie workera Celery."""
    celery.start()
