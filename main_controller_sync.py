#!/usr/bin/env python3
import asyncio
import logging
import traceback
import os
import multiprocessing
import math
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Callable
from functools import wraps
from celery.result import AsyncResult
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Import bazy danych
from src.db.database_facade import DatabaseFacade

# Import Celery tasks
from src.celery_tasks.sync_tasks import sync_exchanges_task
from src.celery_tasks.analysis_tasks import (
    sync_technical_analysis_task,
    sync_fundamental_analysis_task
)
from src.celery_tasks.llm_tasks import (
    sync_llm_technical_interpretation_task,
    sync_llm_fundamental_interpretation_task,
    sync_llm_general_decision_task
)
from src.celery_tasks.transaction_tasks import (
    sync_transactions_wallets_task,
    sync_transactions_task
)
from src.controller_rest_celery_worker import get_celery_app

logger = logging.getLogger(__name__)


def sync_with_cron_db(func: Callable) -> Callable:
    """
    Dekorator sprawdzający stan crona w bazie przed wykonaniem metody.
    
    Sprawdza czy:
    - Proces ma przypisany cron job w bazie
    - Cron job jest włączony (enabled=True)
    - Synchronizuje scheduler z bazą danych przed wykonaniem
    
    Jeśli cron jest wyłączony lub nie istnieje, metoda nie zostanie wykonana.
    Obsługuje zarówno synchroniczne jak i asynchroniczne metody.
    
    Args:
        func: Dekorowana metoda synchronizacji
        
    Returns:
        Callable: Opakowana funkcja z walidacją crona
    """
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        # Pobierz nazwę procesu z nazwy metody
        process_name = func.__name__
        
        try:
            # Sprawdź czy baza jest zainicjalizowana
            if not hasattr(self, 'db') or self.db is None:
                logger.warning(f"⚠️ Baza danych nie zainicjalizowana - wykonuję {process_name} bez sprawdzenia crona")
                if asyncio.iscoroutinefunction(func):
                    return await func(self, *args, **kwargs)
                else:
                    return func(self, *args, **kwargs)
            
            # Zainicjalizuj bazę jeśli potrzeba
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # Synchronizuj scheduler z bazą danych przed sprawdzeniem crona
            logger.debug(f"🔄 Synchronizacja schedulera z bazą przed wykonaniem {process_name}")
            try:
                await self.sync_scheduler_with_database()
            except Exception as sync_error:
                logger.warning(f"⚠️ Błąd synchronizacji schedulera: {sync_error} - kontynuuję bez synchronizacji")
            
            # Pobierz tabele
            system_sync_job_table = self.db.get_factory().get_system_sync_job_table()
            cron_table = self.db.get_factory().get_cron_system_sync_job_table()
            
            # Sprawdź czy proces istnieje w bazie
            process_record = await system_sync_job_table.get_by_process(process_name)
            if not process_record:
                logger.warning(f"⚠️ Proces {process_name} nie znaleziony w bazie - wykonuję bez sprawdzenia crona")
                if asyncio.iscoroutinefunction(func):
                    return await func(self, *args, **kwargs)
                else:
                    return func(self, *args, **kwargs)
            
            # Pobierz crony dla tego procesu
            cron_jobs = await cron_table.get_by_process(process_name)
            
            if not cron_jobs:
                logger.info(f"ℹ️ Brak cron jobów dla procesu {process_name} - task nie będzie wykonany")
                return None
            
            # Sprawdź czy któryś z cronów jest włączony
            enabled_crons = [cron for cron in cron_jobs if cron.get('enabled', False)]
            
            if not enabled_crons:
                logger.info(f"🚫 Wszystkie cron joby dla {process_name} są wyłączone - task nie będzie wykonany")
                return None
            
            # Loguj informacje o włączonych cronach
            for cron in enabled_crons:
                logger.info(f"✅ Cron job '{cron['name']}' jest aktywny dla {process_name}")
            
            # Wykonaj oryginalną funkcję (sync lub async)
            if asyncio.iscoroutinefunction(func):
                return await func(self, *args, **kwargs)
            else:
                return func(self, *args, **kwargs)
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas sprawdzania crona dla {process_name}: {e}")
            logger.error(traceback.format_exc())
            # W przypadku błędu - wykonaj funkcję (fail-safe)
            logger.warning(f"⚠️ Wykonuję {process_name} pomimo błędu sprawdzania crona (fail-safe)")
            if asyncio.iscoroutinefunction(func):
                return await func(self, *args, **kwargs)
            else:
                return func(self, *args, **kwargs)
    
    return wrapper


class SyncController:
    """
    Kontroler synchronizacji odpowiedzialny za zarządzanie cronjonami
    i orkiestrację procesu synchronizacji wszystkich komponentów systemu.
    
    Workflow synchronizacji:
    1. Exchanges (sync_exchanges.py) -> uruchamiany zaraz po starcie i w soboty
    2. FundamentalAnalysis + TechnicalAnalysis (równolegle, po Exchanges)
    3. LlmFundamentalAnalysisInterpretation (po FundamentalAnalysis)
    4. LlmTechnicalAnalysisInterpretation (po TechnicalAnalysis)
    5. LlmGeneralAnalysisTransactionDecision (po obu interpretacjach LLM)
    6. TransactionsWallets (przed transakcjami, po LlmGeneralAnalysisTransactionDecision)
    7. Transactions (po TransactionsWallets)
    8. TransactionsWallets (po transakcjach, aktualizacja portfeli)
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja kontrolera synchronizacji.
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.scheduler = AsyncIOScheduler()
        
        # Inicjalizacja Celery
        self.celery_app = get_celery_app()
        logger.info("🔧 Zainicjalizowano Celery app")
        
        # Inicjalizacja bazy danych
        self._init_database()
        
        # Inicjalizacja klas synchronizacyjnych
        self._init_sync_classes()
    
    def _init_database(self) -> None:
        """Inicjalizuje połączenie z bazą danych."""
        try:
            # Inicjalizacja bazy danych
            if not self.test_mode:
                self.db = DatabaseFacade().get_database_postgresql()
            else:
                self.db = DatabaseFacade().get_test_database_postgresql()
                
            logger.info("Zainicjalizowano połączenie z bazą danych")
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji bazy danych: {e}")
            raise
    
    def _init_sync_classes(self) -> None:
        """
        Metoda zastępcza - klasy synchronizacyjne nie są już bezpośrednio używane.
        Wszystkie operacje synchronizacji są teraz wykonywane przez Celery workers.
        """
        logger.info("Klasy synchronizacyjne są zarządzane przez Celery workers")
    
    def _get_available_celery_workers(self, queue: str = None) -> int:
        """
        Pobiera liczbę dostępnych (wolnych) workerów Celery.
        
        Args:
            queue: Nazwa kolejki (opcjonalnie - jeśli None, liczy wszystkich)
            
        Returns:
            int: Liczba dostępnych workerów
        """
        try:
            inspect = self.celery_app.control.inspect()
            
            # Pobierz statystyki workerów
            stats = inspect.stats()
            active_tasks = inspect.active()
            
            if stats is None or active_tasks is None:
                logger.warning("⚠️ Nie można pobrać statystyk workerów Celery - używam wartości domyślnej (2)")
                return 2  # Domyślna wartość
            
            # Policz dostępnych workerów
            total_workers = 0
            busy_workers = 0
            
            for worker_name in stats.keys():
                total_workers += 1
                # Sprawdź czy worker ma aktywne zadania
                if worker_name in active_tasks and len(active_tasks[worker_name]) > 0:
                    busy_workers += 1
            
            available_workers = max(1, total_workers - busy_workers)  # Minimum 1
            
            logger.info(f"👷 Celery workers: total={total_workers}, busy={busy_workers}, available={available_workers}")
            
            return available_workers
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas pobierania informacji o workerach Celery: {e}")
            return 2  # Domyślna wartość w przypadku błędu
    
    def _calculate_chunk_params(self, total_limit: int, num_workers: int, global_offset: int = 0) -> List[Tuple[int, int]]:
        """
        Oblicza parametry chunków (limit, offset) dla podziału zadań między workerów.
        
        Args:
            total_limit: Całkowita liczba elementów do przetworzenia
            num_workers: Liczba workerów
            global_offset: Globalny offset (opcjonalny)
            
        Returns:
            List[Tuple[int, int]]: Lista tupli (limit, offset) dla każdego chunka
        """
        chunk_size = math.ceil(total_limit / num_workers)
        chunks = []
        
        for i in range(num_workers):
            offset = global_offset + (i * chunk_size)
            limit = min(chunk_size, total_limit - (i * chunk_size))
            
            if limit > 0:  # Dodaj chunk tylko jeśli ma elementy do przetworzenia
                chunks.append((limit, offset))
                
        logger.info(f"🔄 Podzielono zadania na {len(chunks)} chunków (chunk_size={chunk_size}, total_limit={total_limit})")
        for i, (limit, offset) in enumerate(chunks):
            logger.info(f"   Chunk {i+1}: limit={limit}, offset={offset}")
            
        return chunks
    
    @sync_with_cron_db
    async def _run_exchanges_sync(self, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadanie synchronizacji giełd do kolejki Celery bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadania
            
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE SYNCHRONIZACJI GIEŁD DO KOLEJKI ===")
            
            task_result = sync_exchanges_task.apply_async(
                kwargs={
                    'test_mode': self.test_mode,
                    'custom_dependencies': custom_dependencies
                },
                queue='sync_queue'
            )
            
            logger.info(f"✅ Wysłano sync_exchanges: task_id={task_result.id}")
            return [task_result]
                
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadania giełd: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_fundamental_analysis_sync(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania synchronizacji analizy fundamentalnej do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE ANALIZY FUNDAMENTALNEJ DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            tasks = []
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_fundamental_analysis_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='analysis_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_fundamental_analysis: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadań analizy fundamentalnej: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_technical_analysis_sync(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania synchronizacji analizy technicznej do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE ANALIZY TECHNICZNEJ DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            tasks = []
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_technical_analysis_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='analysis_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_technical_analysis: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadań analizy technicznej: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_llm_fundamental_interpretation_sync(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania interpretacji LLM fundamentalnej do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE INTERPRETACJI LLM FUNDAMENTALNEJ DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            tasks = []
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_llm_fundamental_interpretation_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_llm_fundamental_interpretation: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadań interpretacji LLM fundamentalnej: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_llm_technical_interpretation_sync(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania interpretacji LLM technicznej do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE INTERPRETACJI LLM TECHNICZNEJ DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            tasks = []
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_llm_technical_interpretation_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_llm_technical_interpretation: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadań interpretacji LLM technicznej: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_llm_general_decision_sync(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania decyzji generalnej LLM do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE DECYZJI LLM GENERALNEJ DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            tasks = []
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_llm_general_decision_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_llm_general_decision: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadań decyzji LLM generalnej: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_transactions_wallets_sync(self, phase: str = "pre", custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadanie synchronizacji portfeli do kolejki bez czekania.
        
        Args:
            phase: Faza synchronizacji ("pre" lub "post")
            custom_dependencies: Opcjonalne custom zależności dla zadania
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            phase_label = "PRE-TRANSACTIONS" if phase == "pre" else "POST-TRANSACTIONS"
            logger.info(f"=== WYSYŁANIE PORTFELI ({phase_label}) DO KOLEJKI ===")
            
            task_result = sync_transactions_wallets_task.apply_async(
                kwargs={
                    'phase': phase,
                    'test_mode': self.test_mode,
                    'custom_dependencies': custom_dependencies
                },
                queue='transaction_queue'
            )
            
            logger.info(f"✅ Wysłano sync_transactions_wallets ({phase}): task_id={task_result.id}")
            return [task_result]
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadania portfeli ({phase}): {e}")
            logger.error(traceback.format_exc())
            return []

    @sync_with_cron_db
    async def _run_transactions_sync(self, limit: int = 500, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania synchronizacji transakcji do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE TRANSAKCJI DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            tasks = []
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_transactions_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='transaction_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_transactions: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania zadań transakcji: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_parallel_analysis(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania analiz (fundamental + technical) równolegle do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE RÓWNOLEGŁYCH ANALIZ DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            workers_per_analysis = max(1, available_workers // 2)
            
            logger.info(f"👷 Przydzielono {workers_per_analysis} workerów dla każdej analizy")
            
            tasks = []
            
            # Fundamental analysis
            fundamental_chunks = self._calculate_chunk_params(limit, workers_per_analysis, offset)
        for chunk_limit, chunk_offset in fundamental_chunks:
                task_result = sync_fundamental_analysis_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='analysis_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_fundamental_analysis: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Technical analysis
            technical_chunks = self._calculate_chunk_params(limit, workers_per_analysis, offset)
        for chunk_limit, chunk_offset in technical_chunks:
                task_result = sync_technical_analysis_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='analysis_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_technical_analysis: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
            except Exception as e:
            logger.error(f"Błąd podczas wysyłania równoległych analiz: {e}")
            logger.error(traceback.format_exc())
            return []
    
    @sync_with_cron_db
    async def _run_parallel_llm_interpretations(self, limit: int = 50, offset: int = 0, custom_dependencies: Optional[List[str]] = None) -> List[AsyncResult]:
        """
        Wysyła zadania interpretacji LLM (fundamental + technical) równolegle do kolejki bez czekania.
        
        Args:
            custom_dependencies: Opcjonalne custom zależności dla zadań
        
        Returns:
            List[AsyncResult]: Lista wyników zadań Celery
        """
        try:
            logger.info("=== WYSYŁANIE RÓWNOLEGŁYCH INTERPRETACJI LLM DO KOLEJKI ===")
            
            available_workers = self._get_available_celery_workers()
            workers_per_interpretation = max(1, available_workers // 2)
            
            logger.info(f"👷 Przydzielono {workers_per_interpretation} workerów dla każdej interpretacji LLM")
            
            tasks = []
            
            # LLM Fundamental Interpretation
            fundamental_chunks = self._calculate_chunk_params(limit, workers_per_interpretation, offset)
        for chunk_limit, chunk_offset in fundamental_chunks:
                task_result = sync_llm_fundamental_interpretation_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_llm_fundamental_interpretation: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # LLM Technical Interpretation
            technical_chunks = self._calculate_chunk_params(limit, workers_per_interpretation, offset)
        for chunk_limit, chunk_offset in technical_chunks:
                task_result = sync_llm_technical_interpretation_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode,
                        'custom_dependencies': custom_dependencies
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"✅ Wysłano sync_llm_technical_interpretation: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            return tasks
            
            except Exception as e:
            logger.error(f"Błąd podczas wysyłania równoległych interpretacji LLM: {e}")
            logger.error(traceback.format_exc())
            return []
    
    async def sync_scheduler_with_database(self) -> bool:
        """
        Synchronizuje APScheduler z bazą danych - dodaje, usuwa i modyfikuje joby zgodnie z bazą.
        
        Metoda ta powinna być wywoływana okresowo aby utrzymać synchronizację między
        schedulerem a bazą danych (w przypadku zmian w bazie przez REST API).
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("🔄 Rozpoczęcie synchronizacji schedulera z bazą danych")
            
            # Zainicjalizuj bazę jeśli potrzeba
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # Pobierz wszystkie włączone cron jobs z bazy
            cron_table = self.db.get_factory().get_cron_system_sync_job_table()
            enabled_jobs = await cron_table.get_all_enabled()
            
            # Pobierz aktualnie zaplanowane joby z schedulera
            scheduled_jobs = self.scheduler.get_jobs()
            scheduled_job_ids = {job.id for job in scheduled_jobs}
            
            # Sprawdź które joby trzeba dodać/zaktualizować/usunąć
            expected_job_ids = set()
            added_count = 0
            updated_count = 0
            
            for job_config in enabled_jobs:
                job_id = f"cron_job_{job_config['id']}"
                expected_job_ids.add(job_id)
                
                # Pobierz metodę do wykonania
                    process_name = job_config['process']
                    method = getattr(self, process_name, None)
                    
                    if method is None:
                    logger.warning(f"⚠️ Nie znaleziono metody {process_name} w SyncController - pomijam")
                        continue
                    
                    # Przygotuj parametry dla CronTrigger
                    cron_params = {}
                    if job_config['year'] is not None:
                        cron_params['year'] = job_config['year']
                    if job_config['month'] is not None:
                        cron_params['month'] = job_config['month']
                    if job_config['day'] is not None:
                        cron_params['day'] = job_config['day']
                    if job_config['week'] is not None:
                        cron_params['week'] = job_config['week']
                    if job_config['day_of_week'] is not None:
                        cron_params['day_of_week'] = job_config['day_of_week']
                    if job_config['hour'] is not None:
                        cron_params['hour'] = job_config['hour']
                    if job_config['minute'] is not None:
                        cron_params['minute'] = job_config['minute']
                    if job_config['second'] is not None:
                        cron_params['second'] = job_config['second']
                    if job_config['start_date'] is not None:
                        cron_params['start_date'] = job_config['start_date']
                    if job_config['end_date'] is not None:
                        cron_params['end_date'] = job_config['end_date']
                    if job_config['timezone'] is not None:
                        cron_params['timezone'] = job_config['timezone']
                    if job_config['jitter'] is not None and job_config['jitter'] > 0:
                        cron_params['jitter'] = job_config['jitter']
                    
                    trigger = CronTrigger(**cron_params)
                    
                # Sprawdź czy job już istnieje w schedulerze
                if job_id in scheduled_job_ids:
                    # Zaktualizuj istniejący job
                    self.scheduler.reschedule_job(
                        job_id=job_id,
                        trigger=trigger
                    )
                    updated_count += 1
                    logger.debug(f"🔄 Zaktualizowano job: {job_config['name']} (ID: {job_id})")
                else:
                    # Dodaj nowy job
                    self.scheduler.add_job(
                        func=method,
                        trigger=trigger,
                        id=job_id,
                        name=job_config['name'],
                        replace_existing=True
                    )
                    added_count += 1
                    logger.info(f"➕ Dodano nowy job: {job_config['name']} (ID: {job_id})")
            
            # Usuń joby które są w schedulerze ale nie ma ich w bazie (lub są wyłączone)
            removed_count = 0
            for job_id in scheduled_job_ids:
                if job_id.startswith('cron_job_') and job_id not in expected_job_ids:
                    self.scheduler.remove_job(job_id)
                    removed_count += 1
                    logger.info(f"➖ Usunięto job: {job_id}")
            
            logger.info(f"✅ Synchronizacja schedulera zakończona: dodano={added_count}, zaktualizowano={updated_count}, usunięto={removed_count}")
            return True
                    
                except Exception as e:
            logger.error(f"❌ Błąd podczas synchronizacji schedulera z bazą: {e}")
            logger.error(traceback.format_exc())
            return False
    
    @sync_with_cron_db
    async def run_full_sync_workflow(self) -> Dict[str, List[str]]:
        """
        Wysyła wszystkie zadania workflow do kolejki Celery bez czekania.
        Zadania same zarządzają swoimi zależnościami przez wait_for_dependencies().
        
        Workflow (zależności zarządzane w taskach):
        1. Exchanges (brak zależności)
        2. Fundamental + Technical Analysis (czeka na Exchanges)
        3. LLM Fundamental + Technical (czeka na odpowiednie analizy)
        4. LLM General Decision (czeka na obie interpretacje LLM)
        5. TransactionsWallets pre (czeka na LLM General)
        6. Transactions (czeka na TransactionsWallets pre)
        7. TransactionsWallets post (czeka na Transactions)
        
        Returns:
            Dict[str, List[str]]: Słownik z task_id dla każdego etapu workflow
        """
        try:
            logger.info("🚀 ROZPOCZĘCIE WYSYŁANIA WORKFLOW DO KOLEJKI CELERY 🚀")
            start_time = datetime.now()
            
            all_tasks = {}
            
            # KROK 1: Exchanges
            logger.info("📊 KROK 1: Wysyłanie synchronizacji giełd")
            exchanges_tasks = await self._run_exchanges_sync()
            all_tasks['exchanges'] = [t.id for t in exchanges_tasks] if exchanges_tasks else []
            
            # KROK 2: Analizy (Fundamental + Technical) - czekają na Exchanges w taskach
            logger.info("📈 KROK 2: Wysyłanie analiz (Fundamental + Technical)")
            analysis_tasks = await self._run_parallel_analysis(
                custom_dependencies=[
                    'sync_tasks.sync_exchanges'
                ]
            )
            all_tasks['analysis'] = [t.id for t in analysis_tasks] if analysis_tasks else []
            
            # KROK 3: Interpretacje LLM - czekają na analizy w taskach
            logger.info("🤖 KROK 3: Wysyłanie interpretacji LLM")
            llm_interpretation_tasks = await self._run_parallel_llm_interpretations(
                custom_dependencies=[
                    'sync_tasks.sync_exchanges',
                    'analysis_tasks.sync_fundamental_analysis',
                    'analysis_tasks.sync_technical_analysis'
                ]
            )
            all_tasks['llm_interpretations'] = [t.id for t in llm_interpretation_tasks] if llm_interpretation_tasks else []
            
            # KROK 4: Decyzja generalna LLM - czeka na interpretacje w taskach
            logger.info("🎯 KROK 4: Wysyłanie decyzji generalnej LLM")
            llm_general_tasks = await self._run_llm_general_decision_sync(
                custom_dependencies=[
                    'sync_tasks.sync_exchanges',
                    'analysis_tasks.sync_fundamental_analysis',
                    'analysis_tasks.sync_technical_analysis',
                    'llm_tasks.sync_llm_fundamental_interpretation',
                    'llm_tasks.sync_llm_technical_interpretation'
                ]
            )
            all_tasks['llm_general'] = [t.id for t in llm_general_tasks] if llm_general_tasks else []
            
            # KROK 5: Portfele przed transakcjami - czeka na LLM General w taskach
            logger.info("💼 KROK 5: Wysyłanie portfeli (pre-transactions)")
            wallets_pre_tasks = await self._run_transactions_wallets_sync(
                phase="pre", 
                custom_dependencies=[
                    'sync_tasks.sync_exchanges',
                    'analysis_tasks.sync_fundamental_analysis',
                    'analysis_tasks.sync_technical_analysis',
                    'llm_tasks.sync_llm_fundamental_interpretation',
                    'llm_tasks.sync_llm_technical_interpretation',
                    'llm_tasks.sync_llm_general_decision'
                ]
            )
            all_tasks['wallets_pre'] = [t.id for t in wallets_pre_tasks] if wallets_pre_tasks else []
            
            # KROK 6: Transakcje - czeka na portfele pre w taskach
            logger.info("💰 KROK 6: Wysyłanie transakcji")
            transactions_tasks = await self._run_transactions_sync(
                custom_dependencies=[
                    'sync_tasks.sync_exchanges',
                    'analysis_tasks.sync_fundamental_analysis',
                    'analysis_tasks.sync_technical_analysis',
                    'llm_tasks.sync_llm_fundamental_interpretation',
                    'llm_tasks.sync_llm_technical_interpretation',
                    'llm_tasks.sync_llm_general_decision',
                    'transaction_tasks.sync_transactions_wallets'
                ]
            )
            all_tasks['transactions'] = [t.id for t in transactions_tasks] if transactions_tasks else []
            
            # KROK 7: Portfele po transakcjach - czeka na transakcje w taskach
            logger.info("💼 KROK 7: Wysyłanie portfeli (post-transactions)")
            wallets_post_tasks = await self._run_transactions_wallets_sync(
                phase="post",
                custom_dependencies=[
                    'sync_tasks.sync_exchanges',
                    'analysis_tasks.sync_fundamental_analysis',
                    'analysis_tasks.sync_technical_analysis',
                    'llm_tasks.sync_llm_fundamental_interpretation',
                    'llm_tasks.sync_llm_technical_interpretation',
                    'llm_tasks.sync_llm_general_decision',
                    'transaction_tasks.sync_transactions_wallets',
                    'transaction_tasks.sync_transactions'
                ]
            )
            all_tasks['wallets_post'] = [t.id for t in wallets_post_tasks] if wallets_post_tasks else []
            
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Podsumowanie
            total_tasks = sum(len(tasks) for tasks in all_tasks.values())
            logger.info("📋 PODSUMOWANIE WYSYŁANIA WORKFLOW:")
            logger.info(f"⏱️ Czas wysyłania: {duration}")
            logger.info(f"📊 Wysłano łącznie {total_tasks} zadań do kolejki")
            for stage, task_ids in all_tasks.items():
                logger.info(f"   {stage}: {len(task_ids)} zadań")
            logger.info("✅ Wszystkie zadania workflow zostały wysłane do kolejki")
            logger.info("🔄 Zadania będą się wykonywać zgodnie z zależnościami zdefiniowanymi w taskach")
            
            return all_tasks
            
        except Exception as e:
            logger.error(f"❌ Krytyczny błąd podczas wysyłania workflow: {e}")
            logger.error(traceback.format_exc())
            return {}
    
    async def setup_cron_jobs(self) -> None:
        """
        Konfiguruje cronjobs dla automatycznego uruchamiania workflow na podstawie bazy danych.
        Używa metody sync_scheduler_with_database do synchronizacji.
        """
        try:
            # Wykonaj początkową synchronizację schedulera z bazą
            await self.sync_scheduler_with_database()
            
            # Dodaj periodic job do synchronizacji schedulera z bazą co 5 minut
            from apscheduler.triggers.interval import IntervalTrigger
            self.scheduler.add_job(
                func=self.sync_scheduler_with_database,
                trigger=IntervalTrigger(minutes=5),
                id='sync_scheduler_periodic',
                name='Periodic Scheduler-Database Sync',
                replace_existing=True
            )
            logger.info("✅ Dodano periodic job do synchronizacji schedulera z bazą (co 5 minut)")
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas konfiguracji cron jobs: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def start(self) -> None:
        """
        Startuje kontroler synchronizacji.
        Uruchamia workflow od razu po starcie, a następnie konfiguruje cronjobs.
        """
        try:
            logger.info("🚀 URUCHAMIANIE SYNC CONTROLLER")
            
            # Konfiguruj cron jobs
            await self.setup_cron_jobs()
            
            # Uruchom scheduler
            self.scheduler.start()
            logger.info("📅 Scheduler uruchomiony")
            
            # Uruchom workflow od razu po starcie
            logger.info("⚡ Uruchamianie workflow po starcie aplikacji")
            await self.run_full_sync_workflow()
            
            # Utrzymuj aplikację przy życiu
            logger.info("🔄 Kontroler działa - oczekiwanie na zaplanowane zadania...")
            
            try:
                # Pętla nieskończona - aplikacja będzie działać do przerwania
                while True:
                    await asyncio.sleep(60)  # Sprawdzaj co minutę czy aplikacja ma działać
                    
            except KeyboardInterrupt:
                logger.info("🛑 Otrzymano sygnał przerwania")
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas uruchamiania kontrolera: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Zatrzymuje kontroler synchronizacji."""
        try:
            logger.info("🛑 ZATRZYMYWANIE SYNC CONTROLLER")
            
            # Zatrzymaj scheduler
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("📅 Scheduler zatrzymany")
            
            logger.info("✅ Sync Controller zatrzymany pomyślnie")
            
        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania kontrolera: {e}")


async def main():
    """Główna funkcja aplikacji."""
    # Konfiguracja logowania
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('sync_controller.log')
        ]
    )
    
    logger.info("🎉 URUCHAMIANIE APLIKACJI SYNC CONTROLLER")
    
    # Utwórz i uruchom kontroler
    controller = SyncController(test_mode=False)
    await controller.start()


if __name__ == "__main__":
    """Punkt startowy aplikacji synchronizującej."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Aplikacja przerwana przez użytkownika")
    except Exception as e:
        print(f"❌ Krytyczny błąd aplikacji: {e}")
        logging.error(f"Krytyczny błąd aplikacji: {e}")
        logging.error(traceback.format_exc())
    finally:
        print("👋 Aplikacja zakończona")
