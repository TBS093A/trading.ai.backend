"""
Celery Tasks - Utils

Pomocnicze funkcje dla zadań Celery.

Autor: AI Assistant
"""

import asyncio
import logging
import time
from typing import Callable, Any, List, Optional
from celery import current_app

logger = logging.getLogger(__name__)


def run_async_task_safely(async_func: Callable, *args, **kwargs) -> Any:
    """
    Bezpiecznie uruchamia funkcję asynchroniczną w nowej pętli event loop.
    Upewnia się, że wszystkie zadania są zakończone przed zamknięciem pętli.
    
    Args:
        async_func: Funkcja asynchroniczna do uruchomienia
        *args: Argumenty pozycyjne dla funkcji
        **kwargs: Argumenty nazwane dla funkcji
        
    Returns:
        Any: Wynik funkcji asynchronicznej
    """
    loop = None
    try:
        # Utwórz nową pętlę asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Uruchom funkcję async w nowej pętli
        result = loop.run_until_complete(async_func(*args, **kwargs))
        
        # Poczekaj na zakończenie wszystkich oczekujących zadań
        pending = asyncio.all_tasks(loop)
        if pending:
            logger.debug(f"Oczekiwanie na {len(pending)} oczekujących zadań przed zamknięciem pętli")
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        
        return result
            
    except Exception as e:
        logger.error(f"Błąd podczas wykonywania zadania async: {e}")
        raise
    finally:
        # Upewnij się, że pętla jest prawidłowo zamknięta
        if loop is not None and not loop.is_closed():
            try:
                # Anuluj wszystkie pozostałe zadania
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.debug(f"Anulowanie {len(pending)} pozostałych zadań")
                    for task in pending:
                        task.cancel()
                    
                    # Poczekaj na anulowanie zadań
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # Zamknij pętlę
                loop.close()
                logger.debug("Event loop zamknięta pomyślnie")
            except Exception as e:
                logger.warning(f"Błąd podczas zamykania event loop: {e}")


def get_active_tasks_by_name(task_names: List[str]) -> List[dict]:
    """
    Pobiera aktywne zadania Celery o podanych nazwach.
    
    Args:
        task_names: Lista nazw zadań do sprawdzenia (np. ['sync_tasks.sync_exchanges'])
        
    Returns:
        List[dict]: Lista aktywnych zadań pasujących do nazw
    """
    try:
        inspect = current_app.control.inspect()
        active = inspect.active()
        
        if not active:
            return []
        
        matching_tasks = []
        
        # Przeszukaj wszystkie workery
        for worker_name, tasks in active.items():
            for task in tasks:
                if task.get('name') in task_names:
                    matching_tasks.append({
                        'worker': worker_name,
                        'task_id': task.get('id'),
                        'name': task.get('name'),
                        'args': task.get('args', []),
                        'kwargs': task.get('kwargs', {})
                    })
        
        return matching_tasks
        
    except Exception as e:
        logger.error(f"Błąd podczas pobierania aktywnych zadań: {e}")
        return []


def wait_for_tasks_completion(
    task_names: List[str], 
    check_interval: int = 5,
    max_wait_time: Optional[int] = None,
    task_label: str = "tasks"
) -> bool:
    """
    Czeka na zakończenie zadań o podanych nazwach.
    
    Args:
        task_names: Lista nazw zadań na które czekamy
        check_interval: Interwał sprawdzania w sekundach (domyślnie 5s)
        max_wait_time: Maksymalny czas oczekiwania w sekundach (None = bez limitu)
        task_label: Etykieta dla logowania
        
    Returns:
        bool: True jeśli wszystkie zadania się zakończyły, False jeśli timeout
    """
    start_time = time.time()
    wait_logged = False
    
    while True:
        active_tasks = get_active_tasks_by_name(task_names)
        
        if not active_tasks:
            if wait_logged:
                logger.info(f"✅ Wszystkie zadania {task_label} zakończone - kontynuuję")
            return True
        
        if not wait_logged:
            logger.info(f"⏳ Oczekiwanie na zakończenie {len(active_tasks)} zadań {task_label}")
            for task in active_tasks:
                logger.info(f"   - {task['name']} (task_id: {task['task_id']}, worker: {task['worker']})")
            wait_logged = True
        
        # Sprawdź timeout
        if max_wait_time:
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                logger.warning(f"⚠️ Timeout podczas oczekiwania na {task_label} (elapsed: {elapsed}s)")
                return False
        
        # Czekaj przed kolejnym sprawdzeniem
        time.sleep(check_interval)


def wait_for_dependencies(
    default_dependencies: List[str],
    custom_dependencies: Optional[List[str]] = None,
    task_label: str = "dependency"
) -> None:
    """
    Czeka na zakończenie zależności przed rozpoczęciem zadania.
    
    Args:
        default_dependencies: Domyślne zależności (lista nazw zadań)
        custom_dependencies: Opcjonalne custom zależności (override default jeśli podane)
        task_label: Etykieta dla logowania
    """
    # Użyj custom dependencies jeśli podane, w przeciwnym razie default
    dependencies = custom_dependencies if custom_dependencies is not None else default_dependencies
    
    if not dependencies:
        logger.info(f"✅ Brak zależności dla {task_label} - kontynuuję natychmiast")
        return
    
    logger.info(f"🔍 Sprawdzanie zależności dla {task_label}: {dependencies}")
    wait_for_tasks_completion(
        task_names=dependencies,
        check_interval=3,
        max_wait_time=None,  # Bez limitu - czekaj aż się zakończą
        task_label=f"dependencies ({task_label})"
    )

