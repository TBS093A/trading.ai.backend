"""
Celery Tasks - Utils

Pomocnicze funkcje dla zadań Celery.

Autor: AI Assistant
"""

import asyncio
import logging
from typing import Callable, Any

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

