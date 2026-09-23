"""
Celery Worker Configuration for REST API

Konfiguracja workera Celery do obsługi asynchronicznych zadań synchronizacji.
Używa RabbitMQ jako brokera wiadomości.

Autor: AI Assistant
"""

import logging
from celery import Celery
from typing import Dict, Any
from .config import config, _redact_url

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
        },
        
        # Worker configuration
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_max_tasks_per_child=100,
        worker_disable_rate_limits=True,  # Wyłącz rate limiting dla długotrwałych zadań
        
        # Task execution
        task_soft_time_limit=None,  # Brak soft limit (unlimited)
        task_time_limit=None,       # Brak hard limit (unlimited)
        task_track_started=True,
        task_reject_on_worker_lost=True,
        
        # Results
        result_expires=3600,  # 1 godzina
        result_persistent=True,
        
        # Broker transport options (dla długotrwałych zadań)
        broker_transport_options={
            'visibility_timeout': 0,  # Brak timeout dla visibility (unlimited)
            'fanout_prefix': True,
            'fanout_patterns': True,
            'priority_steps': [0, 3, 6, 9]  # Enable priority queues with 4 steps (0=lowest, 9=highest)
        },
        
        # Task priority configuration
        task_default_priority=5,  # Default priority (middle)
        task_inherit_parent_priority=True,
        
        # Monitoring
        worker_send_task_events=True,
        task_send_sent_event=True,
        
        # Error handling
        task_annotations={
            '*': {
                'rate_limit': None,  # Brak rate limiting dla długotrwałych zadań
                'retry_policy': {
                    'max_retries': 3,
                    'interval_start': 0,
                    'interval_step': 0.2,
                    'interval_max': 0.2,
                }
            }
        }
    )
    
    logger.info(f"🔧 Celery configured with broker: {_redact_url(broker_url)}")
    logger.info(f"📊 Result backend: {_redact_url(result_backend)}")
    
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
